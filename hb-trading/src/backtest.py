"""回测引擎 — 用历史数据验证策略

基于 case_001 的策略逻辑:
  1. 识别 H2 结构 + 交易区间 + 假突破 + MTR
  2. 信号确认后才入场（下一根K线突破信号高点）
  3. 止损在信号K线低点，目标为区间顶部
  4. 盈亏比 >= 2:1 才入场
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Optional

import numpy as np
import pandas as pd

from config import INITIAL_CAPITAL, COMMISSION_RATE, MIN_COMMISSION
from src.collector import get_db, PRIMARY_SYMBOL
from src.price_action import analyze as pa_analyze, MarketState, EntrySignal

logger = logging.getLogger("backtest")


@dataclass
class Trade:
    entry_time: pd.Timestamp
    exit_time: Optional[pd.Timestamp]
    direction: str
    entry_price: float
    stop_loss: float
    take_profit: float
    exit_price: float = 0.0
    pnl: float = 0.0
    pnl_pct: float = 0.0
    exit_reason: str = ""    # target / stop / signal_reversed
    bars_held: int = 0


@dataclass
class BacktestResult:
    total_trades: int
    win_trades: int
    lose_trades: int
    win_rate: float
    total_return_pct: float
    max_drawdown_pct: float
    sharpe_ratio: float
    profit_factor: float
    avg_rr: float
    trades: list[Trade] = field(default_factory=list)
    equity_curve: list = field(default_factory=list)


def run_backtest(symbol: str = PRIMARY_SYMBOL,
                 timeframe: str = "5m",
                 signal_confirm: bool = True,
                 min_rr: float = 2.0) -> BacktestResult:
    """回测核心逻辑。

    Args:
        symbol: 品种
        timeframe: 时间框架
        signal_confirm: 是否启用入场确认（等下一根K线）
        min_rr: 最低盈亏比
    """
    db = get_db()
    df = db.get_klines(symbol, timeframe)
    if df.empty:
        raise ValueError(f"无数据: {symbol} {timeframe}")

    trades: list[Trade] = []
    equity = INITIAL_CAPITAL
    equity_curve = [equity]
    current_trade: Optional[Trade] = None
    pending_signal: Optional[dict] = None
    pending_age: int = 0  # 待确认信号已过多少根K线

    window = 200  # 滑动窗口大小
    for i in range(window, len(df)):
        window_df = df.iloc[i - window:i + 1]

        # --- 管理当前持仓 ---
        if current_trade:
            current_trade.bars_held += 1
            bar = df.iloc[i]
            exit_price = None
            reason = ""

            if current_trade.direction == "long":
                if bar["low"] <= current_trade.stop_loss:
                    exit_price = current_trade.stop_loss
                    reason = "stop"
                elif bar["high"] >= current_trade.take_profit:
                    exit_price = current_trade.take_profit
                    reason = "target"
            else:  # short
                if bar["high"] >= current_trade.stop_loss:
                    exit_price = current_trade.stop_loss
                    reason = "stop"
                elif bar["low"] <= current_trade.take_profit:
                    exit_price = current_trade.take_profit
                    reason = "target"

            if exit_price:
                current_trade.exit_time = df.index[i]
                current_trade.exit_price = exit_price
                current_trade.exit_reason = reason

                pnl_per_unit = (exit_price - current_trade.entry_price) if current_trade.direction == "long" else (current_trade.entry_price - exit_price)
                commission = max(exit_price * COMMISSION_RATE, MIN_COMMISSION)
                current_trade.pnl = pnl_per_unit - commission
                current_trade.pnl_pct = current_trade.pnl / current_trade.entry_price * 100

                equity += current_trade.pnl
                trades.append(current_trade)
                current_trade = None
                pending_signal = None

        # --- 信号检测 ---
        if current_trade:  # 有持仓时不找新信号
            equity_curve.append(equity)
            continue

        try:
            result = pa_analyze(window_df)
            entries = (result["entry_signals"] + result["wedges"] + result["failed_breakouts"] +
                       result.get("bear_bar_longs", []) + result.get("support_betrayals", []))
            state = result["state"]
        except Exception:
            equity_curve.append(equity)
            continue

        if not entries:
            equity_curve.append(equity)
            continue

        best = max(entries, key=lambda e: e.confidence)
        rr = (best.target - best.entry_price) / (best.entry_price - best.stop_loss) if best.direction == "long" else (best.entry_price - best.target) / (best.stop_loss - best.entry_price)
        rr = abs(rr)

        if rr < min_rr:
            equity_curve.append(equity)
            continue

        # --- 入场确认 ---
        if signal_confirm:
            if pending_signal is None:
                pending_signal = {
                    "dt": df.index[i],
                    "entry": best.entry_price,
                    "stop": best.stop_loss,
                    "target": best.target,
                    "direction": best.direction,
                }
                pending_age = 0
                equity_curve.append(equity)
                continue
            else:
                pending_age += 1
                bar = df.iloc[i]
                confirmed = False
                if pending_signal["direction"] == "long" and bar["close"] > pending_signal["entry"]:
                    confirmed = True
                elif pending_signal["direction"] == "short" and bar["close"] < pending_signal["entry"]:
                    confirmed = True

                if not confirmed:
                    if pending_age > 3:
                        pending_signal = None
                        pending_age = 0
                    equity_curve.append(equity)
                    continue

                # 已确认，用确认K线数据入场
                best_for_trade = pending_signal
                pending_age = 0
        else:
            best_for_trade = {
                "entry": best.entry_price,
                "stop": best.stop_loss,
                "target": best.target,
                "direction": best.direction,
            }

        # --- 入场 ---
        current_trade = Trade(
            entry_time=df.index[i],
            exit_time=None,
            direction=best_for_trade["direction"],
            entry_price=best_for_trade["entry"],
            stop_loss=best_for_trade["stop"],
            take_profit=best_for_trade["target"],
            bars_held=0,
        )
        pending_signal = None
        equity_curve.append(equity)

    # --- 计算统计 ---
    if not trades:
        return BacktestResult(0, 0, 0, 0, 0, 0, 0, 0, 0)

    wins = [t for t in trades if t.pnl > 0]
    win_rate = len(wins) / len(trades)

    total_return = (equity - INITIAL_CAPITAL) / INITIAL_CAPITAL * 100

    # 最大回撤
    peak = INITIAL_CAPITAL
    max_dd = 0
    for eq in equity_curve:
        peak = max(peak, eq)
        dd = (peak - eq) / peak * 100
        max_dd = max(max_dd, dd)

    # 夏普
    equity_arr = np.array(equity_curve[20:])  # 跳过头20个无交易期
    if len(equity_arr) > 10:
        returns = np.diff(equity_arr) / equity_arr[:-1]
        sharpe = float(np.mean(returns) / np.std(returns) * np.sqrt(252)) if np.std(returns) > 0 else 0
    else:
        sharpe = 0

    # 盈亏因子
    gross_profit = sum(t.pnl for t in wins)
    gross_loss = abs(sum(t.pnl for t in trades if t.pnl <= 0))
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else float("inf")

    avg_rr = np.mean([abs(t.pnl / t.entry_price * 100) for t in wins]) if wins else 0

    return BacktestResult(
        total_trades=len(trades),
        win_trades=len(wins),
        lose_trades=len(trades) - len(wins),
        win_rate=round(win_rate * 100, 1),
        total_return_pct=round(total_return, 2),
        max_drawdown_pct=round(max_dd, 2),
        sharpe_ratio=round(sharpe, 2),
        profit_factor=round(profit_factor, 2),
        avg_rr=round(avg_rr, 2),
        trades=trades,
        equity_curve=equity_curve,
    )


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    result = run_backtest(symbol=PRIMARY_SYMBOL, timeframe="5m")
    print(f"\n回测结果 ({PRIMARY_SYMBOL} 5m):")
    print(f"  交易次数: {result.total_trades}")
    print(f"  胜率: {result.win_rate}%")
    print(f"  总收益: {result.total_return_pct}%")
    print(f"  最大回撤: {result.max_drawdown_pct}%")
    print(f"  夏普: {result.sharpe_ratio}")
    print(f"  盈亏因子: {result.profit_factor}")
    for i, t in enumerate(result.trades[-5:]):
        print(f"  #{i}: {t.entry_time} {t.direction} in={t.entry_price:.0f} out={t.exit_price:.0f} "
              f"pnl={t.pnl:.0f} ({t.pnl_pct:.1f}%) {t.exit_reason} ({t.bars_held}bars)")

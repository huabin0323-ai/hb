"""A股回测引擎 — 验证PA信号在历史数据上的表现

对扫描产生的买入信号进行历史回测：
  1. 从信号日期后拉取K线
  2. 逐根检查：止损先到？止盈先到？还是都未到？
  3. 汇总收益率、胜率、最大回撤、夏普比率
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Optional

import numpy as np
import pandas as pd

from src.a_share.fetcher import http_push2_kline

logger = logging.getLogger("a-share.backtest")


@dataclass
class BacktestTrade:
    """单笔回测交易"""
    code: str
    name: str
    direction: str              # "多" | "空"
    entry_date: str
    entry_price: float
    stop_loss: float
    take_profit: float
    exit_date: str = ""
    exit_price: float = 0.0
    exit_reason: str = ""       # "止盈" | "止损" | "持仓中" | "过期"
    pnl_pct: float = 0.0
    bars_held: int = 0
    signal_score: int = 0
    signal_type: str = ""


@dataclass
class BacktestResult:
    """回测结果汇总"""
    total_signals: int
    executed_trades: int
    win_trades: int
    lose_trades: int
    win_rate: float             # 0-100
    avg_win_pct: float
    avg_loss_pct: float
    total_return_pct: float
    max_drawdown_pct: float
    profit_factor: float
    avg_bars_held: float
    trades: list[BacktestTrade] = field(default_factory=list)
    equity_curve: list[dict] = field(default_factory=list)


def _simulate_trade(
    code: str, name: str, signal: dict,
    max_hold_days: int = 20,
    start_date: str = None,
    use_recent_window: bool = True,
) -> BacktestTrade:
    """模拟单笔交易：从信号日开始，逐日检查止损/止盈

    Args:
        signal: {entry_price, stop_loss, take_profit, direction, score, signal_type, date}
        max_hold_days: 最大持仓天数
        start_date: 信号日期（YYYY-MM-DD），None则自动选数据内合适日期
        use_recent_window: True=从数据末尾倒退max_hold_days作为信号日（模拟最近一笔）
    """
    entry_price = signal.get("entry_price", 0)
    stop_loss = signal.get("stop_loss", 0)
    take_profit = signal.get("take_profit", 0)
    direction = signal.get("direction", "多")

    # 拉取K线（多拉一些用于选日期）
    fetch_days = max_hold_days + 60
    try:
        df = http_push2_kline(code, days=fetch_days)
    except Exception as e:
        logger.warning(f"K-line fetch failed for {code}: {e}")
        return BacktestTrade(code=code, name=name, direction=direction,
                            entry_date="", entry_price=entry_price, stop_loss=stop_loss,
                            take_profit=take_profit, exit_reason="数据获取失败")

    if df.empty or len(df) < max_hold_days + 5:
        return BacktestTrade(code=code, name=name, direction=direction,
                            entry_date="", entry_price=entry_price, stop_loss=stop_loss,
                            take_profit=take_profit, exit_reason="K线不足")

    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values("date")

    # 确定信号日
    if start_date:
        signal_dt = pd.Timestamp(start_date)
    elif use_recent_window:
        # 从最新数据倒退 max_hold_days+5 作为信号日，留足够未来K线
        idx = max(0, len(df) - max_hold_days - 5)
        signal_dt = df["date"].iloc[idx]
    else:
        signal_dt = pd.Timestamp(date.today().isoformat())

    signal_date = str(signal_dt)[:10]

    trade = BacktestTrade(
        code=code, name=name,
        direction=direction,
        entry_date=signal_date,
        entry_price=entry_price,
        stop_loss=stop_loss,
        take_profit=take_profit,
        signal_score=signal.get("total_score", signal.get("score", 0)),
        signal_type=signal.get("signal_type", ""),
    )

    if entry_price <= 0 or stop_loss <= 0 or take_profit <= 0:
        trade.exit_reason = "参数无效"
        return trade

    # 找到信号日之后的K线
    future_bars = df[df["date"] > signal_dt]

    if future_bars.empty:
        trade.exit_reason = "无信号日后数据"
        return trade

    # 取最多max_hold_days根
    check_bars = future_bars.head(max_hold_days)

    # 逐根检查
    for i, (_, bar) in enumerate(check_bars.iterrows()):
        high = float(bar["high"])
        low = float(bar["low"])
        close = float(bar["close"])

        if direction == "多":
            # 做多：止损在下，止盈在上
            if low <= stop_loss:
                # 止损先触发（假设滑点）
                trade.exit_date = str(bar["date"])[:10]
                trade.exit_price = stop_loss * 0.995  # 略低于止损价
                trade.exit_reason = "止损"
                trade.pnl_pct = round((trade.exit_price / entry_price - 1) * 100, 2)
                trade.bars_held = i + 1
                return trade
            elif high >= take_profit:
                trade.exit_date = str(bar["date"])[:10]
                trade.exit_price = take_profit
                trade.exit_reason = "止盈"
                trade.pnl_pct = round((take_profit / entry_price - 1) * 100, 2)
                trade.bars_held = i + 1
                return trade
        else:
            # 做空：止损在上，止盈在下
            if high >= stop_loss:
                trade.exit_date = str(bar["date"])[:10]
                trade.exit_price = stop_loss * 1.005
                trade.exit_reason = "止损"
                trade.pnl_pct = round((entry_price / trade.exit_price - 1) * 100, 2)
                trade.bars_held = i + 1
                return trade
            elif low <= take_profit:
                trade.exit_date = str(bar["date"])[:10]
                trade.exit_price = take_profit
                trade.exit_reason = "止盈"
                trade.pnl_pct = round((entry_price / take_profit - 1) * 100, 2)
                trade.bars_held = i + 1
                return trade

    # 持仓到期未触发
    last_bar = check_bars.iloc[-1]
    last_close = float(last_bar["close"])
    trade.exit_date = str(last_bar["date"])[:10]
    trade.exit_price = last_close
    trade.exit_reason = "持仓中" if len(check_bars) < max_hold_days else "过期"
    trade.bars_held = len(check_bars)

    if direction == "多":
        trade.pnl_pct = round((last_close / entry_price - 1) * 100, 2)
    else:
        trade.pnl_pct = round((entry_price / last_close - 1) * 100, 2)

    return trade


def run_signals_backtest(
    signals: list[dict],
    max_hold_days: int = 20,
    start_date: str = None,
    use_recent_window: bool = True,
) -> BacktestResult:
    """批量回测一组信号

    Args:
        signals: [{code, name, entry_price, stop_loss, take_profit, direction, ...}, ...]
        max_hold_days: 最大持仓天数
        start_date: 统一信号日期（None则自动选数据内合适日期）
        use_recent_window: True=每只从K线末尾倒退模拟最近一笔

    Returns:
        BacktestResult with all trades and metrics
    """
    trades = []
    for sig in signals:
        code = sig.get("code", "")
        name = sig.get("name", "")
        if not code:
            continue

        trade = _simulate_trade(code, name, sig, max_hold_days, start_date,
                               use_recent_window=use_recent_window)
        trades.append(trade)

    return _compute_metrics(trades)


def _compute_metrics(trades: list[BacktestTrade]) -> BacktestResult:
    """从交易列表计算汇总指标"""
    completed = [t for t in trades if t.exit_reason in ("止盈", "止损")]
    wins = [t for t in completed if t.pnl_pct > 0]
    losses = [t for t in completed if t.pnl_pct <= 0]

    n_executed = len(completed)
    n_wins = len(wins)
    n_losses = len(losses)
    win_rate = (n_wins / n_executed * 100) if n_executed > 0 else 0

    avg_win = np.mean([t.pnl_pct for t in wins]) if wins else 0
    avg_loss = np.mean([t.pnl_pct for t in losses]) if losses else 0

    total_return = sum(t.pnl_pct for t in completed)
    avg_bars = np.mean([t.bars_held for t in completed]) if completed else 0

    # 盈亏比
    gross_profit = sum(t.pnl_pct for t in wins)
    gross_loss = abs(sum(t.pnl_pct for t in losses))
    profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else (999 if gross_profit > 0 else 0)

    # 权益曲线
    equity = 100.0
    equity_curve = [{"trade": 0, "equity": equity, "label": "初始"}]
    peak = equity
    max_dd = 0.0

    for i, t in enumerate(completed):
        equity *= (1 + t.pnl_pct / 100)
        peak = max(peak, equity)
        dd = (peak - equity) / peak * 100 if peak > 0 else 0
        max_dd = max(max_dd, dd)
        equity_curve.append({
            "trade": i + 1,
            "equity": round(equity, 2),
            "pnl_pct": t.pnl_pct,
            "label": f"{t.name} {t.exit_reason}",
        })

    return BacktestResult(
        total_signals=len(trades),
        executed_trades=n_executed,
        win_trades=n_wins,
        lose_trades=n_losses,
        win_rate=round(win_rate, 1),
        avg_win_pct=round(avg_win, 2),
        avg_loss_pct=round(avg_loss, 2),
        total_return_pct=round(total_return, 2),
        max_drawdown_pct=round(max_dd, 2),
        profit_factor=round(profit_factor, 2),
        avg_bars_held=round(avg_bars, 1),
        trades=trades,
        equity_curve=equity_curve,
    )

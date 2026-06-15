"""模拟交易引擎 — 多品种虚拟盘跟踪 + 账户报告

每个品种独立持仓，可同时持有多个品种的虚拟仓位。
入场复用 should_notify() 门控；出场检测止损/止盈 + 滑点。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, date
from typing import Optional

import numpy as np
import pandas as pd

from config import (
    PAPER_INITIAL_BALANCE, PAPER_SLIPPAGE_PCT,
    COMMISSION_RATE, MIN_COMMISSION, MAX_SINGLE_LOSS_PCT,
)
from src.collector import get_db
from src.signal_engine import SignalOutput, should_notify
from src.macros import MacroRisk, calculate_position_size

logger = logging.getLogger("paper_trader")


# ======================================================================
# Data structures
# ======================================================================

@dataclass
class PaperPosition:
    """当前虚拟持仓"""
    symbol: str
    direction: str              # "long" | "short"
    entry_time: pd.Timestamp
    entry_price: float
    stop_loss: float
    take_profit: float
    quantity: int = 1
    signal_score: int = 0
    signal_conviction: str = ""
    trade_id: int = -1          # DB row id


@dataclass
class AccountSummary:
    """账户快照"""
    initial_balance: float
    equity: float
    closed_balance: float
    open_pnl: float
    open_pnl_pct: float
    closed_pnl: float
    total_trades: int
    win_trades: int
    lose_trades: int
    win_rate: float             # 0-100
    total_return_pct: float
    max_drawdown_pct: float
    daily_pnl: float
    daily_trades: int
    daily_win_rate: float


# ======================================================================
# PaperTrader
# ======================================================================

class PaperTrader:
    """模拟交易引擎 — 多品种独立持仓"""

    def __init__(self, initial_balance: float = PAPER_INITIAL_BALANCE):
        self.initial_balance = initial_balance
        self.closed_balance = initial_balance
        self._positions: dict[str, PaperPosition] = {}  # symbol → position
        self._closed_trades: list[dict] = []
        self._equity_points: list[tuple] = []
        self._loaded = False

    def _ensure_loaded(self):
        if self._loaded:
            return
        self._loaded = True
        self._load_state()

    def _load_state(self):
        """从 DB 恢复所有品种状态"""
        db = get_db()
        open_rows = db.get_paper_trades(status="open")
        for row in open_rows:
            sym = row["symbol"]
            self._positions[sym] = PaperPosition(
                symbol=sym,
                direction=row["direction"],
                entry_time=pd.Timestamp(row["entry_time"]),
                entry_price=row["entry_price"],
                stop_loss=row["stop_loss"],
                take_profit=row["take_profit"],
                quantity=row["quantity"],
                signal_score=row["signal_score"] or 0,
                signal_conviction=row["signal_conviction"] or "",
                trade_id=row["id"],
            )

        self._closed_trades = db.get_paper_trades(status="closed")
        balance = self.initial_balance
        self._equity_points = []
        for t in sorted(self._closed_trades, key=lambda x: x["exit_time"] or ""):
            balance += t["pnl"] or 0
            self._equity_points.append((t["exit_time"], balance))

        if self._closed_trades:
            self.closed_balance = balance

        pos_syms = list(self._positions.keys())
        logger.info(f"PaperTrader 初始化: 权益={self.closed_balance:.0f} "
                     f"持仓={pos_syms if pos_syms else '无'} "
                     f"已平={len(self._closed_trades)}笔")

    # ==================================================================
    # 主入口
    # ==================================================================

    def evaluate(self, df: pd.DataFrame, signal: SignalOutput,
                 macro: MacroRisk, symbol: str) -> Optional[str]:
        """每品种每轮调用：检查出场 → 检查入场"""
        self._ensure_loaded()
        if df.empty:
            return None

        bar = df.iloc[-1]
        bar_time = df.index[-1]

        # 1. 该品种有持仓 → 检查出场
        if symbol in self._positions:
            result = self._check_exits(symbol, bar, bar_time)
            if result:
                return result
            # 更新权益曲线
            equity = self.closed_balance + self._total_unrealized_pnl()
            self._equity_points.append((bar_time, equity))
            return None

        # 2. 无持仓 → 检查入场
        ok, reason = should_notify(signal)
        if not ok:
            return None

        if signal.score >= 70:
            direction = "long"
        elif signal.score <= 30:
            direction = "short"
        else:
            return None

        size = calculate_position_size(
            capital=self.closed_balance,
            risk_pct=MAX_SINGLE_LOSS_PCT,
            pos_coef=macro.position_coefficient,
            entry=signal.entry_price,
            stop=signal.stop_loss,
        )
        quantity = int(size["quantity"])
        if quantity < 1:
            logger.info(f"{symbol} 仓位不足: 手数={quantity}, 跳过入场")
            return None

        return self._enter_position(symbol, signal, bar, quantity, direction)

    # ==================================================================
    # 出场
    # ==================================================================

    def _check_exits(self, symbol: str, bar: pd.Series, bar_time) -> Optional[str]:
        pos = self._positions.get(symbol)
        if pos is None:
            return None

        if pos.direction == "long":
            if bar["low"] <= pos.stop_loss:
                return self._close_position(symbol, pos.stop_loss * (1 - PAPER_SLIPPAGE_PCT), "stop", bar_time)
            elif bar["high"] >= pos.take_profit:
                return self._close_position(symbol, pos.take_profit * (1 - PAPER_SLIPPAGE_PCT), "target", bar_time)
        else:
            if bar["high"] >= pos.stop_loss:
                return self._close_position(symbol, pos.stop_loss * (1 + PAPER_SLIPPAGE_PCT), "stop", bar_time)
            elif bar["low"] <= pos.take_profit:
                return self._close_position(symbol, pos.take_profit * (1 + PAPER_SLIPPAGE_PCT), "target", bar_time)
        return None

    def _close_position(self, symbol: str, exit_price: float,
                        exit_reason: str, exit_time) -> str:
        pos = self._positions.pop(symbol)
        if pos.direction == "long":
            pnl_per_unit = exit_price - pos.entry_price
        else:
            pnl_per_unit = pos.entry_price - exit_price

        gross_pnl = pnl_per_unit * pos.quantity
        commission = max(abs(exit_price) * COMMISSION_RATE * pos.quantity,
                         MIN_COMMISSION * pos.quantity)
        pnl = gross_pnl - commission
        pnl_pct = (pnl_per_unit / pos.entry_price * 100) if pos.entry_price > 0 else 0

        exit_time_str = str(exit_time)[:19]
        get_db().update_paper_trade(
            pos.trade_id, exit_time_str, round(exit_price, 2),
            round(pnl, 2), round(pnl_pct, 4), round(commission, 2), exit_reason,
        )

        self.closed_balance += pnl
        self._closed_trades.append({
            "symbol": symbol, "direction": pos.direction,
            "entry_time": str(pos.entry_time)[:19], "exit_time": exit_time_str,
            "entry_price": pos.entry_price, "exit_price": round(exit_price, 2),
            "stop_loss": pos.stop_loss, "take_profit": pos.take_profit,
            "quantity": pos.quantity, "pnl": round(pnl, 2),
            "pnl_pct": round(pnl_pct, 4), "commission": round(commission, 2),
            "exit_reason": exit_reason, "signal_score": pos.signal_score,
            "signal_conviction": pos.signal_conviction,
        })
        self._equity_points.append((exit_time, self.closed_balance))

        event = (f"[{symbol}] {'多头' if pos.direction == 'long' else '空头'} "
                 f"{'止盈' if exit_reason == 'target' else '止损'} | "
                 f"入场{pos.entry_price:.0f}→出场{exit_price:.0f} | "
                 f"盈亏{pnl:+.0f}元 | 权益{self.closed_balance:.0f}")
        logger.info(event)
        return event

    # ==================================================================
    # 入场
    # ==================================================================

    def _enter_position(self, symbol: str, signal: SignalOutput,
                        bar: pd.Series, quantity: int, direction: str) -> str:
        entry_price = float(bar["close"])
        entry_time = bar.name if hasattr(bar, 'name') else pd.Timestamp.now()

        trade_id = get_db().insert_paper_trade(
            symbol=symbol, direction=direction,
            entry_time=str(entry_time)[:19], entry_price=entry_price,
            stop_loss=signal.stop_loss, take_profit=signal.take_profit,
            quantity=quantity, signal_score=signal.score,
            signal_conviction=signal.conviction,
        )

        self._positions[symbol] = PaperPosition(
            symbol=symbol, direction=direction,
            entry_time=entry_time, entry_price=entry_price,
            stop_loss=signal.stop_loss, take_profit=signal.take_profit,
            quantity=quantity, signal_score=signal.score,
            signal_conviction=signal.conviction, trade_id=trade_id,
        )

        event = (f"[{symbol}] {'多头' if direction == 'long' else '空头'}入场 | "
                 f"价格{entry_price:.0f} | 止损{signal.stop_loss:.0f} | "
                 f"止盈{signal.take_profit:.0f} | 手数{quantity}")
        logger.info(event)
        return event

    # ==================================================================
    # 持仓查询
    # ==================================================================

    def has_position(self, symbol: str = None) -> bool:
        self._ensure_loaded()
        if symbol:
            return symbol in self._positions
        return len(self._positions) > 0

    def get_position(self, symbol: str = None) -> Optional[PaperPosition]:
        self._ensure_loaded()
        if symbol:
            return self._positions.get(symbol)
        # 无指定时返回第一个（兼容旧接口）
        if self._positions:
            return next(iter(self._positions.values()))
        return None

    def get_all_positions(self) -> list[PaperPosition]:
        self._ensure_loaded()
        return list(self._positions.values())

    def get_all_open_pnl(self) -> dict[str, float]:
        """返回 {symbol: 浮动盈亏} 所有持仓"""
        self._ensure_loaded()
        db = get_db()
        result = {}
        for sym, pos in self._positions.items():
            df = db.get_klines(sym, "5m", limit=1)
            if not df.empty:
                current = float(df.iloc[-1]["close"])
                if pos.direction == "long":
                    pnl = (current - pos.entry_price) * pos.quantity
                else:
                    pnl = (pos.entry_price - current) * pos.quantity
                result[sym] = round(pnl, 2)
            else:
                result[sym] = 0.0
        return result

    def _unrealized_pnl_for(self, symbol: str, current_price: float) -> float:
        pos = self._positions.get(symbol)
        if pos is None:
            return 0.0
        if pos.direction == "long":
            return (current_price - pos.entry_price) * pos.quantity
        else:
            return (pos.entry_price - current_price) * pos.quantity

    def _total_unrealized_pnl(self) -> float:
        db = get_db()
        total = 0.0
        for sym, pos in self._positions.items():
            df = db.get_klines(sym, "5m", limit=1)
            if not df.empty:
                current = float(df.iloc[-1]["close"])
                total += self._unrealized_pnl_for(sym, current)
        return total

    # ==================================================================
    # 账户摘要
    # ==================================================================

    def get_summary(self, symbol: str = None) -> AccountSummary:
        self._ensure_loaded()

        if symbol:
            trades = [t for t in self._closed_trades if t["symbol"] == symbol]
        else:
            trades = self._closed_trades

        wins = [t for t in trades if t["pnl"] > 0]
        losses = [t for t in trades if t["pnl"] <= 0]
        total = len(trades)
        win_rate = (len(wins) / total * 100) if total > 0 else 0

        # 浮动盈亏
        if symbol:
            open_pnl = self._unrealized_pnl_for(symbol, self._get_current_price(symbol))
        else:
            open_pnl = self._total_unrealized_pnl()

        open_pnl_pct = 0.0
        if symbol and symbol in self._positions:
            pos = self._positions[symbol]
            open_pnl_pct = (open_pnl / (pos.entry_price * pos.quantity) * 100
                            ) if pos.entry_price > 0 else 0

        closed_pnl = sum(t["pnl"] for t in trades)
        equity = self.closed_balance + open_pnl
        total_return = (equity / self.initial_balance - 1) * 100

        # 最大回撤
        max_dd = 0.0
        if self._equity_points:
            peak = self.initial_balance
            for _, val in self._equity_points:
                peak = max(peak, val)
                dd = (peak - val) / peak * 100 if peak > 0 else 0
                max_dd = max(max_dd, dd)
            peak = max(peak, equity)
            dd = (peak - equity) / peak * 100 if peak > 0 else 0
            max_dd = max(max_dd, dd)

        # 今日统计
        today_str = date.today().isoformat()
        today_trades = [t for t in trades
                        if (t.get("exit_time") or "")[:10] == today_str]
        today_pnl = sum(t["pnl"] for t in today_trades)
        today_wins = [t for t in today_trades if t["pnl"] > 0]
        today_win_rate = (len(today_wins) / len(today_trades) * 100
                          ) if today_trades else 0

        return AccountSummary(
            initial_balance=self.initial_balance,
            equity=round(equity, 2),
            closed_balance=round(self.closed_balance, 2),
            open_pnl=round(open_pnl, 2),
            open_pnl_pct=round(open_pnl_pct, 4),
            closed_pnl=round(closed_pnl, 2),
            total_trades=total,
            win_trades=len(wins),
            lose_trades=len(losses),
            win_rate=round(win_rate, 1),
            total_return_pct=round(total_return, 2),
            max_drawdown_pct=round(max_dd, 2),
            daily_pnl=round(today_pnl, 2),
            daily_trades=len(today_trades),
            daily_win_rate=round(today_win_rate, 1),
        )

    def _get_current_price(self, symbol: str) -> float:
        db = get_db()
        df = db.get_klines(symbol, "5m", limit=1)
        if not df.empty:
            return float(df.iloc[-1]["close"])
        return 0.0

    # ==================================================================
    # 交易历史 + 权益曲线
    # ==================================================================

    def get_trade_history(self, symbol: str = None) -> pd.DataFrame:
        self._ensure_loaded()
        trades = self._closed_trades
        if symbol:
            trades = [t for t in trades if t["symbol"] == symbol]
        if not trades:
            return pd.DataFrame()
        df = pd.DataFrame(trades)
        cols = ["symbol", "direction", "entry_time", "exit_time",
                "entry_price", "exit_price", "quantity", "pnl",
                "pnl_pct", "exit_reason", "signal_score"]
        available = [c for c in cols if c in df.columns]
        return df[available].sort_values("exit_time", ascending=False)

    def get_equity_curve(self) -> pd.DataFrame:
        self._ensure_loaded()
        if not self._equity_points:
            return pd.DataFrame(columns=["time", "equity"])
        df = pd.DataFrame(self._equity_points, columns=["time", "equity"])
        df["time"] = pd.to_datetime(df["time"])
        return df

    def get_daily_report(self) -> dict:
        s = self.get_summary()
        return {
            "daily_pnl": s.daily_pnl, "daily_trades": s.daily_trades,
            "daily_win_rate": s.daily_win_rate, "equity": s.equity,
            "total_return_pct": s.total_return_pct,
            "open_positions": len(self._positions),
        }

    def get_position_symbols(self) -> list[str]:
        """返回当前持仓的品种列表"""
        self._ensure_loaded()
        return list(self._positions.keys())


# ======================================================================
# 单例
# ======================================================================

_trader: Optional[PaperTrader] = None


def get_paper_trader() -> PaperTrader:
    global _trader
    if _trader is None:
        _trader = PaperTrader()
    return _trader

"""Phase 8 验证脚本 — 模拟交易"""
import sys
sys.path.insert(0, ".")

import logging
logging.basicConfig(level=logging.WARNING)

import numpy as np
import pandas as pd
from datetime import datetime, timedelta

print("=" * 60)
print("Phase 8 验证: 模拟交易")
print("=" * 60)


def ok(msg):
    print(f"  [OK] {msg}")

def fail(msg):
    print(f"  [FAIL] {msg}")


# --- 清理 ---
from src.collector import get_db
db = get_db()
db.execute("DELETE FROM paper_trades")
db.commit()


# --- 1. 数据库表 ---
print("\n1. 数据库 paper_trades 表")
try:
    rows = db.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='paper_trades'"
    ).fetchall()
    assert len(rows) == 1
    ok("paper_trades 表已创建")

    # 验证列
    cols = [d[1] for d in db.execute("PRAGMA table_info(paper_trades)").fetchall()]
    required = ["id", "symbol", "direction", "entry_time", "exit_time",
                "entry_price", "exit_price", "stop_loss", "take_profit",
                "quantity", "pnl", "pnl_pct", "commission", "exit_reason"]
    missing = [c for c in required if c not in cols]
    if missing:
        fail(f"缺少列: {missing}")
    else:
        ok(f"表结构正确 ({len(cols)} 列)")
except Exception as e:
    fail(str(e))


# --- 2. PaperTrader 初始化 ---
print("\n2. PaperTrader 初始化")
try:
    from src.paper_trader import PaperTrader, get_paper_trader, PaperPosition, AccountSummary
    from config import PAPER_INITIAL_BALANCE

    trader = PaperTrader(initial_balance=100000)
    trader._ensure_loaded()

    assert not trader.has_position()
    summary = trader.get_summary()
    assert summary.initial_balance == 100000
    assert summary.equity == 100000
    assert summary.total_trades == 0
    ok(f"初始化: 资金={summary.initial_balance:.0f}, 权益={summary.equity:.0f}")
except Exception as e:
    fail(str(e))


# --- 3. DB 访问方法 ---
print("\n3. DB insert/update/query")
try:
    from config import PRIMARY_SYMBOL

    tid = db.insert_paper_trade(
        "RB", "long", "2026-06-11 10:00:00",
        3500.0, 3480.0, 3550.0, 2, 85, "高确信度",
    )
    assert tid > 0
    ok(f"insert_paper_trade id={tid}")

    # 查询开仓
    open_trades = db.get_paper_trades(status="open")
    assert len(open_trades) == 1
    t = open_trades[0]
    assert t["entry_price"] == 3500.0
    assert t["exit_time"] is None
    ok(f"get open: id={t['id']} entry_price={t['entry_price']}")

    # 更新平仓
    db.update_paper_trade(
        tid, "2026-06-11 14:00:00", 3550.0, 94.0, 1.34, 5.88, "target",
    )
    db.commit()

    # 查询已平仓
    closed = db.get_paper_trades(status="closed")
    assert len(closed) == 1
    c = closed[0]
    assert c["exit_price"] == 3550.0
    assert c["pnl"] == 94.0
    assert c["exit_reason"] == "target"
    ok(f"get closed: exit_price={c['exit_price']} pnl={c['pnl']} reason={c['exit_reason']}")

    # 清理
    db.execute("DELETE FROM paper_trades")
    db.commit()
except Exception as e:
    import traceback
    fail(f"{e}\n{traceback.format_exc()}")


# --- 4. 入场 + 止损出场 ---
print("\n4. 入场 → 止损出场")
try:
    from src.signal_engine import SignalOutput, SignalStatus
    from src.macros import MacroRisk

    trader2 = PaperTrader(initial_balance=100000)
    trader2._ensure_loaded()

    # 手动入场
    now = pd.Timestamp.now()
    tid = db.insert_paper_trade(
        "RB", "long", str(now)[:19],
        3500.0, 3480.0, 3550.0, 1, 82, "高确信度",
    )
    trader2._position = PaperPosition(
        symbol="RB", direction="long",
        entry_time=now, entry_price=3500.0,
        stop_loss=3480.0, take_profit=3550.0,
        quantity=1, signal_score=82,
        signal_conviction="高确信度", trade_id=tid,
    )
    trader2.closed_balance = 100000
    assert trader2.has_position()

    # 触发止损的K线
    base = pd.Timestamp.now()
    dates = pd.date_range(end=base, periods=5, freq="5min")
    df_stop = pd.DataFrame({
        "open": [3505]*5, "high": [3510]*5,
        "low": [3470]*5, "close": [3475]*5,
        "volume": [10000]*5,
    }, index=dates)

    macro = MacroRisk("low", 20, 15.0, 1.0, ["测试"])
    signal_neutral = SignalOutput(50, "中性", "无信号", SignalStatus.REJECTED)

    event = trader2.evaluate(df_stop, signal_neutral, macro)
    assert not trader2.has_position(), "止损应已出场"
    ok(f"止损出场: {event}")

    # 验证DB
    closed = db.get_paper_trades(status="closed")
    assert len(closed) >= 1
    # 找到我们这笔
    our_trade = [t for t in closed if t["id"] == tid][0]
    assert our_trade["exit_reason"] == "stop"
    ok(f"DB确认: 出场价={our_trade['exit_price']} 盈亏={our_trade['pnl']}")

    db.execute("DELETE FROM paper_trades")
    db.commit()
except Exception as e:
    import traceback
    fail(f"{e}\n{traceback.format_exc()}")


# --- 5. 入场 → 止盈出场 ---
print("\n5. 入场 → 止盈出场")
try:
    trader3 = PaperTrader(initial_balance=100000)
    trader3._ensure_loaded()

    now = pd.Timestamp.now()
    tid = db.insert_paper_trade(
        "RB", "long", str(now)[:19],
        3500.0, 3480.0, 3550.0, 1, 85, "高确信度",
    )
    trader3._position = PaperPosition(
        symbol="RB", direction="long",
        entry_time=now, entry_price=3500.0,
        stop_loss=3480.0, take_profit=3550.0,
        quantity=1, signal_score=85,
        signal_conviction="高确信度", trade_id=tid,
    )
    trader3.closed_balance = 100000

    base = pd.Timestamp.now()
    dates = pd.date_range(end=base, periods=5, freq="5min")
    df_tp = pd.DataFrame({
        "open": [3520]*5, "high": [3560]*5,
        "low": [3515]*5, "close": [3555]*5,
        "volume": [10000]*5,
    }, index=dates)

    macro = MacroRisk("low", 20, 15.0, 1.0, ["测试"])
    signal_neutral = SignalOutput(50, "中性", "无信号", SignalStatus.REJECTED)

    event = trader3.evaluate(df_tp, signal_neutral, macro)
    assert not trader3.has_position(), "止盈应已出场"
    ok(f"止盈出场: {event}")

    closed = db.get_paper_trades(status="closed")
    our_trade = [t for t in closed if t["id"] == tid][0]
    assert our_trade["exit_reason"] == "target"
    ok(f"DB确认: 出场价={our_trade['exit_price']} 盈亏={our_trade['pnl']}")

    db.execute("DELETE FROM paper_trades")
    db.commit()
except Exception as e:
    import traceback
    fail(f"{e}\n{traceback.format_exc()}")


# --- 6. 手续费 ---
print("\n6. 手续费验证")
try:
    from config import COMMISSION_RATE, MIN_COMMISSION
    # 3550 * 0.0001 * 1 = 0.355 < 3.0 → 收 3.0
    expected_min = max(3550 * COMMISSION_RATE * 1, MIN_COMMISSION * 1)
    assert expected_min == 3.0
    # 50000 * 0.0001 * 5 = 25.0 > 3.0*5=15 → 收 25.0
    expected_rate = max(50000 * COMMISSION_RATE * 5, MIN_COMMISSION * 5)
    assert expected_rate == 25.0
    ok(f"min(3元)={expected_min:.2f} rate={expected_rate:.2f}")
except Exception as e:
    fail(str(e))


# --- 7. 单仓位约束 ---
print("\n7. 单仓位约束")
try:
    trader4 = PaperTrader(initial_balance=100000)
    trader4._ensure_loaded()

    now = pd.Timestamp.now()
    tid = db.insert_paper_trade(
        "RB", "long", str(now)[:19],
        3500.0, 3480.0, 3550.0, 1, 82, "高确信度",
    )
    trader4._position = PaperPosition(
        symbol="RB", direction="long",
        entry_time=now, entry_price=3500.0,
        stop_loss=3480.0, take_profit=3550.0,
        quantity=1, signal_score=82,
        signal_conviction="高确信度", trade_id=tid,
    )
    assert trader4.has_position()

    # 新信号（不触发出场）
    base = pd.Timestamp.now()
    dates = pd.date_range(end=base, periods=5, freq="5min")
    df_hold = pd.DataFrame({
        "open": [3510]*5, "high": [3520]*5,
        "low": [3495]*5, "close": [3515]*5,
        "volume": [10000]*5,
    }, index=dates)

    signal_strong = SignalOutput(
        score=85, direction="偏多", conviction="高确信度",
        status=SignalStatus.CONFIRMED,
        independent_count=4, min_independent_required=3,
        rr_ratio=2.5, entry_price=3520, stop_loss=3490,
        take_profit=3580, summary="第二个信号",
    )
    macro = MacroRisk("low", 20, 15.0, 1.0, ["测试"])

    trader4.evaluate(df_hold, signal_strong, macro)
    assert trader4.has_position(), "仍应持仓"
    assert trader4.get_position().entry_price == 3500.0, "不应被新信号替换"
    ok("有持仓时不开新仓")

    db.execute("DELETE FROM paper_trades")
    db.commit()
except Exception as e:
    import traceback
    fail(f"{e}\n{traceback.format_exc()}")


# --- 8. 账户摘要 ---
print("\n8. 账户摘要")
try:
    trader5 = PaperTrader(initial_balance=100000)
    trader5._ensure_loaded()

    # 模拟几笔已完成的交易
    for i, (entry, exit_p, direction, pnl) in enumerate([
        (3500, 3550, "long", 47.0),    # 盈
        (3550, 3520, "long", -33.0),   # 亏
        (3520, 3580, "long", 57.0),    # 盈
    ]):
        now = pd.Timestamp.now() - timedelta(hours=i+1)
        tid = db.insert_paper_trade(
            "RB", direction, str(now)[:19],
            entry, entry + 20, entry - 20, 1, 80, "中等确信度",
        )
        db.update_paper_trade(
            tid, str(now + timedelta(hours=1))[:19],
            exit_p, pnl, pnl / entry * 100,
            max(exit_p * 0.0001, 3.0), "target" if pnl > 0 else "stop",
        )
        trader5.closed_balance += pnl
        trader5._closed_trades.append({
            "pnl": pnl, "exit_time": str(now + timedelta(hours=1))[:19],
        })

    summary = trader5.get_summary()
    assert summary.total_trades >= 3
    assert summary.win_trades >= 2
    assert summary.win_rate > 50  # 2/3
    ok(f"胜率: {summary.win_rate:.0f}% | 交易: {summary.total_trades} | "
       f"盈亏: {summary.closed_pnl:+.1f}")

    db.execute("DELETE FROM paper_trades")
    db.commit()
except Exception as e:
    import traceback
    fail(f"{e}\n{traceback.format_exc()}")


# --- 9. 权益曲线 ---
print("\n9. 权益曲线")
try:
    trader6 = PaperTrader(initial_balance=100000)
    trader6._loaded = True  # 跳过从DB加载，使用手动数据
    # 手动填充权益点
    trader6._equity_points = [
        (pd.Timestamp.now() - timedelta(hours=2), 100000),
        (pd.Timestamp.now() - timedelta(hours=1), 100050),
        (pd.Timestamp.now(), 100030),
    ]
    eq = trader6.get_equity_curve()
    assert len(eq) == 3
    ok(f"权益曲线: {len(eq)} 点")

    report = trader6.get_daily_report()
    assert "daily_pnl" in report
    ok(f"每日报告: 盈亏={report['daily_pnl']:+.1f}")
except Exception as e:
    fail(str(e))

# --- 最终清理 ---
db.execute("DELETE FROM paper_trades")
db.commit()

print("\n" + "=" * 60)
print("Phase 8 验证完成")
print("=" * 60)

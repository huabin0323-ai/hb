"""hb-trading 主运行器 — 全品种轮询 + 信号检测 + 微信通知 + 模拟交易

用法:
  python runner.py           # 前台运行，30分钟轮询
  python runner.py --once    # 只跑一次全部品种分析
  python runner.py --interval 10   # 每10分钟一次
"""

import sys
import time
import logging
import argparse
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from src.collector import get_db, fill_all, check_quality, notify, ALL_SYMBOLS, SYMBOLS
from src.signal_engine import analyze_full, should_notify
from src.macros import assess_macro_risk, calculate_position_size
from src.paper_trader import get_paper_trader
from config import INITIAL_CAPITAL

logger = logging.getLogger("runner")


def analyze_symbol(sym: str) -> dict:
    """分析单个品种，返回结果字典"""
    db = get_db()
    info = SYMBOLS[sym]
    result = {"symbol": sym, "name": info["name"], "ok": False}

    try:
        df = db.get_klines(sym, "5m")
        if len(df) < 50:
            result["error"] = f"数据不足({len(df)}根)"
            return result

        # 信号
        signal = analyze_full(df, symbol=sym)
        ok, reason = should_notify(signal)

        # 宏观
        macro = assess_macro_risk(sym)
        size = calculate_position_size(
            INITIAL_CAPITAL, 2.0, macro.position_coefficient,
            float(df.iloc[-1]["close"]),
            signal.stop_loss if signal.stop_loss > 0 else float(df.iloc[-1]["low"]),
        )

        result.update({
            "ok": True,
            "price": float(df.iloc[-1]["close"]),
            "score": signal.score,
            "direction": signal.direction,
            "conviction": signal.conviction,
            "signals": signal.independent_count,
            "rr_ratio": signal.rr_ratio,
            "status": signal.status.value,
            "should_notify": ok,
            "notify_reason": reason,
            "macro_level": macro.risk_level,
            "macro_coef": macro.position_coefficient,
            "size": size,
            "signal": signal,
            "macro": macro,
            "df": df,
        })
    except Exception as e:
        result["error"] = str(e)
        logger.warning(f"{sym} 分析失败: {e}")

    return result


def run_once():
    """单次全品种分析"""
    t0 = time.time()
    info = SYMBOLS.get(ALL_SYMBOLS[0], {})
    print(f"\n{'='*60}")
    print(f"hb-trading 全品种分析 | {datetime.now():%Y-%m-%d %H:%M:%S}")
    print(f"品种: {len(ALL_SYMBOLS)}个 | {datetime.now():%H:%M:%S}")
    print(f"{'='*60}")

    # 1. 数据（全品种）
    print("[1/4] 数据采集...", end=" ", flush=True)
    stats = fill_all()
    total_data = sum(stats.values())
    ok_count = sum(1 for v in stats.values() if v > 0)
    print(f"{total_data}条 ({ok_count}/{len(stats)} 成功)")

    # 2-4. 逐个品种分析
    trader = get_paper_trader()
    events: list[str] = []
    notifications: list[str] = []
    line = "-" * 60

    for sym in ALL_SYMBOLS:
        sym_info = SYMBOLS[sym]
        r = analyze_symbol(sym)

        if r["ok"]:
            # 通知
            if r["should_notify"]:
                msg = (
                    f"🔔 {sym_info['name']}({sym}) {r['direction']} #{r['score']}分\n"
                    f"价格: {r['price']:.0f} | RR={r['rr_ratio']:.1f}:1\n"
                    f"入场: {r['signal'].entry_price:.0f} | "
                    f"止损: {r['signal'].stop_loss:.0f} | "
                    f"目标: {r['signal'].take_profit:.0f}\n"
                    f"信号: {r['signals']}个共振 | {r['conviction']}\n"
                    f"风险: {r['macro_level']} | "
                    f"仓位: {r['size']['quantity']}手"
                )
                if notify(f"🔔 {sym_info['name']} {r['direction']}信号 #{r['score']}分", msg, sym):
                    notifications.append(sym)

            # 模拟交易
            event = trader.evaluate(r["df"], r["signal"], r["macro"], sym)
            if event:
                events.append(event)
                if notify(f"📊 模拟交易: {event[:80]}", event, sym):
                    pass

            # 打印
            pos_flag = "*" if trader.has_position(sym) else " "
            print(f"  {sym:4s} {sym_info['name']:5s} {r['price']:>7.0f}  "
                  f"评分{r['score']:>3d} {r['direction']:3s} "
                  f"信号{r['signals']}个 RR{r['rr_ratio']:.1f} "
                  f"{r['status']:9s} {r['macro_level']:6s} "
                  f"{'📌' if trader.has_position(sym) else '  '}{pos_flag}")
        else:
            error_msg = r.get("error", "未知错误")
            print(f"  {sym:4s} {sym_info['name']:5s} ⚠ {error_msg}")

    # 总结
    elapsed = time.time() - t0
    summary = trader.get_summary()
    print(f"\n{line}")
    print(f"完成: {len(ALL_SYMBOLS)}品种 | 耗时: {elapsed:.0f}s")
    print(f"账户: 权益{summary.equity:,.0f} | "
          f"盈亏{summary.closed_pnl:+,.0f} | "
          f"持仓{len(trader.get_position_symbols())}个 | "
          f"胜率{summary.win_rate:.0f}%")
    if events:
        print(f"交易事件: {len(events)}笔")
        for e in events:
            print(f"  {e}")
    if notifications:
        print(f"微信通知: {len(notifications)}个品种 ({', '.join(notifications)})")


def run_loop(interval_minutes: int = 30):
    """持续轮询"""
    print(f"hb-trading 全品种监控启动")
    print(f"品种: {len(ALL_SYMBOLS)}个 | 间隔: {interval_minutes}分钟")
    print(f"按 Ctrl+C 退出\n")

    while True:
        try:
            run_once()
        except KeyboardInterrupt:
            raise
        except Exception:
            logger.exception("分析异常")
            try:
                notify("⚠ hb-trading 异常", "系统分析出错，请检查日志", "")
            except Exception:
                pass

        sleep_secs = interval_minutes * 60
        next_str = datetime.fromtimestamp(time.time() + sleep_secs).strftime("%H:%M:%S")
        print(f"\n下次分析: {next_str}")
        try:
            time.sleep(sleep_secs)
        except KeyboardInterrupt:
            print("\n已退出")
            break


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--once", action="store_true")
    p.add_argument("--interval", type=int, default=30)
    args = p.parse_args()

    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s")

    if args.once:
        run_once()
    else:
        run_loop(args.interval)

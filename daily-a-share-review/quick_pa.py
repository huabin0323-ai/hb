"""A股PA快速分析 CLI — 单只/多只股票价格行为学分析

用法:
    python quick_pa.py --stock 300750                           # 单只
    python quick_pa.py --stock 300750,002594,600519             # 多只
    python quick_pa.py --stock 300750 --push                    # 分析+飞书推送
    python quick_pa.py --stock 300750 --json                    # JSON输出

输出:
    - 市场结构判定（趋势/区间/通道）
    - 技术评分 0-100 + 因子拆解
    - 支撑/阻力位
    - 入场信号 + 条件单建议
    - 信号K线 近20日
    - 排序摘要（多只时）
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from typing import Optional

import pandas as pd

sys.path.insert(0, ".")
from src.fetcher import http_push2_kline
from src.pa_analyzer import analyze as pa_analyze
from src.pa_signal import generate as gen_signal
from config import PA_MIN_RR_RATIO

logging.basicConfig(
    level=logging.WARNING,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("quick_pa")


def _fetch_and_analyze(code: str) -> Optional[dict]:
    """Fetch K-line data and run PA analysis for a single stock."""
    try:
        raw = http_push2_kline(code, days=250)
        if raw is None or raw.empty or len(raw) < 20:
            return None

        raw["date"] = pd.to_datetime(raw["date"])
        raw.set_index("date", inplace=True)
        raw.sort_index(inplace=True)

        result = pa_analyze(raw)
        result["current_price"] = float(raw["close"].iloc[-1])
        return result
    except Exception as e:
        logger.warning(f"  {code}: {e}")
        return None


def _format_single_stock(code: str, result: dict, name: str = "") -> str:
    """Format PA analysis result for one stock as readable text."""
    state = result["state"]
    score = result["technical_score"]
    signal = gen_signal(result, code, name)

    lines = []
    sep = "=" * 60

    # Header
    dir_symbol = {"偏多": "+", "偏空": "-", "中性": "~"}.get(signal.direction, "?")
    lines.append(sep)
    lines.append(f"  {name}({code})  {dir_symbol}  Score: {score.score}/100  {signal.direction}  {signal.confidence}")
    lines.append(sep)

    # Market structure
    trend_label = {
        "uptrend": "UPTREND",
        "downtrend": "DOWNTREND",
        "trading_range": "RANGE",
        "narrow_channel": "NARROW CH",
        "wide_channel": "WIDE CH",
    }.get(state.trend, state.trend)
    lines.append(f"  Structure: {trend_label}  Strength: {state.strength}  Bias: {state.bias or 'none'}")
    lines.append(f"  {state.description}")
    lines.append(f"  Current: {signal.current_price}  ATR(14): {signal.atr}")

    # Score breakdown
    parts = [f"{k}={v}" for k, v in score.breakdown.items()]
    lines.append(f"  Breakdown: {' | '.join(parts)}")

    # Supports / Resistances
    if signal.supports:
        items = [f"{s.price}({s.label})" for s in signal.supports[:3]]
        lines.append(f"  Supports: {' < '.join(items)}")
    if signal.resistances:
        items = [f"{r.price}({r.label})" for r in signal.resistances[:3]]
        lines.append(f"  Resistances: {' < '.join(items)}")

    # Entry signal
    if signal.primary_signal_desc:
        lines.append(f"  Signal: [{signal.primary_signal_type}] {signal.primary_signal_desc}")
    lines.append(f"  Entry: {signal.suggested_entry}  Stop: {signal.suggested_stop}  Target: {signal.suggested_target}")
    rr_ok = "OK" if signal.rr_ok else f"RR<{PA_MIN_RR_RATIO}"
    lines.append(f"  RR: {signal.rr_ratio}:1 [{rr_ok}]  Position: {signal.suggested_position_pct}%")

    # Signal bars (recent 5)
    sig_bars = result.get("signal_bars", [])
    if sig_bars:
        recent = [s for s in sig_bars if hasattr(s, "index")]
        if recent:
            lines.append(f"  Recent Bars ({min(5, len(recent))}):")
            for s in recent[-5:]:
                short_type = s.type.replace("strong_", "").replace("_bar", "").replace("outside_", "out").replace("inside", "in")
                lines.append(f"    [{s.timestamp}] {short_type}: {s.description}")

    # Climax warnings
    climax = result.get("climax_warnings", [])
    for c in climax:
        lines.append(f"  [!] CLIMAX: {c.description if hasattr(c, 'description') else str(c)}")

    lines.append(sep)
    return "\n".join(lines)


def _format_summary(results: list[tuple], signals: list) -> str:
    """Format ranked summary across multiple stocks."""
    lines = ["", "=" * 68]
    lines.append(f"  PA Summary: {len(signals)} signals from {len(results)} stocks")
    lines.append("=" * 68)
    lines.append(f"  {'#':<3} {'Code':<8} {'Name':<8} {'Score':>5} {'Dir':>4} {'Conf':>8} {'RR':>6} {'Entry':>10} {'Stop':>10} {'Signal':<20}")
    lines.append("  " + "-" * 66)

    # Sort by score descending
    sorted_signals = sorted(signals, key=lambda s: -s.technical_score)
    for i, s in enumerate(sorted_signals[:20], 1):
        lines.append(
            f"  {i:<3} {s.code:<8} {s.name:<8} {s.technical_score:>5} "
            f"{s.direction:>4} {s.confidence:>8} {s.rr_ratio:>5.1f} "
            f"{s.suggested_entry:>10.2f} {s.suggested_stop:>10.2f} "
            f"{s.primary_signal_desc[:20]:<20}"
        )
    lines.append("=" * 68)
    return "\n".join(lines)


def _to_json(result: dict, code: str, name: str) -> dict:
    """Convert PA result to JSON-serializable dict."""
    signal = gen_signal(result, code, name)
    score = result["technical_score"]
    state = result["state"]

    return {
        "code": code, "name": name,
        "ok": signal.ok,
        "current_price": float(signal.current_price),
        "atr": float(signal.atr) if signal.atr else None,
        "market_structure": {
            "trend": state.trend,
            "strength": float(state.strength),
            "bias": state.bias,
            "description": str(state.description),
        },
        "technical_score": {
            "score": int(score.score),
            "direction": str(score.direction),
            "summary": str(score.summary),
            "breakdown": {str(k): float(v) for k, v in score.breakdown.items()},
        },
        "signal": {
            "direction": str(signal.direction),
            "confidence": str(signal.confidence),
            "type": str(signal.primary_signal_type),
            "description": str(signal.primary_signal_desc),
            "entry": float(signal.suggested_entry),
            "stop": float(signal.suggested_stop),
            "target": float(signal.suggested_target),
            "rr_ratio": float(signal.rr_ratio),
            "rr_ok": bool(signal.rr_ok),
            "position_pct": float(signal.suggested_position_pct),
        },
        "supports": [{"price": float(s.price), "label": str(s.label), "desc": str(s.description)}
                     for s in signal.supports[:5]],
        "resistances": [{"price": float(r.price), "label": str(r.label), "desc": str(r.description)}
                        for r in signal.resistances[:5]],
    }


def main():
    parser = argparse.ArgumentParser(description="A股PA快速分析")
    parser.add_argument("--stock", "-s", type=str,
                       help="股票代码，逗号分隔 (如 300750,002594,600519)")
    parser.add_argument("--push", action="store_true", help="推送到飞书")
    parser.add_argument("--json", "-j", action="store_true", help="JSON格式输出")
    parser.add_argument("--quiet", "-q", action="store_true", help="仅输出摘要")
    args = parser.parse_args()

    if not args.stock:
        parser.print_help()
        return

    codes = [c.strip() for c in args.stock.split(",") if c.strip()]

    results = []
    signals = []
    t0 = time.time()

    for code in codes:
        logger.info(f"Analyzing {code}...")
        result = None
        for attempt in range(3):
            result = _fetch_and_analyze(code)
            if result is not None:
                break
            time.sleep(1.0)

        if result is None or not result.get("ok"):
            print(f"[{code}] ERROR: unable to fetch data or analysis failed")
            continue

        signal = gen_signal(result, code, name="")
        results.append((code, result))
        signals.append(signal)

        if not args.quiet and not args.json:
            print(_format_single_stock(code, result))

        if len(codes) > 1:
            time.sleep(1.5)  # rate limit

    elapsed = time.time() - t0

    # Summary
    if len(codes) > 1:
        active = [s for s in signals if s.ok]
        if args.json:
            output = [_to_json(r, c, "") for (c, r) in results]
            sys.stdout.reconfigure(encoding='utf-8')
            print(json.dumps(output, ensure_ascii=False, indent=2))
        elif args.quiet:
            print(_format_summary(results, active))
        else:
            print(_format_summary(results, active))
            print(f"\n  Analyzed {len(codes)} stocks in {elapsed:.1f}s")

    elif args.json:
        output = _to_json(results[0][1], codes[0], "")
        sys.stdout.reconfigure(encoding='utf-8')
        print(json.dumps(output, ensure_ascii=False, indent=2))

    # Feishu push
    if args.push and signals:
        try:
            from src.pa_feishu import render_signal_card, render_summary_card
            from src.feishu import send_card

            active = [s for s in signals if s.ok]
            if len(active) > 1:
                summary = render_summary_card(active, "快速分析")
                send_card(summary)
            for s in active[:5]:
                card = render_signal_card(s)
                send_card(card)
                time.sleep(0.3)
            print(f"  Pushed {len(active)} signals to Feishu")
        except Exception as e:
            print(f"  Feishu push failed: {e}")


if __name__ == "__main__":
    main()

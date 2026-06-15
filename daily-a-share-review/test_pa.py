"""Quick PA single-stock analysis test"""
import sys, logging
logging.basicConfig(level=logging.WARNING)

import pandas as pd
from src.fetcher import http_push2_kline
from src.pa_analyzer import analyze
from src.pa_signal import generate

code = "300750"
name = "CATL"

print("=" * 60)
print(f"  PA Analysis: {name} ({code})")
print("=" * 60)

# 1. Fetch data
print("\n[1] Fetching K-line data...")
raw = http_push2_kline(code, days=250)
raw["date"] = pd.to_datetime(raw["date"])
raw.set_index("date", inplace=True)
raw.sort_index(inplace=True)
df = raw
print(f"  {len(df)} bars, {df.index[0]} ~ {df.index[-1]}")
print(f"  Close: {df['close'].iloc[-1]:.2f} | High: {df['high'].max():.2f} | Low: {df['low'].min():.2f}")

# 2. PA analysis
print("\n[2] PA Structure...")
result = analyze(df)
state = result["state"]
score = result["technical_score"]

print(f"  Market: {state.trend} | Strength: {state.strength} | Bias: {state.bias}")
print(f"  Description: {state.description}")

print(f"\n[3] Score: {score.score}/100 ({score.direction})")
print(f"  Summary: {score.summary}")

for k, v in score.breakdown.items():
    print(f"    {k}: {v}")

# Support/Resistance
supports = result["supports"]
resistances = result["resistances"]
print(f"\n[4] Supports ({len(supports)}):")
for s in supports[:4]:
    print(f"  {s.price:.2f} [{s.strength}] {s.description}")
print(f"  Resistances ({len(resistances)}):")
for r in resistances[:4]:
    print(f"  {r.price:.2f} [{r.strength}] {r.description}")

# Entry signals
all_entries = result["entry_signals"]
print(f"\n[5] Entry Signals ({len(all_entries)}):")
for e in all_entries[:6]:
    tag = {"H2": "[H2]", "H3": "[H3]", "H1": "[H1]", "wedge_break": "[WEDGE]",
           "failed_breakout": "[FAIL]", "bear_bar_long": "[BEAR-L]",
           "support_betrayal_long": "[BETRAY]", "climax_warning": "[!!]"}.get(e.type, "[?]")
    print(f"  {tag} {e.description}")
    print(f"      Entry={e.entry_price} Stop={e.stop_loss} Target={e.target} Conf={e.confidence:.0%}")

# Signal bars (recent 20)
sig_bars = result["signal_bars"]
if sig_bars:
    recent = [s for s in sig_bars if s.index >= len(df) - 20]
    print(f"\n[6] Signal Bars last 20d ({len(recent)}):")
    for s in recent[-5:]:
        tag = {"strong_bullish": "BULL", "strong_bearish": "BEAR", "pin_bar_bullish": "PIN+",
               "pin_bar_bearish": "PIN-", "inside_bar": "INSIDE", "outside_bar_bullish": "OUT+",
               "outside_bar_bearish": "OUT-"}.get(s.type, "?")
        print(f"  {tag} [{s.timestamp}] {s.description} (strength={s.strength})")

# Climax warnings
climax = result["climax_warnings"]
if climax:
    print(f"\n[7] Climax Warnings:")
    for c in climax:
        print(f"  {c.description}")

# ATR & midpoint
atr = result.get("atr")
mid = result.get("range_midpoint")
print(f"\n[8] ATR(14)={atr}, Range Midpoint={mid}")

# Signal generation
print(f"\n[9] Signal:")
result["current_price"] = float(df["close"].iloc[-1])
signal = generate(result, code, name)
print(f"  Valid: {signal.ok}")
print(f"  Direction: {signal.direction}  Confidence: {signal.confidence}")
print(f"  Entry: {signal.suggested_entry}")
print(f"  Stop: {signal.suggested_stop}")
print(f"  Target: {signal.suggested_target}")
print(f"  RR: {signal.rr_ratio}:1 {'OK' if signal.rr_ok else 'RR<2:1'}")
print(f"  Position: {signal.suggested_position_pct}%")

print("\n" + "=" * 60)

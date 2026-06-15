"""Phase 2 验证脚本 — 多时间框架 + 多种币种"""
import sys
sys.path.insert(0, ".")

import logging
logging.basicConfig(level=logging.WARNING)

from src.collector import fetch_historical
from src.price_action import analyze

print("=" * 60)
print("hb-trading Phase 2 验证: 价格行为引擎")
print("=" * 60)

# ---- 1. 多时间框架 ----
print("\n1. BTC/USDT 多时间框架")
for tf in ["15m", "1h", "4h"]:
    df = fetch_historical("BTC/USDT", tf, 200)
    result = analyze(df)
    s = result["state"]
    ts = result["technical_score"]
    print(f"  [{tf}] {s.trend:16s} | strength={s.strength:.2f} bias={str(s.bias):5s} | score={ts.score:3d}/100")

# ---- 2. 多种币种 ----
print("\n2. 多种币种 5m")
for sym in ["ETH/USDT", "SOL/USDT"]:
    df = fetch_historical(sym, "5m", 200)
    result = analyze(df)
    s = result["state"]
    ts = result["technical_score"]
    n_sig = len(result["signal_bars"])
    n_entry = len(result["entry_signals"])
    print(f"  [{sym}] {s.trend:16s} | strength={s.strength:.2f} bias={str(s.bias):5s} | score={ts.score:3d}/100 | sig_bars={n_sig} entries={n_entry}")

# ---- 3. 详细分析样例 ----
print("\n3. BTC/USDT 5m 详细分析")
df = fetch_historical("BTC/USDT", "5m", 200)
result = analyze(df)

state = result["state"]
print(f"  市场状态: {state.trend} ({state.description})")
print(f"  趋势强度: {state.strength:.2f}")
print(f"  方向倾向: {state.bias}")
print(f"  通道上轨: {state.channel_top}")
print(f"  通道下轨: {state.channel_bottom}")

# 摆动点
swings = result["swings"]
print(f"  次要摆动点: {len(swings['minor'])}")
print(f"  主要摆动点: {len(swings['major'])}")

# 信号K线
sig_bars = result["signal_bars"]
print(f"  信号K线总数: {len(sig_bars)}")
recent_sigs = [s for s in sig_bars if s.index >= len(df) - 50]
for s in recent_sigs[-5:]:
    print(f"    [{s.type}] {s.description} strength={s.strength:.2f}")

# 入场信号
entries = result["entry_signals"]
wedges = result["wedges"]
fbs = result["failed_breakouts"]
print(f"  H1/H2/H3入场: {len(entries)}")
for e in entries:
    print(f"    [{e.type}] {e.description} conf={e.confidence:.2f} entry={e.entry_price} sl={e.stop_loss}")
print(f"  楔形: {len(wedges)}")
for w in wedges:
    print(f"    [{w.type}] {w.description} conf={w.confidence:.2f}")
print(f"  失败突破: {len(fbs)}")
for f in fbs:
    print(f"    [{f.type}] {f.description} conf={f.confidence:.2f}")

# 技术面评分
ts = result["technical_score"]
print(f"\n  技术面评分: {ts.score}/100")
print(f"  方向: {ts.direction}")
print(f"  因子拆解:")
for k, v in ts.breakdown.items():
    print(f"    {k}: {v:.1f}")
print(f"  总结: {ts.summary}")

# ---- 4. 边界情况 ----
print("\n4. 边界情况测试")
import pandas as pd
from src.price_action import _validate_df, analyze_structure

# 空数据
try:
    analyze_structure(pd.DataFrame())
    print("  [FAIL] 空DataFrame应该抛异常")
except ValueError:
    print("  [PASS] 空DataFrame正确抛异常")

# 数据不足
try:
    empty_df = pd.DataFrame({"open": [1,2,3], "high": [2,3,4], "low": [0,1,2], "close": [1.5,2.5,3.5], "volume": [100,200,300]})
    result = analyze(empty_df)
    assert result["technical_score"].score == 0
    print("  [PASS] 数据不足返回score=0")
except Exception as e:
    print(f"  [FAIL] 数据不足处理异常: {e}")

# 平盘（所有价格相同）
flat_df = pd.DataFrame({
    "open": [100]*100, "high": [100]*100, "low": [100]*100,
    "close": [100]*100, "volume": [100]*100,
})
result = analyze(flat_df)
assert result["state"].trend == "trading_range"
print(f"  [PASS] 平盘判定为trading_range (strength={result['state'].strength})")

print("\n" + "=" * 60)
print("Phase 2 验证完成")
print("=" * 60)

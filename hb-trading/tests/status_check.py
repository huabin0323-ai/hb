"""全项目状态检查 — 国内期货版"""
import sys
sys.path.insert(0, ".")

import logging
logging.basicConfig(level=logging.WARNING)

def ok(msg):
    print(f"  [OK] {msg}")

def fail(msg):
    print(f"  [FAIL] {msg}")

print("=" * 60)
print("hb-trading 项目状态检查")
print("=" * 60)

# ---- Phase 1: 行情采集 ----
print("\n[Phase 1] 行情采集 (collector.py)")
try:
    from src.collector import get_db, check_quality, PRIMARY_SYMBOL
    db = get_db()
    counts = db.total_count()
    ok(f"K线统计: {counts}")
    # 质量检查
    q = check_quality(PRIMARY_SYMBOL, "5m")
    status = "OK" if q.healthy else "WARN"
    print(f"    数据质量({PRIMARY_SYMBOL} 5m): {status} | {q.total_rows}条 | "
          f"范围: {q.date_range[0]} ~ {q.date_range[1]} | "
          f"新鲜度: {q.freshness_hours:.1f}h")
    if q.price_anomalies:
        print(f"    价格异常: {q.price_anomalies[-3:]}")
    if q.volume_anomalies:
        print(f"    成交量异常: {q.volume_anomalies[-3:]}")
except Exception as e:
    fail(str(e))

# ---- Phase 2: 价格行为 ----
print("\n[Phase 2] 价格行为引擎 (price_action.py)")
try:
    from src.price_action import analyze
    df = db.get_klines(PRIMARY_SYMBOL, "5m", 200)
    if len(df) < 20:
        fail(f"数据不足: {len(df)}条 (需要>=20)")
    else:
        result = analyze(df)
        state = result["state"]
        ts = result["technical_score"]
        n_sig = len(result["signal_bars"])
        n_entry = (len(result["entry_signals"]) + len(result["wedges"])
                   + len(result["failed_breakouts"])
                   + len(result.get("bear_bar_longs", []))
                   + len(result.get("support_betrayals", [])))
        ok(f"K线: {len(df)}条 | 市场: {state.trend} | 强度: {state.strength:.2f}")
        print(f"    描述: {state.description}")
        print(f"    信号K线: {n_sig}个 | 入场信号: {n_entry}个")
        print(f"    技术评分: {ts.score}/100 {ts.direction or '中性'}")
except Exception as e:
    fail(str(e))

# ---- Phase 3: 情绪聚合 ----
print("\n[Phase 3] 情绪聚合 (sentiment.py)")
try:
    from src.sentiment import get_full_sentiment, get_basis, get_position_sentiment
    sentiment = get_full_sentiment()
    if sentiment.score is not None:
        ok(f"综合情绪: {sentiment.score}/100")
        print(f"    拆解: {sentiment.summary}")
        if sentiment.basis:
            print(f"    基差: {sentiment.basis.basis_pct:+.1f}% ({sentiment.basis.signal})")
        if sentiment.position:
            print(f"    持仓: {sentiment.position.change_5d:+.1f}%/5d ({sentiment.position.signal})")
    else:
        fail("情绪评分获取失败")
except Exception as e:
    fail(str(e))

# ---- Phase 4: 信号引擎 ----
print("\n[Phase 4] 信号引擎 (signal_engine.py)")
try:
    from src.signal_engine import compute_signal
    if len(df) >= 20:
        tech_result = result  # from Phase 2
        all_entries = (tech_result["entry_signals"] +
                       tech_result["wedges"] +
                       tech_result["failed_breakouts"] +
                       tech_result.get("bear_bar_longs", []) +
                       tech_result.get("support_betrayals", []) +
                       tech_result.get("climax_warnings", []))
        signal = compute_signal(
            df,
            tech_result["technical_score"],
            sentiment,
            all_entries,
            tech_result["state"],
        )
        ok(f"评分: {signal.score}/100 | 方向: {signal.direction} | "
           f"确信度: {signal.conviction} | 状态: {signal.status.value}")
        print(f"    独立信号: {signal.independent_count}个 (需≥{signal.min_independent_required})")
        print(f"    盈亏比: {signal.rr_ratio:.1f} | 入场: {signal.entry_price} | "
              f"止损: {signal.stop_loss} | 止盈: {signal.take_profit}")
        if signal.breakdown:
            print(f"    拆解: {signal.breakdown}")
    else:
        fail("数据不足，跳过信号分析")
except Exception as e:
    fail(str(e))

# ---- Phase 5: 宏观风险 ----
print("\n[Phase 5] 宏观风险 (macros.py)")
try:
    from src.macros import assess_macro_risk, calculate_position_size
    macro = assess_macro_risk()
    ok(f"风险等级: {macro.risk_level} | 评分: {macro.risk_score}/100")
    print(f"    仓位系数: {macro.position_coefficient}")
    for r in macro.reasons:
        print(f"    - {r}")
    pos = calculate_position_size(10000, 2.0, macro.position_coefficient, 3500, 3480)
    print(f"    仓位示例(RB 3500): {pos['quantity']}手, "
          f"风险{pos['risk_amount']}元, 占用{pos['capital_usage_pct']}%")
except Exception as e:
    fail(str(e))

# ---- 文件清单 ----
import os
print("\n" + "=" * 60)
print("源文件清单:")
for f in sorted(os.listdir("src")):
    if f.endswith(".py") and not f.startswith("__"):
        size = os.path.getsize(f"src/{f}")
        print(f"  src/{f} ({size:,} bytes)")

if os.path.exists("tests"):
    for f in sorted(os.listdir("tests")):
        if f.endswith(".py"):
            print(f"  tests/{f}")

print("\n" + "=" * 60)
print("状态检查完成")
print("=" * 60)

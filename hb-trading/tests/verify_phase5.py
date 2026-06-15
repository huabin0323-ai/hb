"""Phase 5 验证脚本 — 宏观风险感知（国内期货版）"""
import sys
sys.path.insert(0, ".")

import logging
logging.basicConfig(level=logging.WARNING)

from src.macros import assess_macro_risk, calculate_position_size

print("=" * 60)
print("Phase 5 验证: 宏观风险感知")
print("=" * 60)

# 1. 综合评估
print("\n1. 宏观风险评估")
result = assess_macro_risk()
print(f"   风险等级: {result.risk_level}")
print(f"   风险评分: {result.risk_score}/100")
print(f"   波动率(年化): {result.volatility}%")
print(f"   仓位系数: {result.position_coefficient}")
print(f"   风险原因:")
for r in result.reasons:
    print(f"     - {r}")

# 2. 仓位计算（螺纹钢期货，约3500元/吨）
print("\n2. 仓位计算示例（螺纹钢RB，10,000元本金）")
pos = calculate_position_size(
    capital=10000, risk_pct=2.0,
    pos_coef=result.position_coefficient,
    entry=3500, stop=3480,
)
print(f"   入场: 3500 | 止损: 3480 | 止损距离: {pos['stop_distance']}")
print(f"   手数: {pos['quantity']}")
print(f"   风险金额: {pos['risk_amount']}元")
print(f"   资金占用: {pos['capital_usage_pct']}%")

# 3. 不同风险系数对比
print("\n3. 不同风险系数对比")
for coef in [1.0, 0.5, 0.2]:
    pos = calculate_position_size(10000, 2.0, coef, 3500, 3480)
    print(f"   系数={coef}: 手数={pos['quantity']} "
          f"风险={pos['risk_amount']}元 "
          f"资金占用={pos['capital_usage_pct']}%")

# 4. 边界情况
print("\n4. 边界情况")
pos2 = calculate_position_size(10000, 2.0, 1.0, 3500, 3500)
assert pos2["quantity"] == 0
print("   [PASS] 止损=入场 -> quantity=0")

print("\n" + "=" * 60)
print("Phase 5 验证完成")
print("=" * 60)

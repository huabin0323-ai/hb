"""PA Pipeline — A股价格行为学全量扫描+深度评审

Phase 0: 大盘行情概览
Phase 1: 全市场粗筛 (5000→~200)
Phase 2: PA结构判定 (全部~200)
Phase 3: 信号扫描+决策 (每只:买入/不动, TOP5)
Phase 4: 五角色委员会深度评审
Phase 5: 次日全量回顾
"""

__version__ = "0.1.0"

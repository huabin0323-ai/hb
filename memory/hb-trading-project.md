---
name: hb-trading-project
description: 加密货币半自动交易系统项目 — 本地运行，Streamlit 面板，Binance 数据
metadata:
  type: project
---

用户正在开发 hb-trading 项目，位于 D:\hb\hb-trading。

**Why:** 用户起步资金少，想通过加密货币交易赚钱，同时了解世界局势和金融风险。基础薄弱，靠 vibe coding 开发。

**How to apply:** 所有开发围绕这个项目展开。技术栈固定为 Python + SQLite + Streamlit + ccxt。策略基于 Al Brooks 价格行为学 + 情绪复合打分。半自动交易（信号+手动确认），前期只做回测和模拟。

**关键决策：**
- 市场：加密货币（Binance），因为API免费、门槛低、7x24
- 策略：趋势跟踪 + Al Brooks 价格行为学 + 情绪复合评分
- 自动化：半自动（信号面板 + 用户手动确认买卖）
- 部署：本地 Streamlit 面板
- 回测：先模拟验证策略，通过后再考虑小资金实盘

**8阶段开发计划：** 见 D:\hb\hb-trading\ROADMAP.md
1. 行情采集 → 2. 价格行为引擎 → 3. 情绪聚合 → 4. 信号引擎 → 5. 宏观风险 → 6. 回测 → 7. 面板 → 8. 模拟交易

**当前进度（2026-06-03 暂停）：**
- ✅ 阶段1完成：行情采集模块 `src/collector.py`（Binance REST API，6时间框架，资金费率，未平仓合约，数据质量监控）
- 验证脚本：`tests/verify_phase1.py`，11项检查全部PASS
- 数据量：9000条K线（3币种×6时间框架×500根）
- ⏸️ 下一阶段：阶段2 — 价格行为引擎 `src/price_action.py`
- GitHub: https://github.com/huabin0323-ai/hb-trading 已推送

**恢复方法：** 说"继续 hb-trading 阶段2"，Claude会读 ROADMAP.md + 现有代码自动接上

**价格行为学核心：** 80%规则、H2/L2二次入场、楔形=衰竭信号、市场四阶段循环
参考文件：D:\hb\.claude\skills\price-action\SKILL.md

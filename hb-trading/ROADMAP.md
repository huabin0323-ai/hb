# hb-trading 开发路线图

## 分阶段计划

---

### 阶段 1：行情采集管道

**目标**：数据能进库，能查，轮询不断线

**文件**：`src/collector.py`

**做什么**：
- AKShare 拉取国内期货数据（新浪财经/东方财富，免费实时）
- 主品种：螺纹钢 RB，备用：甲醇 MA
- 多时间框架：5分钟线 + 日线，存入 SQLite
- Server酱微信推送通知（数据就绪 / 异常告警）
- 数据质量检查：价格异常（单根>5%）、成交量突变（3倍均值）、数据新鲜度（<24h）
- 后台轮询线程，默认30分钟间隔

**验证方式**：
```bash
python -c "
from src.collector import get_db, fill_all, check_quality, PRIMARY_SYMBOL
db = get_db()
stats = fill_all()
print(f'拉取成功: {stats}')
q = check_quality(PRIMARY_SYMBOL, '5m')
print(f'数据质量: {\"OK\" if q.healthy else \"WARN\"} | {q.total_rows}条')
"
```
**完成标准**：✅ 历史数据拉取无报错，数据新鲜度 < 24h

---

### 阶段 2：价格行为引擎

**目标**：裸K结构识别正确，输出人类可读的市场状态

**文件**：`src/price_action.py`

**做什么**：
- 识别 swing highs/lows（摆动点）
- 判定市场状态：上升趋势 / 下降趋势 / 交易区间 / 窄通道 / 宽通道
- 检测信号K线（强趋势K、Pin Bar、Inside Bar、Outside Bar）
- 检测入场信号（H1/H2/H3 序列）
- 检测楔形（3推+收敛）
- 检测失败突破（80%规则）
- Al Brooks 高级理论：#19 支撑背叛（最强盈利工具）、#23 熊棒做多、#21 高潮警告
- 区间中点计算
- 输出 0-100 技术面评分

**验证方式**：
```bash
python -c "
from src.collector import get_db, PRIMARY_SYMBOL
from src.price_action import analyze

df = get_db().get_klines(PRIMARY_SYMBOL, '5m', 200)
result = analyze(df)
state = result['state']
print(f'市场状态: {state.trend} | {state.description}')
print(f'技术评分: {result[\"technical_score\"].score}/100')
print(f'信号K线: {len(result[\"signal_bars\"])}个')
"
```
**完成标准**：✅ 拿一段明显趋势+一段震荡的数据，状态判定与实际一致

---

### 阶段 3：情绪聚合器

**目标**：输出合理的 0-100 情绪分，反映国内期货市场情绪

**文件**：`src/sentiment.py`

**做什么**：
- 基差分析（60%权重）：现货 vs 期货价差。正基差 = 现货紧张 = 偏多
- 持仓量分析（40%权重）：OI 增减反映资金流向
- 综合：基差 60% + 持仓 40% → 0-100 分数
- 兼容旧 `get_fear_greed()` 接口（返回 None）

**验证方式**：
```bash
python -c "
from src.sentiment import get_full_sentiment
s = get_full_sentiment()
print(f'综合情绪: {s.score}/100')
print(f'拆解: {s.summary}')
"
```
**完成标准**：✅ 返回合理分数，基差/持仓数据可获取

---

### 阶段 4：综合信号引擎

**目标**：技术面 + 情绪面 → 一个分数 + 确认机制，信号质量可靠

**文件**：`src/signal_engine.py`

**做什么**：
- 加权：技术面 60% + 情绪面 40%
- 三层升级（来自案例001）：
  1. 入场确认 — 信号出现后需下一根K线确认
  2. 多信号共振 — 独立信号 ≥3 才出通知
  3. 盈亏比过滤器 — R:R < 2:1 不发通知
- 输出综合评分 + 方向建议 + 确信度
- 输出各因子拆解

**验证方式**：
```bash
python -c "
from src.collector import get_db, PRIMARY_SYMBOL
from src.signal_engine import analyze_full
df = get_db().get_klines(PRIMARY_SYMBOL, '5m', 200)
signal = analyze_full(df)
print(f'评分: {signal.score}/100 | 方向: {signal.direction} | 状态: {signal.status.value}')
print(f'独立信号: {signal.independent_count}个 | 盈亏比: {signal.rr_ratio:.1f}')
"
```
**完成标准**：✅ 趋势上涨+情绪偏多时评分 > 70，趋势下跌+情绪偏空时评分 < 30

---

### 阶段 5：宏观风险感知

**目标**：识别市场风险水平，影响仓位建议

**文件**：`src/macros.py`

**做什么**：
- 波动率评估（年化，从20日日线收益）
- 日内振幅分析（5日均值）
- 持仓量异动检测
- 输出风险等级：低/中/高 + 仓位系数（1.0x / 0.8x / 0.5x）
- 仓位计算器：根据本金、风险%、系数、入场/止损价计算手数

**验证方式**：
```bash
python -c "
from src.macros import assess_macro_risk, calculate_position_size
macro = assess_macro_risk()
print(f'风险等级: {macro.risk_level} | 评分: {macro.risk_score}/100')
print(f'仓位系数: {macro.position_coefficient}')
pos = calculate_position_size(10000, 2.0, macro.position_coefficient, 3500, 3480)
print(f'仓位: {pos[\"quantity\"]}手, 风险{pos[\"risk_amount\"]}元')
"
```
**完成标准**：✅ 波动率升高时风险等级自动上调

---

### 阶段 6：回测引擎

**目标**：用历史数据验证策略，得到可量化的胜率/回撤

**文件**：`src/backtest.py`

**做什么**：
- 基于 Al Brooks 策略的滑动窗口回测（200根窗口）
- 入场确认模式（等下一根K线确认）
- 实现 case_001 策略：H2结构 + 交易区间 + 失败突破 + MTR
- 手续费：0.01% 费率，最低3元
- 输出：总收益率、胜率、最大回撤、夏普比率、盈亏比

**验证方式**：
```bash
python -c "
from src.backtest import run_backtest
result = run_backtest()
print(f'收益率: {result[\"total_return\"]:.1f}%')
print(f'胜率: {result[\"win_rate\"]:.1f}%')
print(f'最大回撤: {result[\"max_drawdown\"]:.1f}%')
print(f'夏普比率: {result[\"sharpe\"]:.2f}')
"
```
**完成标准**：✅ 回测跑通，夏普 > 0.5，回撤不超过 30%

---

### 阶段 7：Streamlit 面板

**目标**：一个浏览器页面，看懂一切，不用碰命令行

**文件**：`dashboard.py`

**做什么**：
- 实时K线图（Plotly，最近100根）
- 市场状态指示器
- 综合信号仪表盘（评分 + 因子拆解 + 入场参数）
- 情绪面板（基差 + 持仓量）
- 宏观风险等级 + 仓位建议
- 通知决策显示

**验证方式**：
```bash
streamlit run dashboard.py
# 浏览器打开，肉眼确认每个面板有数据
```
**完成标准**：✅ 所有面板正常显示数据，5分钟内无报错

---

### 阶段 8：模拟交易

**目标**：虚拟盘跑一个星期，验证信号实战价值

**文件**：`src/paper_trader.py`（待创建）

**做什么**：
- 监听实时信号，满足阈值自动记录虚拟交易
- 记录：入场价、出场价、持仓时长、盈亏
- 每晚生成当日报告

**验证方式**：跑一周 → 导出虚拟交易记录 → 算盈亏
**完成标准**：连续 1 周正收益或小亏损（-5%以内），则策略通过验证，可考虑小资金实盘

---

## 总结图

```
阶段1 ──→ 阶段2 ──→ 阶段4 ──→ 阶段6 ──→ 阶段7 ──→ 阶段8
(数据)    (技术)    (信号)    (回测)    (面板)    (模拟)
              ↘         ↗
              阶段3 ──→ 阶段5
             (情绪)    (宏观)
```

**数据源**：AKShare（新浪财经）+ SQLite  
**主品种**：螺纹钢 RB（上期所）  
**备用品种**：甲醇 MA（郑商所）  
**主时间框架**：5分钟（Al Brooks 推荐）

---

## 当前状态

| 阶段 | 状态 | 备注 |
|------|:----:|------|
| 1. 数据采集 | ✅ | AKShare + SQLite + 微信通知 |
| 2. 价格行为引擎 | ✅ | Al Brooks 全套方法论 |
| 3. 情绪聚合 | ✅ | 基差+持仓量 |
| 4. 信号引擎 | ✅ | 三层升级（确认+共振+盈亏比） |
| 5. 宏观风险 | ✅ | 波动率+振幅+OI |
| 6. 回测引擎 | ✅ | 滑动窗口回测 |
| 7. Dashboard | ✅ | Streamlit |
| 8. 模拟交易 | ✅ | paper_trader.py + A股驾驶舱 |

每一阶段完成后，下一阶段才能开始。任一阶段验证不通过，停下来修，不带着 bug 往前走。

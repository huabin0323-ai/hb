# 小红书起号：硬科技投资笔记 — 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 建立每日硬件新闻→10个名词提取→用户选择→小红书图文的完整内容生产管线

**Architecture:** Claude Code 工作流项目。核心是一条每日命令（`/daily-topic`），串联新闻扫描、名词策展、选题确认、**双代理并行产出（文案Agent + 出图Agent）**、合稿自检五个环节。配套四个内容模板 + 产业链数据库 + 内容日历追踪。图的来源分两类：知识点/产业链图必须原创生成（guizang-social-card-skill），实物图可搜索获取。

**Tech Stack:** Claude Code commands, guizang-social-card-skill (图文生成), Markdown (模板和数据), WebSearch (新闻采集)

---

## 文件结构

```
xhs-hardware-investment/
├── SKILL.md                         # 项目入口 skill
├── .claude/
│   └── commands/
│       └── daily-topic.md           # /daily-topic 每日选题命令
├── templates/
│   ├── learn-concept.md             # 学概念 模板
│   ├── industry-chain.md            # 拆产业链 模板
│   ├── event-analysis.md            # 跟事件 模板
│   └── comparison.md                # 做对比 模板
├── data/
│   ├── industry-chain-db.md         # 产业链数据库
│   ├── news-sources.md              # 新闻来源配置
│   └── content-calendar.md          # 内容日历 + 已发布追踪
└── output/                          # 生成的小红书图文存档
```

---

### Task 1: 项目脚手架

**Files:**
- Create: `D:\hb\xhs-hardware-investment\SKILL.md`
- Create: `D:\hb\xhs-hardware-investment\README.md`

- [ ] **Step 1: 创建目录结构**

```powershell
New-Item -ItemType Directory -Force -Path D:\hb\xhs-hardware-investment\.claude\commands
New-Item -ItemType Directory -Force -Path D:\hb\xhs-hardware-investment\templates
New-Item -ItemType Directory -Force -Path D:\hb\xhs-hardware-investment\data
New-Item -ItemType Directory -Force -Path D:\hb\xhs-hardware-investment\output
```

- [ ] **Step 2: 创建 SKILL.md**

```markdown
---
name: xhs-hardware-investment
description: 硬科技投资笔记 — 每日硬件新闻扫描、名词策展、小红书图文生成。覆盖：产业链拆解、技术→投资翻译、事件解读、标的对比。
version: 1.0.0
author: huabin0323-ai
---

# 硬科技投资笔记 · 小红书起号

## 每日工作流

在 Claude Code 中输入：

```
/daily-topic
```

系统自动：
1. 扫描当日硬件/半导体行业新闻
2. 提取 10 个相关名词/概念
3. 用户从中选择一个
4. 按对应模板生成小红书图文
5. 更新内容日历

## 内容类型

| 类型 | 触发场景 | 模板 |
|------|---------|------|
| 学概念 | 新技术名词、协议、工艺 | `templates/learn-concept.md` |
| 拆产业链 | 完整产业链梳理 | `templates/industry-chain.md` |
| 跟事件 | 涨价/缺货/财报/技术突破 | `templates/event-analysis.md` |
| 做对比 | 三家公司/三条路线怎么选 | `templates/comparison.md` |

## 关键规则

- 不荐股：所有标的表述为"产业链公司梳理"，不做"推荐买入"
- 不预测股价：不给目标价
- 华为信息：只说公开行业趋势，不涉及内部数据
- 引用来源：研报/招股书/公告注明出处
```

- [ ] **Step 3: 创建 README.md**

```markdown
# 硬科技投资笔记 · 小红书起号

用硬件工程师视角，做硬科技产业链投资分析。

## 定位

一个华为硬件工程师的硬科技投资笔记。两根柱子：
- **学硬件，公开学** — 高速接口、协议、芯片架构、仿真测试
- **产业链投资分析** — 技术变化→谁受益→A股谁在做

## 使用

```
/daily-topic    # 每日选题：新闻扫描 → 10个名词 → 你选 → 出内容
```

## 目录

- `templates/` — 四种内容类型的结构模板
- `data/` — 产业链数据库、新闻来源、内容日历
- `output/` — 已生成的小红书图文存档
```

- [ ] **Step 4: 提交**

```bash
git add D:\hb\xhs-hardware-investment
git commit -m "feat: scaffold xhs-hardware-investment project — SKILL.md, README, directory structure"
```

---

### Task 2: 新闻来源配置

**Files:**
- Create: `D:\hb\xhs-hardware-investment\data\news-sources.md`

- [ ] **Step 1: 创建新闻来源配置文件**

```markdown
# 硬件/半导体新闻来源

## 每日必扫（免费、中文）

| 来源 | URL | 覆盖领域 | 更新频率 |
|------|-----|---------|---------|
| 集微网 | https://www.jiwei.net | 半导体全产业链 | 每日 |
| 半导体行业观察 | https://www.semiinsights.com | 芯片设计/制造/封测 | 每日 |
| 电子工程专辑 | https://www.eet-china.com | 电子元器件/设计 | 每日 |
| IC咖啡 | https://www.ic.cafe | 半导体创投/IPO | 每日 |
| 芯智讯 | https://www.icsmart.cn | 芯片/终端 | 每日 |
| 雪球-半导体板块 | https://xueqiu.com | A股半导体讨论 | 实时 |

## 每日辅助（英文，技术深度）

| 来源 | URL | 覆盖领域 |
|------|-----|---------|
| SemiEngineering | https://semiengineering.com | 半导体工程/工艺 |
| AnandTech | https://www.anandtech.com | 芯片架构/评测 |
| ServeTheHome | https://www.servethehome.com | 服务器/数据中心硬件 |
| IEEE Spectrum | https://spectrum.ieee.org | 前沿技术 |

## 财报/公告

| 来源 | URL |
|------|-----|
| 巨潮资讯 | http://www.cninfo.com.cn |
| 科创板公告 | https://www.sse.com.cn/star |

## 扫描策略

1. **优先扫描中文源**：集微网 + 半导体行业观察 + 电子工程专辑
2. **关键词过滤**：MLCC, PCB, HBM, 光模块, SerDes, PCIe, DDR, 先进封装, CoWoS, SiC, GaN, RISC-V, Chiplet, UCIe, Retimer, DSP, EDA, 光刻胶, 硅光, CPO, LPO, 800G, 1.6T, 铜连接, 高频覆铜板, 载板, HDI
3. **事件优先**：涨价/缺货/扩产/技术突破/财报超预期 > 常规行业动态 > 政策/人事
4. **每周至少扫一次英文源**获取技术前沿
```

- [ ] **Step 2: 提交**

```bash
git add D:\hb\xhs-hardware-investment\data\news-sources.md
git commit -m "feat: add news source configuration for daily scanning"
```

---

### Task 3: 内容模板（四种类型）

**Files:**
- Create: `D:\hb\xhs-hardware-investment\templates\learn-concept.md`
- Create: `D:\hb\xhs-hardware-investment\templates\industry-chain.md`
- Create: `D:\hb\xhs-hardware-investment\templates\event-analysis.md`
- Create: `D:\hb\xhs-hardware-investment\templates\comparison.md`

- [ ] **Step 1: 创建「学概念」模板**

`D:\hb\xhs-hardware-investment\templates\learn-concept.md`:

```markdown
# 模板：学概念

## 适用场景
今天搞懂了一个技术名词/概念 → 写成别人也能看懂的一篇

## 结构

### 封面图（1张，3:4竖版）
- 核心概念名（中英文）
- 一句话解释（<15字）
- 归藏风格排版

### 正文（800-1200字）

**1. 这个[概念名]到底是干嘛的（100字）**
用大白话解释，假设读者完全不懂。
不良示范："PCIe Retimer是一种信号调理芯片，用于补偿高速信号在传输路径上的损耗"
良好示范："信号跑在PCB走线上，跟人跑马拉松一样，跑远了就累了变形了。Retimer就是中途的补给站——它把变形了的信号重新'整形'，让它精神抖擞地继续跑。"

**2. 为什么现在需要关注它（150字）**
- 是什么变化（速率/工艺/需求）让这个概念变得重要？
- 以前怎么解决的，现在为什么不够了？

**3. 技术关键点（200-300字，配图1-2张）**
- 核心原理（用图说话）
- 关键参数/指标
- 和竞品/替代方案的差异

**4. 产业链位置 + A股相关公司（200-300字，配产业链图1张）**
- 这个概念在产业链的哪个环节
- 哪些A股公司在做（梳理，不推荐）
- 各自做到了什么程度

**5. 一句话总结 + 观察点（50字）**
"总结：XXX。接下来关注：XXX。"

### 标签
#硬件 #半导体 #[具体技术名] #[产业链环节] #投资 #科技

### 参考来源
- [列出数据/信息的出处]
```

- [ ] **Step 2: 创建「拆产业链」模板**

`D:\hb\xhs-hardware-investment\templates\industry-chain.md`:

```markdown
# 模板：拆产业链

## 适用场景
系统性拆解一个产业链 → 从上游到下游，每环标出A股标的

## 结构

### 封面图（1张，3:4竖版）
- "[产业链名] 全景图"
- 副标题：从XX到XX，谁在赚什么钱
- 归藏风格排版

### 正文（1000-1500字）

**1. 这张图怎么看（100字）**
一句话说明这个产业链的输入→输出。给出全景图（第2张图）。

**2. 上游：材料/设备（200字）**
- 用了什么材料？谁供的？
- 用了什么设备？谁造的？
- 卡脖子环节在哪？

**3. 中游：制造/设计（200-300字）**
- 核心工艺是什么？
- 技术壁垒在哪？
- 谁在做，谁做得好？

**4. 下游：封装/测试/应用（200字）**
- 封装方案有哪些？
- 终端应用场景，谁是大客户？

**5. A股全链扫描（200-300字，配合产业链标注图）**
用一张标注图，在每个环节标出A股相关公司。
格式：
- 环节A → 公司1（龙头），公司2（追赶），公司3（新进入）
- 环节B → ...

**6. 几个值得关注的点（100字）**
- 这个产业链未来12个月最大的变化是什么？
- 哪个环节利润最厚？
- 哪个环节国产化率最低（=潜在空间最大）？

### 标签
#产业链 #半导体 #[具体产业链名] #[相关技术] #投资 #科技

### 参考来源
- [列出数据来源：研报/招股书/公告]
```

- [ ] **Step 3: 创建「跟事件」模板**

`D:\hb\xhs-hardware-investment\templates\event-analysis.md`:

```markdown
# 模板：跟事件

## 适用场景
涨价/缺货/扩产/新技术发布/财报超预期 → 用产业链逻辑说清谁真受益

## 结构

### 封面图（1张，3:4竖版）
- 事件关键词
- 副标题：谁真受益，谁蹭概念
- 归藏风格排版

### 正文（800-1200字）

**1. 发生了什么（100字）**
三句话讲清楚事件的客观事实。
"XX公司宣布YY技术突破/涨价/扩产计划。影响范围：ZZ。"

**2. 为什么重要（150字）**
- 这个事件改变了什么？
- 影响到产业链的哪个环节？
- 是短期扰动还是长期趋势？

**3. 产业链影响链条（200-300字，配影响链条图）**
从事件发生点，向上游/下游推导：
- 直接受益者（第一层）
- 间接受益者（第二层）
- 潜在受损者

**4. A股相关公司扫描（200-300字）**
- 真链公司（确实在供应链里）
- 概念公司（沾边但不是真受益）
- 区分标准是什么

**5. 接下来关注什么（100字）**
- 什么信号能确认/证伪这个逻辑？
- 建议观察的时间节点

### 标签
#产业链 #[事件关键词] #半导体 #投资 #科技

### 参考来源
- [事件来源链接 + 数据出处]
```

- [ ] **Step 4: 创建「做对比」模板**

`D:\hb\xhs-hardware-investment\templates\comparison.md`:

```markdown
# 模板：做对比

## 适用场景
三条技术路线/三家公司需要选 → 技术差异决定投资逻辑差异

## 结构

### 封面图（1张，3:4竖版）
- "XX vs XX vs XX：怎么选？"
- 副标题：技术路线不同，投资逻辑完全不同
- 归藏风格排版

### 正文（1000-1500字）

**1. 为什么需要选（100字）**
这三者解决的是同一个问题吗？还是解决不同场景下的同一类问题？

**2. 技术路线对比（300字，配对比表图）**
| 维度 | A | B | C |
|------|---|---|---|
| 技术原理 | | | |
| 核心优势 | | | |
| 主要劣势 | | | |
| 适用场景 | | | |
| 成熟度 | | | |
| 成本 | | | |

**3. 各自的产业链位置（200字）**
- A的上游/下游和B、C有什么不同？
- 谁的产业链更成熟？谁的还在早期？

**4. 代表性公司对比（200-300字）**
- 做A的三家公司 vs 做B的两家公司 vs 做C的一家
- 不是"谁更好"，是"各自适合什么场景"

**5. 我的判断 + 观察框架（100字）**
- 我认为哪个路线在什么条件下会胜出
- 需要跟踪哪些信号来验证/推翻这个判断

### 标签
#技术对比 #[技术名] #产业链 #半导体 #投资 #科技

### 参考来源
- [列出数据来源]
```

- [ ] **Step 5: 提交**

```bash
git add D:\hb\xhs-hardware-investment\templates
git commit -m "feat: add four content templates — learn-concept, industry-chain, event-analysis, comparison"
```

---

### Task 4: 产业链数据库（初始化）

**Files:**
- Create: `D:\hb\xhs-hardware-investment\data\industry-chain-db.md`

- [ ] **Step 1: 创建产业链数据库**

`D:\hb\xhs-hardware-investment\data\industry-chain-db.md`:

对每条产业链，自顶向下分层记录。初始化覆盖以下产业链：

```markdown
# 产业链数据库

> 用法：写内容时查对应产业链，找到相关环节和标的。持续更新。

---

## 1. HBM 产业链

### 上游：材料
| 环节 | A股标的 | 备注 |
|------|--------|------|
| 硅通孔(TSV)设备 | 中微公司 | 刻蚀设备 |
| 临时键合/解键合 | 拓荆科技 | 薄膜沉积 |
| 电镀液 | 上海新阳 | TSV填充 |
| 封装基板 | 深南电路、兴森科技 | FC-BGA载板 |

### 中游：制造
| 环节 | A股标的 | 备注 |
|------|--------|------|
| DRAM芯片 | （三星/SK海力士/美光垄断） | 国内无直接标的 |
| HBM堆叠封装 | 长电科技、通富微电 | 先进封装OSAT |
| CoWoS | 台积电垄断 | 国内无 |

### 下游：应用
| 环节 | A股标的 | 备注 |
|------|--------|------|
| AI芯片 | 寒武纪、海光信息 | GPU/NPU |
| 服务器 | 浪潮信息、中科曙光 | AI服务器 |

---

## 2. 光模块产业链

### 上游：光芯片
| 环节 | A股标的 | 备注 |
|------|--------|------|
| 激光器芯片(EML/DFB) | 源杰科技、长光华芯 | 25G/50G EML |
| 探测器芯片(PD/APD) | 三安光电 | 化合物半导体 |
| 硅光芯片 | 中际旭创(自研)、光迅科技 | 硅光集成 |

### 上游：电芯片
| 环节 | A股标的 | 备注 |
|------|--------|------|
| DSP芯片 | （Credo/博通/Marvell主导） | 国内澜起有布局 |
| CDR/Retimer | 澜起科技 | PCIe Retimer |
| 驱动芯片 | 芯原股份 | 芯片IP |

### 中游：光模块制造
| 环节 | A股标的 | 备注 |
|------|--------|------|
| 800G光模块 | 中际旭创、新易盛、天孚通信 | 全球第一梯队 |
| 1.6T光模块 | 中际旭创(在研) | 下一代 |
| 光器件 | 天孚通信、光库科技 | 光引擎/光连接 |

### 下游：数据中心/算力
| 环节 | A股标的 | 备注 |
|------|--------|------|
| AI芯片 | 寒武纪、海光信息 | 光模块大客户 |
| 交换机 | 锐捷网络、紫光股份 | 数据中心网络 |

---

## 3. 先进封装产业链

### 封装技术路线
| 路线 | 代表 | 特点 | A股标的 |
|------|------|------|--------|
| CoWoS | 台积电 | 2.5D集成，AI芯片主力 | 国内无直接标的 |
| EMIB | Intel | 嵌入式多芯片互连桥 | / |
| 混合键合(Hybrid Bonding) | 台积电/三星/Intel | 3D堆叠，下一代 | 拓荆科技(设备) |
| Fan-out | 日月光/长电 | 扇出型封装 | 长电科技、通富微电 |

### 封装环节
| 环节 | A股标的 | 备注 |
|------|--------|------|
| 封测OSAT | 长电科技、通富微电、华天科技 | 国内前三 |
| 封装设备 | 长川科技、华峰测控 | 测试分选 |
| 封装基板 | 深南电路、兴森科技、鹏鼎控股 | FC-BGA |
| EDA/IP | 华大九天、概伦电子 | 封装设计 |

---

## 4. 高频/高速PCB产业链

### 材料
| 环节 | A股标的 | 备注 |
|------|--------|------|
| 高频覆铜板 | 生益科技、联茂电子(TW) | PTFE/碳氢 |
| 高速覆铜板 | 生益科技、南亚新材 | 低损耗 |
| 铜箔 | 诺德股份、嘉元科技 | 电子铜箔 |
| 玻纤布 | 宏和科技 | 电子级玻纤 |

### PCB制造
| 环节 | A股标的 | 备注 |
|------|--------|------|
| AI服务器PCB | 深南电路、沪电股份、鹏鼎控股 | 高层数(24+) |
| IC载板 | 深南电路、兴森科技 | FC-BGA |
| HDI板 | 景旺电子、胜宏科技 | 高密度互连 |

---

## 5. SerDes/高速互连IP产业链

### IP授权
| 环节 | A股标的 | 备注 |
|------|--------|------|
| SerDes IP | 芯原股份 | 32G/56G/112G |
| PCIe IP | 芯原股份、国芯科技 | PCIe 5.0/6.0 |
| DDR IP | 芯原股份 | DDR5/LPDDR5 |
| UCIe IP | 芯原股份(在研) | Chiplet互连 |

### 芯片
| 环节 | A股标的 | 备注 |
|------|--------|------|
| Retimer | 澜起科技 | PCIe 5.0 Retimer |
| Redriver | （TI/谱瑞主导） | 国内少 |
| SerDes PHY | （博通/Credo主导） | 国内少 |

---

## 6. 铜连接产业链（GB300概念）

### 上游：材料
| 环节 | A股标的 | 备注 |
|------|--------|------|
| 铜合金线材 | 博威合金 | 高速铜缆导体 |
| 绝缘材料 | 东材科技 | PTFE/氟塑料 |

### 中游：组件
| 环节 | A股标的 | 备注 |
|------|--------|------|
| 高速背板连接器 | 立讯精密、瑞可达 | GB300概念 |
| 铜缆组件 | 景旺电子(软板) | 铜连接方案 |

### 下游：系统
| 环节 | A股标的 | 备注 |
|------|--------|------|
| AI服务器 | 工业富联、浪潮信息 | 铜连接客户 |

---

## 维护规则

- 每次写内容时，如果发现新的产业链环节或标的，补充到此文件
- 同一公司在不同产业链中出现是正常的（如深南电路在HBM、先进封装、PCB中都有出现）
- 备注栏记录关键变化（如"2026Q1进入英伟达供应链"）
```

- [ ] **Step 2: 提交**

```bash
git add D:\hb\xhs-hardware-investment\data\industry-chain-db.md
git commit -m "feat: initialize industry chain database with 6 chains — HBM, optical modules, advanced packaging, high-speed PCB, SerDes IP, copper interconnect"
```

---

### Task 5: 内容日历

**Files:**
- Create: `D:\hb\xhs-hardware-investment\data\content-calendar.md`

- [ ] **Step 1: 创建内容日历文件**

`D:\hb\xhs-hardware-investment\data\content-calendar.md`:

```markdown
# 内容日历

> 追踪每篇内容的选题、状态、发布情况

## 状态说明
- 🎯 已选题：用户确认了选题
- ✍️ 撰写中：正在生成内容
- 🎨 制图中：正在用 guizang-social-card-skill 生成图片
- ✅ 已发布：已在小红书发布
- ⏸️ 搁置：选题暂时不做

## 2026年6月

| 日期 | 选题 | 类型 | 状态 | 发布链接 | 收藏/点赞 |
|------|------|------|------|---------|----------|
| 6/16 | — | — | — | — | — |

## 选题池（待选）

| # | 选题 | 类型 | 建议时间 | 优先级 |
|---|------|------|---------|--------|
| 1 | 搞懂S参数 → SI仿真+国产EDA | 学概念 | 随时 | ⭐⭐⭐ |
| 2 | 搞懂眼图 → 高速测试 | 学概念 | 随时 | ⭐⭐⭐ |
| 3 | 搞懂PCIe Retimer → 澜起 | 学概念 | 随时 | ⭐⭐⭐ |
| 4 | HBM产业链全景 | 拆产业链 | 随时 | ⭐⭐⭐⭐⭐ |
| 5 | 光模块产业链全景 | 拆产业链 | 随时 | ⭐⭐⭐⭐⭐ |
| 6 | 先进封装产业链全景 | 拆产业链 | 随时 | ⭐⭐⭐⭐ |
| 7 | 铜连接概念真伪辨析 | 跟事件 | 热点期内 | ⭐⭐⭐⭐ |
| 8 | CPO vs LPO vs 可插拔 | 做对比 | 随时 | ⭐⭐⭐⭐ |
| 9 | AI服务器PCB三家对比 | 做对比 | 随时 | ⭐⭐⭐ |

## 发布统计

- 本月发布：0 篇
- 总计发布：0 篇
- 平均互动：—
```

- [ ] **Step 2: 提交**

```bash
git add D:\hb\xhs-hardware-investment\data\content-calendar.md
git commit -m "feat: add content calendar with tracking fields and initial topic pool"
```

---

### Task 6: 每日选题命令 `/daily-topic`

**Files:**
- Create: `D:\hb\xhs-hardware-investment\.claude\commands\daily-topic.md`

- [ ] **Step 1: 创建命令定义**

`D:\hb\xhs-hardware-investment\.claude\commands\daily-topic.md`:

```markdown
---
name: daily-topic
description: 每日硬件新闻扫描 → 10个名词策展 → 用户选择 → 生成小红书图文
---

# /daily-topic — 每日选题

## 执行流程

### 第1步：扫描当日新闻

使用 WebSearch 工具扫描当日硬件/半导体行业新闻，优先搜索：
- `半导体 今日 新闻`
- `芯片 最新 动态`
- `HBM 光模块 MLCC PCB 先进封装 行业动态`

同时访问（WebFetch）：
- 集微网 jiwei.net 首页
- 半导体行业观察 semiinsights.com 首页
- 电子工程专辑 eet-china.com

汇总当日 5-8 条最值得关注的硬件新闻。

### 第2步：提取10个名词/概念

基于当日新闻，提取 **10 个** 值得写一篇小红书图文的名词/概念。规则：
- 每个名词必须是"读者一看就好奇、但又不太懂"的
- 优先提取：新技术名词、产业链环节名、公司名（有技术差异化的）、技术路线名
- 每个名词附带：一句话解释（<20字）+ 适合用哪个内容模板
- 混合技术名词、产业链概念、事件相关名词
- 避免过泛的词（"芯片""半导体"），选具体的（"CoWoS先进封装""112G SerDes"）

**输出格式（给用户选）：**

```
今日硬件新闻速览：
[3-5条关键新闻一句话概括]

📌 今日10个选题：

1️⃣ [名词] — [一句话解释] → [模板类型]
2️⃣ [名词] — [一句话解释] → [模板类型]
...
🔟 [名词] — [一句话解释] → [模板类型]

选一个数字？
```

### 第3步：用户选择

等待用户输入数字（1-10）。

### 第4步：双代理并行 — 文案 + 出图

用户选择后，**同时启动两个子代理**（Agent tool, run_in_background）：

#### 子代理A：📝 文案 Agent

**输入：** 选题名词 + 对应模板 + 产业链数据库查询结果
**任务：** 按模板结构生成小红书正文

写作要求：
- **钩子前置**：前30字必须有钩子——一个反常识的事实、一个数字、一个问题。让读者在瀑布流里停下来
  不良："今天我们来聊聊HBM。HBM是一种高带宽存储器..."
  良好："GPU算力10年翻了1000倍，但显存带宽只翻了30倍。卡住AI芯片脖子的不是光刻机——是内存带宽。"
- **技术翻译**：每个工程术语都配大白话解释。读者是散户，不是EE
- **段落短**：手机上每段不超过3行。多分段，多用短句
- **结尾引导互动**：提出一个问题或一个观察点，引导评论
- **不荐股**：标的是"梳理"，不是"推荐"
- **标签策略**：标签覆盖搜索关键词（具体技术名+产业链名+投资+科技），不用泛标签

**输出：** 
- 小红书正文（800-1200字）
- 正文中标注需要配图的位置 `[图1: 描述]`, `[图2: 描述]`

#### 子代理B：🎨 出图 Agent

**输入：** 选题名词 + 选题类型 + 文案Agent输出的配图位置描述
**任务：** 为图文准备所有图片

**图片来源策略：**

| 图片类型 | 来源 | 说明 |
|---------|------|------|
| 封面图 | 🎨 **必须原创生成** | guizang-social-card-skill，归藏风格。核心概念+钩子标题。必须让人想点 |
| 产业链图解 | 🎨 **必须原创生成** | guizang-social-card-skill，信息图风格。标注每个环节+对应公司 |
| 技术原理图 | 🎨 **必须原创生成** | guizang-social-card-skill，图解风格。抽象概念可视化 |
| 产品/设备/芯片实物图 | 🔍 WebSearch 搜索 | 真实产品照片（芯片、电路板、设备、工厂） |
| 公司 logo/园区 | 🔍 WebSearch 搜索 | 如有需要 |
| K线/行情截图 | 🔍 如有需要 | 不主要依赖这个 |

**封面图规则（最重要）：**
- 3:4 竖版，归藏/Swiss Style
- 必须有钩子元素：一个大数字、一个对比、或一个问句
- 不良封面："HBM产业链全景"（太像教科书，不会有人点）
- 良好封面："GPU涨1000倍，内存只涨30倍 → HBM：解开AI芯片的内存死结"
- 字体：大标题 > 小副标题 > 标签。层级分明
- 色彩：克制，2-3色。归藏风格不是彩虹色

**产业链/技术图解规则：**
- 信息图风格，干净清晰
- 产业链图：纵向或横向流程，每环标注（环节名 + A股公司名）
- 技术图解：抽象概念可视化（信号流、堆叠结构、工艺步骤）
- 配色统一，和封面同一套色板
- 不要堆满文字——留白，让读者愿意细看

**搜图规则：**
- 搜索关键词用英文（结果质量更高）：如 "HBM chip package photo", "advanced packaging CoWoS diagram"
- 优先用高质量来源：anandtech, servethehome, semiengineering, wikichip
- 避免模糊/水印过多的图

**输出：**
- 所有图片文件路径列表
- 每张图的用途说明（封面/图1/图2...）

### 第5步：合稿 + 自检

等两个子代理都完成后：
1. 将文案和图片组装成完整的小红书图文
2. 按内容质量检查清单逐项自检
3. 如有问题，修正后重新合稿

### 第6步：更新日历

更新 `data/content-calendar.md`：
- 记录选题、类型、状态为"✅ 已发布"
- 补充发布统计数据

### 第7步：输出最终结果

展示完整的图文内容 + 图片文件路径，用户可直接发布到小红书。

---

## 内容质量检查清单（生成后自检）

**文案自检：**
- [ ] 前30字有钩子？（反常识事实/数字/问题）
- [ ] 技术解释有没有错误？（概念准确）
- [ ] 每个术语都有大白话翻译？（读者是散户）
- [ ] 段落短？（手机端每段≤3行）
- [ ] 产业链映射对不对？（标的和它做的业务匹配）
- [ ] 有没有"推荐买入""肯定涨"类表述？（合规）
- [ ] 有没有华为内部信息？（保密）
- [ ] 正文800-1200字？（长度适中）
- [ ] 标签覆盖了搜索关键词？
- [ ] 结尾有互动引导？（提问/观察点）

**图片自检：**
- [ ] 封面有钩子？（不是教科书标题，是让人想点的）
- [ ] 产业链图/技术图解是原创生成的？（不是截图/搜的）
- [ ] 搜来的实物图清晰无水印？
- [ ] 所有图片统一色板？（封面+内容图一套视觉）
- [ ] 图片够不够吸睛？（小红书上图不好看=没人点）
```

- [ ] **Step 2: 提交**

```bash
git add D:\hb\xhs-hardware-investment\.claude\commands\daily-topic.md
git commit -m "feat: add /daily-topic command — daily news scan → 10 terms → user selects → content generation pipeline"
```

---

### Task 7: 端到端验证

**Files:**
- Read: `D:\hb\xhs-hardware-investment\data\news-sources.md`
- Read: `D:\hb\xhs-hardware-investment\templates\*`
- Read: `D:\hb\xhs-hardware-investment\data\industry-chain-db.md`

- [ ] **Step 1: 验证所有文件存在且内容完整**

```powershell
Get-ChildItem -Recurse D:\hb\xhs-hardware-investment | Where-Object { -not $_.PSIsContainer } | ForEach-Object { Write-Host "$($_.FullName) ($($_.Length) bytes)" }
```

预期：8个文件，每个 > 500 bytes。

- [ ] **Step 2: 运行一次模拟选题流程**

在 Claude Code 中输入 `/daily-topic`，验证：
1. 新闻扫描输出 5-8 条新闻摘要
2. 10 个名词选项清晰可辨
3. 选择一个后，能按对应模板生成完整内容
4. 检查生成内容合规性（无荐股/无内部信息/有来源标注）

- [ ] **Step 3: 检查产业链数据库覆盖**

验证：选题时查 `industry-chain-db.md` 能匹配到对应产业链数据。如覆盖不全，补充对应条目。

- [ ] **Step 4: 最终提交**

```bash
git add -A
git commit -m "feat: complete xhs-hardware-investment daily content pipeline — all files verified"
```

---

## 完成标准

全部7个任务完成后，应满足：

1. `/daily-topic` 命令可正常执行，完整走通新闻→名词→选题→内容→图片→日历全流程
2. 四个内容模板覆盖四种内容类型
3. 产业链数据库至少覆盖6条核心产业链
4. 内容日历可追踪每篇内容状态
5. 所有生成内容通过合规检查（不荐股/不泄露/有来源）

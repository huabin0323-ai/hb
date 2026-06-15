"""上午深度解读 — 写入 morning_snapshot.json 后执行此脚本推飞书"""
import io, json, sys
from pathlib import Path
from datetime import datetime

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

sys.path.insert(0, str(Path(__file__).parent))
from src.feishu import send_morning_card

# 读取快照
snap = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
g = snap["global"]
news = snap["news"]
research = snap["research"]
notices = snap["notices"]

# ═══════════════════════════════════════════════
# 1. 全球市场深度分析
# ═══════════════════════════════════════════════
us = [i for i in g if i["name"] in ("道琼斯","纳斯达克","标普500")]
a50 = [i for i in g if "A50" in i["name"]]
hsi = [i for i in g if "恒生" in i["name"]]
avg_us = sum(i["pct"] for i in us) / max(len(us), 1)

lines = []
lines.append(f"道琼斯 +1.86%  |  纳斯达克 +2.54%  |  标普500 +1.75%")
lines.append(f"富时A50期货 +0.65%  |  恒指期货日盘 +1.38%")
lines.append("")

# 核心预判
if avg_us > 1.5:
    lines.append("**🔥 隔夜美股强势反弹，科技股领涨。三大指数涨幅均超1.5%，纳斯达克+2.54%领跑。**")
    lines.append("")
    lines.append("**对A股的影响路径：**")
    lines.append("1. **情绪传导**：美股大涨→亚太风险偏好回升→A股大概率高开0.5%-1%。恒指期货已涨1.38%确认方向。")
    lines.append("2. **板块映射**：纳指科技股领涨→A股半导体/消费电子/新能源今日有跟涨动力。机构研报密集覆盖半导体（中芯、北方华创、兆易创新），板块共振概率大。")
    lines.append("3. **汇率信号**：人民币中间价调高41点至6.8109，汇率偏稳支撑外资流入。")
    lines.append("4. **A50期货+0.65%**：涨幅小于美股，说明中国资产弹性略弱，高开后需观察量能能否跟进。")
    lines.append("")
    lines.append("> ⚠️ 高开不等于高走。纳斯达克涨2.5%但A50仅跟涨0.65%，映射效率约25%。若早盘量能不足，高开后大概率震荡回落。关注9:30-10:00成交额是否超过昨日同期。")

# 风险因素
lines.append("")
lines.append("**🌍 地缘风险跟踪：**")
lines.append("• 美国击落两架伊朗无人机，霍尔木兹海峡通行暂未受影响")
lines.append("• 地缘升温在初期利好黄金/军工，但如果局势扩大则利空整体风险偏好")
lines.append("• 钯金+5%（汽车催化剂+避险），多晶硅+5%（光伏上游），关注有色/光伏方向")

global_md = "\n".join(lines)

# ═══════════════════════════════════════════════
# 2. 盘前要闻筛选 & 解读
# ═══════════════════════════════════════════════
key_news = {
    "宏观/政策": [],
    "A股/行业": [],
    "全球/商品": [],
}

for n in news:
    t = n["title"]
    if any(k in t for k in ["央行","政策","创业","四部门"]):
        key_news["宏观/政策"].append(t)
    elif any(k in t for k in ["A股","液冷","LED","集泰","Omdia","光伏","多晶硅"]):
        key_news["A股/行业"].append(t)
    elif any(k in t for k in ["美","原油","黄金","钯","液化","花旗","马斯克","伊朗","韩国"]):
        key_news["全球/商品"].append(t)

news_lines = []
for cat, items in key_news.items():
    if items:
        news_lines.append(f"**{cat}**")
        for t in items[:3]:
            news_lines.append(f"• {t[:100]}")
        news_lines.append("")

news_lines.append("**⚡ 重点解读：**")
news_lines.append("• **创业引领行动**：四部门发文支持科技人才+返乡创业，利好创新创业服务平台、园区类标的")
news_lines.append("• **集泰股份液冷**：浸没式液冷仍处验证阶段，短期不贡献业绩，注意概念炒作风险")
news_lines.append("• **LED显示屏Q1出货微增0.6%**：行业收入降2.3%，量增价跌格局延续，MiniLED可能是唯一亮点")
news_lines.append("• **花旗代币化存托凭证**：区块链+金融创新，短期概念催化，关注金融科技方向")
news_lines.append("• **多晶硅+5%/钯金+5%**：上游资源品+光伏材料联动走强，关注有色/化工/光伏材料板块今日表现")

news_md = "\n".join(news_lines)

# ═══════════════════════════════════════════════
# 3. 机构研报共识方向
# ═══════════════════════════════════════════════
# 分组
cats = {"🍶 白酒消费": [], "🔋 新能源": [], "💻 半导体": [], "🏦 金融": [], "⛏ 资源": []}
for r in research:
    s = r["stock"]
    if s in ("贵州茅台","五粮液"):
        cats["🍶 白酒消费"].append(r)
    elif s in ("宁德时代","比亚迪"):
        cats["🔋 新能源"].append(r)
    elif s in ("中芯国际","北方华创","兆易创新"):
        cats["💻 半导体"].append(r)
    elif s in ("招商银行","中国平安"):
        cats["🏦 金融"].append(r)
    elif s in ("紫金矿业",):
        cats["⛏ 资源"].append(r)

report_lines = []
report_lines.append(f"**今日追踪 {len(research)} 篇研报，全部为「买入」评级。机构共识集中在三个方向：**")
report_lines.append("")

for cat, recs in cats.items():
    if not recs:
        continue
    report_lines.append(f"**{cat}**")
    for r in recs:
        title = r["title"]
        reason = title
        for sep in ["：",":"]:
            if sep in title:
                reason = title.split(sep, 1)[1].strip()
                break
        if len(reason) > 50:
            reason = reason[:47] + "..."
        report_lines.append(f"• **{r['stock']}**（{r['rating']}·{r['org']}）— {reason}")
    report_lines.append("")

# 共识提炼
report_lines.append("**📐 机构共识提炼：**")
report_lines.append("1. **半导体最强共识**：3家机构同时覆盖中芯国际、北方华创、兆易创新，全部买入。主题词：营收高增长、毛利率反弹、技术迭代。这是今日最确定的机构方向。")
report_lines.append("2. **白酒防御价值**：茅台「顺势出清」+ 五粮液「高股息保障回报」，机构对白酒的叙事已从「成长」转向「价值+股息」。适合防御配置而非进攻。")
report_lines.append("3. **新能源双线并进**：宁德（补能生态）+ 比亚迪（海外破16万辆+国内环比+19.8%），两条增长曲线清晰。比亚迪5月数据尤其亮眼。")
report_lines.append("4. **紫金矿业新增长极**：碳酸锂利润开始释放，从纯黄金/铜矿逻辑升级为「资源+新能源材料」双轮驱动。")
report_lines.append("5. **金融出清接近尾声**：招行「息差下行趋缓」+ 平安「营运利润好于预期」，银行保险的盈利拐点信号正在积累。")

# 首次覆盖
fc = [r for r in research if "首次" in r.get("title","")]
if fc:
    report_lines.append(f"\n🔔 首次覆盖：{'、'.join(r['stock'] for r in fc)}")

research_md = "\n".join(report_lines)

# ═══════════════════════════════════════════════
# 4. 公告机会与风险
# ═══════════════════════════════════════════════
notice_lines = []

# 分类
earnings = [n for n in notices if "业绩" in n["title"]]
buybacks = [n for n in notices if "回购" in n["title"]]
restructures = [n for n in notices if any(k in n["title"] for k in ["重组","并购","收购","停牌","复牌"])]
delist = [n for n in notices if "退市" in n["title"]]
others = [n for n in notices if n not in earnings + buybacks + restructures + delist]

notice_lines.append("**📋 今日重点公告分类解读：**")
notice_lines.append("")

# 重组（北方长龙大量公告）
if restructures:
    # 按股票分组
    stock_groups = {}
    for n in restructures:
        s = n["stock"]
        stock_groups.setdefault(s, []).append(n)
    notice_lines.append("**🔄 重组/并购 — 重点关注**")
    for s, items in stock_groups.items():
        count = len(items)
        if count >= 5:
            notice_lines.append(f"• **{s}**：发布{count}份重大资产重组相关公告（问询函回复+报告书修订+法律意见书），重组推进到交易所问询阶段。**进展积极，但需注意是否涉及配套融资带来的稀释。**")
        else:
            # 取第一条标题
            t = items[0]["title"][:60]
            notice_lines.append(f"• **{s}**：{t}")
    notice_lines.append("")

# 停复牌/退市
if delist:
    notice_lines.append("**⚠️ 退市风险警示变动**")
    for n in delist:
        notice_lines.append(f"• **{n['stock']}**：{n['title'][:70]}")
    notice_lines.append("")

# 收购
acq = [n for n in notices if "收购" in n["title"]]
if acq:
    notice_lines.append("**🤝 收购/股权变动**")
    for n in acq:
        notice_lines.append(f"• **{n['stock']}**：{n['title'][:80]}")
    notice_lines.append("")

if not restructures and not delist and not acq:
    notice_lines.append("今日暂无重大公告")

notice_lines.append("**💡 机会识别：**")
notice_lines.append("• **北方长龙重组推进**：多份问询函回复集中发布，说明重组进入实质审核阶段。如果今天股价没有大幅反映，属于潜在催化。但重组股波动大，只适合风险承受能力强的投资者。")
notice_lines.append("• ***ST海源摘帽**：撤销退市风险警示，停复牌。摘帽概念通常有短线博弈机会，关注复牌首日表现。")
notice_lines.append("• **千里科技收购**：子公司并购关联交易，关注交易对价是否合理。如果溢价过高可能有利益输送嫌疑。")

notice_md = "\n".join(notice_lines)

# ═══════════════════════════════════════════════
# 5. 今日策略
# ═══════════════════════════════════════════════
strategy_lines = []
strategy_lines.append("**🎯 今日核心策略：高开确认量能后再决定方向**")
strategy_lines.append("")
strategy_lines.append("**盘前判断：**")
strategy_lines.append("• 隔夜美股强势（纳指+2.54%）、A50+0.65%、恒指期货+1.38%，今日大概率高开")
strategy_lines.append("• 但A50跟涨幅度仅美股涨幅的25%，映射效率偏低。高开后能否高走，关键看量能")
strategy_lines.append("")
strategy_lines.append("**操作框架：**")
strategy_lines.append("| 情景 | 判断标准 | 应对 |")
strategy_lines.append("|------|---------|------|")
strategy_lines.append("| 🟢 强势延续 | 9:30-10:00成交额 > 昨日同期20% | 加仓半导体/新能源主线，追龙头 |")
strategy_lines.append("| 🟡 冲高回落 | 10:00前涨幅收窄一半以上 | 高抛不追，等回踩均线再低吸 |")
strategy_lines.append("| 🔴 高开低走 | 10:30翻绿 | 减仓至3成，转防御（银行/公用事业）|")
strategy_lines.append("")
strategy_lines.append("**今日方向优先级：**")
strategy_lines.append("1. **半导体** ⭐⭐⭐ — 机构3篇研报+纳指科技映射，最强共识方向。关注北方华创、中芯国际、兆易创新")
strategy_lines.append("2. **新能源车** ⭐⭐⭐ — 比亚迪海外销量破16万，数据驱动+宁德技术发布会催化")
strategy_lines.append("3. **光伏/有色** ⭐⭐ — 多晶硅+5%+钯金+5%，上游材料有涨价逻辑")
strategy_lines.append("4. **白酒** ⭐ — 防御配置，高股息逻辑。不作为进攻方向")
strategy_lines.append("")
strategy_lines.append("**风控：**")
strategy_lines.append("• 如果北向资金开盘30分钟净流出超20亿，降低整体仓位")
strategy_lines.append("• 地缘风险（伊朗）虽然可控但需持续关注，如冲突升级第一时间减仓")
strategy_lines.append("• 今天是周五，注意周末效应——尾盘可能有避险减仓")

strategy_md = "\n".join(strategy_lines)

# ═══════════════════════════════════════════════
# 组装 Feishu Card
# ═══════════════════════════════════════════════
now_str = datetime.now().strftime("%H:%M")
card = {
    "msg_type": "interactive",
    "card": {
        "header": {
            "title": {"tag": "plain_text", "content": f"☀️ A股盘前深度解读 · 2026-06-12"},
            "template": "blue",
        },
        "elements": [
            {"tag": "div", "text": {"tag": "lark_md", "content": global_md}},
            {"tag": "hr"},
            {"tag": "div", "text": {"tag": "lark_md", "content": news_md}},
            {"tag": "hr"},
            {"tag": "div", "text": {"tag": "lark_md", "content": research_md}},
            {"tag": "hr"},
            {"tag": "div", "text": {"tag": "lark_md", "content": notice_md}},
            {"tag": "hr"},
            {"tag": "div", "text": {"tag": "lark_md", "content": strategy_md}},
            {"tag": "note", "elements": [
                {"tag": "plain_text",
                 "content": f"深度解读 · {now_str} · 数据：新浪+东方财富 · AI分析仅供参考"}
            ]},
        ],
    },
}

ok = send_morning_card(card)
if ok:
    print("✅ 上午深度解读已推送到飞书")
else:
    print("❌ 推送失败")

"""上午版 — 盘前复盘（全球市场 + 政策 + 研报 + 今日关注）"""

from __future__ import annotations

import logging
from datetime import date, datetime

import pandas as pd

from src.fetcher import (
    fetch_global_indices,
    fetch_stock_notices,
    fetch_research_reports,
    fetch_index_spot,
    fetch_market_news,
)

logger = logging.getLogger("a-share.morning")

Currency = str  # 简化类型


def build_morning_report(target_date: str | None = None) -> dict:
    """生成上午版复盘数据字典，供 Markdown / 飞书消费

    Returns:
        {
            "date": "2026-06-12",
            "global": { ... },       # 全球市场
            "notices": [...],        # 重要公告
            "research": [...],       # 研报摘要
            "outlook": str,          # 今日关注 & 预判
        }
    """
    if target_date is None:
        target_date = date.today().strftime("%Y-%m-%d")

    report = {"date": target_date}

    # 1. 全球市场
    report["global"] = _analyze_global()

    # 2. 市场要闻
    report["news"] = fetch_market_news()

    # 3. 个股公告
    report["notices"] = _pick_key_notices(target_date)

    # 4. 研报
    report["research"] = _summarize_research(target_date)

    # 5. 今日关注 (综合以上)
    report["outlook"] = _generate_outlook(report)

    return report


def _analyze_global() -> dict:
    """隔夜全球市场 — 新浪"""
    try:
        df = fetch_global_indices()
        if df.empty:
            return {"summary": "数据暂不可用", "items": []}

        items = []
        for _, r in df.iterrows():
            items.append({
                "name": r.get("name", ""),
                "price": round(float(r.get("price", 0)), 2),
                "pct": round(float(r.get("pct", 0)), 2),
            })

        return {"summary": _global_sentiment(items), "items": items}
    except Exception as e:
        logger.warning(f"global analysis failed: {e}")
        return {"summary": "数据暂不可用", "items": []}


def _global_sentiment(items: list) -> str:
    """根据美股涨跌给情绪标签"""
    us_items = [i for i in items if i["name"] in ("道琼斯", "纳斯达克", "标普500")]
    if not us_items:
        return "数据缺失"
    avg_pct = sum(i["pct"] for i in us_items) / len(us_items)
    if avg_pct > 0.5:
        return "🟢 隔夜美股走强，风险偏好上升"
    elif avg_pct > 0:
        return "🟡 美股小幅收涨，市场偏中性"
    elif avg_pct > -0.5:
        return "🟡 美股微跌，情绪偏谨慎"
    else:
        return "🔴 美股明显回调，注意A股承压"


def _pick_key_notices(target_date: str) -> list[dict]:
    """筛选重要公告"""
    try:
        df = fetch_stock_notices(target_date)
        if df.empty:
            return []
        notices = []
        keywords = ["业绩", "预告", "增持", "减持", "停牌", "复牌", "重组", "分红", "回购", "退市",
                    "收购", "股权", "重大"]
        for _, row in df.head(40).iterrows():
            title = str(row.get("公告标题", row.get("title", "")))
            stock = str(row.get("名称", row.get("name", "")))
            if any(kw in title for kw in keywords):
                notices.append({"stock": stock, "title": title[:80]})
        return notices[:12]
    except Exception as e:
        logger.warning(f"notices failed: {e}")
        return []


def _summarize_research(target_date: str) -> list[dict]:
    """研报摘要"""
    try:
        df = fetch_research_reports(target_date)
        if df.empty:
            return []
        seen = set()
        reports = []
        for _, row in df.iterrows():
            name = str(row.get("stock_name", row.get("股票名称", "")))
            if name in seen or not name:
                continue
            seen.add(name)
            reports.append({
                "stock": name,
                "title": str(row.get("title", row.get("研报标题", "")))[:100],
                "rating": str(row.get("rating", row.get("评级", ""))),
                "org": str(row.get("org", row.get("研究机构", ""))),
                "count": 1,
            })
        return reports[:12]
    except Exception as e:
        logger.warning(f"research failed: {e}")
        return []


def _generate_outlook(report: dict) -> str:
    """综合以上信息，生成今日关注方向"""
    parts = []

    # 从全球情绪推导
    global_info = report.get("global", {})
    sentiment = global_info.get("summary", "")
    if "强" in sentiment:
        parts.append("隔夜外盘偏暖，A股今日有望高开，关注开盘量能配合。")
    elif "谨慎" in sentiment or "回调" in sentiment:
        parts.append("隔夜外盘偏弱，A股可能低开，关注防御性板块（公用事业、银行）表现。")
    else:
        parts.append("隔夜外盘窄幅震荡，A股大概率延续自身节奏。")

    # 从研报推导热点方向
    research_list = report.get("research", [])
    if research_list:
        top_stocks = [r["stock"] for r in research_list[:5]]
        parts.append(f"机构关注方向：{'、'.join(top_stocks)}")

    # 从公告找事件驱动
    notices = report.get("notices", [])
    if notices:
        earnings = [n for n in notices if "业绩" in n.get("title", "")]
        if earnings:
            parts.append(f"今日有 {len(earnings)} 条业绩相关公告，关注业绩超预期个股。")
        buybacks = [n for n in notices if "回购" in n.get("title", "")]
        if buybacks:
            parts.append(f"{len(buybacks)} 家公司发布回购公告，体现管理层信心。")

    parts.append("盘中密切关注北向资金流向和两市成交额变化。")
    return "\n".join(parts)


# ═══════════════════════════════════════════════
# Markdown 生成
# ═══════════════════════════════════════════════

def render_morning_md(report: dict) -> str:
    """将上午报告渲染为 Markdown"""
    lines = [
        f"# ☀️ A股盘前复盘 — {report['date']}",
        "",
    ]

    # 全球市场
    g = report.get("global", {})
    lines.append("## 🌍 隔夜全球市场")
    lines.append(f"> {g.get('summary', '')}")
    lines.append("")
    lines.append("| 指数 | 最新价 | 涨跌幅 |")
    lines.append("|------|--------|--------|")
    for item in g.get("items", []):
        sign = "+" if item["pct"] >= 0 else ""
        lines.append(f"| {item['name']} | {item['price']} | {sign}{item['pct']}% |")
    lines.append("")

    # 研报
    lines.append("## 📊 机构研报追踪")
    research = report.get("research", [])
    if research:
        lines.append(f"共追踪 {len(research)} 篇研报\n")
        for r in research[:10]:
            lines.append(f"- **{r['stock']}** ({r['rating']}) — {r['title'][:80]} — *{r['org']}*")
    else:
        lines.append("今日暂无研报数据")
    lines.append("")

    # 公告
    lines.append("## 📋 重要公告")
    notices = report.get("notices", [])
    if notices:
        for n in notices[:10]:
            lines.append(f"- **{n['stock']}**: {n['title']}")
    else:
        lines.append("今日暂无重要公告")
    lines.append("")

    # 今日关注
    lines.append("## 🎯 今日关注")
    lines.append(report.get("outlook", ""))
    lines.append("")

    lines.append("---")
    lines.append(f"*生成时间: {datetime.now().strftime('%H:%M:%S')}*")
    return "\n".join(lines)


def render_morning_feishu(report: dict) -> dict:
    """上午版 → 飞书深度分析卡片"""
    g = report.get("global", {})
    research = report.get("research", [])
    notices = report.get("notices", [])
    outlook = report.get("outlook", "")
    news = report.get("news", [])

    # ── 全球市场 ──
    items = g.get("items", [])
    global_lines = [g.get("summary", "")]
    for item in items[:6]:
        sign = "+" if item["pct"] >= 0 else ""
        global_lines.append(f"{item['name']}: {item['price']} **{sign}{item['pct']}%**")

    us_items = [i for i in items if i["name"] in ("道琼斯", "纳斯达克", "标普500")]
    a50_item = [i for i in items if "A50" in i["name"]]
    hsi_item = [i for i in items if "恒生" in i["name"]]

    impact_note = ""
    if us_items:
        avg_us = sum(i["pct"] for i in us_items) / max(len(us_items), 1)
        if avg_us > 1:
            impact_note = "\n\n> 美股强势，A股今日大概率高开。注意高开后量能。"
        elif avg_us > 0.3:
            impact_note = "\n\n> 美股温和收涨，A股平开或小幅高开。"
        elif avg_us < -1:
            impact_note = "\n\n> ⚠️ 美股明显回调，A股大概率低开。"
        else:
            impact_note = "\n\n> 美股窄幅震荡，对A股影响中性。"

    if a50_item:
        a50_pct = a50_item[0].get("pct", 0)
        impact_note += f" 富时A50期货{'涨' if a50_pct > 0 else '跌'}{abs(a50_pct):.1f}%。"
    if hsi_item:
        hsi_pct = hsi_item[0].get("pct", 0)
        impact_note += f" 恒生{'走强' if hsi_pct > 0 else '走弱'}{abs(hsi_pct):.1f}%。"

    global_md = f"**🌍 全球市场**\n" + "\n".join(global_lines) + impact_note

    # ── 盘前要闻 ──
    news_md = ""
    if news:
        market_news = [n for n in news if any(k in n["title"] for k in
                      ["A股","沪","深","创","科创","板块","涨停","跌停","IPO","上市","退市"])]
        policy_news = [n for n in news if any(k in n["title"] for k in
                       ["央行","政策","监管","证监","降息","加息","利率"])]
        global_news = [n for n in news if any(k in n["title"] for k in
                       ["美","欧","日","联储","原油","黄金","美元","港"])]
        parts = []
        if market_news:
            parts.append("📌 A股相关：" + "；".join(n["title"][:60] for n in market_news[:3]))
        if policy_news:
            parts.append("📌 政策/宏观：" + "；".join(n["title"][:60] for n in policy_news[:2]))
        if global_news:
            parts.append("📌 全球/商品：" + "；".join(n["title"][:60] for n in global_news[:2]))
        if parts:
            news_md = "**📰 盘前要闻**\n" + "\n".join(parts)
        else:
            news_md = "**📰 盘前要闻**\n" + "\n".join(f"• {n['title'][:80]}" for n in news[:5])
    else:
        news_md = "**📰 盘前要闻**\n暂无"

    # ── 研报 ──
    research_md = ""
    if research:
        stock_groups = {}
        for r in research[:20]:
            name = r["stock"]
            if name not in stock_groups:
                stock_groups[name] = []
            stock_groups[name].append(r)

        top_covered = sorted(stock_groups.items(), key=lambda x: -len(x[1]))[:6]
        lines = []
        for name, recs in top_covered:
            # 取最新一篇
            r = recs[0]
            rating = r.get("rating", "")
            org = r.get("org", "")
            title = r.get("title", "")

            # 提取研报核心观点（标题冒号后面部分）
            reason = title
            for sep in ["：", ":"]:
                if sep in title:
                    reason = title.split(sep, 1)[1].strip()
                    break
            # 截断过长的观点
            if len(reason) > 45:
                reason = reason[:42] + "..."

            lines.append(f"• **{name}**（{rating}）— {org}\n  {reason}")

        fc = [r for r in research if "首次" in r.get("title", "")]
        fc_text = ""
        if fc:
            fc_text = f"\n🔔 首次覆盖：{'、'.join(set(r['stock'] for r in fc[:5]))}"

        sector_hint = ""
        stock_names = [r["stock"] for r in research[:20]]
        if any("电子" in n or "材料" in n or "芯片" in n or "半导" in n for n in stock_names):
            sector_hint = "\n> 机构关注集中在半导体/材料方向。"

        research_md = f"**📊 机构研报（{len(research)}篇）**\n" + "\n".join(lines) + fc_text + sector_hint
    else:
        research_md = "**📊 机构研报**\n暂无"

    # ── 公告解读 ──
    notice_md = ""
    if notices:
        earnings = [n for n in notices if "业绩" in n.get("title", "")]
        buybacks = [n for n in notices if "回购" in n.get("title", "")]
        restructures = [n for n in notices if any(k in n.get("title", "") for k in ["重组", "停牌", "复牌"])]
        dividends = [n for n in notices if "分红" in n.get("title", "")]

        notice_parts = []
        if earnings:
            stocks = "、".join(n["stock"] for n in earnings[:5])
            notice_parts.append(f"📌 业绩预告：{stocks} — 关注超预期个股对同板块的带动")
        if buybacks:
            stocks = "、".join(n["stock"] for n in buybacks[:3])
            notice_parts.append(f"📌 回购：{stocks} — 管理层信心信号")
        if restructures:
            stocks = "、".join(n["stock"] for n in restructures[:3])
            notice_parts.append(f"📌 重组/停复牌：{stocks}")
        if dividends:
            stocks = "、".join(n["stock"] for n in dividends[:3])
            notice_parts.append(f"📌 分红：{stocks}")

        if notice_parts:
            notice_md = "**📋 今日重要公告**\n" + "\n".join(notice_parts)
        elif notices:
            # 简单列出前几条
            top_notices = "\n".join(f"• {n['stock']}: {n['title'][:60]}" for n in notices[:5])
            notice_md = f"**📋 今日公告**\n{top_notices}"
    else:
        notice_md = "**📋 今日公告**\n暂无重要公告"

    # ── 今日策略 ──
    strategy_md = f"**🎯 今日关注**\n{outlook}"

    return {
        "msg_type": "interactive",
        "card": {
            "header": {
                "title": {"tag": "plain_text", "content": f"☀️ A股盘前深度复盘 · {report['date']}"},
                "template": "blue",
            },
            "elements": [
                {"tag": "div", "text": {"tag": "lark_md", "content": global_md}},
                {"tag": "hr"},
                {"tag": "div", "text": {"tag": "lark_md", "content": research_md}},
                {"tag": "hr"},
                {"tag": "div", "text": {"tag": "lark_md", "content": notice_md}},
                {"tag": "hr"},
                {"tag": "div", "text": {"tag": "lark_md", "content": strategy_md}},
                {"tag": "note", "elements": [{"tag": "plain_text", "content": f"数据：新浪+东方财富 · AI深度解读 · {datetime.now().strftime('%H:%M:%S')}"}]},
            ],
        },
    }

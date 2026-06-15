"""下午版 — 收盘深度复盘（涨停解读引擎 + 龙虎榜 + 明日预判）"""

from __future__ import annotations

import logging
from collections import defaultdict
from datetime import date, datetime

import pandas as pd

from config import (
    ZT_MIN_BOARDS_FOR_TIER,
    SECTOR_STRONG_THRESHOLD,
    SECTOR_TOP_N,
    SECTOR_BOTTOM_N,
)

from src.fetcher import (
    fetch_index_spot,
    fetch_market_stats,
    fetch_sector_spot,
    fetch_north_flow,
    fetch_limit_up_pool,
    fetch_limit_down_pool,
    fetch_dragon_tiger,
    fetch_market_news,
)

logger = logging.getLogger("a-share.afternoon")


def build_afternoon_report(target_date: str | None = None) -> dict:
    """生成下午版复盘数据

    Returns:
        {
            "date": "2026-06-12",
            "indices": pd.DataFrame,          # 大盘指数
            "market_stats": dict,             # 涨跌家数
            "sectors": {"top": [...], "bottom": [...]},  # 板块排名
            "north_flow": dict,               # 北向资金
            "zt_analysis": {                   # 涨停深度解读
                "total": int,
                "tiers": [...],               # 连板梯队
                "themes": [...],              # 题材聚合
                "leaders": [...],             # 龙头股
            },
            "dt_total": int,                  # 跌停数
            "dragon_tiger_highlights": [...],  # 龙虎榜亮点
            "outlook": str,                    # 明日预判
            "watchlist": [...],                # 观察池
        }
    """
    if target_date is None:
        target_date = date.today().strftime("%Y%m%d")

    report = {"date": target_date}

    # 1. 大盘
    report["indices"] = _pick_indices()
    report["market_stats"] = _safe_fetch_market_stats()

    # 2. 板块
    report["sectors"] = _analyze_sectors()

    # 3. 资金
    report["north_flow"] = fetch_north_flow()

    # 4. 涨停深度解读
    report["zt_analysis"] = _analyze_zt_pool(target_date)

    # 5. 跌停
    report["dt_total"] = _count_dt(target_date)

    # 6. 龙虎榜
    report["dragon_tiger_highlights"] = _dragon_tiger_highlights(target_date)

    # 7. 市场要闻
    report["news"] = fetch_market_news()

    # 8. 明日预判 + 观察池（综合以上）
    outlook = _generate_outlook(report)
    report["outlook"] = outlook["text"]
    report["watchlist"] = outlook["watchlist"]

    return report


# ═══════════════════════════════════════════════
# 各模块
# ═══════════════════════════════════════════════

def _pick_indices() -> list[dict]:
    """大盘指数摘要"""
    try:
        df = fetch_index_spot()
        return [
            {"name": r["name"], "price": round(r["price"], 2),
             "pct": round(r["pct_chg"], 2), "change": round(r["change"], 2),
             "amount": _fmt_amount(r.get("amount", 0))}
            for _, r in df.iterrows()
        ]
    except Exception as e:
        logger.warning(f"indices failed: {e}")
        return []


def _safe_fetch_market_stats() -> dict:
    try:
        return fetch_market_stats()
    except Exception:
        return {"up": 0, "down": 0, "flat": 0, "total": 0}


def _analyze_sectors() -> dict:
    """行业板块 Top/Bottom"""
    try:
        df = fetch_sector_spot()
        if df.empty:
            return {"top": [], "bottom": []}
        top = []
        for _, r in df.head(SECTOR_TOP_N).iterrows():
            top.append({"name": r.get("name", ""), "pct": round(float(r.get("pct_chg", 0)), 2),
                        "lead": str(r.get("lead_stock", ""))})
        bottom = []
        for _, r in df.tail(SECTOR_BOTTOM_N).iterrows():
            bottom.append({"name": r.get("name", ""), "pct": round(float(r.get("pct_chg", 0)), 2),
                           "lead": str(r.get("lead_stock", ""))})
        return {"top": top, "bottom": bottom}
    except Exception as e:
        logger.warning(f"sectors failed: {e}")
        return {"top": [], "bottom": []}


def _analyze_zt_pool(target_date: str) -> dict:
    """涨停板深度解读"""
    try:
        df = fetch_limit_up_pool(target_date)
        if df.empty:
            return {"total": 0, "tiers": [], "themes": [], "leaders": [],
                    "analysis": "今日无涨停数据（可能非交易日或数据延迟）"}

        total = len(df)

        # ── 连板梯队 ──
        tiers = _build_tiers(df)

        # ── 题材聚合 ──
        themes = _build_themes(df)

        # ── 龙头识别 ──
        leaders = _identify_leaders(df, themes)

        # ── 综合解读 ──
        analysis = _write_zt_analysis(total, tiers, themes, leaders)

        return {
            "total": total,
            "tiers": tiers,
            "themes": themes,
            "leaders": leaders,
            "analysis": analysis,
        }
    except Exception as e:
        logger.error(f"zt_analysis failed: {e}")
        return {"total": 0, "tiers": [], "themes": [], "leaders": [],
                "analysis": f"涨停数据解析异常: {e}"}


def _build_tiers(df: pd.DataFrame) -> list[dict]:
    """按连板数分组，构建连板梯队"""
    if "boards" not in df.columns:
        return []

    multi = df[df["boards"] >= ZT_MIN_BOARDS_FOR_TIER].copy()
    if multi.empty:
        return []

    tiers = []
    for boards in sorted(multi["boards"].unique(), reverse=True):
        group = multi[multi["boards"] == boards]
        stocks = []
        for _, r in group.iterrows():
            stocks.append({
                "name": str(r.get("name", "")),
                "code": str(r.get("code", "")),
                "reason": str(r.get("reason", ""))[:30],
                "seal_time": str(r.get("seal_time", r.get("first_seal", ""))),
                "breaks": int(r.get("break_count", 0)),
            })
        label = f"{boards}连板" if boards < 7 else f"{boards}板（空间板）"
        tier = {"boards": int(boards), "label": label, "count": len(stocks), "stocks": stocks}
        tiers.append(tier)

    return tiers


def _build_themes(df: pd.DataFrame) -> list[dict]:
    """按涨停原因聚合题材，计算题材强度"""
    if "reason" not in df.columns:
        return []

    theme_groups = defaultdict(list)
    for _, r in df.iterrows():
        reason = str(r.get("reason", "")).strip()
        if not reason or reason == "nan":
            continue
        # 提取核心关键词（取前两个逗号/顿号分隔的词）
        key = reason.split("+")[0].strip()
        theme_groups[key].append({
            "name": str(r.get("name", "")),
            "boards": int(r.get("boards", 1)),
            "seal_time": str(r.get("seal_time", r.get("first_seal", ""))),
        })

    themes = []
    for theme, stocks in theme_groups.items():
        count = len(stocks)
        # 题材强度分类
        if count >= SECTOR_STRONG_THRESHOLD:
            strength = "主线"
        elif count >= 2:
            strength = "支线"
        else:
            strength = "脉冲"

        # 核心股 = 连板最高的那只
        best = max(stocks, key=lambda s: s["boards"])
        stock_names = [s["name"] for s in stocks]

        themes.append({
            "theme": theme,
            "count": count,
            "strength": strength,
            "core": best["name"],
            "stocks": stock_names,
        })

    themes.sort(key=lambda t: -t["count"])
    return themes


def _identify_leaders(df: pd.DataFrame, themes: list[dict]) -> list[dict]:
    """识别龙头股：主线题材中最早封板 + 最高连板"""
    leaders = []
    main_themes = [t for t in themes if t["strength"] == "主线"]
    for mt in main_themes[:3]:
        theme_stocks = df[df["name"].isin(mt["stocks"])] if "name" in df.columns else pd.DataFrame()
        if theme_stocks.empty:
            continue
        # 按连板数排序取龙头
        if "boards" in theme_stocks.columns:
            theme_stocks = theme_stocks.sort_values(["boards", "seal_time"], ascending=[False, True])
        leader_row = theme_stocks.iloc[0]
        leaders.append({
            "name": str(leader_row.get("name", mt["core"])),
            "theme": mt["theme"],
            "boards": int(leader_row.get("boards", 1)),
            "reason": mt["theme"],
            "note": "龙头 · 主线核心" if int(leader_row.get("boards", 1)) >= 3 else "领涨 · 封板最早",
        })

    return leaders


def _write_zt_analysis(total: int, tiers: list[dict], themes: list[dict],
                       leaders: list[dict]) -> str:
    """生成涨停深度解读（叙事性）"""
    parts = []
    parts.append(f"今日涨停共 **{total}** 家。")

    # 空间板高度判断
    max_board = max((t["boards"] for t in tiers), default=0)
    if max_board >= 7:
        parts.append(f"空间板高度 **{max_board}板**，市场情绪亢奋，短线赚钱效应强。但高位票随时面临分歧，追高需极度谨慎。")
    elif max_board >= 5:
        parts.append(f"空间板高度 **{max_board}板**，短线情绪健康。龙头打出空间后，同方向低位补涨机会值得关注。")
    elif max_board >= 3:
        parts.append(f"空间板仅 **{max_board}板**，短线追高意愿偏弱。操作重心放在首板和1进2，不宜追高位。")
    else:
        parts.append("连板高度极低，市场处于情绪冰点。关注新题材首板破局机会。")

    # 梯队结构
    if tiers:
        tier_descs = []
        for t in tiers[:5]:
            names = "、".join(s["name"] for s in t["stocks"][:3])
            tier_descs.append(f"{t['label']}（{names}）")
        parts.append(f"梯队结构：{' → '.join(tier_descs)}。")

    # 主线题材分析
    main_themes = [t for t in themes if t["strength"] == "主线"]
    sub_themes = [t for t in themes if t["strength"] == "支线"][:5]

    if main_themes:
        for mt in main_themes[:3]:
            parts.append(f"**主线：{mt['theme']}**（{mt['count']}家涨停），核心票 **{mt['core']}**，板块效应确认。"
                        f"同方向可关注{'、'.join(mt['stocks'][:4])}。")
    else:
        parts.append("今日无明确主线题材，资金分散攻击，板块效应弱。")
        if sub_themes:
            parts.append(f"支线题材：{'、'.join(t['theme'] + '(' + str(t['count']) + '家)' for t in sub_themes)}。")

    # 龙头点评
    if leaders:
        for l in leaders[:3]:
            quality = ""
            # 找对应的涨停详情
            for t in tiers:
                for s in t.get("stocks", []):
                    if s["name"] == l["name"]:
                        if s.get("breaks", 0) == 0:
                            quality = "，封板质量好，一字未开"
                        elif s.get("breaks", 0) == 1:
                            quality = "，有一次换手后回封，属于健康换手板"
                        else:
                            quality = f"，炸板{s['breaks']}次，封板不坚决需警惕"
                        break
            parts.append(f"**{l['name']}**：{l['theme']}方向龙头{quality}。")

    # 风险提示
    risky = _find_risky_stocks(tiers)
    if risky:
        parts.append(f"⚠️ **炸板警报**：{'、'.join(risky)} 反复炸板，明日大概率低开，回避。")

    return "\n\n".join(parts)


def _generate_outlook(report: dict) -> dict:
    """生成明日策略（有具体方向和风控）"""
    zt = report.get("zt_analysis", {})
    themes = zt.get("themes", [])
    leaders = zt.get("leaders", [])
    tiers = zt.get("tiers", [])
    indices = report.get("indices", [])
    sectors = report.get("sectors", {})

    parts = []
    watchlist = []

    # 1. 从指数推导市场状态
    if indices:
        up_count = sum(1 for i in indices if i["pct"] > 0)
        if up_count >= 3:
            parts.append("今日普涨，明日大概率分化。去弱留强，只持有主线方向。")
        elif up_count == 0:
            parts.append("今日全线回调，市场恐慌释放。关注错杀品种和明日早盘率先反弹的方向。")
        else:
            # 结构性行情
            up_names = [i["name"] for i in indices if i["pct"] > 0]
            down_names = [i["name"] for i in indices if i["pct"] < 0]
            parts.append(f"结构性行情：{'、'.join(up_names)}逆势走强，{'、'.join(down_names[:2])}偏弱。"
                        f"操作上紧跟强势方向，不抄底弱势指数。")

    # 2. 从板块推导资金方向
    top_sectors = sectors.get("top", [])[:5]
    bottom_sectors = sectors.get("bottom", [])[:5]
    if top_sectors:
        top_names = [s["name"] for s in top_sectors[:3]]
        if any("有色" in n or "材料" in n or "煤炭" in n for n in top_names):
            parts.append("资金向上游资源品集中，关注有色/煤炭/化工的持续性。如明天继续领涨，确认周期主线。")
        elif any("消费" in n or "食品" in n or "白酒" in n or "医药" in n for n in top_names):
            parts.append("防御性消费占优，市场风险偏好偏低。如科技方向无法接力，防御逻辑继续演绎。")

    # 3. 从涨停推导主线持续性
    main_themes = [t for t in themes if t["strength"] == "主线"]
    if main_themes:
        mt = main_themes[0]
        parts.append(f"主线 **{mt['theme']}** 有 {mt['count']} 家涨停，板块效应确认。"
                    f"明天重点看 **{mt['core']}** 的开盘情况——高开缩量秒板=强势延续，低开放量=分歧加大。")
        for l in leaders[:5]:
            watchlist.append({"name": l["name"], "reason": f"{l['theme']} · {l['note']}"})
    else:
        parts.append("市场无主线，明天关注哪个方向率先出现3家以上涨停——那可能就是新主线。")
        # 从2连板中找潜在突破方向
        for t in tiers:
            if t["boards"] >= 2:
                for s in t["stocks"][:3]:
                    watchlist.append({"name": s["name"], "reason": f"{t['label']} · 潜在空间板"})

    # 4. 风控
    max_board = max((t["boards"] for t in tiers), default=0)
    if max_board >= 5:
        parts.append(f"⚠️ 风控：空间板 {max_board} 板，高位分歧风险加大。高位票设好移动止盈，不追缩量加速板。")
    else:
        parts.append("风控：仓位控制在5成以内。如果明天10:00前跌停数超过涨停数，减仓至3成。")

    return {"text": "\n\n".join(parts), "watchlist": watchlist}


# ═══════════════════════════════════════════════
# 工具
# ═══════════════════════════════════════════════

def _fmt_amount(amount) -> str:
    """格式化金额"""
    try:
        a = float(amount)
    except (ValueError, TypeError):
        return str(amount)
    if abs(a) >= 1e8:
        return f"{a/1e8:.1f}亿"
    elif abs(a) >= 1e4:
        return f"{a/1e4:.0f}万"
    else:
        return f"{a:.0f}"


def _find_risky_stocks(tiers: list[dict]) -> list[str]:
    risky = []
    for t in tiers:
        for s in t.get("stocks", []):
            if s.get("breaks", 0) >= 2:
                risky.append(f"{s['name']}(炸{s['breaks']}次)")
    return risky[:5]


def _count_dt(target_date: str) -> int:
    try:
        df = fetch_limit_down_pool(target_date)
        return len(df)
    except Exception:
        return 0


def _dragon_tiger_highlights(target_date: str) -> list[dict]:
    try:
        df = fetch_dragon_tiger(target_date)
        if df.empty:
            return []
        if "净买额" in df.columns:
            df["净买额"] = pd.to_numeric(df["净买额"], errors="coerce")
            df = df.sort_values("净买额", ascending=False, key=abs).head(5)
        highlights = []
        for _, r in df.iterrows():
            highlights.append({
                "name": str(r.get("名称", "")),
                "reason": str(r.get("上榜原因", "")),
                "net_buy": _fmt_amount(r.get("净买额", 0)),
                "pct": round(float(r.get("涨跌幅", 0)), 2),
            })
        return highlights
    except Exception:
        return []


def _fmt_amount(amount) -> str:
    try:
        a = float(amount)
    except (ValueError, TypeError):
        return str(amount)
    if abs(a) >= 1e8:
        return f"{a/1e8:.1f}亿"
    elif abs(a) >= 1e4:
        return f"{a/1e4:.0f}万"
    return f"{a:.0f}"


# ═══════════════════════════════════════════════
# Markdown 渲染
# ═══════════════════════════════════════════════

def render_afternoon_md(report: dict) -> str:
    """生成下午版 Markdown 报告"""
    lines = [
        f"# 📈 A股收盘复盘 — {report['date']}",
        "",
    ]

    # ── 市场概况 ──
    stats = report.get("market_stats", {})
    lines.append("## 📊 市场概况")
    lines.append(f"上涨 {stats.get('up', 0)} 家 / 下跌 {stats.get('down', 0)} 家 / 平盘 {stats.get('flat', 0)} 家")
    lines.append("")

    # ── 盘后要闻 ──
    news = report.get("news", [])
    if news:
        lines.append("## 📰 今日要闻")
        for n in news[:8]:
            lines.append(f"- {n['title'][:100]}")
        lines.append("")

    # ── 指数 ──
    lines.append("| 指数 | 收盘价 | 涨跌幅 | 涨跌额 | 成交额 |")
    lines.append("|------|--------|--------|--------|--------|")
    for idx in report.get("indices", []):
        sign = "+" if idx["pct"] >= 0 else ""
        lines.append(f"| {idx['name']} | {idx['price']} | {sign}{idx['pct']}% | {sign}{idx['change']} | {idx['amount']} |")
    lines.append("")

    # 板块
    sectors = report.get("sectors", {})
    lines.append("## 🔥 行业板块")
    lines.append("### 📈 涨幅榜")
    lines.append("| 板块 | 涨跌幅 | 领涨股 |")
    lines.append("|------|--------|--------|")
    for s in sectors.get("top", []):
        lines.append(f"| {s['name']} | +{s['pct']}% | {s['lead']} |")
    lines.append("")
    lines.append("### 📉 跌幅榜")
    lines.append("| 板块 | 涨跌幅 | 领跌股 |")
    lines.append("|------|--------|--------|")
    for s in sectors.get("bottom", []):
        lines.append(f"| {s['name']} | {s['pct']}% | {s['lead']} |")
    lines.append("")

    # 资金流向
    nf = report.get("north_flow", {})
    lines.append("## 💰 资金流向")
    lines.append(f"北向资金：沪股通 {nf.get('hgt', 0):+.2f}亿 / 深股通 {nf.get('sgt', 0):+.2f}亿 / **合计 {nf.get('total', 0):+.2f}亿**")
    lines.append("")

    # 涨停深度解读
    zt = report.get("zt_analysis", {})
    lines.append("## 🚀 涨停板深度解读")
    lines.append(f"涨停 **{zt.get('total', 0)}** 家 / 跌停 **{report.get('dt_total', 0)}** 家")
    lines.append("")
    lines.append(zt.get("analysis", ""))
    lines.append("")

    # 连板梯队
    tiers = zt.get("tiers", [])
    if tiers:
        lines.append("### 🪜 连板梯队")
        for t in tiers:
            lines.append(f"**{t['label']}** ({t['count']}家)")
            for s in t["stocks"]:
                warn = f" ⚠️炸{s['breaks']}次" if s["breaks"] >= 2 else ""
                lines.append(f"  - {s['name']} | {s['reason']} | {s['seal_time']}{warn}")
            lines.append("")

    # 题材聚合
    themes = zt.get("themes", [])
    if themes:
        lines.append("### 🧩 题材聚合")
        main = [t for t in themes if t["strength"] == "主线"]
        sub = [t for t in themes if t["strength"] == "支线"]
        if main:
            lines.append("**🔥 主线题材**")
            for t in main:
                lines.append(f"- **{t['theme']}** — {t['count']}家涨停，核心：{t['core']}")
        if sub:
            lines.append("**🔹 支线题材**")
            for t in sub:
                lines.append(f"- {t['theme']} — {t['count']}家涨停，核心：{t['core']}")
        lines.append("")

    # 龙虎榜
    dt_hl = report.get("dragon_tiger_highlights", [])
    if dt_hl:
        lines.append("## 🐉 龙虎榜亮点")
        lines.append("| 个股 | 涨跌幅 | 净买额 | 上榜原因 |")
        lines.append("|------|--------|--------|----------|")
        for d in dt_hl:
            sign = "+" if d["pct"] >= 0 else ""
            lines.append(f"| {d['name']} | {sign}{d['pct']}% | {d['net_buy']} | {d['reason']} |")
        lines.append("")

    # 明日预判
    lines.append("## 🔮 明日预判")
    lines.append(report.get("outlook", ""))
    lines.append("")

    # 观察池
    watchlist = report.get("watchlist", [])
    if watchlist:
        lines.append("### 👀 明日观察池")
        for w in watchlist:
            lines.append(f"- **{w['name']}** — {w['reason']}")
        lines.append("")

    lines.append("---")
    lines.append(f"*生成时间: {datetime.now().strftime('%H:%M:%S')}*")
    return "\n".join(lines)

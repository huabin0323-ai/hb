"""收盘后热门股识别 — 综合多维度热度评分"""
from __future__ import annotations

import logging
from collections import defaultdict

logger = logging.getLogger("a-share.hot_stocks")


def identify_hot_stocks(date_str: str, limit_up_df=None, dragon_tiger_df=None,
                        sector_data=None, news=None, top_n: int = 3) -> list[dict]:
    """识别当日最热门股票，返回按热度排序的列表

    综合评分维度：
    1. 连板高度（空间板加分）
    2. 题材强度（同题材涨停数）
    3. 龙虎榜净买入排名
    4. 换手/成交额
    5. 新闻提及次数

    Returns:
        [{code, name, heat_score, reasons: [str], boards, theme, net_buy, ...}, ...]
    """
    heat = defaultdict(lambda: {"score": 0, "reasons": [], "boards": 0, "theme": "", "net_buy": 0})

    # ── 维度1: 涨停板连板高度 ──
    if limit_up_df is not None and not limit_up_df.empty:
        for _, row in limit_up_df.iterrows():
            name = str(row.get("name", ""))
            code = str(row.get("code", ""))
            if not name or not code:
                continue
            boards = int(row.get("boards", 0))
            reason = str(row.get("reason", ""))

            score = 0
            r = []

            # 空间板（最高连板）
            if boards >= 7:
                score += 50
                r.append(f"空间板{boards}连板")
            elif boards >= 5:
                score += 35
                r.append(f"高度板{boards}连板")
            elif boards >= 3:
                score += 20
                r.append(f"连板{boards}板")
            elif boards >= 2:
                score += 10
                r.append(f"2连板")

            # 封板时间早=强势
            seal_time = str(row.get("seal_time", ""))
            if seal_time and "09:" in seal_time:
                score += 10
                r.append("早盘秒板")

            # 炸板少=封板质量好
            breaks = int(row.get("break_count", 0))
            if breaks == 0 and boards >= 2:
                score += 5
                r.append("一字未开")

            heat[(code, name)]["score"] += score
            heat[(code, name)]["reasons"].extend(r)
            heat[(code, name)]["boards"] = max(heat[(code, name)]["boards"], boards)
            heat[(code, name)]["theme"] = reason

    # ── 维度2: 题材强度 ──
    if limit_up_df is not None and not limit_up_df.empty and "reason" in limit_up_df.columns:
        theme_count = defaultdict(int)
        theme_stocks = defaultdict(list)
        for _, row in limit_up_df.iterrows():
            reason = str(row.get("reason", "")).strip()
            if reason and reason != "nan":
                key = reason.split("+")[0].strip()
                theme_count[key] += 1
                theme_stocks[key].append(str(row.get("name", "")))

        for theme, count in theme_count.items():
            if count >= 5:  # 强主线
                for stock_name in theme_stocks[theme]:
                    for key in heat:
                        if key[0] == stock_name:
                            heat[key]["score"] += 20
                            heat[key]["reasons"].append(f"主线题材「{theme}」({count}家涨停)")
                            heat[key]["theme"] = theme
            elif count >= 3:  # 主线
                for stock_name in theme_stocks[theme]:
                    for key in heat:
                        if key[0] == stock_name:
                            heat[key]["score"] += 10
                            heat[key]["reasons"].append(f"题材「{theme}」({count}家涨停)")

    # ── 维度3: 龙虎榜净买入 ──
    if dragon_tiger_df is not None and not dragon_tiger_df.empty:
        for _, row in dragon_tiger_df.iterrows():
            name = str(row.get("名称", ""))
            if not name:
                continue
            net = float(row.get("净买额", 0)) if "净买额" in row.index else 0

            # 找到对应的 heat entry
            matched = None
            for key in heat:
                if key[0] == name:
                    matched = key
                    break

            if matched:
                abs_net = abs(net)
                if abs_net >= 5:  # 净买超5亿
                    heat[matched]["score"] += 15
                    heat[matched]["reasons"].append(f"龙虎榜净买{net:+.1f}亿")
                    heat[matched]["net_buy"] = net
                elif abs_net >= 2:
                    heat[matched]["score"] += 8
                    heat[matched]["reasons"].append(f"龙虎榜净买{net:+.1f}亿")
                    heat[matched]["net_buy"] = net
            elif name:
                # 龙虎榜出现的新股票（不在涨停池内）
                heat[(name, "")]["score"] += 6
                heat[(name, "")]["reasons"].append(f"龙虎榜上榜(净买{net:+.1f}亿)")
                heat[(name, "")]["net_buy"] = net

    # ── 维度4: 新闻提及 ──
    if news:
        for n in news:
            title = n.get("title", "")
            for key in heat:
                if key[0] and key[0] in title:
                    heat[key]["score"] += 3
                    heat[key]["reasons"].append("盘后要闻提及")

    # ── 排序 & 输出 ──
    sorted_stocks = sorted(heat.items(), key=lambda x: -x[1]["score"])

    result = []
    for (code, name), info in sorted_stocks[:top_n]:
        if info["score"] >= 10:  # 热度门槛
            result.append({
                "code": code,
                "name": name,
                "heat_score": info["score"],
                "boards": info["boards"],
                "theme": info["theme"],
                "net_buy": info["net_buy"],
                "reasons": info["reasons"],
            })

    # 如果涨停池识别不够，补充龙虎榜头部
    if len(result) < top_n and dragon_tiger_df is not None and not dragon_tiger_df.empty:
        existing_names = {r["name"] for r in result}
        for _, row in dragon_tiger_df.iterrows():
            name = str(row.get("名称", ""))
            if name in existing_names or not name:
                continue
            net = float(row.get("净买额", 0)) if "净买额" in row.index else 0
            result.append({
                "code": str(row.get("代码", "")),
                "name": name,
                "heat_score": 8,
                "boards": 0,
                "theme": "",
                "net_buy": net,
                "reasons": [f"龙虎榜净买{net:+.1f}亿"],
            })
            if len(result) >= top_n:
                break

    return result


def format_hot_stocks_text(stocks: list[dict]) -> str:
    """格式化热门股摘要文本"""
    if not stocks:
        return "今日暂无显著热门个股"

    lines = []
    for i, s in enumerate(stocks, 1):
        lines.append(f"**#{i} {s['name']}**（{s['code']}）热度分：{s['heat_score']}")
        if s["boards"]:
            lines.append(f"  连板：{s['boards']}板")
        if s["theme"]:
            lines.append(f"  题材：{s['theme']}")
        if s["net_buy"]:
            lines.append(f"  龙虎榜净买：{s['net_buy']:+.1f}亿")
        if s["reasons"]:
            lines.append(f"  标签：{' · '.join(s['reasons'][:5])}")
        lines.append("")

    return "\n".join(lines)

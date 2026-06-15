"""飞书推送 — urllib 直连，保证 UTF-8 编码"""

from __future__ import annotations

import json
import logging
from urllib import request
from urllib.error import URLError

from config import FEISHU_WEBHOOK_AM, FEISHU_WEBHOOK_PM

logger = logging.getLogger("a-share.feishu")

TIMEOUT = 15


def _post(url: str, payload: dict) -> bool:
    """urllib POST，确保 UTF-8 编码"""
    try:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        req = request.Request(url, data=data,
                              headers={"Content-Type": "application/json; charset=utf-8"})
        resp = request.urlopen(req, timeout=TIMEOUT)
        result = json.loads(resp.read().decode())
        if result.get("code") == 0 or result.get("StatusCode") == 0:
            logger.info("Feishu sent OK")
            return True
        else:
            logger.error(f"Feishu failed: {result}")
            return False
    except Exception as e:
        logger.error(f"Feishu error: {e}")
        return False


def send_card(card: dict, webhook_url: str | None = None) -> bool:
    url = webhook_url or FEISHU_WEBHOOK_PM
    if not url:
        logger.error("Feishu webhook not configured")
        return False
    if "msg_type" not in card:
        card = {"msg_type": "interactive", "card": card}
    return _post(url, card)


def send_morning_card(card: dict) -> bool:
    return send_card(card, FEISHU_WEBHOOK_AM)


def send_afternoon_card(card: dict) -> bool:
    return send_card(card, FEISHU_WEBHOOK_PM)


# ═══════════════════════════════════════════════
# 深度解读卡片渲染
# ═══════════════════════════════════════════════

def render_afternoon_feishu_card(report: dict) -> dict:
    """下午版 → 飞书深度解读卡片"""
    date_str = report.get("date", "")
    indices = report.get("indices", [])
    sectors = report.get("sectors", {})
    zt = report.get("zt_analysis", {})
    dt_hl = report.get("dragon_tiger_highlights", [])
    outlook = report.get("outlook", "")
    watchlist = report.get("watchlist", [])
    news = report.get("news", [])

    # ── 大盘解读 ──
    idx_lines = []
    for idx in indices[:4]:
        sign = "+" if idx["pct"] >= 0 else ""
        idx_lines.append(f"{idx['name']} **{sign}{idx['pct']}%**")

    # 判断结构性特征
    pcts = [i["pct"] for i in indices]
    has_divergence = max(pcts) - min(pcts) > 0.8 if pcts else False
    divergence_note = ""
    if has_divergence:
        up_idx = [i for i in indices if i["pct"] > 0]
        down_idx = [i for i in indices if i["pct"] < 0]
        if up_idx and down_idx:
            divergence_note = f"\n\n结构分化明显：{'、'.join(i['name'] for i in up_idx)}逆势走强，{'、'.join(i['name'] for i in down_idx[:2])}回调。资金在大科技内部调仓——卖软件/互联网，买半导体/硬件。"

    idx_md = "**📊 大盘指数**\n" + "  ".join(idx_lines) + divergence_note

    # ── 板块解读 ──
    top_sectors = sectors.get("top", [])[:5]
    bottom_sectors = sectors.get("bottom", [])[:5]
    top_text = "\n".join(f"• {s['name']} **{s['pct']:+.2f}%**" for s in top_sectors)
    bottom_text = "\n".join(f"• {s['name']} {s['pct']:+.2f}%" for s in bottom_sectors)

    # 板块逻辑推断
    sector_narrative = ""
    if top_sectors:
        top_names = [s["name"] for s in top_sectors[:3]]
        if any("有色" in n or "煤炭" in n or "材料" in n for n in top_names):
            sector_narrative = "\n\n> 上游资源品领涨，资金沿产业链向上游集中。"
        elif any("消费" in n or "食品" in n or "白酒" in n for n in top_names):
            sector_narrative = "\n\n> 防御性消费走强，市场风险偏好下降，资金寻求确定性。"
        if bottom_sectors:
            bot_names = [s["name"] for s in bottom_sectors[:3]]
            if any("信息" in n or "通信" in n or "传媒" in n or "文化" in n for n in bot_names):
                sector_narrative += "\n>TMT方向承压，前期热门赛道获利回吐。"

    sector_md = f"**🔥 板块**\n🟢 涨幅:\n{top_text}\n\n🔴 跌幅:\n{bottom_text}{sector_narrative}"

    # ── 涨停解读 ──
    zt_total = zt.get("total", 0)
    dt_total = report.get("dt_total", 0)
    tiers = zt.get("tiers", [])

    tier_lines = []
    max_board = 0
    for t in tiers[:4]:
        stocks = ",".join(s["name"] for s in t["stocks"][:4])
        tier_lines.append(f"• {t['label']} ×{t['count']}：{stocks}")
        if t["boards"] > max_board:
            max_board = t["boards"]

    tier_text = "\n".join(tier_lines) if tier_lines else "无连板股"

    # 炸板风险
    risky_stocks = []
    for t in tiers:
        for s in t.get("stocks", []):
            if s.get("breaks", 0) >= 2:
                risky_stocks.append(f"{s['name']}(炸{s['breaks']}次)")
    risky_text = ""
    if risky_stocks:
        risky_text = f"\n\n⚠️ 炸板警报：{'、'.join(risky_stocks[:5])}"

    # 情绪判断
    sentiment = ""
    if max_board >= 5:
        sentiment = "\n\n> 空间板高度充足，短线情绪亢奋。高位票注意分歧日风险。"
    elif max_board >= 3:
        sentiment = "\n\n> 空间板仅3板，追高意愿不足。重点看首板和2板机会。"
    else:
        sentiment = "\n\n> 连板高度极低，市场处于冰点。关注新题材首板破局。"

    zt_md = f"**🚀 涨停解读**\n涨停 **{zt_total}** 家 / 跌停 **{dt_total}** 家\n\n{tier_text}{risky_text}{sentiment}"

    # ── 龙虎榜 ──
    dt_md = ""
    if dt_hl:
        dt_lines = [f"• {d['name']} {d['pct']:+.2f}% — {d['reason'][:30]}" for d in dt_hl[:5]]
        dt_md = f"**🐉 龙虎榜**\n" + "\n".join(dt_lines)

        # 题材共振判断
        dt_names = [d["name"] for d in dt_hl[:5]]
        if len(dt_names) >= 3:
            # 简单判断：如果龙虎榜个股名字包含材料/电子/芯片等，判断为半导体主线
            if any("电子" in n or "材料" in n or "气体" in n or "芯片" in n or "微" in n for n in dt_names):
                dt_md += "\n\n> 龙虎榜集中半导体材料/设备，资金主攻方向明确。"

    # ── 明日策略 ──
    outlook_text = outlook.replace("\n", "\n\n") if outlook else ""

    watch_text = ""
    if watchlist:
        watch_lines = [f"• **{w['name']}** — {w['reason']}" for w in watchlist[:5]]
        watch_text = "\n".join(watch_lines)

    # ── 组装卡片 ──
    elements = [
        {"tag": "div", "text": {"tag": "lark_md", "content": idx_md}},
        {"tag": "hr"},
        {"tag": "div", "text": {"tag": "lark_md", "content": sector_md}},
        {"tag": "hr"},
        {"tag": "div", "text": {"tag": "lark_md", "content": zt_md}},
    ]
    # 盘后要闻
    if news:
        news_lines = [f"• {n['title'][:90]}" for n in news[:6]]
        elements.insert(3, {"tag": "hr"})
        elements.insert(3, {"tag": "div", "text": {"tag": "lark_md",
                           "content": "**📰 今日要闻**\n" + "\n".join(news_lines)}})
    if dt_md:
        elements.append({"tag": "hr"})
        elements.append({"tag": "div", "text": {"tag": "lark_md", "content": dt_md}})

    elements.append({"tag": "hr"})
    elements.append({"tag": "div", "text": {"tag": "lark_md",
                     "content": f"**🔮 明日策略**\n\n{outlook_text}"}})
    if watch_text:
        elements.append({"tag": "div", "text": {"tag": "lark_md",
                         "content": f"**👀 观察池**\n{watch_text}"}})

    elements.append({"tag": "note", "elements": [
        {"tag": "plain_text", "content": f"数据：新浪+东财 · {date_str} · AI深度解读 · 仅供参考"}
    ]})

    return {
        "header": {
            "title": {"tag": "plain_text", "content": f"📈 A股收盘深度复盘 · {date_str}"},
            "template": "blue",
        },
        "elements": elements,
    }

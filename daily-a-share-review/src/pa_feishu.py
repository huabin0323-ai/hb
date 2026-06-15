"""PA信号飞书卡片渲染

将 PASignal 渲染为飞书卡片消息，包含：
- 标的信号概览
- 支撑/阻力位
- 条件单挂单建议
- 风险提示
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

from config import COLORS

logger = logging.getLogger("a-share.pa_feishu")


# ═══════════════════════════════════════════════
# 单标的卡片
# ═══════════════════════════════════════════════

def _direction_emoji(direction: str) -> str:
    if direction == "偏多":
        return "📈"
    elif direction == "偏空":
        return "📉"
    return "➡️"


def _confidence_color(confidence: str) -> str:
    if "高" in confidence:
        return "green"
    elif "中" in confidence:
        return "yellow"
    return "red"


def _score_color(score: int) -> str:
    if score >= 75:
        return "green"
    elif score >= 55:
        return "yellow"
    else:
        return "red"


def _trend_emoji(trend: str) -> str:
    return {
        "uptrend": "🔺",
        "downtrend": "🔻",
        "trading_range": "📦",
        "narrow_channel": "📏",
        "wide_channel": "📐",
    }.get(trend, "📊")


def render_signal_card(signal) -> dict:
    """渲染单标的 PA 信号卡片

    Args:
        signal: PASignal 对象

    Returns:
        飞书卡片 dict（msg_type: "interactive", card: {...}）
    """
    emoji = _direction_emoji(signal.direction)
    conf_color = _confidence_color(signal.confidence)
    score_c = _score_color(signal.technical_score)
    trend_e = _trend_emoji(signal.market_structure)

    # ── 标题行 ──
    title = f"{emoji} {signal.name}({signal.code}) · {signal.direction} · {signal.confidence}"

    # ── 市场结构 & 评分 ──
    structure_md = (
        f"**市场结构**：{trend_e} {signal.structure_desc}\n"
        f"**技术评分**：<font color='{score_c}'>{signal.technical_score}/100</font>　"
        f"**独立信号**：{signal.independent_signals}个\n"
        f"**当前价**：<font color='{COLORS['accent']}'>{signal.current_price}</font>　"
        f"**ATR(14)**：{signal.atr or '-'}"
    )

    # ── 入场信号 ──
    if signal.primary_signal_desc:
        signal_md = f"**入场信号**：{signal.primary_signal_desc}"
    else:
        signal_md = "**入场信号**：无明确入场信号，等待突破确认"

    # ── 支撑位 ──
    if signal.supports:
        sup_lines = []
        for s in signal.supports[:4]:
            sup_lines.append(f"• <font color='{COLORS['green']}'>{s.price}</font> — {s.description}")
        sup_md = "**🛡️ 支撑位**\n" + "\n".join(sup_lines)
    else:
        sup_md = "**🛡️ 支撑位**\n无明确支撑位"

    # ── 阻力位 ──
    if signal.resistances:
        res_lines = []
        for r in signal.resistances[:4]:
            res_lines.append(f"• <font color='{COLORS['red']}'>{r.price}</font> — {r.description}")
        res_md = "**⚔️ 阻力位**\n" + "\n".join(res_lines)
    else:
        res_md = "**⚔️ 阻力位**\n无明确阻力位"

    # ── 条件单建议 ──
    rr_color = "green" if signal.rr_ok else "red"
    direction_label = "做多" if signal.direction == "偏多" else ("做空" if signal.direction == "偏空" else "观望")

    order_md = (
        f"**📋 条件单建议（{direction_label}）**\n"
        f"突破买入：<font color='{COLORS['accent']}'>{signal.suggested_entry}</font>\n"
        f"止损价位：<font color='{COLORS['red']}'>{signal.suggested_stop}</font>\n"
        f"目标价位：<font color='{COLORS['green']}'>{signal.suggested_target}</font>\n"
        f"盈亏比：<font color='{rr_color}'>{signal.rr_ratio}:1</font>　"
        f"{'✅' if signal.rr_ok else '❌ RR<2:1'}"
    )

    # ── 仓位 ──
    risk_pct = signal.suggested_position_pct
    position_md = (
        f"**⚠️ 仓位建议**\n"
        f"单票风险：总资金 2%\n"
        f"建议仓位：总资金 {risk_pct}%\n"
        f"每股风险：{signal.risk_per_share} 元"
    )

    # ── 组装卡片 ──
    now = datetime.now().strftime("%m-%d %H:%M")
    elements = [
        {"tag": "div", "text": {"tag": "lark_md", "content": structure_md}},
        {"tag": "hr"},
        {"tag": "div", "text": {"tag": "lark_md", "content": signal_md}},
        {"tag": "hr"},
        {"tag": "div", "text": {"tag": "lark_md", "content": sup_md}},
        {"tag": "hr"},
        {"tag": "div", "text": {"tag": "lark_md", "content": res_md}},
        {"tag": "hr"},
        {"tag": "div", "text": {"tag": "lark_md", "content": order_md}},
        {"tag": "hr"},
        {"tag": "div", "text": {"tag": "lark_md", "content": position_md}},
        {"tag": "note", "elements": [
            {"tag": "plain_text", "content": f"🤖 AI分析 · 仅供参考不构成投资建议 · {now}"}
        ]},
    ]

    # 如果有高潮警告，在最后加一个红框提示
    if signal.pa_analysis:
        climax = signal.pa_analysis.get("climax_warnings", [])
        if climax:
            for c in climax:
                elements.insert(-1, {"tag": "hr"})
                elements.insert(-1, {"tag": "div", "text": {"tag": "lark_md",
                    "content": f"🚨 **风险警告**：{c.description if hasattr(c, 'description') else str(c)}"}})

    return {
        "header": {
            "title": {"tag": "plain_text", "content": title},
            "template": conf_color,
        },
        "elements": elements,
    }


# ═══════════════════════════════════════════════
# 汇总卡片（一次推多个标的时的概览）
# ═══════════════════════════════════════════════

def render_summary_card(signals: list, session_label: str = "") -> dict:
    """渲染多标的汇总卡片——在一张卡片中列出所有信号"""
    if not signals:
        return {}

    now = datetime.now().strftime("%m-%d %H:%M")
    label = session_label or "PA扫描"
    active = [s for s in signals if s.ok]

    lines = [f"**{label} · 扫描结果** {now}", "",
             f"筛选 {len(signals)} 只，**{len(active)} 只有效信号**", ""]

    for i, s in enumerate(active[:15], 1):
        emoji = _direction_emoji(s.direction)
        conf = s.confidence
        rr_icon = "✅" if s.rr_ok else "⚠️"
        lines.append(
            f"{i}. {emoji} **{s.name}**({s.code}) "
            f"评分{s.technical_score} · {conf} · "
            f"入场{s.suggested_entry} · 止损{s.suggested_stop} · "
            f"RR={s.rr_ratio} {rr_icon}"
        )
        lines.append(f"   信号：{s.primary_signal_desc[:60]}")
        lines.append("")

    lines.append("---")
    lines.append("*点击单标的卡片查看支撑/阻力详情*")

    content = "\n".join(lines)

    return {
        "header": {
            "title": {"tag": "plain_text", "content": f"📊 A股PA信号汇总 · {label}"},
            "template": "blue",
        },
        "elements": [
            {"tag": "div", "text": {"tag": "lark_md", "content": content}},
            {"tag": "note", "elements": [
                {"tag": "plain_text", "content": f"🤖 AI分析 · 仅供参考 · {now} · 完整分析请查看单标卡片"}
            ]},
        ],
    }

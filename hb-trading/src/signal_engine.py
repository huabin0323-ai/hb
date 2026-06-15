"""综合信号引擎 — 技术面 + 情绪面 → 评分 + 确认 + 盈亏比过滤

三层升级（来自案例001）：
  1. 入场确认 — 信号出现后需下一根K线确认
  2. 多信号共振 — 独立信号 ≥3 才出通知
  3. 盈亏比过滤器 — R:R < 2:1 不发通知
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

import pandas as pd

from src.price_action import (
    TechnicalScore, MarketState, EntrySignal, SignalBar,
    analyze as analyze_technicals,
)
from src.sentiment import (
    SentimentResult, get_full_sentiment,
)

logger = logging.getLogger("signal_engine")


# ======================================================================
# 新增枚举
# ======================================================================

class SignalStatus(Enum):
    PENDING = "pending"        # 待确认
    CONFIRMED = "confirmed"    # 已确认
    REJECTED = "rejected"      # 被否定
    EXPIRED = "expired"        # 超时未确认


# ======================================================================
# Data structures
# ======================================================================

@dataclass
class SignalOutput:
    score: int
    direction: str
    conviction: str
    status: SignalStatus = SignalStatus.PENDING
    breakdown: dict = field(default_factory=dict)
    technical_score: Optional[TechnicalScore] = None
    sentiment_result: Optional[SentimentResult] = None
    entry_signals: list = field(default_factory=list)
    independent_count: int = 0     # 独立信号个数
    min_independent_required: int = 3  # 最少需要几个独立信号
    rr_ratio: float = 0.0          # 盈亏比
    stop_loss: float = 0.0
    take_profit: float = 0.0
    entry_price: float = 0.0
    summary: str = ""
    risk_warning: str = ""


# ======================================================================
# 信号类型计数（独立信号识别）
# ======================================================================

def _count_independent_signals(
    technical: TechnicalScore,
    entry_signals: list,
    state: MarketState,
) -> tuple[int, list[str]]:
    """统计有多少个独立信号类型。同一类型只算一次。"""
    signal_types: set[str] = set()
    details: list[str] = []

    # 信号类型 → 中文标签
    TYPE_LABELS: dict[str, str] = {
        "bear_bar_long": "#23 阴线做多",
        "support_betrayal_long": "#19 支撑背叛",
        "double_bottom": "双底牛旗",
        "ema_interaction": "EMA20互动",
        "final_flag_reversal": "最终旗形反转",
        "vacuum_effect": "真空效应反转",
        "horizontal_sr": "水平S/R位",
        "measuring_gap": "测量缺口",
    }

    for es in entry_signals:
        if hasattr(es, 'type'):
            t = str(es.type)
            signal_types.add(t)
            if t in TYPE_LABELS:
                details.append(TYPE_LABELS[t])

    # 2. 80%规则 — 交易区间中的假突破
    if state.trend == "trading_range" and any(
        hasattr(es, 'type') and 'breakout' in str(es.type).lower()
        for es in entry_signals
    ):
        signal_types.add("80pct_rule")

    # 3. 市场结构信号
    if state.trend in ("uptrend", "downtrend"):
        signal_types.add("trend_structure")

    # 4. 通道类型
    if state.strength > 0.6:
        signal_types.add("strong_momentum")

    # 5. 二次入场(H2)
    if any(hasattr(e, 'type') and 'H2' in str(e.type) for e in entry_signals):
        signal_types.add("h2_entry")
        details.append("H2入场")

    # 6. 楔形/三次推
    if any(hasattr(e, 'type') and ('H3' in str(e.type) or 'wedge' in str(e.type).lower())
           for e in entry_signals):
        signal_types.add("wedge_h3")
        details.append("楔形H3")

    count = len(signal_types)
    details.insert(0, f"独立信号: {count}个 ({', '.join(sorted(signal_types))})")
    return count, details


# ======================================================================
# 确认检查
# ======================================================================

def _check_confirmation(df: pd.DataFrame, best_entry: EntrySignal | None) -> SignalStatus:
    """检查最近一根K线是否确认了入场信号。

    做多: 最近K线收盘 > 信号入场价 → 确认
    做空: 最近K线收盘 < 信号入场价 → 确认
    无信号: PENDING
    """
    if best_entry is None or len(df) < 2:
        return SignalStatus.PENDING

    latest = df.iloc[-1]
    direction = best_entry.direction
    entry_price = best_entry.entry_price

    if direction == "long":
        if latest["close"] > entry_price:
            return SignalStatus.CONFIRMED
        elif latest["low"] < best_entry.stop_loss:
            return SignalStatus.REJECTED
    elif direction == "short":
        if latest["close"] < entry_price:
            return SignalStatus.CONFIRMED
        elif latest["high"] > best_entry.stop_loss:
            return SignalStatus.REJECTED

    return SignalStatus.PENDING


# ======================================================================
# 盈亏比计算
# ======================================================================

def _calc_rr_ratio(entry_price: float, stop_loss: float, take_profit: float,
                    direction: str) -> float:
    """计算盈亏比"""
    if entry_price <= 0 or stop_loss <= 0 or take_profit <= 0:
        return 0.0
    if direction == "long":
        reward = take_profit - entry_price
        risk = entry_price - stop_loss
    else:
        reward = entry_price - take_profit
        risk = stop_loss - entry_price
    if risk <= 0:
        return 0.0
    return abs(reward / risk)


MIN_RR_RATIO = 2.0  # 最低盈亏比要求


# ======================================================================
# 核心逻辑
# ======================================================================

def compute_signal(
    df: pd.DataFrame,
    technical: TechnicalScore,
    sentiment: SentimentResult,
    entry_signals: list | None = None,
    state: MarketState | None = None,
) -> SignalOutput:
    if entry_signals is None:
        entry_signals = []

    breakdown: dict = {}
    signal_bonus = 0.0
    signal_penalty = 0.0
    risk_msgs: list[str] = []

    # --- 权重 ---
    tech_weighted = technical.score * 0.6
    sentiment_weighted = sentiment.score * 0.4
    breakdown["技术面(60%)"] = round(tech_weighted, 1)
    breakdown["情绪面(40%)"] = round(sentiment_weighted, 1)

    # --- 情绪方向 ---
    sentiment_value = sentiment.fear_greed.value if sentiment.fear_greed else 50
    sentiment_bias: Optional[str] = None
    if sentiment_value >= 60:
        sentiment_bias = "greedy"
    elif sentiment_value <= 40:
        sentiment_bias = "fearful"

    tech_direction = technical.direction
    resonance = False
    divergence = False

    if tech_direction == "long":
        if sentiment_bias in ("greedy", None):
            resonance = True
            signal_bonus += 8
            breakdown["共振加分"] = 8.0
        elif sentiment_bias == "fearful":
            divergence = True
            signal_bonus += (10 if sentiment_value <= 25 else 3)
            breakdown["逆向加分"] = (10.0 if sentiment_value <= 25 else 3.0)
    elif tech_direction == "short":
        if sentiment_bias in ("fearful", None):
            resonance = True
            signal_bonus += 8
            breakdown["共振加分"] = 8.0
        elif sentiment_bias == "greedy":
            divergence = True
            signal_bonus += (10 if sentiment_value >= 75 else 3)
            breakdown["逆向加分"] = (10.0 if sentiment_value >= 75 else 3.0)

    if tech_direction is None and sentiment_bias is not None:
        if sentiment_value <= 20 or sentiment_value >= 80:
            signal_penalty += 10
            breakdown["情绪极端无技术确认"] = -10.0
            risk_msgs.append("情绪极端但技术面未确认")

    # --- ⭐ 入场信号质量 + 独立信号计数 ---
    best_entry: Optional[EntrySignal] = None
    independent_count = 0
    signal_details: list[str] = []

    if entry_signals:
        best_entry = max(entry_signals, key=lambda e: e.confidence)
        entry_bonus = best_entry.confidence * 5
        signal_bonus += entry_bonus
        breakdown["入场信号"] = round(entry_bonus, 1)

        # 独立信号计数
        if state:
            independent_count, signal_details = _count_independent_signals(
                technical, entry_signals, state
            )
        else:
            independent_count = 1

        # H2/H3 额外加分
        if best_entry.type in ("H2", "H3", "wedge_break"):
            signal_bonus += 3
            breakdown["高质量入场形态"] = 3.0

    # --- ⭐ 多信号共振评分（来自案例001） ---
    if independent_count >= 5:
        signal_bonus += 12
        breakdown["多信号共振(5+)"] = 12.0
    elif independent_count >= 4:
        signal_bonus += 8
        breakdown["多信号共振(4)"] = 8.0
    elif independent_count >= 3:
        signal_bonus += 5
        breakdown["多信号共振(3)"] = 5.0

    # --- 合成得分 ---
    raw = tech_weighted + sentiment_weighted + signal_bonus - signal_penalty
    final_score = int(round(max(0, min(100, raw))))

    # --- 方向和确信度 ---
    if tech_direction == "long":
        direction = "偏多"
    elif tech_direction == "short":
        direction = "偏空"
    elif sentiment_bias == "greedy" and sentiment_value >= 70:
        direction = "偏多"
    elif sentiment_bias == "fearful" and sentiment_value <= 30:
        direction = "偏空"
    else:
        direction = "中性"

    if final_score >= 75:
        conviction = "高确信度"
    elif final_score >= 55:
        conviction = "中等确信度"
    elif final_score >= 35:
        conviction = "低确信度"
    else:
        conviction = "无信号"
        direction = "中性"

    # --- ⭐ 入场确认检查 ---
    status = _check_confirmation(df, best_entry)

    # --- ⭐ 盈亏比计算 ---
    rr_ratio = 0.0
    stop_loss = 0.0
    take_profit = 0.0
    entry_price = 0.0
    if best_entry:
        stop_loss = best_entry.stop_loss
        take_profit = best_entry.target
        entry_price = best_entry.entry_price
        rr_ratio = _calc_rr_ratio(entry_price, stop_loss, take_profit, best_entry.direction)

        if rr_ratio < MIN_RR_RATIO and rr_ratio > 0:
            signal_penalty += 5
            breakdown["盈亏比不足"] = -5.0
            risk_msgs.append(f"盈亏比 {rr_ratio:.1f}:1 (要求≥{MIN_RR_RATIO}:1)")

    # --- 信号是否值得通知 ---
    if independent_count < 3 and conviction not in ("高确信度",):
        risk_msgs.append(f"独立信号不足({independent_count}<3)，观望")
    if status == SignalStatus.REJECTED:
        risk_msgs.append("入场信号已被否定(跌破止损)")
    if status == SignalStatus.PENDING and conviction != "无信号":
        risk_msgs.append("信号待确认，等待下一根K线")

    # --- 风险 ---
    if sentiment_value >= 80:
        risk_msgs.append("极度贪婪")
    elif sentiment_value <= 20:
        risk_msgs.append("极度恐惧")
    if resonance and final_score >= 75:
        risk_msgs.append("共振顺势，小心反转")
    if divergence:
        risk_msgs.append("背离入场，严格止损")

    summary = _build_summary(final_score, direction, conviction, status,
                             independent_count, rr_ratio)

    return SignalOutput(
        score=final_score, direction=direction, conviction=conviction,
        status=status, breakdown=breakdown,
        technical_score=technical, sentiment_result=sentiment,
        entry_signals=entry_signals,
        independent_count=independent_count, min_independent_required=3,
        rr_ratio=rr_ratio, stop_loss=stop_loss, take_profit=take_profit,
        entry_price=entry_price,
        summary=summary, risk_warning="; ".join(risk_msgs) if risk_msgs else "",
    )


def _build_summary(score: int, direction: str, conviction: str,
                   status: SignalStatus, independent_count: int,
                   rr_ratio: float) -> str:
    parts = [f"{conviction}{direction} ({score}分)"]
    if status == SignalStatus.CONFIRMED:
        parts.append("| 信号已确认")
    elif status == SignalStatus.PENDING:
        parts.append("| 信号待确认")
    elif status == SignalStatus.REJECTED:
        parts.append("| 信号被否定")
    if independent_count >= 3:
        parts.append(f"| {independent_count}信号共振")
    if rr_ratio >= MIN_RR_RATIO:
        parts.append(f"| RR {rr_ratio:.1f}:1")
    return " ".join(parts)


# ======================================================================
# 通知决策
# ======================================================================

def should_notify(signal: SignalOutput) -> tuple[bool, str]:
    """判断是否应该发送交易通知。

    条件:
      1. 信号已确认 (CONFIRMED)
      2. 评分 ≥ 70 或 ≤ 30
      3. 独立信号 ≥ 3
      4. 盈亏比 ≥ 2:1
    """
    if signal.status not in (SignalStatus.CONFIRMED, SignalStatus.PENDING):
        return False, f"信号状态: {signal.status.value}"

    if signal.independent_count < signal.min_independent_required:
        return False, f"独立信号不足 ({signal.independent_count}/{signal.min_independent_required})"

    if signal.rr_ratio > 0 and signal.rr_ratio < MIN_RR_RATIO:
        return False, f"盈亏比不足 ({signal.rr_ratio:.1f}:1 < {MIN_RR_RATIO}:1)"

    if signal.score >= 70:
        return True, f"做多信号 {signal.score}分"
    elif signal.score <= 30:
        return True, f"做空信号 {signal.score}分"

    return False, f"评分中性 ({signal.score}分)"


# ======================================================================
# 一站式入口
# ======================================================================

def analyze_full(df: pd.DataFrame, symbol: str = None) -> SignalOutput:
    logger.info("综合分析...")
    tech_result = analyze_technicals(df)
    tech_score = tech_result["technical_score"]
    state = tech_result["state"]
    all_entries = (tech_result["entry_signals"] +
                   tech_result["wedges"] +
                   tech_result["failed_breakouts"] +
                   tech_result.get("bear_bar_longs", []) +
                   tech_result.get("support_betrayals", []) +
                   tech_result.get("climax_warnings", []) +
                   tech_result.get("double_bottoms", []) +
                   tech_result.get("ema_signals", []) +
                   tech_result.get("final_flags", []) +
                   tech_result.get("vacuum_effects", []) +
                   tech_result.get("horizontal_srs", []) +
                   tech_result.get("measuring_gaps", []) +
                   tech_result.get("spike_channels", []) +
                   tech_result.get("trend_resumptions", []))

    sentiment_result = get_full_sentiment(symbol)
    signal = compute_signal(df, tech_score, sentiment_result, all_entries, state)
    logger.info(f"信号: {signal.score}/100 {signal.direction} {signal.status.value} "
                f"信号数{signal.independent_count} RR{signal.rr_ratio:.1f}")
    return signal

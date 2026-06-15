"""宏观风险感知 — 国内期货版

风险来源:
  1. 市场波动率（近期振幅扩大 = 风险升高）
  2. 基差异常（现货/期货大幅偏离）
  3. 持仓量突变（大资金进出）
  4. 综合风险等级 + 仓位建议系数
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

import numpy as np
import pandas as pd

from src.collector import get_db, PRIMARY_SYMBOL

logger = logging.getLogger("macros")


@dataclass
class MacroRisk:
    risk_level: str       # low / medium / high
    risk_score: float     # 0-100, 越高越危险
    volatility: float     # 近期波动率%
    position_coefficient: float  # 仓位系数 (0-1)
    reasons: list


def assess_macro_risk(symbol: str = None) -> MacroRisk:
    """评估当前宏观风险"""
    sym = symbol or PRIMARY_SYMBOL
    db = get_db()
    reasons = []

    # 1. 波动率 — 看日线最近20天
    df_daily = db.get_klines(sym, "daily", limit=20)
    volatility = 0.0
    if len(df_daily) >= 10:
        returns = df_daily["close"].pct_change().dropna()
        volatility = float(returns.std() * np.sqrt(252) * 100)  # 年化波动率%
        if volatility > 30:
            reasons.append(f"波动率偏高({volatility:.0f}%)")
        elif volatility < 15:
            reasons.append(f"波动率正常({volatility:.0f}%)")

    # 2. 最近振幅
    atr_pct = 0.0
    if len(df_daily) >= 5:
        df_daily["range_pct"] = (df_daily["high"] - df_daily["low"]) / df_daily["close"] * 100
        atr_pct = float(df_daily["range_pct"].tail(5).mean())
        if atr_pct > 3:
            reasons.append(f"日内振幅大({atr_pct:.1f}%)")

    # 3. 持仓量方向（从 sentiment 获取）
    try:
        from src.sentiment import get_position_sentiment
        pos = get_position_sentiment(sym)
        if pos:
            if abs(pos.change_5d) > 15:
                reasons.append(f"持仓异动({pos.change_5d:+.1f}%/5d)")
    except Exception:
        pass

    # 4. 综合评分
    risk_score = min(100, (volatility * 1.5 + atr_pct * 5))
    risk_score = max(0, risk_score)

    if risk_score < 30:
        level = "low"
        pos_coef = 1.0
    elif risk_score < 60:
        level = "medium"
        pos_coef = 0.8
    else:
        level = "high"
        pos_coef = 0.5

    if not reasons:
        reasons.append("宏观环境平稳")

    return MacroRisk(
        risk_level=level,
        risk_score=round(risk_score, 1),
        volatility=round(volatility, 1),
        position_coefficient=pos_coef,
        reasons=reasons,
    )


def calculate_position_size(capital: float, risk_pct: float,
                            pos_coef: float, entry: float,
                            stop: float) -> dict:
    """计算仓位大小"""
    risk_amount = capital * (risk_pct / 100) * pos_coef
    stop_distance = abs(entry - stop)
    if stop_distance == 0:
        return {"quantity": 0, "risk_amount": 0,
                "capital_usage_pct": 0, "stop_distance": 0}
    quantity = risk_amount / stop_distance
    margin_used = entry * quantity
    return {
        "quantity": round(quantity, 2),
        "risk_amount": round(risk_amount, 2),
        "capital_usage_pct": round(margin_used / capital * 100, 1),
        "stop_distance": round(stop_distance, 2),
    }

"""Phase 4: 五角色PA委员会深度评审 + 正式报告生成

五角色：
  1. 市场结构师 — 趋势/阶段/通道/关键价位
  2. 信号K线分析师 — PA信号类型/质量/可靠性
  3. 量能资金分析师 — 量价配合/资金流向
  4. 风险控制官 — R:R/止损/A股特有风险
  5. 首席交易员 — 综合评审+交易计划

输出：
  - top5_committee.json (结构化评审数据)
  - daily_report.md (完整日报)
  - daily_report_feishu.md (飞书文档版)
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field, asdict
from datetime import date
from pathlib import Path
from typing import Optional

import akshare as ak
import numpy as np
import pandas as pd

from .stock_scanner import (
    PASignal, PAStructure, StockSnapshot, ScanResult,
    _fetch_daily_kline, _normalize_columns, OUTPUT_DIR,
)

logger = logging.getLogger("pa_pipeline.committee")


# ======================================================================
# Role data structures
# ======================================================================

@dataclass
class RoleReport:
    """单角色评审报告"""
    role_name: str
    score: int           # 0-100
    summary: str         # 一句话结论
    detail: str          # 详细分析
    flags: list[str] = field(default_factory=list)  # 关注点/风险点


@dataclass
class CommitteeReport:
    """五角色委员会对单只股票的完整评审"""
    code: str
    name: str
    direction: str       # "做多" | "做空"
    signal_type: str
    # 五角色
    structure_analyst: RoleReport
    signal_bar_analyst: RoleReport
    volume_analyst: RoleReport
    risk_officer: RoleReport
    head_trader: RoleReport
    # 综合
    composite_score: int  # 0-100
    final_decision: str   # "强烈买入" | "买入" | "谨慎买入"
    pa_reasons: dict      # {结构层面, 信号层面, 量能层面, 风险层面}
    trade_plan: dict      # {入场价, 止损价, 止盈1, 止盈2, 仓位%, R:R}
    falsification: list[str]  # 证伪条件


# ======================================================================
# Role 1: 市场结构师
# ======================================================================

def _analyze_structure_role(
    signal: PASignal, df: pd.DataFrame,
) -> RoleReport:
    """角色1: 市场结构师 — 深度结构分析"""
    struct = signal.structure
    if struct is None:
        return RoleReport("市场结构师", 0, "结构数据缺失", "", [])

    score = struct.structure_score

    # 详细文字
    stage_desc = {1: "Spike急涨/急跌", 2: "窄通道强趋势", 3: "宽通道趋势减弱", 4: "交易区间"}
    detail_parts = [
        f"趋势判定：{struct.trend}",
        f"阶段：阶段{struct.stage}（{stage_desc.get(struct.stage, '未知')}）",
        f"通道类型：{struct.channel}",
        f"摆动结构：{struct.swing_structure}",
        f"20EMA方向：{struct.ema20_direction}（值{struct.key_levels.get('ema20', 'N/A')}）",
    ]

    if struct.key_levels.get("support"):
        detail_parts.append(f"关键支撑：{struct.key_levels['support']}")
    if struct.key_levels.get("resistance"):
        detail_parts.append(f"关键阻力：{struct.key_levels['resistance']}")

    # 结构风险
    flags = []
    if struct.stage == 3:
        flags.append("宽通道趋势减弱，回调可能变反转")
    elif struct.stage == 4:
        flags.append("交易区间中，突破方向不确定")
    if struct.ema20_direction == "走平":
        flags.append("20EMA走平，趋势暂停")
    if struct.swing_structure in ("混乱", "无序列"):
        flags.append("摆动结构不清晰，PA可靠性下降")

    summary = f"{struct.trend}阶段{struct.stage}，{'结构清晰' if score >= 60 else '结构有待确认'}"

    return RoleReport(
        role_name="市场结构师",
        score=score,
        summary=summary,
        detail="\n".join(detail_parts),
        flags=flags,
    )


# ======================================================================
# Role 2: 信号K线分析师
# ======================================================================

def _analyze_signal_role(
    signal: PASignal, df: pd.DataFrame, struct: Optional[PAStructure],
) -> RoleReport:
    """角色2: 信号K线分析师"""
    if signal.signal_type is None:
        return RoleReport("信号K线分析师", 0, "未识别到PA信号", "", [])

    # 从K线数据提取更详细的信息
    df = _normalize_columns(df)
    close = df["close"].values
    open_ = df["open"].values
    high = df["high"].values
    low = df["low"].values
    vol = df["volume"].values

    n = len(close)
    body = abs(close[-1] - open_[-1])
    total_range = high[-1] - low[-1]
    body_pct = body / total_range * 100 if total_range > 0 else 0
    close_pos = (close[-1] - low[-1]) / total_range * 100 if total_range > 0 else 50
    avg_range = np.mean(high[-4:-1] - low[-4:-1])
    range_ratio = total_range / avg_range if avg_range > 0 else 1
    avg_vol_5 = np.mean(vol[-6:-1]) if len(vol) >= 6 else vol[-1]
    vol_ratio = vol[-1] / avg_vol_5 if avg_vol_5 > 0 else 1

    # 信号质量评分
    quality_score = 0
    if body_pct >= 60:
        quality_score += 30
    elif body_pct >= 50:
        quality_score += 25
    elif body_pct >= 35:
        quality_score += 15
    else:
        quality_score += 5

    if (signal.direction == "多" and close_pos > 60) or (signal.direction == "空" and close_pos < 40):
        quality_score += 25
    elif (signal.direction == "多" and close_pos > 40) or (signal.direction == "空" and close_pos < 60):
        quality_score += 15

    if range_ratio >= 1.5:
        quality_score += 25
    elif range_ratio >= 1.0:
        quality_score += 15

    if vol_ratio >= 1.5:
        quality_score += 20
    elif vol_ratio >= 1.0:
        quality_score += 10

    quality_score = min(100, quality_score)

    detail_parts = [
        f"信号类型：{signal.signal_type}",
        f"实体/振幅：{body_pct:.0f}% {'✅强K线' if body_pct >= 50 else '⚠️力量不足'}",
        f"收盘位置：{close_pos:.0f}%（{'顶部' if close_pos > 60 else '底部' if close_pos < 40 else '中间'}）",
        f"振幅vs前3均值：{range_ratio:.1f}x {'✅放大' if range_ratio >= 1.5 else '正常' if range_ratio >= 1.0 else '缩量'}",
        f"量比：{vol_ratio:.1f}x",
    ]

    flags = []
    if body_pct < 45:
        flags.append("K线实体不足，信号力量偏弱")
    if range_ratio < 1.0:
        flags.append("振幅缩小，市场不活跃")
    if vol_ratio < 1.0:
        flags.append("量能不足，资金确认弱")

    summary = f"{signal.signal_type}·质量{'强' if quality_score >= 70 else '中' if quality_score >= 50 else '弱'}"

    return RoleReport(
        role_name="信号K线分析师",
        score=quality_score,
        summary=summary,
        detail="\n".join(detail_parts),
        flags=flags,
    )


# ======================================================================
# Role 3: 量能资金分析师
# ======================================================================

def _analyze_volume_role(
    signal: PASignal, snapshot: Optional[StockSnapshot],
) -> RoleReport:
    """角色3: 量能资金分析师"""
    if snapshot is None:
        return RoleReport("量能资金分析师", 50, "量能数据不足", "", [])

    score = 50
    detail_parts = [
        f"当日成交额：{snapshot.amount/1e8:.1f}亿",
        f"换手率：{snapshot.turnover_rate:.2f}%",
        f"流通市值：{snapshot.circ_market_cap:.1f}亿",
    ]

    flags = []

    # 成交额评分
    amount_yi = snapshot.amount / 1e8
    if amount_yi > 10:
        score += 15
        detail_parts.append("成交额>10亿，流动性充裕")
    elif amount_yi > 3:
        score += 10
        detail_parts.append("成交额>3亿，流动性正常")
    elif amount_yi > 1:
        score += 5
    else:
        score -= 10
        flags.append("成交额偏低，流动性不足")

    # 换手率评分
    if 3 <= snapshot.turnover_rate <= 10:
        score += 15
        detail_parts.append("换手率合理(3-10%)")
    elif 1 <= snapshot.turnover_rate < 3:
        score += 8
        detail_parts.append("换手率偏低但可接受")
    elif snapshot.turnover_rate > 15:
        score -= 10
        flags.append("换手率>15%，警惕对倒")
    else:
        score += 3

    # 流通市值
    if 50 <= snapshot.circ_market_cap <= 500:
        score += 10
        detail_parts.append("流通市值适中(50-500亿)")
    elif snapshot.circ_market_cap > 500:
        score += 5
        detail_parts.append("大盘股，波动可能偏小")
    else:
        score -= 5
        flags.append("小盘股，波动风险大")

    score = max(0, min(100, score))

    summary = f"量能{'健康' if score >= 70 else '正常' if score >= 50 else '偏弱'}"

    return RoleReport(
        role_name="量能资金分析师",
        score=score,
        summary=summary,
        detail="\n".join(detail_parts),
        flags=flags,
    )


# ======================================================================
# Role 4: 风险控制官
# ======================================================================

def _analyze_risk_role(
    signal: PASignal, snapshot: Optional[StockSnapshot],
) -> RoleReport:
    """角色4: 风险控制官"""
    rr = signal.rr_ratio
    max_loss = signal.max_loss_pct

    score = 50
    detail_parts = []
    flags = []

    # R:R
    if rr is not None:
        if rr >= 3:
            score += 25
            detail_parts.append(f"R:R={rr:.1f}:1 ✅ 优秀")
        elif rr >= 2:
            score += 15
            detail_parts.append(f"R:R={rr:.1f}:1 ✅ 合格")
        elif rr >= 1.5:
            score += 5
            detail_parts.append(f"R:R={rr:.1f}:1 ⚠️ 勉强")
            flags.append(f"R:R仅{rr:.1f}:1，空间偏小")
        else:
            score -= 15
            detail_parts.append(f"R:R={rr:.1f}:1 ❌ 不足")
            flags.append("R:R不足，不建议交易")
    else:
        detail_parts.append("R:R：未计算（无明确信号方向）")

    # 最大亏损
    if max_loss is not None:
        if max_loss < 3:
            score += 15
            detail_parts.append(f"单笔最大亏损：{max_loss:.1f}% ✅")
        elif max_loss < 5:
            score += 10
            detail_parts.append(f"单笔最大亏损：{max_loss:.1f}%")
        else:
            score -= 5
            flags.append(f"单笔最大亏损{max_loss:.1f}%偏高")

    # A股风险
    if signal.risk_flags:
        for flag in signal.risk_flags:
            score -= 5
            detail_parts.append(f"⚠️ {flag}")
            flags.append(flag)

    # 止损合理性
    if signal.stop_loss and signal.entry_price:
        if signal.direction == "多":
            sl_pct = (signal.entry_price - signal.stop_loss) / signal.entry_price * 100
        else:
            sl_pct = (signal.stop_loss - signal.entry_price) / signal.entry_price * 100
        detail_parts.append(f"止损距离：{sl_pct:.1f}%")

    score = max(0, min(100, score))
    summary = f"风险{'可控' if score >= 70 else '偏高，注意仓位' if score >= 50 else '较大，谨慎参与'}"

    return RoleReport(
        role_name="风险控制官",
        score=score,
        summary=summary,
        detail="\n".join(detail_parts),
        flags=flags,
    )


# ======================================================================
# Role 5: 首席交易员
# ======================================================================

def _synthesize_trader(
    signal: PASignal,
    r1: RoleReport, r2: RoleReport, r3: RoleReport, r4: RoleReport,
) -> RoleReport:
    """角色5: 首席交易员 — 综合前四角色意见"""
    # 加权综合
    composite = int(
        r1.score * 0.30 +
        r2.score * 0.30 +
        r3.score * 0.20 +
        r4.score * 0.20
    )

    # 决策
    if composite >= 75:
        decision = "强烈买入"
    elif composite >= 65:
        decision = "买入"
    else:
        decision = "谨慎买入"

    # 冲突检测
    conflicts = []
    if r1.score >= 70 and r4.score < 40:
        conflicts.append("结构好但风险高，R:R可能不够")
    if r2.score >= 70 and r1.score < 40:
        conflicts.append("信号强但结构弱，可能假信号")
    if r3.score < 40:
        conflicts.append("量能不配合，信号可靠性下降")

    detail_parts = [
        f"综合评分：{composite}/100",
        f"决策：{decision}",
    ]
    if conflicts:
        detail_parts.append("⚠️ 角色意见冲突：")
        detail_parts.extend(f"  • {c}" for c in conflicts)
    else:
        detail_parts.append("✅ 各角色意见一致，无显著冲突")

    flags = []
    if composite < 60:
        flags.append("综合评分偏低，严格止损")
    if conflicts:
        flags.extend(conflicts)

    summary = f"{decision}·综合{composite}分{'·角色一致' if not conflicts else '·有分歧'}"

    return RoleReport(
        role_name="首席交易员",
        score=composite,
        summary=summary,
        detail="\n".join(detail_parts),
        flags=flags,
    )


# ======================================================================
# PA理由生成
# ======================================================================

def _generate_pa_reasons(
    signal: PASignal,
    r1: RoleReport, r2: RoleReport,
) -> dict:
    """生成PA符合理由（四层面）"""
    struct = signal.structure
    reasons = {
        "结构层面": "",
        "信号层面": "",
        "量能层面": "",
        "风险层面": "",
    }

    # 结构层面
    if struct:
        reasons["结构层面"] = (
            f"该股日线处于{struct.trend}，属于Al Brooks阶段{struct.stage}"
            f"（{'Spike急涨' if struct.stage == 1 else '窄通道强趋势' if struct.stage == 2 else '宽通道趋势减弱' if struct.stage == 3 else '交易区间'}），"
            f"通道类型为{struct.channel}。"
            f"摆动结构为{struct.swing_structure}，"
            f"20EMA{struct.ema20_direction}。"
            f"{'结构清晰，适合PA交易。' if struct.structure_score >= 60 else '结构有待进一步确认。'}"
        )
    else:
        reasons["结构层面"] = "结构数据不足，无法完整分析。"

    # 信号层面
    reasons["信号层面"] = (
        f"识别到PA信号：{signal.signal_type or '无明确信号'}。"
        f"{r2.detail.replace(chr(10), '；')}"
    )

    # 量能层面
    reasons["量能层面"] = r3.detail.replace(chr(10), '；')

    # 风险层面
    reasons["风险层面"] = (
        f"R:R={signal.rr_ratio or 'N/A'}，"
        f"止损{signal.stop_loss or '未设'}，"
        f"最大亏损约{signal.max_loss_pct or 'N/A'}%。"
        f"{'；'.join(signal.risk_flags) if signal.risk_flags else '无显著A股特有风险。'}"
    )

    return reasons


def _generate_falsification(signal: PASignal) -> list[str]:
    """生成证伪条件"""
    conditions = []

    if signal.direction == "多":
        if signal.stop_loss:
            conditions.append(f"如果盘中跌破止损价{signal.stop_loss}，立即止损离场")
        conditions.append("如果开盘30分钟跌幅>2%，放弃入场")
        conditions.append("如果上证指数开盘30分钟跌幅>1%，暂缓所有买入")
        if signal.structure and signal.structure.key_levels.get("support"):
            conditions.append(f"如果收盘跌破支撑{signal.structure.key_levels['support']}，结构破坏，退出")
    else:
        if signal.stop_loss:
            conditions.append(f"如果盘中突破止损价{signal.stop_loss}，立即止损离场")
        conditions.append("如果开盘30分钟涨幅>2%，放弃入场（A股做空受限，仅限融券）")

    conditions.append("如果当日成交额<前日50%，流动性不足，不参与")

    return conditions


# ======================================================================
# 主入口: 对TOP5运行五角色评审
# ======================================================================

def run_committee(
    top5: list[PASignal],
    snapshots: list[StockSnapshot],
) -> list[CommitteeReport]:
    """对TOP5每只股票运行五角色委员会评审"""
    snap_map = {s.code: s for s in snapshots}
    reports = []

    for signal in top5:
        code = signal.code
        snap = snap_map.get(code)

        # 获取K线数据
        df = _fetch_daily_kline(code)

        # 角色1: 市场结构师
        r1 = _analyze_structure_role(signal, df)

        # 角色2: 信号K线分析师
        r2 = _analyze_signal_role(signal, df, signal.structure)

        # 角色3: 量能资金分析师
        r3 = _analyze_volume_role(signal, snap)

        # 角色4: 风险控制官
        r4 = _analyze_risk_role(signal, snap)

        # 角色5: 首席交易员
        r5 = _synthesize_trader(signal, r1, r2, r3, r4)

        # PA理由
        pa_reasons = _generate_pa_reasons(signal, r1, r2)

        # 证伪条件
        falsification = _generate_falsification(signal)

        # 交易计划
        trade_plan = {
            "入场价": signal.entry_price,
            "止损价": signal.stop_loss,
            "止盈1": signal.target_1,
            "止盈2": signal.target_2,
            "R:R": signal.rr_ratio,
            "最大亏损%": signal.max_loss_pct,
            "建议仓位%": 2.0,  # 默认2%风险
        }

        reports.append(CommitteeReport(
            code=code,
            name=signal.name,
            direction="做多" if signal.direction == "多" else "做空" if signal.direction == "空" else "—",
            signal_type=signal.signal_type or "—",
            structure_analyst=r1,
            signal_bar_analyst=r2,
            volume_analyst=r3,
            risk_officer=r4,
            head_trader=r5,
            composite_score=r5.score,
            final_decision="强烈买入" if r5.score >= 75 else "买入" if r5.score >= 65 else "谨慎买入",
            pa_reasons=pa_reasons,
            trade_plan=trade_plan,
            falsification=falsification,
        ))

    return reports


def save_committee_result(reports: list[CommitteeReport], scan_date: str) -> Path:
    """保存五角色评审结果"""
    out_dir = OUTPUT_DIR / scan_date
    out_dir.mkdir(parents=True, exist_ok=True)

    data = {
        "date": scan_date,
        "top5": [asdict(r) for r in reports],
    }
    with open(out_dir / "top5_committee.json", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2, default=str)

    logger.info(f"五角色评审已保存至 {out_dir / 'top5_committee.json'}")
    return out_dir

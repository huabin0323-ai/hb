"""报告生成 — 生成完整日报Markdown和飞书文档版"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict
from datetime import date
from pathlib import Path
from typing import Optional

from .stock_scanner import ScanResult, PASignal, OUTPUT_DIR
from .committee import CommitteeReport
from .market_overview import MarketOverview

logger = logging.getLogger("pa_pipeline.report")


# ======================================================================
# Markdown 报告生成
# ======================================================================

def _format_price(p: Optional[float]) -> str:
    if p is None:
        return "—"
    return f"¥{p:.2f}"


def _format_pct(p: Optional[float]) -> str:
    if p is None:
        return "—"
    return f"{p:+.2f}%"


def _format_rr(r: Optional[float]) -> str:
    if r is None:
        return "—"
    return f"{r:.1f}:1"


def generate_daily_report(
    market: MarketOverview,
    scan: ScanResult,
    committee: list[CommitteeReport],
    prev_review: Optional[dict] = None,
) -> str:
    """生成完整日报 Markdown

    Args:
        market: Phase 0 大盘概览
        scan: Phase 1-3 扫描结果
        committee: Phase 4 五角色评审
        prev_review: 前一日回顾数据（如有）

    Returns:
        完整日报 Markdown 字符串
    """
    today = date.today().isoformat()
    lines = []

    # ===== 标题 =====
    lines.append(f"# 🔬 A股PA全量扫描日报 · {today}")
    lines.append("")
    lines.append(f"*报告由 PA Stock Discovery Pipeline 自动生成 · {today}*")
    lines.append("")

    # ===== 大盘环境 =====
    lines.append("---")
    lines.append("")
    lines.append("## 📊 大盘PA环境")
    lines.append("")
    lines.append("### 主要指数")
    lines.append("")
    lines.append("| 指数 | 收盘 | 涨跌 | 趋势 | 阶段 | 通道 | 20EMA |")
    lines.append("|------|:---:|:---:|------|:---:|------|------|")
    for idx in market.indices:
        lines.append(
            f"| {idx.name}({idx.code}) | {idx.close:.0f} | {idx.pct_change:+.2f}% | "
            f"{idx.trend} | {idx.stage} | {idx.channel} | {idx.ema20_direction} |"
        )
    lines.append("")

    lines.append("### 全市场")
    lines.append("")
    b = market.breadth
    lines.append(f"- 上涨 {b.up_count} / 下跌 {b.down_count} / 平盘 {b.flat_count}")
    lines.append(f"- 涨停 {b.limit_up_count} / 跌停 {b.limit_down_count}")
    lines.append(f"- 成交额 {b.total_volume_yi:.0f} 亿")
    lines.append("")

    if market.top_sectors:
        lines.append("### 领涨板块")
        lines.append("")
        lines.append("| 板块 | 涨跌幅 |")
        lines.append("|------|:---:|")
        for s in market.top_sectors:
            lines.append(f"| {s.name} | {s.pct_change:+.2f}% |")
        lines.append("")

    # PA环境评分
    env = market.pa_environment
    lines.append(f"### 🎯 PA环境评分: **{env.total}/100**")
    lines.append("")
    lines.append(f"- 趋势性: {env.trend_score:.0f}/40")
    lines.append(f"- 活跃度: {env.activity_score:.0f}/30")
    lines.append(f"- 结构性: {env.structure_score:.0f}/30")
    lines.append(f"- **结论: {env.verdict}**")
    lines.append(f"  - {env.description}")
    lines.append("")

    # ===== 昨日回顾（如有）=====
    if prev_review:
        lines.append("---")
        lines.append("")
        lines.append(f"## 📈 昨日回顾 ({prev_review.get('date', 'N/A')})")
        lines.append("")
        lines.append("### 混淆矩阵")
        lines.append("")
        m = prev_review.get("matrix", {})
        lines.append("|  | 实际盈利 | 实际亏损 |")
        lines.append("|------|:---:|:---:|")
        lines.append(f"| 🟢 买入信号 | {m.get('tp', 0)} ✅ | {m.get('fp', 0)} ❌ |")
        lines.append(f"| ⚪ 不动信号 | {m.get('fn', 0)} ⚠️ | {m.get('tn', 0)} ✅ |")
        lines.append("")

        metrics = prev_review.get("metrics", {})
        lines.append("### 核心指标")
        lines.append("")
        lines.append(f"| 指标 | 数值 |")
        lines.append(f"|------|:----:|")
        lines.append(f"| 胜率 | {metrics.get('win_rate', 'N/A')} |")
        lines.append(f"| 盈亏比 | {metrics.get('profit_factor', 'N/A')} |")
        lines.append(f"| 漏判率 | {metrics.get('miss_rate', 'N/A')} |")
        lines.append(f"| 准确率 | {metrics.get('accuracy', 'N/A')} |")
        lines.append("")

    # ===== 本日决策概览 =====
    lines.append("---")
    lines.append("")
    lines.append("## 📊 本日决策概览")
    lines.append("")
    lines.append(f"- 全市场扫描: **{scan.total_scanned}** 只")
    lines.append(f"- 粗筛通过: **{scan.phase1_passed}** 只")
    lines.append("")
    lines.append("| 决策类型 | 数量 | 占比 |")
    lines.append("|----------|:---:|:---:|")
    for k, v in scan.summary.items():
        pct = v / scan.phase1_passed * 100 if scan.phase1_passed > 0 else 0
        emoji = "🟢" if "买入" in k else "🟡" if "信号不够强" in k else "🔴"
        lines.append(f"| {emoji} {k} | {v} | {pct:.1f}% |")
    lines.append("")

    # 信号类型分布
    lines.append("### 信号类型分布")
    lines.append("")
    sig_dist = {}
    for s in scan.phase3_signals:
        st = s.signal_type or "无明确信号"
        sig_dist[st] = sig_dist.get(st, {"buy": 0, "wait": 0})
        if s.decision == "买入":
            sig_dist[st]["buy"] += 1
        else:
            sig_dist[st]["wait"] += 1

    lines.append("| 信号类型 | 总数 | 买入 | 不动 |")
    lines.append("|----------|:---:|:---:|:---:|")
    for sig, counts in sorted(sig_dist.items(), key=lambda x: x[1]["buy"] + x[1]["wait"], reverse=True):
        lines.append(f"| {sig} | {counts['buy']+counts['wait']} | {counts['buy']} | {counts['wait']} |")
    lines.append("")

    # ===== TOP5 深度评审 =====
    lines.append("---")
    lines.append("")
    lines.append("## 🏆 TOP 5 五角色PA委员会深度评审")
    lines.append("")

    for i, cr in enumerate(committee, 1):
        lines.append(f"### #{i} · {cr.name}({cr.code}) · {cr.direction} · 综合评分 {cr.composite_score}/100")
        lines.append("")
        lines.append(f"**信号类型：** {cr.signal_type}")
        lines.append(f"**最终决策：** 🟢 {cr.final_decision}")
        lines.append("")

        # 五角色评分表
        lines.append("| 角色 | 评分 | 结论 |")
        lines.append("|------|:---:|------|")
        lines.append(f"| 🔍 市场结构师 | {cr.structure_analyst.score} | {cr.structure_analyst.summary} |")
        lines.append(f"| 📊 信号K线分析师 | {cr.signal_bar_analyst.score} | {cr.signal_bar_analyst.summary} |")
        lines.append(f"| 💰 量能资金分析师 | {cr.volume_analyst.score} | {cr.volume_analyst.summary} |")
        lines.append(f"| 🛡️ 风险控制官 | {cr.risk_officer.score} | {cr.risk_officer.summary} |")
        lines.append(f"| 🎯 首席交易员 | {cr.head_trader.score} | {cr.head_trader.summary} |")
        lines.append("")

        # PA符合理由
        lines.append("#### 🎯 PA符合理由")
        lines.append("")
        pr = cr.pa_reasons
        for level in ["结构层面", "信号层面", "量能层面", "风险层面"]:
            text = pr.get(level, "")
            if text:
                lines.append(f"**{level}：** {text}")
                lines.append("")
        lines.append("")

        # 交易计划
        lines.append("#### 💰 交易计划")
        lines.append("")
        tp = cr.trade_plan
        lines.append("| 项目 | 价位 | 说明 |")
        lines.append("|------|------|------|")
        lines.append(f"| 入场价 | {_format_price(tp.get('入场价'))} | 次日开盘价参考 |")
        lines.append(f"| 止损价 | {_format_price(tp.get('止损价'))} | 亏损 {_format_pct(tp.get('最大亏损%'))} |")
        lines.append(f"| 止盈1 | {_format_price(tp.get('止盈1'))} | R:R = {_format_rr(tp.get('R:R'))} |")
        lines.append(f"| 止盈2 | {_format_price(tp.get('止盈2'))} | 测量目标 |")
        lines.append(f"| 建议仓位 | {tp.get('建议仓位%', 2.0)}% | 按2%单笔风险上限 |")
        lines.append("")

        # 证伪条件
        lines.append("#### ⚠️ 证伪条件")
        lines.append("")
        for fc in cr.falsification:
            lines.append(f"- [ ] {fc}")
        lines.append("")

        # 各角色详情（折叠）
        lines.append("<details>")
        lines.append("<summary>📋 各角色详细分析</summary>")
        lines.append("")
        for role_name, role in [
            ("1. 市场结构师", cr.structure_analyst),
            ("2. 信号K线分析师", cr.signal_bar_analyst),
            ("3. 量能资金分析师", cr.volume_analyst),
            ("4. 风险控制官", cr.risk_officer),
            ("5. 首席交易员", cr.head_trader),
        ]:
            lines.append(f"**{role_name}** (评分: {role.score})")
            lines.append(f"{role.detail}")
            if role.flags:
                lines.append(f"关注点: {'; '.join(role.flags)}")
            lines.append("")
        lines.append("</details>")
        lines.append("")

    # ===== 免责声明 =====
    lines.append("---")
    lines.append("")
    lines.append("## ⚠️ 免责声明")
    lines.append("")
    lines.append("> 本报告仅供PA策略研究参考，**不构成任何投资建议**。")
    lines.append("> 所有信号基于Al Brooks价格行为学方法论，概率思维 ≠ 确定性。")
    lines.append("> A股实行T+1交易制度，今日买入最早明日卖出。")
    lines.append("> **严格止损。过往表现不代表未来收益。**")
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append(f"*🤖 由 PA Stock Discovery Pipeline v0.1 自动生成 · {today}*")

    return "\n".join(lines)


def generate_feishu_doc(report_md: str) -> str:
    """将完整报告转为飞书文档格式（简化Markdown，兼容飞书）"""
    # 飞书文档支持大部分Markdown，去掉HTML标签
    import re
    doc = re.sub(r"<details>.*?</details>", lambda m: m.group(0).replace("<details>", "").replace("</details>", "").replace("<summary>", "**").replace("</summary>", "**"), report_md, flags=re.DOTALL)
    doc = doc.replace("<details>", "").replace("</details>", "").replace("<summary>", "**").replace("</summary>", "**")
    return doc


def save_reports(
    report_md: str,
    feishu_doc: str,
    scan_date: str,
) -> tuple[Path, Path]:
    """保存日报到文件"""
    out_dir = OUTPUT_DIR / scan_date
    out_dir.mkdir(parents=True, exist_ok=True)

    report_path = out_dir / "daily_report.md"
    report_path.write_text(report_md, encoding="utf-8")

    feishu_path = out_dir / "daily_report_feishu.md"
    feishu_path.write_text(feishu_doc, encoding="utf-8")

    logger.info(f"日报已保存: {report_path}")
    return report_path, feishu_path

"""飞书推送 — webhook 推送中文消息 + 创建飞书文档"""

from __future__ import annotations

import json
import logging
from datetime import date
from pathlib import Path
from typing import Optional

import requests

from src.feishu import create_doc

from .market_overview import MarketOverview
from .stock_scanner import ScanResult

logger = logging.getLogger("pa_pipeline.feishu")

OUTPUT_DIR = Path("D:/hb/output")
FEISHU_DOCS_INDEX = OUTPUT_DIR / "feishu_docs.json"

WEBHOOK_URL = "https://open.feishu.cn/open-apis/bot/v2/hook/265e665c-fae5-4eba-af40-223613b6b281"


def _send_webhook(text: str) -> bool:
    try:
        resp = requests.post(WEBHOOK_URL, json={
            "msg_type": "text",
            "content": {"text": text},
        }, timeout=10)
        ok = resp.json().get("code") == 0
        if not ok:
            logger.warning(f"webhook失败: {resp.json()}")
        return ok
    except Exception as e:
        logger.error(f"webhook异常: {e}")
        return False


# ======================================================================
# 推送 #1: 大盘PA环境 + TOP5速览 + 200只决策摘要
# ======================================================================

def push_market_overview(market: MarketOverview, scan: ScanResult) -> bool:
    """15:10 - 大盘PA环境 + TOP5买入速览 + 200只决策分布"""
    today = date.today().isoformat()
    env = market.pa_environment
    b = market.breadth

    # ---- 大盘指数 ----
    text = f"大盘PA环境 - {today}\n\n-- 主要指数 --"
    for idx in market.indices:
        arrow = '↗' if idx.ema20_direction == '上升' else '↘' if idx.ema20_direction == '下降' else '→'
        text += f"\n{idx.name}: {idx.close:.0f} {idx.pct_change:+.2f}% | {idx.trend} 阶段{idx.stage} | 20EMA{arrow}"

    # ---- 全市场 ----
    text += f"\n\n-- 全市场 --"
    text += f"\n上涨 {b.up_count} / 下跌 {b.down_count} | 成交 {b.total_volume_yi:.0f}亿"
    text += f"\n涨停 {b.limit_up_count} / 跌停 {b.limit_down_count}"

    # ---- 领涨板块 ----
    if market.top_sectors:
        text += "\n\n-- 领涨板块 --"
        for s in market.top_sectors[:3]:
            text += f"\n{s.name} {s.pct_change:+.2f}%"

    # ---- PA环境评分 ----
    text += f"\n\n-- PA环境评分: {env.total}/100 --"
    text += f"\n趋势性: {env.trend_score:.0f}/40 | 活跃度: {env.activity_score:.0f}/30 | 结构性: {env.structure_score:.0f}/30"
    text += f"\n=> {env.verdict}"

    # ---- 200只决策分布 ----
    text += f"\n\n-- 今日决策分布 (共{scan.phase1_passed}只候选) --"
    for k, v in scan.summary.items():
        emoji = "买入" if "买入" in k else "信号偏弱" if "信号不够强" in k else "无信号" if "无有效" in k or "无信号" in k else "空间不足" if "空间" in k else "风险"
        pct = v / scan.phase1_passed * 100 if scan.phase1_passed > 0 else 0
        text += f"\n{emoji}: {v}只 ({pct:.1f}%)"

    # ---- TOP5 买入信号速览 ----
    if scan.top5:
        text += "\n\n-- TOP5 买入信号 --"
        for i, s in enumerate(scan.top5, 1):
            direction = "做多" if s.direction == "多" else "做空" if s.direction == "空" else "-"
            entry = f"入场{s.entry_price:.2f}" if s.entry_price else ""
            stop = f"止损{s.stop_loss:.2f}" if s.stop_loss else ""
            target = f"止盈{s.target_1:.2f}" if s.target_1 else ""
            rr = f"R:R={s.rr_ratio:.1f}" if s.rr_ratio else ""
            text += f"\n{i}. {s.name}({s.code}) {s.signal_type} {direction} {s.total_score}分 {entry} {stop} {target} {rr}"

    text += "\n\n不构成投资建议"

    return _send_webhook(text)


# ======================================================================
# 推送 #2: 飞书文档链接
# ======================================================================

def push_daily_report_doc(report_md: str, scan_date: str) -> Optional[str]:
    """15:20 - 创建飞书文档 + 推送链接"""
    doc_title = f"PA扫描日报 - {scan_date}"
    try:
        doc = create_doc(doc_title, "")
        doc_url = doc["url"]
        _save_doc_index(scan_date, "daily", doc["document_id"], doc_url)

        text = (
            f"PA扫描完整日报 - {scan_date}\n"
            f"{doc_url}\n\n"
            f"包含: 大盘PA环境 / TOP5五角色评审 / 200只全量决策矩阵\n"
            f"不构成投资建议"
        )
        _send_webhook(text)
        logger.info(f"推送#2成功: {doc_url}")
        return doc_url
    except Exception as e:
        logger.error(f"推送#2失败: {e}")
        return None


# ======================================================================
# 推送 #3: 回顾混淆矩阵
# ======================================================================

def push_review(review_data: dict) -> bool:
    """次日15:10 - 回顾混淆矩阵"""
    m = review_data.get("matrix", {})
    metrics = review_data.get("metrics", {})
    top5_review = review_data.get("top5_review", [])
    fix = review_data.get("strategy_fix", "")

    tp, fp = m.get("tp", 0), m.get("fp", 0)
    fn, tn = m.get("fn", 0), m.get("tn", 0)

    text = f"PA回顾 - {review_data.get('date', 'N/A')}\n"
    text += f"\n-- 混淆矩阵 --"
    text += f"\n买入信号: 盈利 {tp}只 / 亏损 {fp}只 (胜率: {metrics.get('win_rate', 'N/A')})"
    text += f"\n不动信号: 漏判 {fn}只 / 正确 {tn}只 (漏判率: {metrics.get('miss_rate', 'N/A')})"
    text += f"\n\n盈亏比: {metrics.get('profit_factor', 'N/A')}"
    text += f"\n平均盈亏: {metrics.get('avg_pnl', 'N/A')}"
    text += f"\n准确率: {metrics.get('accuracy', 'N/A')}"

    if top5_review:
        text += "\n\n-- TOP5 回顾 --"
        for r in top5_review[:5]:
            mark = "OK" if r.get("result") == "win" else "XX" if r.get("result") == "loss" else "--"
            text += f"\n{r.get('rank','?')}. {r.get('name','?')} {r.get('signal','?')} {r.get('pnl','?')} [{mark}]"

    if fix:
        text += f"\n\n-- 策略修正 --\n{fix}"

    text += "\n\n不构成投资建议"
    return _send_webhook(text)


# ======================================================================
# Helpers
# ======================================================================

def _load_doc_index() -> dict:
    if FEISHU_DOCS_INDEX.exists():
        return json.loads(FEISHU_DOCS_INDEX.read_text(encoding="utf-8"))
    return {}


def _save_doc_index(scan_date: str, doc_type: str, doc_id: str, doc_url: str):
    index = _load_doc_index()
    index.setdefault(scan_date, {})[doc_type] = {"doc_id": doc_id, "url": doc_url}
    FEISHU_DOCS_INDEX.write_text(json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8")


def get_doc_url(scan_date: str, doc_type: str = "daily") -> Optional[str]:
    return _load_doc_index().get(scan_date, {}).get(doc_type, {}).get("url")

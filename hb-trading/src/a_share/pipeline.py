"""股票研究流水线编排模块

四阶段流水线：
  Phase 1: discover_candidates()  → 发现标的
  Phase 2: compute_quick_filter() → 快速筛选
  Phase 3: 交给 Claude agent 做 investment-committee 深度分析
  Phase 4: 格式化输出 + 飞书推送

Phase 1-2 在此模块完成（纯Python），Phase 3 由主线程/claude agent完成。
"""

from __future__ import annotations

import json
import logging
from datetime import date, datetime
from pathlib import Path

from config import OUTPUT_BASE
from src.a_share.discovery import discover_candidates, compute_quick_filter
from src.a_share.fetcher import fetch_limit_up_pool

logger = logging.getLogger("a-share.pipeline")


def run_pipeline(date_str: str, top_n: int = 5) -> dict:
    """运行完整流水线 Phase 1-2

    Returns:
        {
            "date": "2026-06-12",
            "candidates": [...],        # Phase 1 全部候选
            "qualified": [...],         # Phase 2 通过筛选的
            "rejected": [...],          # Phase 2 未通过的（含理由）
            "snapshot_path": str,       # 保存路径
        }
    """
    date_display = f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:]}"

    # ── Phase 1: Discovery ──
    logger.info("=" * 50)
    logger.info(f"Phase 1: 发现候选标的 ({date_display})")
    logger.info("=" * 50)

    candidates = discover_candidates(date_str, top_n=top_n)

    if not candidates:
        logger.warning("未发现候选标的")
        return {"date": date_display, "candidates": [], "qualified": [], "rejected": [], "snapshot_path": ""}

    # ── Phase 2: Quick Filter ──
    logger.info("=" * 50)
    logger.info("Phase 2: 快速筛选")
    logger.info("=" * 50)

    try:
        zt_df = fetch_limit_up_pool(date_str)
    except Exception:
        zt_df = None

    qualified = []
    rejected = []

    for c in candidates:
        filter_result = compute_quick_filter(c, zt_df)
        c["filter"] = filter_result

        if filter_result["passed"]:
            qualified.append(c)
            logger.info(f"✅ {c['name']}({c['code']}) 通过筛选 (评分:{filter_result['score']})")
        else:
            rejected.append(c)
            logger.info(f"❌ {c['name']}({c['code']}) 未通过: {'; '.join(filter_result['warnings'][:2])}")

    logger.info(f"筛选结果: {len(qualified)}/{len(candidates)} 通过")

    # ── 保存快照 ──
    out_dir = Path(OUTPUT_BASE) / date_display
    out_dir.mkdir(parents=True, exist_ok=True)

    snapshot = {
        "date": date_display,
        "generated_at": datetime.now().strftime("%H:%M:%S"),
        "pipeline_version": "1.0",
        "phases": {
            "discovery": {
                "total_candidates": len(candidates),
                "sources": {
                    "data_driven": sum(1 for c in candidates if c["source"] == "data-driven"),
                    "event_driven": sum(1 for c in candidates if c["source"] == "event-driven"),
                },
            },
            "quick_filter": {
                "qualified": len(qualified),
                "rejected": len(rejected),
            },
        },
        "candidates": candidates,
        "qualified": qualified,
        "rejected": rejected,
    }

    snapshot_path = out_dir / "pipeline_snapshot.json"
    snapshot_path.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info(f"📸 流水线快照 → {snapshot_path}")

    return {
        "date": date_display,
        "candidates": candidates,
        "qualified": qualified,
        "rejected": rejected,
        "snapshot_path": str(snapshot_path),
    }


def format_pipeline_summary(result: dict) -> str:
    """生成流水线摘要文本"""
    lines = [
        f"## 🔬 股票研究流水线 · {result['date']}",
        "",
        f"### Phase 1: 发现 {len(result['candidates'])} 只候选",
    ]

    for i, c in enumerate(result["candidates"], 1):
        source_label = "📊数据" if c["source"] == "data-driven" else "📰事件"
        reasons = " · ".join(c.get("discovery_reasons", [])[:3])
        lines.append(f"{i}. {source_label} **{c['name']}**({c['code']}) — {reasons}")

    lines.append("")
    lines.append(f"### Phase 2: {len(result['qualified'])}/{len(result['candidates'])} 通过筛选")

    if result["qualified"]:
        lines.append("")
        lines.append("**✅ 进入深度分析：**")
        for c in result["qualified"]:
            f = c.get("filter", {})
            lines.append(f"- **{c['name']}**({c['code']}) 评分:{f.get('score', 'N/A')} | {' · '.join(f.get('warnings', [])[:2])}")

    if result["rejected"]:
        lines.append("")
        lines.append("**❌ 未通过筛选：**")
        for c in result["rejected"]:
            f = c.get("filter", {})
            lines.append(f"- {c['name']}({c['code']}) — {'; '.join(f.get('warnings', [])[:2])}")

    lines.append("")
    lines.append("---")
    lines.append("*流水线Phase 1-2完成，Phase 3深度分析由Claude Agent执行*")

    return "\n".join(lines)

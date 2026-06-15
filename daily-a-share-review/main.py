#!/usr/bin/env python3
"""每日A股深度复盘 — 主入口

用法:
  python main.py am                        # 上午版 → 飞书推送
  python main.py pm                        # 下午版 → 飞书推送 + 本地长图
  python main.py pm --no-push              # 仅本地文件
  python main.py am --date 2026-06-10      # 指定日期
"""

from __future__ import annotations

import argparse
import io
import json
import logging
import os
import subprocess
import sys
from datetime import date, datetime
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# 项目根加入 path
sys.path.insert(0, str(Path(__file__).parent))

from config import OUTPUT_BASE
from src.morning import build_morning_report, render_morning_md, render_morning_feishu
from src.afternoon import build_afternoon_report, render_afternoon_md
from src.html_gen import build_afternoon_html
from src.feishu import send_morning_card, send_afternoon_card, render_afternoon_feishu_card

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("a-share.main")


def main():
    parser = argparse.ArgumentParser(description="每日A股深度复盘")
    parser.add_argument("mode", choices=["am", "pm", "pipeline", "pa"], help="上午版(am) / 下午版(pm) / 研究流水线(pipeline) / PA标的扫描(pa)")
    parser.add_argument("--date", default=None, help="日期 (am: YYYY-MM-DD, pm: YYYYMMDD)")
    parser.add_argument("--no-push", action="store_true", help="跳过飞书推送")
    parser.add_argument("--deep", action="store_true", help="深度解读模式：生成数据快照供 Claude 分析")
    parser.add_argument("--candidates", type=int, default=5, help="pipeline模式候选数量（默认5）")
    parser.add_argument("--filter-only", action="store_true", help="pipeline模式仅筛选不深研")
    args = parser.parse_args()

    today = date.today()

    if args.mode == "am":
        run_morning(args, today)
    elif args.mode == "pm":
        run_afternoon(args, today)
    elif args.mode == "pipeline":
        run_pipeline_cmd(args, today)
    else:
        run_pa_cmd(args, today)


def run_morning(args, today: date):
    """上午版"""
    target_date = args.date or today.strftime("%Y-%m-%d")
    logger.info(f"📡 生成上午版复盘 — {target_date}")

    # 1. 构建报告
    report = build_morning_report(target_date)

    # 2. 保存快照 + Markdown
    out_dir = Path(OUTPUT_BASE) / target_date
    out_dir.mkdir(parents=True, exist_ok=True)

    snapshot = {
        "date": target_date,
        "global": report.get("global", {}).get("items", []),
        "news": report.get("news", []),
        "research": report.get("research", []),
        "notices": report.get("notices", []),
    }
    snapshot_path = out_dir / "morning_snapshot.json"
    snapshot_path.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info(f"📸 快照 → {snapshot_path}")

    if args.deep:
        logger.info("📸 --deep：快照已就绪，Claude 读取 morning_snapshot.json 生成深度解读推飞书")
        return

    md_path = out_dir / "morning.md"
    md_path.write_text(render_morning_md(report), encoding="utf-8")
    logger.info(f"📄 Markdown → {md_path}")

    # 3. 飞书推送
    if not args.no_push:
        card = render_morning_feishu(report)
        ok = send_morning_card(card)
        if ok:
            logger.info("✅ 飞书上午卡片发送成功")
        else:
            logger.warning("⚠️ 飞书推送失败，检查 Webhook 配置")
    else:
        logger.info("⏭️ 跳过飞书推送 (--no-push)")

    logger.info(f"✅ 上午版完成 → {out_dir}")


def run_afternoon(args, today: date):
    """下午版"""
    target_date = args.date or today.strftime("%Y%m%d")
    date_display = f"{target_date[:4]}-{target_date[4:6]}-{target_date[6:]}"
    logger.info(f"📡 生成下午版复盘 — {date_display}")

    # 1. 构建报告
    report = build_afternoon_report(target_date)
    report["date"] = date_display

    # 2. 保存数据快照 (供手动深度解读)
    out_dir = Path(OUTPUT_BASE) / date_display
    out_dir.mkdir(parents=True, exist_ok=True)

    snapshot = {
        "date": date_display,
        "indices": report.get("indices", []),
        "sectors": {k: v for k, v in report.get("sectors", {}).items() if k in ("top", "bottom")},
        "zt_total": report.get("zt_analysis", {}).get("total", 0),
        "dt_total": report.get("dt_total", 0),
        "zt_tiers": report.get("zt_analysis", {}).get("tiers", []),
        "zt_themes": report.get("zt_analysis", {}).get("themes", []),
        "zt_leaders": report.get("zt_analysis", {}).get("leaders", []),
        "dragon_tiger": report.get("dragon_tiger_highlights", []),
    }
    snapshot_path = out_dir / "snapshot.json"
    snapshot_path.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info(f"📸 数据快照 → {snapshot_path}")

    if args.deep:
        # --deep 模式：生成数据快照，等待 Claude 手动解读
        logger.info("📸 --deep 模式：数据快照已就绪。请让 Claude 读取 snapshot.json 并生成深度解读推飞书。")
        return

    # 3. 保存 Markdown + HTML + PNG (自动化快速版)
    md_path = out_dir / "afternoon.md"
    md_path.write_text(render_afternoon_md(report), encoding="utf-8")
    logger.info(f"📄 Markdown → {md_path}")

    html_content = build_afternoon_html(report)
    html_path = out_dir / "afternoon.html"
    html_path.write_text(html_content, encoding="utf-8")
    logger.info(f"🌐 HTML → {html_path}")

    png_path = out_dir / "afternoon.png"
    render_script = Path(__file__).parent / "template" / "render.cjs"
    try:
        result = subprocess.run(
            ["node", str(render_script), str(html_path), str(png_path)],
            capture_output=True, text=True, timeout=60,
            cwd=str(Path(__file__).parent),
        )
        if result.returncode == 0:
            logger.info(f"🖼️ 长图 → {png_path}")
        else:
            logger.error(f"渲染失败: {result.stderr}")
    except FileNotFoundError:
        logger.warning("⚠️ Node.js 未安装，跳过 PNG 渲染")
    except subprocess.TimeoutExpired:
        logger.warning("⚠️ 渲染超时，跳过 PNG")

    # 4. 飞书推送 (自动化版)
    if not args.no_push:
        card = render_afternoon_feishu_card(report)
        ok = send_afternoon_card(card)
        if ok:
            logger.info("✅ 飞书卡片发送成功")
        else:
            logger.warning("⚠️ 飞书推送失败")
    else:
        logger.info("⏭️ 跳过飞书推送 (--no-push)")

    logger.info(f"✅ 下午版完成 → {out_dir}")
    logger.info("💡 需要深度解读？运行: python main.py pm --deep")


def run_pipeline_cmd(args, today: date):
    """研究流水线：发现→筛选→保存快照（深度分析由Claude Agent完成）"""
    from src.pipeline import run_pipeline, format_pipeline_summary
    from src.feishu import send_afternoon_card
    from datetime import datetime

    target_date = args.date or today.strftime("%Y%m%d")
    logger.info(f"🔬 启动研究流水线 — {target_date}")

    # Phase 1 + 2
    result = run_pipeline(target_date, top_n=getattr(args, 'candidates', 5))

    summary = format_pipeline_summary(result)
    print(summary)

    # Phase 2.5: 推送到飞书预览
    if not args.no_push:
        qualified = result.get("qualified", [])
        if qualified:
            lines = [f"**🔬 研究候选标的 · {result['date']}**\n"]
            lines.append(f"Phase 1 发现 {len(result['candidates'])} 只 → Phase 2 筛选通过 {len(qualified)} 只\n")
            for i, c in enumerate(qualified, 1):
                f = c.get("filter", {})
                reasons = " · ".join(c.get("discovery_reasons", [])[:3])
                lines.append(f"**#{i} {c['name']}**({c['code']})")
                lines.append(f"来源：{reasons}")
                lines.append(f"评分：{f.get('score','N/A')}/15 | {' · '.join(f.get('warnings',[])[:1])}")
                lines.append("")
            lines.append("---")
            lines.append("💡 深度分析（6角色投委会）正在进行，稍后推送每只的完整研究...")

            card = {
                "header": {
                    "title": {"tag": "plain_text", "content": f"🔬 研究候选 · {result['date']}"},
                    "template": "blue",
                },
                "elements": [
                    {"tag": "div", "text": {"tag": "lark_md", "content": "\n".join(lines)}},
                    {"tag": "note", "elements": [{"tag": "plain_text",
                        "content": f"研究流水线Phase1-2 · {datetime.now().strftime('%H:%M')} · 不构成投资建议"}]},
                ],
            }
            send_afternoon_card(card)
            logger.info("✅ 研究候选预览已推送到飞书")

    logger.info(f"\n📌 下一步：读取 {result['snapshot_path']}")
    logger.info("   对 qualified 中的每只股票调用 /investment-committee")
    logger.info("   或让 Claude Agent 自动读取 pipeline_snapshot.json 并执行 Phase 3-4")


def run_pa_cmd(args, today: date):
    """PA标的扫描：全市场扫描满足PA操作条件的股票"""
    from src.pa_discovery import discover_pa_candidates, compute_pa_quick_filter
    from src.feishu import send_afternoon_card
    from datetime import datetime

    target_date = args.date or today.strftime("%Y%m%d")
    top_n = getattr(args, 'candidates', 10)
    logger.info(f"🔍 PA标的扫描 — 全市场搜索满足PA操作条件的股票 (Top {top_n})")

    # PA发现
    candidates = discover_pa_candidates(top_n=top_n)

    if not candidates:
        logger.warning("未发现满足PA条件的候选")
        return

    # 对每只做估值确认
    for c in candidates:
        f = compute_pa_quick_filter(c)
        c["filter"] = f

    qualified = [c for c in candidates if c["filter"]["passed"]]

    # 输出
    date_display = f"{target_date[:4]}-{target_date[4:6]}-{target_date[6:]}"
    print(f"\n## 📐 PA标的扫描 · {date_display}")
    print(f"\n全市场扫描 → {len(candidates)} 只满足PA条件\n")
    for i, c in enumerate(qualified[:5], 1):
        dma = c.get("dma", {})
        print(f"**#{i} {c['name']}**({c['code']}) | {c['price']}元 | PE={c.get('pe','?')}")
        print(f"  PA={c['pa_score']}分 | {c['pa_structure']}")
        print(f"  {c['pa_setup']}")
        print(f"  均线: MA20={dma.get('ma20')} MA50={dma.get('ma50')} | 乖离20={dma.get('dma20_pct')}%")
        print()

    # 飞书推送
    if not args.no_push and qualified:
        lines = [f"**📐 PA标的扫描 · {date_display}**\n"]
        lines.append(f"全市场扫描 → {len(qualified)} 只满足PA操作条件\n")
        for i, c in enumerate(qualified[:5], 1):
            dma = c.get("dma", {})
            lines.append(f"**#{i} {c['name']}**({c['code']}) {c['price']}元 PE={c.get('pe','?')}")
            lines.append(f"PA={c['pa_score']}分 | {c['pa_structure']}")
            lines.append(f"{c['pa_setup']}")
            d20 = dma.get('dma20_pct')
            lines.append(f"MA20乖离: {d20:+.1f}%" if d20 else "")
            lines.append("")

        lines.append("---")
        lines.append("💡 PA框架：Al Brooks价格行为学 | 不构成投资建议")

        card = {
            "header": {
                "title": {"tag": "plain_text", "content": f"📐 PA标的扫描 · {date_display}"},
                "template": "blue",
            },
            "elements": [
                {"tag": "div", "text": {"tag": "lark_md", "content": "\n".join(lines)}},
                {"tag": "note", "elements": [{"tag": "plain_text",
                    "content": f"Al Brooks PA框架 · {datetime.now().strftime('%H:%M')} · 不构成投资建议"}]},
            ],
        }
        send_afternoon_card(card)
        logger.info("✅ PA候选已推送到飞书")

    # 保存快照
    import json
    out_dir = Path(OUTPUT_BASE) / date_display
    out_dir.mkdir(parents=True, exist_ok=True)
    snap = {"date": date_display, "mode": "pa", "qualified": qualified, "candidates": candidates}
    (out_dir / "pa_snapshot.json").write_text(json.dumps(snap, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info(f"📸 PA快照 → {out_dir / 'pa_snapshot.json'}")


if __name__ == "__main__":
    main()

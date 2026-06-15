"""长图 HTML 生成器 — 下午版复盘数据 → HTML → Playwright 截图"""

from __future__ import annotations

from pathlib import Path
from datetime import datetime


def build_afternoon_html(report: dict) -> str:
    """根据下午版报告数据生成完整 HTML"""

    date_str = report.get("date", "")
    indices = report.get("indices", [])
    stats = report.get("market_stats", {})
    sectors = report.get("sectors", {})
    nf = report.get("north_flow", {})
    zt = report.get("zt_analysis", {})
    dt_hl = report.get("dragon_tiger_highlights", [])
    outlook = report.get("outlook", "")
    watchlist = report.get("watchlist", [])

    html = f"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<title>A股复盘 · {date_str}</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Noto+Sans+SC:wght@300;400;500;700;900&family=Inter:wght@300;400;500;700&family=IBM+Plex+Mono:wght@400;500&display=swap" rel="stylesheet">
<style>
  *,*::before,*::after{{box-sizing:border-box;margin:0;padding:0}}
  body{{
    background:#0d1117;color:#e6edf3;font-family:'Noto Sans SC','Inter',sans-serif;
    -webkit-font-smoothing:antialiased;display:flex;justify-content:center;
  }}
  .page{{
    width:1080px;background:#0d1117;padding:0;overflow:hidden;
  }}
  /* ── 区块 ── */
  .section{{
    padding:48px 64px;border-bottom:1px solid #21262d;
  }}
  .section-header{{
    display:flex;align-items:center;gap:12px;margin-bottom:32px;
  }}
  .section-icon{{font-size:28px}}
  .section-title{{
    font-size:28px;font-weight:700;color:#e6edf3;letter-spacing:.04em;
  }}
  /* ── 头部 ── */
  .hero{{
    padding:56px 64px 40px;
    background:linear-gradient(180deg,#161b22 0%,#0d1117 100%);
  }}
  .hero-date{{font-family:'IBM Plex Mono',monospace;font-size:18px;color:#8b949e;letter-spacing:.12em;text-transform:uppercase;margin-bottom:12px}}
  .hero-title{{font-size:48px;font-weight:900;color:#e6edf3;letter-spacing:.06em;margin-bottom:8px}}
  .hero-sub{{font-size:20px;color:#8b949e}}
  .hero-stats{{display:flex;gap:32px;margin-top:28px}}
  .hero-stat{{flex:1;background:#161b22;border:1px solid #21262d;padding:20px;text-align:center}}
  .hero-stat-val{{font-family:'IBM Plex Mono',monospace;font-size:36px;font-weight:700}}
  .hero-stat-label{{font-size:16px;color:#8b949e;margin-top:6px}}
  /* ── 指数 ── */
  .index-grid{{display:grid;grid-template-columns:repeat(4,1fr);gap:16px}}
  .index-card{{background:#161b22;border:1px solid #21262d;padding:24px;text-align:center}}
  .index-card .name{{font-size:18px;color:#8b949e;margin-bottom:8px}}
  .index-card .price{{font-family:'IBM Plex Mono',monospace;font-size:36px;font-weight:700;color:#e6edf3;margin-bottom:6px}}
  .index-card .change{{font-family:'IBM Plex Mono',monospace;font-size:20px;font-weight:700}}
  .index-card .amount{{font-size:15px;color:#8b949e;margin-top:8px}}
  /* ── 板块 ── */
  .sector-cols{{display:grid;grid-template-columns:1fr 1fr;gap:32px}}
  .sector-col h3{{font-size:22px;margin-bottom:16px;font-weight:700}}
  .sector-row{{display:flex;justify-content:space-between;align-items:center;padding:12px 0;border-bottom:1px solid #21262d;font-size:20px}}
  .sector-row .lead{{font-size:16px;color:#8b949e}}
  /* ── 资金 ── */
  .flow-grid{{display:grid;grid-template-columns:repeat(3,1fr);gap:16px}}
  .flow-card{{background:#161b22;border:1px solid #21262d;padding:28px;text-align:center}}
  .flow-card .label{{font-size:18px;color:#8b949e;margin-bottom:10px}}
  .flow-card .val{{font-family:'IBM Plex Mono',monospace;font-size:40px;font-weight:700}}
  /* ── 涨停深度 ── */
  .zt-summary{{background:#161b22;border:1px solid #21262d;padding:28px;margin-bottom:32px;font-size:22px;line-height:1.8;color:#c9d1d9}}
  .tier-block{{margin-bottom:28px}}
  .tier-label{{font-size:24px;font-weight:700;color:#58a6ff;margin-bottom:12px;padding-bottom:8px;border-bottom:1px solid #21262d}}
  .tier-stocks{{display:flex;flex-wrap:wrap;gap:10px}}
  .tier-stock{{background:#161b22;border:1px solid #21262d;padding:10px 18px;font-size:19px;display:flex;align-items:center;gap:10px}}
  .tier-stock .reason{{color:#8b949e;font-size:16px}}
  .tier-stock .warn{{color:#f85149;font-size:16px}}
  .theme-block{{margin-bottom:20px}}
  .theme-header{{font-size:22px;font-weight:700;margin-bottom:8px}}
  .theme-stocks{{color:#8b949e;font-size:19px}}
  .leader-tag{{display:inline-block;padding:4px 14px;font-size:16px;margin-right:6px;border-radius:3px;background:#3fb95020;color:#3fb950;border:1px solid #3fb95040}}
  /* ── 龙虎榜 ── */
  .dt-table{{width:100%;border-collapse:collapse;font-size:20px}}
  .dt-table th{{text-align:left;padding:12px 16px;border-bottom:1px solid #21262d;color:#8b949e;font-weight:500;font-size:17px}}
  .dt-table td{{padding:14px 16px;border-bottom:1px solid #161b22}}
  /* ── 明日 ── */
  .outlook-text{{font-size:22px;line-height:1.8;color:#c9d1d9;margin-bottom:24px}}
  .watchlist{{display:flex;flex-wrap:wrap;gap:12px}}
  .watch-item{{background:#161b22;border:1px solid #58a6ff40;padding:12px 20px;font-size:19px}}
  .watch-item .reason{{color:#8b949e;font-size:16px;margin-left:8px}}
  /* ── 颜色工具 ── */
  .c-green{{color:#3fb950}}
  .c-red{{color:#f85149}}
  .c-accent{{color:#58a6ff}}
  .c-warn{{color:#d29922}}
  /* ── 脚注 ── */
  .footer{{padding:40px 64px;text-align:center;font-family:'IBM Plex Mono',monospace;font-size:16px;color:#484f58}}
</style>
</head>
<body>
<div class="page">

  <!-- ═══ 头部 ═══ -->
  <div class="hero">
    <div class="hero-date">{date_str}</div>
    <div class="hero-title">A股收盘深度复盘</div>
    <div class="hero-sub">大盘 · 板块 · 资金 · 涨停解读 · 明日预判</div>
    <div class="hero-stats">
      <div class="hero-stat">
        <div class="hero-stat-val c-green">{stats.get('up', 0)}</div>
        <div class="hero-stat-label">上涨</div>
      </div>
      <div class="hero-stat">
        <div class="hero-stat-val c-red">{stats.get('down', 0)}</div>
        <div class="hero-stat-label">下跌</div>
      </div>
      <div class="hero-stat">
        <div class="hero-stat-val" style="color:#8b949e">{stats.get('flat', 0)}</div>
        <div class="hero-stat-label">平盘</div>
      </div>
      <div class="hero-stat">
        <div class="hero-stat-val c-accent">{zt.get('total', 0)}</div>
        <div class="hero-stat-label">涨停</div>
      </div>
    </div>
  </div>

  <!-- ═══ 大盘指数 ═══ -->
  <div class="section">
    <div class="section-header">
      <span class="section-icon">📊</span>
      <span class="section-title">大盘指数</span>
    </div>
    <div class="index-grid">
"""

    for idx in indices:
        color_class = "c-green" if idx["pct"] >= 0 else "c-red"
        sign = "+" if idx["pct"] >= 0 else ""
        html += f"""      <div class="index-card">
        <div class="name">{idx['name']}</div>
        <div class="price">{idx['price']}</div>
        <div class="change {color_class}">{sign}{idx['pct']}%  {sign}{idx['change']}</div>
        <div class="amount">{idx['amount']}</div>
      </div>
"""

    html += """    </div>
  </div>

  <!-- ═══ 板块热力 ═══ -->
  <div class="section">
    <div class="section-header">
      <span class="section-icon">🔥</span>
      <span class="section-title">行业板块</span>
    </div>
    <div class="sector-cols">
      <div class="sector-col">
        <h3 class="c-green">📈 涨幅榜</h3>
"""

    for s in sectors.get("top", []):
        html += f"""        <div class="sector-row">
          <span>{s['name']}<span class="lead">  {s['lead']}</span></span>
          <span class="c-green">+{s['pct']}%</span>
        </div>
"""

    html += """      </div>
      <div class="sector-col">
        <h3 class="c-red">📉 跌幅榜</h3>
"""

    for s in sectors.get("bottom", []):
        html += f"""        <div class="sector-row">
          <span>{s['name']}<span class="lead">  {s['lead']}</span></span>
          <span class="c-red">{s['pct']}%</span>
        </div>
"""

    html += """      </div>
    </div>
  </div>

  <!-- ═══ 资金流向 ═══ -->
  <div class="section">
    <div class="section-header">
      <span class="section-icon">💰</span>
      <span class="section-title">北向资金</span>
    </div>
    <div class="flow-grid">
"""

    hgt_color = "c-green" if nf.get("hgt", 0) >= 0 else "c-red"
    sgt_color = "c-green" if nf.get("sgt", 0) >= 0 else "c-red"
    total_color = "c-green" if nf.get("total", 0) >= 0 else "c-red"
    html += f"""      <div class="flow-card">
        <div class="label">沪股通</div>
        <div class="val {hgt_color}">{nf.get('hgt', 0):+.1f}亿</div>
      </div>
      <div class="flow-card">
        <div class="label">深股通</div>
        <div class="val {sgt_color}">{nf.get('sgt', 0):+.1f}亿</div>
      </div>
      <div class="flow-card">
        <div class="label">合计</div>
        <div class="val {total_color}">{nf.get('total', 0):+.1f}亿</div>
      </div>
"""

    html += """    </div>
  </div>

  <!-- ═══ 涨停深度解读 ═══ -->
  <div class="section">
    <div class="section-header">
      <span class="section-icon">🚀</span>
      <span class="section-title">涨停板深度解读</span>
    </div>
    <div class="zt-summary">
"""

    html += zt.get("analysis", "").replace("\n", "<br>")

    html += """
    </div>
"""

    # 连板梯队
    tiers = zt.get("tiers", [])
    if tiers:
        for t in tiers:
            label_color = "c-accent" if t["boards"] >= 3 else "#e6edf3"
            html += f"""    <div class="tier-block">
      <div class="tier-label" style="color:{label_color}">{t['label']} ({t['count']}家)</div>
      <div class="tier-stocks">
"""
            for s in t["stocks"]:
                warn = f' <span class="warn">炸{s["breaks"]}次</span>' if s["breaks"] >= 2 else ""
                html += f"""        <div class="tier-stock">
          <span>{s['name']}</span>
          <span class="reason">{s['reason']}</span>
          {warn}
        </div>
"""
            html += "      </div>\n    </div>\n"

    # 题材聚合
    themes = zt.get("themes", [])
    if themes:
        html += """    <div class="section-header" style="margin-top:20px">
      <span style="font-size:22px;font-weight:700">🧩 题材聚合</span>
    </div>
"""
        main = [t for t in themes if t["strength"] == "主线"]
        sub = [t for t in themes if t["strength"] == "支线"]

        if main:
            html += """    <div class="theme-block">
      <div class="theme-header" style="color:#3fb950;font-size:22px">🔥 主线题材</div>
"""
            for t in main:
                html += f"""      <div style="margin-bottom:12px;font-size:20px">
        <span class="leader-tag">主线</span>
        <span style="color:#e6edf3;font-weight:700">{t['theme']}</span>
        <span style="color:#8b949e"> — {t['count']}家涨停 · 核心：{t['core']}</span>
        <div class="theme-stocks" style="margin-top:4px">{'、'.join(t['stocks'])}</div>
      </div>
"""
            html += "    </div>\n"

        if sub:
            html += """    <div class="theme-block">
      <div class="theme-header" style="color:#58a6ff;font-size:22px">🔹 支线题材</div>
"""
            for t in sub[:6]:
                html += f"""      <div style="margin-bottom:12px;font-size:20px">
        <span style="color:#e6edf3;font-weight:700">{t['theme']}</span>
        <span style="color:#8b949e"> — {t['count']}家涨停 · 核心：{t['core']}</span>
        <div class="theme-stocks" style="margin-top:4px">{'、'.join(t['stocks'])}</div>
      </div>
"""
            html += "    </div>\n"

    html += """  </div>
"""

    # ═══ 龙虎榜 ═══
    if dt_hl:
        html += """  <!-- ═══ 龙虎榜 ═══ -->
  <div class="section">
    <div class="section-header">
      <span class="section-icon">🐉</span>
      <span class="section-title">龙虎榜亮点</span>
    </div>
    <table class="dt-table">
      <tr><th>个股</th><th>涨跌幅</th><th>净买额</th><th>上榜原因</th></tr>
"""
        for d in dt_hl:
            pct_color = "c-green" if d["pct"] >= 0 else "c-red"
            sign = "+" if d["pct"] >= 0 else ""
            html += f"""      <tr>
        <td style="font-weight:700">{d['name']}</td>
        <td class="{pct_color}" style="font-weight:700">{sign}{d['pct']}%</td>
        <td>{d['net_buy']}</td>
        <td style="color:#8b949e;font-size:18px">{d['reason']}</td>
      </tr>
"""
        html += """    </table>
  </div>
"""

    # ═══ 明日预判 ═══
    html += f"""  <!-- ═══ 明日预判 ═══ -->
  <div class="section">
    <div class="section-header">
      <span class="section-icon">🔮</span>
      <span class="section-title">明日预判</span>
    </div>
    <div class="outlook-text">{outlook.replace(chr(10), '<br>')}</div>
"""

    if watchlist:
        html += """    <div class="watchlist">
"""
        for w in watchlist:
            html += f"""      <div class="watch-item"><span style="font-weight:700;color:#58a6ff">{w['name']}</span><span class="reason">{w['reason']}</span></div>
"""
        html += "    </div>\n"

    html += f"""  </div>

  <!-- ═══ 脚注 ═══ -->
  <div class="footer">
    每日A股复盘 · {date_str} · 数据来源：东方财富 · AI生成仅供参考
  </div>

</div>
</body>
</html>"""

    return html

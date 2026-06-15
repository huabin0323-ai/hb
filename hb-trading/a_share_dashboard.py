"""A股PA回测驾驶舱 — TOP10扫描 + 逐股回测 + K线信号标注

streamlit run a_share_dashboard.py --server.port 8502
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import date, datetime, timedelta
import json, time, logging

logging.basicConfig(level=logging.WARNING)

# ══════════════════════════════════════════════════════════════
st.set_page_config(page_title="PA回测驾驶舱", layout="wide", page_icon="📊",
                   initial_sidebar_state="expanded")

st.markdown("""
<style>
.stApp { background: #0d1117; }
.main .block-container { padding: 0.5rem 1rem; max-width: 100%; }
div[data-testid="stMetric"] {
    background: #161b22; border: 1px solid #21262d; border-radius: 6px; padding: 10px 14px;
}
div[data-testid="stMetric"] label { color: #8b949e !important; font-size: 0.75rem; }
div[data-testid="stMetric"] div[data-testid="stMetricValue"] { color: #e6edf3; font-size: 1.3rem; }
div.stButton > button {
    background: #21262d; color: #c9d1d9; border: 1px solid #30363d; border-radius: 6px;
    font-size: 0.8rem;
}
div.stButton > button:hover { background: #30363d; }
div.stButton > button[kind="primary"] { background: #d4a017; border-color: #d4a017; color: #000; font-weight:600; }
div.stButton > button[kind="primary"]:hover { background: #e6b422; }
</style>
""", unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════
SS = st.session_state
for k, v in dict(results={}, scan=None, active_code="", loading=False, codes=[]).items():
    if k not in SS: SS[k] = v

# ══════════════════════════════════════════════════════════════

@st.cache_data(ttl=600)
def _dma(code):
    from src.a_share.fetcher import compute_dma_metrics
    return compute_dma_metrics(code)

@st.cache_data(ttl=3600)
def _run_backtest(code, name, window, min_score, min_rr, max_hold):
    from src.a_share.pa_backtest import run_pa_backtest
    return run_pa_backtest(code, name, window=window, min_score=min_score,
                           min_rr=min_rr, max_hold=max_hold)


def build_kline_chart(bt_result):
    """日线K线 + 买卖点标注"""
    klines = bt_result.daily_klines
    if not klines:
        return go.Figure()

    df = pd.DataFrame(klines)
    fig = make_subplots(rows=2, cols=1, shared_xaxes=True,
                        row_heights=[0.7, 0.3], vertical_spacing=0.03)

    colors = ["#f85149" if df["close"].iloc[i] < df["open"].iloc[i] else "#3fb950"
              for i in range(len(df))]

    fig.add_trace(go.Candlestick(
        x=df["date"], open=df["open"], high=df["high"], low=df["low"], close=df["close"],
        name="", increasing_line_color="#3fb950", decreasing_line_color="#f85149",
    ), row=1, col=1)

    # MA20
    if len(df) >= 20:
        ma20 = df["close"].rolling(20).mean()
        fig.add_trace(go.Scatter(x=df["date"], y=ma20, mode="lines",
                                 line=dict(color="#d4a017", width=1, dash="dot"),
                                 name="MA20"), row=1, col=1)

    # 买点标注（绿色三角）
    if bt_result.buy_markers:
        buy_df = pd.DataFrame(bt_result.buy_markers)
        # Map idx to date
        buy_dates = []
        for _, b in buy_df.iterrows():
            if b["idx"] < len(df):
                buy_dates.append(df["date"].iloc[min(b["idx"], len(df)-1)])
            else:
                buy_dates.append("")
        fig.add_trace(go.Scatter(
            x=buy_dates, y=buy_df["price"].tolist(),
            mode="markers+text",
            marker=dict(symbol="triangle-up", size=14, color="#3fb950", line=dict(width=1, color="#fff")),
            text=buy_df["signal"].tolist(),
            textposition="top center",
            textfont=dict(size=9, color="#3fb950"),
            name="买入", hovertext=buy_df["reason"].tolist(),
        ), row=1, col=1)

    # 卖点标注（红色三角）
    if bt_result.sell_markers:
        sell_df = pd.DataFrame(bt_result.sell_markers)
        sell_dates = []
        for _, s in sell_df.iterrows():
            if s["idx"] < len(df):
                sell_dates.append(df["date"].iloc[min(s["idx"], len(df)-1)])
            else:
                sell_dates.append("")
        fig.add_trace(go.Scatter(
            x=sell_dates, y=sell_df["price"].tolist(),
            mode="markers+text",
            marker=dict(symbol="triangle-down", size=14, color="#f85149", line=dict(width=1, color="#fff")),
            text=sell_df["reason"].tolist(),
            textposition="bottom center",
            textfont=dict(size=9, color="#f85149"),
            name="卖出",
            hovertext=[f"{r} | {p:+.2f}%" for r, p in zip(sell_df["reason"], sell_df["pnl_pct"])],
        ), row=1, col=1)

    # Volume
    fig.add_trace(go.Bar(x=df["date"], y=df["volume"], marker_color=colors,
                        opacity=0.35, name=""), row=2, col=1)

    fig.update_layout(
        template="plotly_dark", height=500, margin=dict(l=0, r=0, t=30, b=0),
        paper_bgcolor="#0d1117", plot_bgcolor="#0d1117",
        xaxis_rangeslider_visible=False, showlegend=True,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
        hovermode="x unified",
    )
    fig.update_xaxes(gridcolor="#21262d", zeroline=False)
    fig.update_yaxes(gridcolor="#21262d", zeroline=False)
    return fig


def build_equity_chart(bt_result):
    if not bt_result.equity_curve:
        return go.Figure()
    eq = pd.DataFrame(bt_result.equity_curve)
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=eq["date"], y=eq["equity"], mode="lines",
        line=dict(color="#d4a017", width=2),
        fill="tozeroy", fillcolor="rgba(212,160,23,0.08)",
        name="",
    ))
    fig.add_hline(y=100, line_dash="dash", line_color="#30363d")
    fig.update_layout(
        template="plotly_dark", height=300, margin=dict(l=0, r=0, t=10, b=0),
        paper_bgcolor="#0d1117", plot_bgcolor="#0d1117",
        showlegend=False, hovermode="x unified",
    )
    fig.update_xaxes(gridcolor="#21262d", zeroline=False)
    fig.update_yaxes(gridcolor="#21262d", zeroline=False)
    return fig


# ══════════════════════════════════════════════════════════════
def main():
    st.title("PA策略回测")

    # ── Control bar ──
    c1, c2, c3, c4, c5, c6 = st.columns([1.5, 1, 1, 1, 1, 1])
    with c1:
        codes_input = st.text_input("股票代码", value="600519,000858,300750,002415,601318,600036,002594,601899,600900,000333",
                                    placeholder="逗号分隔", label_visibility="collapsed")
    with c2:
        window = st.number_input("PA窗口", 60, 200, 100, 20, label_visibility="collapsed")
    with c3:
        min_score = st.slider("最低分", 20, 60, 35, 5, label_visibility="collapsed")
    with c4:
        min_rr = st.slider("最低RR", 1.0, 3.0, 1.3, 0.1, label_visibility="collapsed")
    with c5:
        max_hold = st.slider("最大持仓天", 5, 40, 20, 5, label_visibility="collapsed")
    with c6:
        go_btn = st.button("运行回测", use_container_width=True, type="primary")

    if go_btn:
        codes = [c.strip() for c in codes_input.split(",") if c.strip()]
        SS.codes = codes
        SS.results = {}
        SS.loading = True
        st.rerun()

    if SS.loading:
        progress = st.progress(0, "回测中...")
        total = len(SS.codes)
        for i, code in enumerate(SS.codes):
            dma = _dma(code)
            name = dma.get("name", code) if isinstance(dma, dict) else code
            if isinstance(dma, dict) and dma.get("price"):
                bt = _run_backtest(code, name, window, min_score, min_rr, max_hold)
                SS.results[code] = bt
            progress.progress((i+1)/total, f"{name}({code}) 完成")
        SS.loading = False
        progress.empty()
        st.rerun()

    if not SS.results:
        st.info("输入股票代码（逗号分隔），点击「运行回测」")
        return

    results = SS.results

    # ── TOP10 summary table ──
    rows = []
    for code, bt in results.items():
        rows.append({
            "代码": code, "名称": bt.name,
            "胜率%": bt.win_rate, "收益%": bt.total_return_pct,
            "回撤%": bt.max_drawdown_pct, "PF": bt.profit_factor,
            "交易": bt.trade_count, "信号": bt.signal_count,
            "K线": bt.total_bars,
        })

    df_sum = pd.DataFrame(rows).sort_values("收益%", ascending=False)

    def _color_summary(val):
        if isinstance(val, (int, float)):
            if val > 0: return "color:#3fb950"
            if val < 0: return "color:#f85149"
        return ""

    st.dataframe(
        df_sum.style.map(_color_summary, subset=["收益%","胜率%"]),
        use_container_width=True, hide_index=True,
        column_config={c: st.column_config.NumberColumn(format="%.1f") for c in ["胜率%","收益%","回撤%","PF"]},
        height=200,
    )

    # ── Select stock to view detail ──
    st.divider()
    st.caption("点击股票查看详细回测报告")

    cols = st.columns(min(len(results), 10))
    for i, (code, bt) in enumerate(results.items()):
        with cols[i]:
            ret = bt.total_return_pct
            color = "#3fb950" if ret > 0 else "#f85149"
            active = SS.active_code == code
            border = "2px solid #d4a017" if active else "1px solid #21262d"
            st.markdown(f"""
            <div style="background:#161b22;border:{border};border-radius:8px;padding:10px;
                        text-align:center;cursor:pointer;margin:2px 0"
                 onclick="console.log('{code}')">
                <div style="font-size:0.8rem;color:#8b949e">{bt.name}</div>
                <div style="font-size:0.75rem;color:#8b949e">{code}</div>
                <div style="font-size:1.1rem;font-weight:700;color:{color};margin:4px 0">{ret:+.1f}%</div>
                <div style="font-size:0.7rem;color:#8b949e">{bt.win_rate:.0f}% | {bt.trade_count}笔</div>
            </div>
            """, unsafe_allow_html=True)
            if st.button(f"查看 {code}", key=f"sel_{code}", use_container_width=True):
                SS.active_code = code
                st.rerun()

    # ── Detail view ──
    active_code = SS.active_code
    if not active_code or active_code not in results:
        st.info("点击上方股票卡片查看详细回测报告")
        return

    bt = results[active_code]
    st.divider()
    st.subheader(f"{bt.name} ({bt.code}) — 回测详细报告")

    # Metrics
    m1, m2, m3, m4, m5, m6, m7 = st.columns(7)
    m1.metric("胜率", f"{bt.win_rate:.0f}%")
    m2.metric("总收益", f"{bt.total_return_pct:+.1f}%")
    m3.metric("最大回撤", f"{bt.max_drawdown_pct:.1f}%")
    m4.metric("盈亏比", f"{bt.profit_factor:.2f}")
    m5.metric("交易次数", str(bt.trade_count))
    m6.metric("平均盈利", f"{bt.avg_win_pct:+.1f}%")
    m7.metric("平均持仓", f"{bt.avg_bars_held:.0f}天")

    # K-line chart with signals
    st.plotly_chart(build_kline_chart(bt), use_container_width=True)

    # Equity curve
    st.plotly_chart(build_equity_chart(bt), use_container_width=True)

    # Trade log
    st.divider()
    st.caption(f"逐笔交易明细 ({bt.trade_count}笔)")
    if bt.trades:
        trade_rows = []
        for t in bt.trades:
            trade_rows.append({
                "入场日": t.entry_date,
                "信号": t.signal_type,
                "入场价": f"{t.entry_price:.2f}",
                "出场日": t.exit_date,
                "出场价": f"{t.exit_price:.2f}",
                "盈亏": f"{t.pnl_pct:+.2f}%",
                "结果": t.exit_reason,
                "持仓天": t.bars_held,
                "入场理由": t.entry_reason[:50],
                "出场详情": t.exit_detail,
            })
        def _color_pnl(val):
            if isinstance(val, str):
                if val.startswith("+"): return "color:#3fb950"
                if val.startswith("-"): return "color:#f85149"
            return ""

        st.dataframe(
            pd.DataFrame(trade_rows).style.map(_color_pnl, subset=["盈亏"]),
            use_container_width=True, hide_index=True,
        )

    st.caption(f"数据: push2his · 回测窗口={window}根K线 · {datetime.now():%Y-%m-%d %H:%M}")


if __name__ == "__main__":
    main()

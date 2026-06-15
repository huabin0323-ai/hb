"""PA 投研面板 — A股多时间框架 · K线PA标注 · 入场/离场信号"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime, timedelta
import time
import baostock as bs

from src.price_action import analyze as pa_analyze

st.set_page_config(page_title="PA 投研面板", layout="wide", page_icon="📊")

# ======================================================================
# Data — baostock (稳定, 不依赖东财API)
# ======================================================================

TIMEFRAME_MAP = {
    "📅 日线": "d",
    "📆 周线": "w",
    "🕐 60分钟": "60",
    "⏱ 30分钟": "30",
}

SH_PREFIX = {"600", "601", "603", "605"}
SZ_PREFIX = {"000", "001", "002", "003", "300", "301"}

def to_baostock_code(code: str) -> str:
    """600519 -> sh.600519"""
    if code.startswith(("sh.", "sz.")):
        return code
    prefix = "sh." if any(code.startswith(p) for p in SH_PREFIX) else "sz."
    return prefix + code


@st.cache_data(ttl=300)
def fetch_klines(code: str, freq: str = "d", limit: int = 200):
    """拉A股K线。freq: d/w/60/30。baostock日线秒出，分钟级约5秒。"""
    try:
        bs_code = to_baostock_code(code)
        bs.login()

        # 确定起止日期
        end = datetime.now()
        if freq in ("d", "w"):
            start = end - timedelta(days=limit * 2)  # 覆盖足够交易日
        else:
            start = end - timedelta(days=5)  # 分钟数据只取最近几天

        start_str = start.strftime("%Y-%m-%d")
        end_str = end.strftime("%Y-%m-%d")

        fields = "date,time,open,high,low,close,volume" if freq in ("60", "30") else "date,open,high,low,close,volume"
        rs = bs.query_history_k_data_plus(bs_code, fields, start_date=start_str,
                                           end_date=end_str, frequency=freq, adjustflag="2")
        if rs.error_code != "0":
            bs.logout()
            return pd.DataFrame()

        rows = []
        while (rs.error_code == "0") & rs.next():
            rows.append(rs.get_row_data())
        bs.logout()

        if not rows:
            return pd.DataFrame()

        if freq in ("60", "30"):
            df = pd.DataFrame(rows, columns=["date", "time", "open", "high", "low", "close", "volume"])
            df["datetime"] = pd.to_datetime(df["date"] + " " + df["time"])
            df = df.set_index("datetime")
        else:
            df = pd.DataFrame(rows, columns=["date", "open", "high", "low", "close", "volume"])
            df["date"] = pd.to_datetime(df["date"])
            df = df.set_index("date")

        for col in ["open", "high", "low", "close", "volume"]:
            df[col] = pd.to_numeric(df[col], errors="coerce")

        return df.tail(limit).dropna()
    except Exception:
        return pd.DataFrame()


DEFAULT_POOL = [
    {"code": "600519", "name": "贵州茅台"},
    {"code": "000858", "name": "五粮液"},
    {"code": "300750", "name": "宁德时代"},
    {"code": "601318", "name": "中国平安"},
    {"code": "600036", "name": "招商银行"},
    {"code": "002415", "name": "海康威视"},
    {"code": "000333", "name": "美的集团"},
    {"code": "600900", "name": "长江电力"},
]


@st.cache_data(ttl=600)
def load_stock_pool():
    pool = [{"code": s["code"], "name": s["name"]} for s in DEFAULT_POOL]
    for code in st.session_state.get("custom_wl", []):
        if not any(s["code"] == code for s in pool):
            pool.append({"code": code, "name": code})
    return pool


# ======================================================================
# Chart Builder — K线图 + PA 标注
# ======================================================================

def build_pa_chart(df: pd.DataFrame, pa_result: dict, title: str = "",
                   show_volume: bool = True):
    """构建带 PA 标注的 K 线图"""
    if df.empty or len(df) < 20:
        return go.Figure()

    # Run PA analysis
    state = pa_result.get("state")
    swings = pa_result.get("swings", {}).get("minor", [])
    tech_score = pa_result.get("technical_score")
    all_entries = [e for k in ["entry_signals", "double_bottoms", "ema_signals",
                                "spike_channels", "trend_resumptions", "final_flags",
                                "support_betrayals", "vacuum_effects", "wedges"]
                   for e in pa_result.get(k, [])]

    rows = 2 if show_volume else 1
    fig = make_subplots(
        rows=rows, cols=1, shared_xaxes=True,
        row_heights=[0.7, 0.3] if show_volume else [1.0],
        vertical_spacing=0.03,
    )

    # K-line
    colors = ["#ef5350" if df["close"].iloc[i] < df["open"].iloc[i] else "#26a69a"
              for i in range(len(df))]
    fig.add_trace(go.Candlestick(
        x=df.index, open=df["open"], high=df["high"],
        low=df["low"], close=df["close"], name="K线",
        increasing_line_color="#26a69a", decreasing_line_color="#ef5350",
    ), row=1, col=1)

    # EMA20
    if len(df) >= 20:
        ema20 = df["close"].ewm(span=20, adjust=False).mean()
        fig.add_trace(go.Scatter(
            x=df.index, y=ema20, mode="lines", name="EMA20",
            line=dict(color="#ff9800", width=1, dash="dot"),
            opacity=0.6,
        ), row=1, col=1)

    # Swing points
    if swings:
        high_pts = [(s.index, s.price) for s in swings if s.type == "high" and s.index < len(df)]
        low_pts = [(s.index, s.price) for s in swings if s.type == "low" and s.index < len(df)]
        if high_pts:
            hx, hy = zip(*high_pts)
            fig.add_trace(go.Scatter(
                x=[df.index[i] for i in hx], y=hy, mode="markers",
                marker=dict(symbol="triangle-down", size=8, color="#ef5350"),
                name="摆动高点",
            ), row=1, col=1)
        if low_pts:
            lx, ly = zip(*low_pts)
            fig.add_trace(go.Scatter(
                x=[df.index[i] for i in lx], y=ly, mode="markers",
                marker=dict(symbol="triangle-up", size=8, color="#26a69a"),
                name="摆动低点",
            ), row=1, col=1)

    # S/R lines from channel
    if state and state.channel_top:
        fig.add_hline(y=state.channel_top, line_dash="dash", line_color="#ef5350",
                      opacity=0.4, annotation_text="阻力", row=1, col=1)
    if state and state.channel_bottom:
        fig.add_hline(y=state.channel_bottom, line_dash="dash", line_color="#26a69a",
                      opacity=0.4, annotation_text="支撑", row=1, col=1)

    # Entry signals
    for es in all_entries:
        if es.entry_price > 0:
            fig.add_hline(y=es.entry_price, line_dash="dot", line_color="#ffeb3b",
                          opacity=0.5, row=1, col=1,
                          annotation_text=f"{es.type}:{es.entry_price:.1f}")
        if es.stop_loss > 0:
            fig.add_hline(y=es.stop_loss, line_dash="dot", line_color="#ef5350",
                          opacity=0.3, row=1, col=1)

    # Volume
    if show_volume:
        fig.add_trace(go.Bar(
            x=df.index, y=df["volume"], name="成交量",
            marker_color=colors, opacity=0.5,
        ), row=2, col=1)

    # Layout
    score_text = f" | PA评分: {tech_score.score}/100" if tech_score else ""
    fig.update_layout(
        title=f"{title}{score_text}",
        height=500, margin=dict(l=10, r=10, t=40, b=10),
        xaxis_rangeslider_visible=False,
        template="plotly_dark",
        hovermode="x unified",
        showlegend=False,
    )
    fig.update_xaxes(gridcolor="#333", row=1, col=1)
    fig.update_xaxes(gridcolor="#333", row=2, col=1)
    fig.update_yaxes(gridcolor="#333", row=1, col=1)
    fig.update_yaxes(gridcolor="#333", row=2, col=1)

    return fig


# ======================================================================
# Signal Analysis Panel
# ======================================================================

def render_signal_panel(pa_result: dict):
    """渲染信号分析面板"""
    state = pa_result.get("state")
    tech = pa_result.get("technical_score")
    if not state or not tech:
        st.info("需要更多K线数据进行分析")
        return

    # 市场结构
    st.subheader("📐 市场结构")
    c1, c2, c3, c4 = st.columns(4)
    trend_labels = {
        "uptrend": "🟢 上升趋势", "downtrend": "🔴 下降趋势",
        "trading_range": "🟡 交易区间", "narrow_channel": "🟢 窄通道",
        "wide_channel": "🟡 宽通道",
    }
    c1.metric("趋势", trend_labels.get(state.trend, state.trend))
    c2.metric("强度", f"{state.strength:.2f}")
    c3.metric("倾向", "偏多" if state.bias == "long" else "偏空" if state.bias == "short" else "中性")
    c4.metric("说明", state.description if state.description else "-")

    if state.channel_top and state.channel_bottom:
        st.caption(f"通道: {state.channel_bottom:.2f} - {state.channel_top:.2f}")

    # 技术评分
    st.subheader(f"🎯 技术评分: {tech.score}/100")
    st.progress(tech.score / 100, text=tech.summary)
    if tech.breakdown:
        cols = st.columns(len(tech.breakdown))
        for i, (k, v) in enumerate(tech.breakdown.items()):
            cols[i].metric(k, f"{v:.1f}")

    # 入场信号详情
    all_signals = {}
    for k in ["entry_signals", "double_bottoms", "ema_signals", "final_flags",
              "vacuum_effects", "spike_channels", "trend_resumptions",
              "support_betrayals", "failed_breakouts", "wedges"]:
        signals = pa_result.get(k, [])
        if signals:
            all_signals[k] = signals

    if all_signals:
        st.subheader("🚦 检测到的信号")
        for sig_type, signals in all_signals.items():
            for s in signals:
                conf_color = "🟢" if s.confidence >= 0.7 else "🟡" if s.confidence >= 0.5 else "🔴"
                with st.expander(f"{conf_color} [{sig_type}] {s.description} (置信度: {s.confidence:.0%})"):
                    c1, c2, c3, c4 = st.columns(4)
                    c1.metric("方向", "做多" if s.direction == "long" else "做空")
                    if s.entry_price > 0:
                        c2.metric("入场价", f"{s.entry_price:.2f}")
                        c3.metric("止损", f"{s.stop_loss:.2f}")
                        c4.metric("目标", f"{s.target:.2f}")
                        if s.stop_loss > 0 and s.entry_price > 0:
                            rr = abs(s.target - s.entry_price) / abs(s.entry_price - s.stop_loss)
                            st.caption(f"盈亏比: {rr:.1f}:1")
    else:
        st.info("当前未检测到明确入场信号 — 等待价格行为确认")


# ======================================================================
# Main Dashboard
# ======================================================================

def main():
    st.title("📊 PA 投研面板")
    st.caption("Al Brooks 价格行为学 · 多时间框架 · 15策略自动检测")
    st.caption("数据: Binance · PA 策略品种无关，加密/A股/期货逻辑一致")

    # ---- Sidebar ----
    with st.sidebar:
        st.header("🎯 自选池")

        if "custom_wl" not in st.session_state:
            st.session_state["custom_wl"] = []

        if st.button("🔄 刷新", use_container_width=True):
            st.rerun()

        pool = load_stock_pool()
        st.caption(f"共 {len(pool)} 只")

        code_input = st.text_input("添加代码", placeholder="600519")
        if st.button("➕ 添加") and code_input:
            if code_input not in st.session_state["custom_wl"]:
                st.session_state["custom_wl"].append(code_input)
                load_stock_pool.clear()
                st.rerun()

        st.divider()

        for i, s in enumerate(pool):
            label = f"{s['name']} ({s['code']})"
            btn_type = "primary" if st.session_state.get("active_stock") == s["code"] else "secondary"
            if st.button(label, key=f"stock_{i}", use_container_width=True, type=btn_type):
                st.session_state["active_stock"] = s["code"]
                st.session_state["active_name"] = s["name"]
                st.rerun()

        st.divider()
        st.caption(f"数据: baostock · {datetime.now().strftime('%H:%M:%S')}")

    # ---- Main ----
    active_code = st.session_state.get("active_stock", "")
    active_name = st.session_state.get("active_name", "")

    if not active_code:
        st.info("👈 左侧选一只股票开始分析")
        st.markdown("""
        ### 多时间框架 PA 分析流程
        1. **日线看趋势** → 判断大方向（上升/下降/区间/通道）
        2. **周线看结构** → 找主要摆动点、通道边界
        3. **60分钟定入场** → 精确入场/止损/目标位
        4. **30分钟确认** → 小周期信号共振验证

        ### 自动检测 15 个 PA 策略
        H1/H2/H3 · 楔形 · 假突破 · 支撑背叛 · 阴线做多 · 高潮预警
        双底牛旗 · EMA20互动 · 最终旗形 · 真空效应 · 水平S/R
        测量缺口 · 急速与通道 · 趋势恢复日 · 孕线衰竭
        """)
        return

    st.header(f"{active_name} ({active_code})")
    try:
        df_q = fetch_klines(active_code, "d", 5)
        if not df_q.empty:
            latest = df_q.iloc[-1]
            prev = df_q.iloc[-2] if len(df_q) >= 2 else latest
            chg = (latest["close"] - prev["close"]) / prev["close"] * 100
            st.caption(f"¥{latest['close']:.2f} ({chg:+.2f}%)")
    except Exception:
        pass

    # Timeframe tabs
    tf_tabs = st.tabs(list(TIMEFRAME_MAP.keys()))
    pa_results = {}

    for tab, (tf_label, tf_freq) in zip(tf_tabs, TIMEFRAME_MAP.items()):
        with tab:
            with st.spinner(f"加载 {tf_label} + PA分析..."):
                df = fetch_klines(active_code, tf_freq, limit=200)
                if df.empty or len(df) < 20:
                    st.warning(f"{tf_label} 数据不足（{len(df)}根K线，需要≥20）")
                    continue

                pa_result = pa_analyze(df)
                pa_results[tf_freq] = pa_result

                fig = build_pa_chart(df, pa_result, title=f"{active_name} · {tf_label}")
                if fig.data:
                    st.plotly_chart(fig, use_container_width=True, key=f"chart_{tf_freq}")

                render_signal_panel(pa_result)

    # Cross-TF Summary
    if pa_results:
        st.divider()
        st.subheader("🔍 多时间框架综合判断")

        scores = []
        for tf, r in pa_results.items():
            ts = r.get("technical_score")
            stt = r.get("state")
            if ts and stt:
                scores.append((tf, ts.score, stt.trend, stt.strength, stt.bias))

        if scores:
            cols = st.columns(len(scores))
            for i, (tf, sc, trend, strength, bias) in enumerate(scores):
                dir_icon = "🟢" if bias == "long" else "🔴" if bias == "short" else "🟡"
                cols[i].metric(tf, f"{sc}/100", f"{dir_icon} {trend}")

            long_tfs = [s for s in scores if s[4] == "long"]
            if len(long_tfs) >= 3:
                st.success(f"✅ {len(long_tfs)}/4 时间框架一致看多 — 高确信度")
            elif len(long_tfs) >= 2:
                st.info(f"⚠️ {len(long_tfs)}/4 看多 — 等待更多确认")
            elif len([s for s in scores if s[1] >= 50]) == 0:
                st.warning("❌ 各时间框架信号均偏弱 — 建议观望")

    st.divider()
    st.caption("PA 投研面板 · baostock · Al Brooks + Mr.西土瓦 15策略")
    st.caption("分钟数据首次加载约5-8秒（只拉最近几天），后续有缓存")


if __name__ == "__main__":
    main()

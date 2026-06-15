"""A股PA回测桌面应用 — PySide6 + matplotlib
原生窗口 · 深色主题 · K线信号标注 · 可扩展 · 全中文界面
"""
from __future__ import annotations

import sys, json, logging
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("QtAgg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QSplitter, QTabWidget, QTableWidget, QTableWidgetItem, QHeaderView,
    QLabel, QLineEdit, QPushButton, QSpinBox, QDoubleSpinBox,
    QSlider, QGroupBox, QFormLayout, QProgressBar, QStatusBar,
    QMessageBox, QCheckBox, QComboBox, QFrame,
)
from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import (
    QColor, QPalette, QFont, QAction,
)

logging.basicConfig(level=logging.WARNING)
sys.path.insert(0, str(Path(__file__).parent))

# 中文字体设置
plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False


# ══════════════════════════════════════════════════════════════
# 回测工作线程
# ══════════════════════════════════════════════════════════════

class BacktestWorker(QThread):
    """后台跑回测，不阻塞界面"""
    进度 = Signal(int, str)
    单股完成 = Signal(str, object)
    全部完成 = Signal()

    def __init__(self, 代码列表, 窗口, 最低分, 最低盈亏比, 最大持仓):
        super().__init__()
        self.代码列表 = 代码列表
        self.窗口 = 窗口
        self.最低分 = 最低分
        self.最低盈亏比 = 最低盈亏比
        self.最大持仓 = 最大持仓

    def run(self):
        from src.a_share.fetcher import compute_dma_metrics
        from src.a_share.pa_backtest import run_pa_backtest, BacktestResult
        total = len(self.代码列表)
        for i, code in enumerate(self.代码列表):
            try:
                bt = run_pa_backtest(code, code, self.窗口, self.最低分,
                                    self.最低盈亏比, self.最大持仓)
                self.单股完成.emit(code, bt)
                self.进度.emit(int((i+1)/total*100), f"{code} 完成")
            except Exception as e:
                # 失败了也要显示在列表里
                bt = BacktestResult(code=code, name=code, total_bars=0,
                    signal_count=0, trade_count=0, win_trades=0, lose_trades=0,
                    win_rate=0, total_return_pct=0, max_drawdown_pct=0,
                    profit_factor=0, avg_win_pct=0, avg_loss_pct=0, avg_bars_held=0)
                self.单股完成.emit(code, bt)
                self.进度.emit(int((i+1)/total*100), f"{code} 失败: {str(e)[:40]}")
        self.全部完成.emit()


# ══════════════════════════════════════════════════════════════
# 筛选工作线程
# ══════════════════════════════════════════════════════════════

class ScreenerWorker(QThread):
    进度 = Signal(int, str)
    结果就绪 = Signal(list)
    完成 = Signal()

    def __init__(self, 最低价=5.0, 最高价=60.0, 最低成交额亿=1.5, 最低振幅=4.0, 取前N=10):
        super().__init__()
        self.最低价 = 最低价; self.最高价 = 最高价
        self.最低成交额亿 = 最低成交额亿; self.最低振幅 = 最低振幅; self.取前N = 取前N

    def run(self):
        from src.a_share.ifind_adapter import fetch_kline
        from src.a_share.pa_backtest import analyze_structure

        self.进度.emit(5, "拉取全A股实时行情(Sina源)...")

        # 用AKShare Sina源（HTTP，不走SSL）
        stock_codes = []
        try:
            import akshare as ak
            df_all = ak.stock_zh_a_spot()
            # Sina columns: 代码 名称 最新价 涨跌额 涨跌幅 买入 卖出 昨收 今开 最高 最低 成交量 成交额
            for _, r in df_all.iterrows():
                code = str(r.get("代码",""))
                name = str(r.get("名称",""))
                if not code or "ST" in name: continue
                price = float(r.get("最新价",0))
                if price < self.最低价 or price > self.最高价: continue
                pct = float(r.get("涨跌幅",0))
                if abs(pct) >= 9.8: continue
                amount = float(r.get("成交额",0))
                if amount < self.最低成交额亿 * 1e8: continue
                # 新浪源: 用最高/最低算振幅
                high = float(r.get("最高",0)); low = float(r.get("最低",0))
                prev_close = float(r.get("昨收",0))
                amplitude = (high - low) / prev_close * 100 if prev_close > 0 else 0
                if amplitude < self.最低振幅: continue
                stock_codes.append({"code":code,"name":name,"price":price,"pct":pct,
                    "amount":amount,"amplitude":amplitude,"turnover":0,"total_mv":0})
        except Exception as e:
            self.进度.emit(100, f"股票列表获取失败: {e}"); self.完成.emit(); return

        if not stock_codes:
            self.进度.emit(100, "硬过滤后无候选，放宽条件试试"); self.完成.emit(); return

        # 候选太多时按成交额排序取前200，控制PA评分耗时
        if len(stock_codes) > 200:
            stock_codes.sort(key=lambda x: -x["amount"])
            stock_codes = stock_codes[:200]

        self.进度.emit(25, f"硬过滤: {len(stock_codes)}只，PA评分中...")
        candidates = stock_codes
        scored = []
        total = len(candidates)
        for i, c in enumerate(candidates):
            try:
                df = fetch_kline(c["code"], days=80)  # 80天够判断结构
                if df.empty or len(df) < 30: continue
                struct = analyze_structure(
                    df["high"].values.astype(float), df["low"].values.astype(float),
                    df["close"].values.astype(float))
                trend = struct.get("trend",""); stage = struct.get("stage",0)
                score = 0
                if trend in ("上升趋势","下降趋势"): score += 30 + (10 if stage in (2,3) else 0)
                elif trend == "交易区间": score += 15
                amp = c["amplitude"]
                score += 25 if amp > 8 else 20 if amp > 6 else 15 if amp > 4 else 10
                sup = struct.get("support",0); res = struct.get("resistance",0)
                if sup > 0 and res > 0:
                    rng = (res-sup)/sup*100; score += 15 if 5 < rng < 30 else 10
                if len(struct.get("swing_highs",[])) >= 3 and len(struct.get("swing_lows",[])) >= 3:
                    score += 5
                to = c.get("turnover",0)
                if to > 0: score += 15 if 3 <= to <= 15 else 10 if 1 <= to <= 20 else 5
                else: score += 10  # 无换手数据，给基础分
                c["pa_score"] = score; c["trend"] = trend; c["stage"] = stage
                c["channel"] = struct.get("channel",""); c["strength"] = round(struct.get("strength",0),2)
                c["support"] = round(sup,2); c["resistance"] = round(res,2)
                c["ema20"] = round(struct.get("ema20",0),2); c["atr14"] = round(struct.get("atr14",0),2)
                scored.append(c)
            except: continue
            if i % 5 == 0:
                self.进度.emit(25 + int(i/total*65), f"{c['name']}({c['code']}) {i}/{total}")
        scored.sort(key=lambda x: -x["pa_score"])
        self.进度.emit(95, f"完成: TOP{min(self.取前N, len(scored))}")
        self.结果就绪.emit(scored[:self.取前N])
        self.完成.emit()

# ══════════════════════════════════════════════════════════════
# K线图
# ══════════════════════════════════════════════════════════════

class K线画布(FigureCanvas):
    """日线K线 + 买卖点标注"""
    def __init__(self, parent=None):
        self.fig = Figure(figsize=(12, 6), dpi=100, facecolor="#0d1117")
        self.fig.subplots_adjust(left=0.06, right=0.98, top=0.93, bottom=0.12, hspace=0.05)
        self.ax主图 = self.fig.add_subplot(211)
        self.ax量 = self.fig.add_subplot(212, sharex=self.ax主图)
        super().__init__(self.fig)
        self.setParent(parent)
        self.setStyleSheet("background:#0d1117;")
        self.setSizePolicy(
            self.sizePolicy().horizontalPolicy(),
            self.sizePolicy().verticalPolicy().Expanding
        )

    def 画图(self, 回测结果):
        self.ax主图.clear()
        self.ax量.clear()

        bt = 回测结果
        if not bt or not bt.daily_klines:
            self.draw(); return

        df = pd.DataFrame(bt.daily_klines)
        if df.empty:
            self.draw(); return

        df["date"] = pd.to_datetime(df["date"])
        df = df.set_index("date")

        阳色, 阴色 = "#3fb950", "#f85149"

        # 画K线
        for i, (idx, row) in enumerate(df.iterrows()):
            o, h, l, c = row["open"], row["high"], row["low"], row["close"]
            color = 阳色 if c >= o else 阴色
            # 影线
            self.ax主图.plot([i, i], [l, h], color=color, linewidth=0.8, solid_capstyle="round")
            # 实体
            bottom = min(o, c)
            height = max(abs(c - o), (h - l) * 0.05)
            self.ax主图.bar(i, height, 0.6, bottom=bottom, color=color,
                          edgecolor=color, linewidth=0.5, alpha=0.95)

        # MA20
        if len(df) >= 20:
            ma20 = df["close"].rolling(20).mean()
            self.ax主图.plot(range(len(df)), ma20.values, color="#d4a017",
                          linewidth=1, linestyle="dotted", alpha=0.7, label="MA20")

        # 买点 ▲
        if bt.buy_markers:
            for bm in bt.buy_markers:
                idx = min(bm["idx"], len(df)-1)
                self.ax主图.scatter(idx, bm["price"], marker="^", s=90, c="#3fb950",
                                 edgecolors="#fff", linewidths=0.8, zorder=5)
                self.ax主图.annotate(bm["signal"], (idx, bm["price"]),
                                  textcoords="offset points", xytext=(0, 12),
                                  fontsize=7, color="#3fb950", ha="center", fontweight="bold")

        # 卖点 ▼
        if bt.sell_markers:
            for sm in bt.sell_markers:
                idx = min(sm["idx"], len(df)-1)
                self.ax主图.scatter(idx, sm["price"], marker="v", s=90, c="#f85149",
                                 edgecolors="#fff", linewidths=0.8, zorder=5)
                label = f"{sm['reason']} {sm['pnl_pct']:+.1f}%"
                self.ax主图.annotate(label, (idx, sm["price"]),
                                  textcoords="offset points", xytext=(0, -14),
                                  fontsize=6.5, color="#f85149", ha="center")

        self.ax主图.set_facecolor("#0d1117")
        self.ax主图.tick_params(colors="#8b949e", labelsize=7)
        self.ax主图.grid(axis="y", color="#21262d", linewidth=0.5, alpha=0.5)
        标题 = f"{bt.name} ({bt.code})    胜率 {bt.win_rate:.0f}%    收益 {bt.total_return_pct:+.1f}%    交易 {bt.trade_count} 笔"
        self.ax主图.set_title(标题, color="#e6edf3", fontsize=10, fontweight="bold", loc="left", pad=10)

        # 成交量
        for i, (idx, row) in enumerate(df.iterrows()):
            color = 阳色 if row["close"] >= row["open"] else 阴色
            self.ax量.bar(i, row["volume"], 0.6, color=color, alpha=0.35)

        self.ax量.set_facecolor("#0d1117")
        self.ax量.tick_params(colors="#8b949e", labelsize=7)
        self.ax量.grid(axis="y", color="#21262d", linewidth=0.5, alpha=0.5)
        self.ax量.set_ylabel("成交量", color="#8b949e", fontsize=8)
        self.ax量.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, _: f"{x/1e6:.0f}M"))

        n = len(df)
        step = max(1, n // 8)
        ticks = list(range(0, n, step))
        labels = [df.index[i].strftime("%m/%d") for i in ticks]
        self.ax量.set_xticks(ticks)
        self.ax量.set_xticklabels(labels, fontsize=7, color="#8b949e")
        plt.setp(self.ax主图.get_xticklabels(), visible=False)

        plt.setp(self.ax主图.get_xticklabels(), visible=False)
        self.draw()


class 权益曲线画布(FigureCanvas):
    """权益曲线"""
    def __init__(self, parent=None):
        self.fig = Figure(figsize=(8, 2.5), dpi=100, facecolor="#0d1117")
        self.fig.subplots_adjust(left=0.06, right=0.98, top=0.90, bottom=0.18)
        self.ax = self.fig.add_subplot(111)
        super().__init__(self.fig)
        self.setParent(parent)
        self.setStyleSheet("background:#0d1117;")

    def 画图(self, bt):
        self.ax.clear()
        if not bt or not bt.equity_curve:
            self.draw(); return
        eq = pd.DataFrame(bt.equity_curve)
        self.ax.plot(range(len(eq)), eq["equity"].values, color="#d4a017", linewidth=2)
        self.ax.fill_between(range(len(eq)), 100, eq["equity"].values,
                            color="#d4a017", alpha=0.08)
        self.ax.axhline(y=100, color="#30363d", linewidth=0.8, linestyle="--")

        self.ax.set_facecolor("#0d1117")
        self.ax.tick_params(colors="#8b949e", labelsize=7)
        self.ax.grid(color="#21262d", linewidth=0.5, alpha=0.5)
        self.ax.set_title("权益曲线", color="#e6edf3", fontsize=9, fontweight="bold", loc="left", pad=8)
        self.ax.set_ylabel("权益", color="#8b949e", fontsize=8)
        plt.setp(self.ax主图.get_xticklabels(), visible=False)
        self.draw()


# ══════════════════════════════════════════════════════════════
# 主窗口
# ══════════════════════════════════════════════════════════════

class 主窗口(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("A股PA策略回测系统")
        self.resize(1500, 880)
        self.setMinimumSize(1200, 750)

        self.回测结果: dict[str, object] = {}
        self.当前代码 = ""
        self.工作线程: Optional[BacktestWorker] = None
        self.筛选线程: Optional[ScreenerWorker] = None
        self.top10结果 = []

        self._设置主题()
        self._构建界面()
        self._构建菜单()

        self.statusBar().showMessage("就绪 — 输入股票代码，点击「开始回测」")

    def _设置主题(self):
        p = QPalette()
        p.setColor(QPalette.Window, QColor("#0d1117"))
        p.setColor(QPalette.WindowText, QColor("#e6edf3"))
        p.setColor(QPalette.Base, QColor("#161b22"))
        p.setColor(QPalette.AlternateBase, QColor("#0d1117"))
        p.setColor(QPalette.Text, QColor("#c9d1d9"))
        p.setColor(QPalette.Button, QColor("#21262d"))
        p.setColor(QPalette.ButtonText, QColor("#c9d1d9"))
        p.setColor(QPalette.Highlight, QColor("#d4a017"))
        p.setColor(QPalette.HighlightedText, QColor("#000000"))
        self.setPalette(p)
        self.setStyleSheet("""
            QMainWindow { background: #0d1117; }
            QGroupBox { color: #e6edf3; border: 1px solid #21262d; border-radius: 6px;
                       margin-top: 14px; padding-top: 18px; font-weight: bold; font-size: 13px; }
            QGroupBox::title { subcontrol-origin: margin; left: 12px; padding: 0 6px; }
            QLineEdit, QSpinBox, QDoubleSpinBox {
                background: #0d1117; color: #c9d1d9; border: 1px solid #30363d;
                border-radius: 4px; padding: 4px 8px; font-size: 13px;
            }
            QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus { border-color: #d4a017; }
            QPushButton {
                background: #21262d; color: #c9d1d9; border: 1px solid #30363d;
                border-radius: 6px; padding: 6px 16px; font-size: 13px;
            }
            QPushButton:hover { background: #30363d; border-color: #8b949e; }
            QPushButton#开始回测按钮 {
                background: #d4a017; color: #000000; font-weight: bold; border: none;
                padding: 10px 24px; font-size: 15px;
            }
            QPushButton#开始回测按钮:hover { background: #e6b422; }
            QTableWidget {
                background: #161b22; color: #c9d1d9; border: 1px solid #21262d;
                border-radius: 6px; gridline-color: #21262d; font-size: 12px;
            }
            QTableWidget::item { padding: 4px 10px; }
            QTableWidget::item:selected { background: #1f2a3a; color: #e6edf3; }
            QHeaderView::section {
                background: #161b22; color: #8b949e; border: none;
                border-bottom: 1px solid #21262d; padding: 6px 10px; font-size: 11px; font-weight: bold;
            }
            QTabWidget::pane { border: 1px solid #21262d; border-radius: 6px; background: #0d1117; }
            QTabBar::tab {
                background: #161b22; color: #8b949e; border: 1px solid #21262d;
                padding: 7px 18px; margin-right: 2px; border-radius: 4px 4px 0 0; font-size: 13px;
            }
            QTabBar::tab:selected { background: #0d1117; color: #d4a017; border-bottom: 2px solid #d4a017; }
            QProgressBar {
                background: #21262d; border: none; border-radius: 4px; height: 6px;
                text-align: center; color: #8b949e; font-size: 11px;
            }
            QProgressBar::chunk { background: #d4a017; border-radius: 4px; }
            QSplitter::handle { background: #21262d; width: 2px; }
            QStatusBar { background: #161b22; color: #8b949e; border-top: 1px solid #21262d; }
        """)

    def _构建界面(self):
        central = QWidget()
        self.setCentralWidget(central)
        main_h = QHBoxLayout(central)
        main_h.setContentsMargins(8, 8, 8, 8)
        main_h.setSpacing(8)

        splitter = QSplitter(Qt.Horizontal)
        main_h.addWidget(splitter)

        # ── 左侧面板 ──
        left = QWidget()
        left.setMinimumWidth(300)
        left.setMaximumWidth(380)
        ll = QVBoxLayout(left)
        ll.setContentsMargins(6, 6, 6, 6)
        ll.setSpacing(8)

        # 参数组
        ctrl = QGroupBox("回测参数")
        cf = QFormLayout(ctrl)
        cf.setSpacing(6)

        self.代码输入 = QLineEdit()
        self.代码输入.setPlaceholderText("600519,000858,300750...")
        self.代码输入.setText("600519,000858,300750,002415,601318,600036,002594,601899,600900,000333")
        self.代码输入.returnPressed.connect(self._开始回测)
        代码标签 = QLabel("股票代码 (逗号分隔，回车直接回测)")
        代码标签.setStyleSheet("color:#8b949e; font-size:11px;")
        cf.addRow(代码标签, self.代码输入)

        self.PA窗口 = QSpinBox()
        self.PA窗口.setRange(50, 200); self.PA窗口.setValue(100)
        self.PA窗口.setSuffix(" 根K线")
        窗口标签 = QLabel("PA分析窗口 (滑动窗口大小，越大趋势判定越稳定)")
        窗口标签.setStyleSheet("color:#8b949e; font-size:11px;")
        cf.addRow(窗口标签, self.PA窗口)

        self.最低分 = QSpinBox()
        self.最低分.setRange(20, 60); self.最低分.setValue(35)
        分标签 = QLabel("最低信号分 (低于此分数的信号被过滤)")
        分标签.setStyleSheet("color:#8b949e; font-size:11px;")
        cf.addRow(分标签, self.最低分)

        self.最低盈亏比 = QDoubleSpinBox()
        self.最低盈亏比.setRange(1.0, 3.0); self.最低盈亏比.setValue(1.3)
        self.最低盈亏比.setSingleStep(0.1); self.最低盈亏比.setDecimals(1)
        rr标签 = QLabel("最低盈亏比 R:R (止盈距离/止损距离，越大越保守)")
        rr标签.setStyleSheet("color:#8b949e; font-size:11px;")
        cf.addRow(rr标签, self.最低盈亏比)

        self.最大持仓 = QSpinBox()
        self.最大持仓.setRange(5, 40); self.最大持仓.setValue(20)
        self.最大持仓.setSuffix(" 天")
        持仓标签 = QLabel("最大持仓天数 (超过未触发止盈/止损则强制平仓)")
        持仓标签.setStyleSheet("color:#8b949e; font-size:11px;")
        cf.addRow(持仓标签, self.最大持仓)

        ll.addWidget(ctrl)

        # 开始按钮
        self.开始按钮 = QPushButton("开始回测")
        self.开始按钮.setObjectName("开始回测按钮")
        self.开始按钮.clicked.connect(self._开始回测)
        ll.addWidget(self.开始按钮)

        # 进度条
        self.进度条 = QProgressBar()
        self.进度条.setVisible(False)
        ll.addWidget(self.进度条)

        # 结果列表（可拉伸）
        stock_gb = QGroupBox("回测结果")
        sl = QVBoxLayout(stock_gb)
        self.结果表格 = QTableWidget(0, 4)
        self.结果表格.setHorizontalHeaderLabels(["代码", "收益", "胜率", "交易"])
        self.结果表格.setSelectionBehavior(QTableWidget.SelectRows)
        self.结果表格.setEditTriggers(QTableWidget.NoEditTriggers)
        self.结果表格.clicked.connect(self._点击结果)
        self.结果表格.setColumnWidth(0, 65)
        self.结果表格.setColumnWidth(1, 65)
        self.结果表格.setColumnWidth(2, 48)
        self.结果表格.setColumnWidth(3, 42)
        self.结果表格.horizontalHeader().setStretchLastSection(True)
        self.结果表格.verticalHeader().setDefaultSectionSize(24)  # 紧凑行高
        sl.addWidget(self.结果表格)
        ll.addWidget(stock_gb, stretch=1)  # 占据剩余所有空间

        splitter.addWidget(left)

        # ── 右侧面板 ──
        right = QTabWidget()
        splitter.addWidget(right)

        # Tab 1: 图表
        chart_tab = QWidget()
        cl = QVBoxLayout(chart_tab)
        cl.setContentsMargins(4, 4, 4, 4)
        cl.setSpacing(6)

        # 指标 — 一排横排
        self.指标标签 = {}
        metrics_w = QWidget()
        mh = QHBoxLayout(metrics_w)
        mh.setContentsMargins(0, 0, 0, 0)
        mh.setSpacing(8)
        for 中文名 in ["胜率", "总收益", "最大回撤", "盈亏比", "交易次数", "平均盈利", "平均持仓"]:
            gb = QGroupBox(中文名)
            gb.setAlignment(Qt.AlignCenter)
            lbl = QLabel("—")
            lbl.setAlignment(Qt.AlignCenter)
            lbl.setStyleSheet("font-size:18px; font-weight:bold; color:#e6edf3; padding:2px;")
            gbl = QVBoxLayout(gb)
            gbl.addWidget(lbl)
            self.指标标签[中文名] = lbl
            mh.addWidget(gb)
        cl.addWidget(metrics_w)

        self.k线画布 = K线画布()
        cl.addWidget(self.k线画布, stretch=3)

        self.权益画布 = 权益曲线画布()
        cl.addWidget(self.权益画布, stretch=1)

        right.addTab(chart_tab, "📊 K线图表")

        # Tab 2: 交易明细
        log_tab = QWidget()
        ll2 = QVBoxLayout(log_tab)
        self.交易表格 = QTableWidget(0, 9)
        self.交易表格.setHorizontalHeaderLabels([
            "入场日期", "信号类型", "入场价", "出场日期", "出场价",
            "盈亏", "出场原因", "持仓天", "入场理由"
        ])
        self.交易表格.setEditTriggers(QTableWidget.NoEditTriggers)
        self.交易表格.setSelectionBehavior(QTableWidget.SelectRows)
        self.交易表格.setAlternatingRowColors(True)
        self.交易表格.horizontalHeader().setStretchLastSection(True)
        ll2.addWidget(self.交易表格)
        right.addTab(log_tab, "📋 交易明细")

        # Tab 3: 汇总排名
        summary_tab = QWidget()
        sl2 = QVBoxLayout(summary_tab)
        self.汇总表格 = QTableWidget(0, 8)
        self.汇总表格.setHorizontalHeaderLabels([
            "排名", "代码", "名称", "胜率%", "收益%", "最大回撤%", "盈亏比", "交易数"
        ])
        self.汇总表格.setEditTriggers(QTableWidget.NoEditTriggers)
        self.汇总表格.setAlternatingRowColors(True)
        self.汇总表格.horizontalHeader().setStretchLastSection(True)
        self.汇总表格.clicked.connect(self._点击汇总)
        sl2.addWidget(self.汇总表格)
        right.addTab(summary_tab, "🏆 汇总排名")

        # Tab 4: 筛选TOP10
        self._构建筛选标签(right)

        splitter.setSizes([320, 1160])

    def _构建筛选标签(self, right):
        """Tab 4: 筛选TOP10"""
        tab = QWidget()
        tv = QVBoxLayout(tab)
        tv.setContentsMargins(6, 6, 6, 6)
        tv.setSpacing(8)

        # 参数行
        params_w = QWidget()
        ph = QHBoxLayout(params_w)
        ph.setContentsMargins(0,0,0,0); ph.setSpacing(12)

        ph.addWidget(QLabel("股价 ¥"))
        self.筛最低价 = QDoubleSpinBox(); self.筛最低价.setRange(2,200); self.筛最低价.setValue(5); self.筛最低价.setPrefix("¥")
        ph.addWidget(self.筛最低价)
        ph.addWidget(QLabel("—"))
        self.筛最高价 = QDoubleSpinBox(); self.筛最高价.setRange(5,200); self.筛最高价.setValue(60); self.筛最高价.setPrefix("¥")
        ph.addWidget(self.筛最高价)

        ph.addWidget(QLabel("  日成交≥"))
        self.筛成交额 = QDoubleSpinBox(); self.筛成交额.setRange(0.5,20); self.筛成交额.setValue(1.5); self.筛成交额.setSuffix("亿")
        ph.addWidget(self.筛成交额)

        ph.addWidget(QLabel("  日振幅≥"))
        self.筛振幅 = QDoubleSpinBox(); self.筛振幅.setRange(2,15); self.筛振幅.setValue(4.0); self.筛振幅.setSuffix("%")
        ph.addWidget(self.筛振幅)

        ph.addWidget(QLabel("  取前"))
        self.筛取前N = QSpinBox(); self.筛取前N.setRange(5,30); self.筛取前N.setValue(10)
        ph.addWidget(self.筛取前N)
        ph.addWidget(QLabel("名"))

        # 说明文字
        hint = QLabel("  股价:买得起 | 成交额:流动性 | 振幅:有波动才有利润 | PA评分自动排序取TOP")
        hint.setStyleSheet("color:#8b949e; font-size:10px;")

        self.筛按钮 = QPushButton("开始筛选")
        self.筛按钮.setObjectName("开始回测按钮")
        self.筛按钮.clicked.connect(self._开始筛选)
        ph.addWidget(self.筛按钮)

        self.筛进度 = QProgressBar()
        self.筛进度.setVisible(False)
        self.筛进度.setMaximumWidth(200)
        ph.addWidget(self.筛进度)

        ph.addStretch()
        tv.addWidget(params_w)
        tv.addWidget(hint)

        # 结果表格
        self.筛结果表格 = QTableWidget(0, 10)
        self.筛结果表格.setHorizontalHeaderLabels([
            "排名","代码","名称","现价","涨跌%","振幅%","PA评分","趋势","通道","换手%"
        ])
        self.筛结果表格.setSelectionBehavior(QTableWidget.SelectRows)
        self.筛结果表格.setEditTriggers(QTableWidget.NoEditTriggers)
        self.筛结果表格.setAlternatingRowColors(True)
        self.筛结果表格.verticalHeader().setDefaultSectionSize(26)
        self.筛结果表格.setColumnWidth(0,40); self.筛结果表格.setColumnWidth(1,65)
        self.筛结果表格.setColumnWidth(2,75); self.筛结果表格.setColumnWidth(6,65)
        self.筛结果表格.horizontalHeader().setStretchLastSection(True)
        tv.addWidget(self.筛结果表格)

        # 操作行
        btn_row = QHBoxLayout()
        self.筛复制按钮 = QPushButton("复制到回测输入框")
        self.筛复制按钮.clicked.connect(self._筛选复制)
        self.筛回测按钮 = QPushButton("直接用TOP10回测")
        self.筛回测按钮.setObjectName("开始回测按钮")
        self.筛回测按钮.clicked.connect(self._筛选直接回测)
        self.筛导出按钮 = QPushButton("导出JSON")
        self.筛导出按钮.clicked.connect(self._筛选导出)
        btn_row.addWidget(self.筛复制按钮)
        btn_row.addWidget(self.筛回测按钮)
        btn_row.addWidget(self.筛导出按钮)
        btn_row.addStretch()
        tv.addLayout(btn_row)

        right.addTab(tab, "🔍 筛选TOP10")

    def _开始筛选(self):
        self.筛结果表格.setRowCount(0)
        self.top10结果 = []
        self.筛按钮.setEnabled(False); self.筛按钮.setText("筛选中...")
        self.筛进度.setVisible(True); self.筛进度.setValue(0)
        self.筛线程 = ScreenerWorker(self.筛最低价.value(), self.筛最高价.value(),
                                       self.筛成交额.value(), self.筛振幅.value(),
                                       self.筛取前N.value())
        self.筛线程.进度.connect(self._筛更新进度)
        self.筛线程.结果就绪.connect(self._筛展示)
        self.筛线程.完成.connect(self._筛完成)
        self.筛线程.start()

    def _筛更新进度(self, pct, msg):
        self.筛进度.setValue(pct)
        self.statusBar().showMessage(msg)

    def _筛展示(self, results):
        self.top10结果 = results
        self.筛结果表格.setRowCount(0)
        for rank, r in enumerate(results, 1):
            row = self.筛结果表格.rowCount()
            self.筛结果表格.insertRow(row)
            pct = r.get("pct",0); 评分 = r.get("pa_score",0)
            items = [
                (str(rank),None), (r["code"],None), (r["name"],None),
                (f"{r['price']:.2f}",None),
                (f"{pct:+.2f}%", QColor("#3fb950") if pct>=0 else QColor("#f85149")),
                (f"{r.get('amplitude',0):.1f}%",None),
                (str(评分), QColor("#d4a017") if 评分>=70 else None),
                (r.get("trend","—"),None), (r.get("channel","—"),None),
                (f"{r.get('turnover',0):.1f}%",None),
            ]
            for c, (text, color) in enumerate(items):
                item = QTableWidgetItem(text)
                if color: item.setForeground(color)
                if c == 6: item.setTextAlignment(Qt.AlignCenter); fnt=item.font(); fnt.setBold(True); item.setFont(fnt)
                self.筛结果表格.setItem(row, c, item)

    def _筛完成(self):
        self.筛按钮.setEnabled(True); self.筛按钮.setText("开始筛选")
        self.筛进度.setVisible(False)
        self.statusBar().showMessage(f"筛选完成 — TOP{len(self.top10结果)}")

    def _筛选复制(self):
        if not self.top10结果: return
        codes = ",".join(r["code"] for r in self.top10结果)
        QApplication.clipboard().setText(codes)
        self.代码输入.setText(codes)
        self.statusBar().showMessage(f"已复制 {len(self.top10结果)} 个代码到回测输入框")

    def _筛选直接回测(self):
        """筛选完后直接跳到回测"""
        if not self.top10结果:
            QMessageBox.information(self, "提示", "请先筛选")
            return
        codes = ",".join(r["code"] for r in self.top10结果)
        self.代码输入.setText(codes)
        # 切换到回测参数区并自动开始
        self.statusBar().showMessage(f"开始回测TOP{len(self.top10结果)}...")
        self._开始回测()

    def _筛选导出(self):
        if not self.top10结果: return
        out_dir = Path("output/screener")
        out_dir.mkdir(parents=True, exist_ok=True)
        fname = out_dir / f"top10_{date.today().isoformat()}.json"
        fname.write_text(json.dumps(self.top10结果, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
        self.statusBar().showMessage(f"已导出 → {fname}")

    def _构建菜单(self):
        mb = self.menuBar()
        file_m = mb.addMenu("文件")
        export_a = QAction("导出结果 JSON", self)
        export_a.triggered.connect(self._导出结果)
        file_m.addAction(export_a)
        file_m.addSeparator()
        quit_a = QAction("退出", self)
        quit_a.setShortcut("Ctrl+Q")
        quit_a.triggered.connect(self.close)
        file_m.addAction(quit_a)

    # ════════════════ 事件 ════════════════

    def _开始回测(self):
        代码们 = [c.strip() for c in self.代码输入.text().split(",") if c.strip()]
        if not 代码们:
            QMessageBox.warning(self, "提示", "请输入股票代码，用逗号分隔")
            return

        self.回测结果.clear()
        self.当前代码 = ""
        self.结果表格.setRowCount(0)
        self.汇总表格.setRowCount(0)
        self.开始按钮.setEnabled(False)
        self.开始按钮.setText("回测中...")
        self.进度条.setVisible(True)
        self.进度条.setValue(0)
        self.statusBar().showMessage(f"正在回测 {len(代码们)} 只股票...")

        self.工作线程 = BacktestWorker(
            代码们, self.PA窗口.value(), self.最低分.value(),
            self.最低盈亏比.value(), self.最大持仓.value(),
        )
        self.工作线程.单股完成.connect(self._单股完成)
        self.工作线程.进度.connect(self._更新进度)
        self.工作线程.全部完成.connect(self._全部完成)
        self.工作线程.start()

    def _单股完成(self, code, bt):
        self.回测结果[code] = bt
        row = self.结果表格.rowCount()
        self.结果表格.insertRow(row)

        代码项 = QTableWidgetItem(code)
        收益项 = QTableWidgetItem(f"{bt.total_return_pct:+.1f}%")
        胜率项 = QTableWidgetItem(f"{bt.win_rate:.0f}%")
        交易项 = QTableWidgetItem(str(bt.trade_count))

        收益项.setForeground(QColor("#3fb950") if bt.total_return_pct > 0 else QColor("#f85149"))
        胜率项.setForeground(QColor("#3fb950") if bt.win_rate >= 50 else QColor("#f85149"))

        self.结果表格.setItem(row, 0, 代码项)
        self.结果表格.setItem(row, 1, 收益项)
        self.结果表格.setItem(row, 2, 胜率项)
        self.结果表格.setItem(row, 3, 交易项)

        if not self.当前代码:
            self.结果表格.selectRow(0)
            self._显示详情(code)

    def _更新进度(self, pct, msg):
        self.进度条.setValue(pct)
        self.statusBar().showMessage(msg)

    def _全部完成(self):
        self.开始按钮.setEnabled(True)
        self.开始按钮.setText("开始回测")
        self.进度条.setVisible(False)
        c = len(self.回测结果)
        self.statusBar().showMessage(f"完成 — {c} 只股票。点击左侧结果查看K线和交易明细")
        self._更新汇总()

    def _点击结果(self, idx):
        row = idx.row()
        if row < self.结果表格.rowCount():
            code = self.结果表格.item(row, 0).text()
            self._显示详情(code)

    def _点击汇总(self, idx):
        row = idx.row()
        if row < self.汇总表格.rowCount():
            code = self.汇总表格.item(row, 1).text()
            self.centralWidget().findChild(QSplitter).widget(1).setCurrentIndex(0)
            self._显示详情(code)

    def _显示详情(self, code: str):
        self.当前代码 = code
        bt = self.回测结果.get(code)
        if not bt:
            return

        # 更新指标
        self.指标标签["胜率"].setText(f"{bt.win_rate:.0f}%")
        self.指标标签["总收益"].setText(f"{bt.total_return_pct:+.1f}%")
        self.指标标签["最大回撤"].setText(f"{bt.max_drawdown_pct:.1f}%")
        self.指标标签["盈亏比"].setText(f"{bt.profit_factor:.2f}")
        self.指标标签["交易次数"].setText(str(bt.trade_count))
        self.指标标签["平均盈利"].setText(f"{bt.avg_win_pct:+.1f}%")
        self.指标标签["平均持仓"].setText(f"{bt.avg_bars_held:.0f}天")

        胜率色 = "#3fb950" if bt.win_rate >= 50 else "#f85149"
        收益色 = "#3fb950" if bt.total_return_pct > 0 else "#f85149"
        self.指标标签["胜率"].setStyleSheet(
            f"font-size:20px; font-weight:bold; color:{胜率色}; padding:4px;")
        self.指标标签["总收益"].setStyleSheet(
            f"font-size:20px; font-weight:bold; color:{收益色}; padding:4px;")

        # 画图
        self.k线画布.画图(bt)
        self.权益画布.画图(bt)

        # 交易明细
        self.交易表格.setRowCount(0)
        for t in bt.trades:
            r = self.交易表格.rowCount()
            self.交易表格.insertRow(r)
            数据 = [
                (t.entry_date, None),
                (t.signal_type, None),
                (f"{t.entry_price:.2f}", None),
                (t.exit_date, None),
                (f"{t.exit_price:.2f}", None),
                (f"{t.pnl_pct:+.2f}%", QColor("#3fb950") if t.pnl_pct > 0 else QColor("#f85149")),
                (t.exit_reason, None),
                (str(t.bars_held), None),
                (t.entry_reason[:60], None),
            ]
            for c, (text, color) in enumerate(数据):
                item = QTableWidgetItem(text)
                if color: item.setForeground(color)
                self.交易表格.setItem(r, c, item)

        self.交易表格.resizeColumnsToContents()

        for r in range(self.结果表格.rowCount()):
            if self.结果表格.item(r, 0).text() == code:
                self.结果表格.selectRow(r)
                break

    def _更新汇总(self):
        self.汇总表格.setRowCount(0)
        排序 = sorted(self.回测结果.values(), key=lambda x: x.total_return_pct, reverse=True)
        for rank, bt in enumerate(排序, 1):
            r = self.汇总表格.rowCount()
            self.汇总表格.insertRow(r)
            数据 = [
                (str(rank), None),
                (bt.code, None),
                (bt.name, None),
                (f"{bt.win_rate:.1f}%", QColor("#3fb950") if bt.win_rate >= 50 else QColor("#f85149")),
                (f"{bt.total_return_pct:+.1f}%", QColor("#3fb950") if bt.total_return_pct > 0 else QColor("#f85149")),
                (f"{bt.max_drawdown_pct:.1f}%", None),
                (f"{bt.profit_factor:.2f}", None),
                (str(bt.trade_count), None),
            ]
            for c, (text, color) in enumerate(数据):
                item = QTableWidgetItem(text)
                if color: item.setForeground(color)
                self.汇总表格.setItem(r, c, item)

    def _导出结果(self):
        out_dir = Path("output/backtest")
        out_dir.mkdir(parents=True, exist_ok=True)
        output = {}
        for code, bt in self.回测结果.items():
            output[code] = {
                "code": bt.code, "name": bt.name,
                "win_rate": bt.win_rate, "total_return": bt.total_return_pct,
                "max_dd": bt.max_drawdown_pct, "profit_factor": bt.profit_factor,
                "trade_count": bt.trade_count, "signal_count": bt.signal_count,
                "trades": [{
                    "entry_date": t.entry_date, "signal": t.signal_type,
                    "entry_price": t.entry_price, "exit_date": t.exit_date,
                    "exit_price": t.exit_price, "pnl_pct": t.pnl_pct,
                    "exit_reason": t.exit_reason, "bars_held": t.bars_held,
                    "entry_reason": t.entry_reason,
                } for t in bt.trades],
            }
        fname = out_dir / f"backtest_{date.today().isoformat()}.json"
        fname.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
        self.statusBar().showMessage(f"已导出 → {fname}")


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("A股PA回测")
    font = QFont("Microsoft YaHei UI", 10)
    app.setFont(font)
    window = 主窗口()
    window.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()

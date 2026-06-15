"""A股PA标的筛选器 — 全市场5000→TOP10
条件: 5-60元股价 + 非ST + 流动性 + 振幅 → PA结构评分 → TOP10
适用: 1w资金 + 短期波段 + 日线PA
"""
from __future__ import annotations

import sys, json, logging, time
from pathlib import Path
from datetime import date, datetime
from typing import Optional

import numpy as np
import pandas as pd

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QSplitter, QTableWidget, QTableWidgetItem, QHeaderView,
    QLabel, QPushButton, QSpinBox, QDoubleSpinBox,
    QGroupBox, QFormLayout, QProgressBar, QStatusBar,
    QMessageBox, QTextEdit, QCheckBox, QFrame, QTabWidget,
    QGridLayout,
)
from PySide6.QtCore import Qt, QThread, Signal, QTimer
from PySide6.QtGui import (
    QColor, QPalette, QFont, QAction, QBrush,
)

logging.basicConfig(level=logging.WARNING)
sys.path.insert(0, str(Path(__file__).parent))


# ══════════════════════════════════════════════════════════════
# 全市场筛选线程
# ══════════════════════════════════════════════════════════════

class ScreenerWorker(QThread):
    进度 = Signal(int, str)
    结果就绪 = Signal(list)  # list of dict
    完成 = Signal()

    def __init__(self, 最低价=5.0, 最高价=60.0, 最低成交额亿=1.5, 最低振幅=4.0, 取前N=10):
        super().__init__()
        self.最低价 = 最低价
        self.最高价 = 最高价
        self.最低成交额亿 = 最低成交额亿
        self.最低振幅 = 最低振幅
        self.取前N = 取前N

    def run(self):
        from src.a_share.fetcher import http_push2, http_push2_kline
        import urllib.request, json as _json

        self.进度.emit(5, "拉取全A股实时行情...")

        # ── 1. 全A股快照 ──
        try:
            params = {
                "pn": "1", "pz": "5000", "po": "1", "np": "1",
                "fltt": "2", "fid": "f3",
                "fs": "m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23,m:0+t:81+s:2048",
                "fields": "f2,f3,f4,f5,f6,f7,f8,f9,f10,f12,f14,f15,f16,f17,f18,f20,f21",
            }
            data = http_push2("clist/get", params, timeout=30)
            rows_raw = data.get("data", {}).get("diff", [])
        except Exception as e:
            self.进度.emit(100, f"行情拉取失败: {e}")
            self.完成.emit()
            return

        self.进度.emit(15, f"获取到 {len(rows_raw)} 只股票，开始筛选...")

        # ── 2. 硬过滤 ──
        candidates = []
        for r in rows_raw:
            code = str(r.get("f12", ""))
            name = str(r.get("f14", ""))
            if not code: continue

            # ST
            if "ST" in name: continue

            price = float(r.get("f2", 0))
            if price < self.最低价 or price > self.最高价: continue

            pct = float(r.get("f3", 0))
            # 涨跌停跳过（无法买入/卖出）
            if abs(pct) >= 9.8: continue

            amount = float(r.get("f6", 0))  # 成交额(元)
            if amount < self.最低成交额亿 * 1e8: continue

            amplitude = float(r.get("f7", 0))  # 振幅%
            if amplitude < self.最低振幅: continue

            turnover = float(r.get("f8", 0))  # 换手%
            total_mv = float(r.get("f20", 0))  # 总市值

            candidates.append({
                "code": code, "name": name,
                "price": price, "pct": pct,
                "amount": amount, "amplitude": amplitude,
                "turnover": turnover, "total_mv": total_mv,
            })

        self.进度.emit(35, f"硬过滤完成: {len(candidates)} 只候选")

        if len(candidates) < self.取前N:
            self.结果就绪.emit(candidates)
            self.完成.emit()
            return

        # ── 3. PA结构评分 ──
        from src.a_share.pa_backtest import analyze_structure
        scored = []
        total = len(candidates)

        for i, c in enumerate(candidates):
            try:
                df = http_push2_kline(c["code"], days=120)
                if df.empty or len(df) < 50: continue

                close = df["close"].values.astype(float)
                high = df["high"].values.astype(float)
                low = df["low"].values.astype(float)

                struct = analyze_structure(high, low, close)
                trend = struct.get("trend", "")
                stage = struct.get("stage", 0)
                strength = struct.get("strength", 0)

                # PA适配分 (0-100)
                score = 0

                # 趋势清晰度 (0-40)
                if trend in ("上升趋势", "下降趋势"):
                    score += 30
                    if stage in (2, 3):  # 窄/宽通道=最好操作
                        score += 10
                elif trend == "交易区间":
                    score += 15

                # 振幅充分度 (0-25)
                amp = c["amplitude"]
                if amp > 8: score += 25
                elif amp > 6: score += 20
                elif amp > 4: score += 15
                else: score += 10

                # 结构规整度 (0-20) — 有明确S/R位
                support = struct.get("support", 0)
                resistance = struct.get("resistance", 0)
                if support > 0 and resistance > 0:
                    rng = (resistance - support) / support * 100
                    if 5 < rng < 30: score += 15
                    else: score += 10
                # 摆动点充足
                if len(struct.get("swing_highs", [])) >= 3 and len(struct.get("swing_lows", [])) >= 3:
                    score += 5

                # 流动性/人气 (0-15)
                to = c["turnover"]
                if 3 <= to <= 15: score += 15
                elif 1 <= to <= 20: score += 10
                else: score += 5

                c["pa_score"] = score
                c["trend"] = trend
                c["stage"] = stage
                c["channel"] = struct.get("channel", "")
                c["strength"] = round(strength, 2)
                c["support"] = round(support, 2)
                c["resistance"] = round(resistance, 2)
                c["ema20"] = round(struct.get("ema20", 0), 2)
                c["atr14"] = round(struct.get("atr14", 0), 2)
                scored.append(c)

            except Exception as e:
                continue

            if i % 20 == 0:
                pct = 35 + int((i / total) * 55)
                self.进度.emit(pct, f"PA评分: {i}/{total} ({len(scored)} 有效)")

        # ── 4. 按PA分排序 → TOP N ──
        scored.sort(key=lambda x: -x["pa_score"])
        top = scored[:self.取前N]

        self.进度.emit(95, f"筛选完成: TOP{len(top)} 只")
        self.结果就绪.emit(top)
        self.完成.emit()


# ══════════════════════════════════════════════════════════════
# 主窗口
# ══════════════════════════════════════════════════════════════

class 筛选器主窗口(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("A股PA标的筛选器 — 每日TOP10")
        self.resize(1300, 850)
        self.setMinimumSize(1000, 650)

        self.top10 = []
        self.工作线程: Optional[ScreenerWorker] = None

        self._设置主题()
        self._构建界面()
        self._构建菜单()

        self.statusBar().showMessage("就绪 — 调整参数后点击「开始筛选」")

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
            QPushButton:hover { background: #30363d; }
            QPushButton#主按钮 {
                background: #d4a017; color: #000000; font-weight: bold; border: none;
                padding: 12px 28px; font-size: 15px;
            }
            QPushButton#主按钮:hover { background: #e6b422; }
            QPushButton#小按钮 {
                background: #21262d; color: #c9d1d9; border: 1px solid #30363d;
                border-radius: 4px; padding: 2px 8px; font-size: 11px;
            }
            QTableWidget {
                background: #161b22; color: #c9d1d9; border: 1px solid #21262d;
                border-radius: 6px; gridline-color: #21262d; font-size: 12px;
            }
            QTableWidget::item { padding: 5px 10px; }
            QTableWidget::item:selected { background: #1f2a3a; color: #e6edf3; }
            QHeaderView::section {
                background: #161b22; color: #8b949e; border: none;
                border-bottom: 1px solid #21262d; padding: 7px 10px;
                font-size: 11px; font-weight: bold;
            }
            QProgressBar {
                background: #21262d; border: none; border-radius: 4px; height: 8px;
                text-align: center; color: #8b949e; font-size: 11px;
            }
            QProgressBar::chunk { background: #d4a017; border-radius: 4px; }
            QTextEdit {
                background: #161b22; color: #c9d1d9; border: 1px solid #21262d;
                border-radius: 6px; font-size: 12px;
            }
            QSplitter::handle { background: #21262d; width: 2px; }
            QStatusBar { background: #161b22; color: #8b949e; border-top: 1px solid #21262d; }
        """)

    def _构建界面(self):
        central = QWidget()
        self.setCentralWidget(central)
        main_v = QVBoxLayout(central)
        main_v.setContentsMargins(10, 10, 10, 10)
        main_v.setSpacing(10)

        # ── 顶部: 标题 + 参数 ──
        top = QWidget()
        top_layout = QHBoxLayout(top)
        top_layout.setContentsMargins(0, 0, 0, 0)
        top_layout.setSpacing(20)

        # 标题区
        title_area = QWidget()
        tl = QVBoxLayout(title_area)
        tl.setContentsMargins(0, 0, 0, 0)
        title_lbl = QLabel("A股PA标的筛选器")
        title_lbl.setStyleSheet("font-size:22px; font-weight:bold; color:#e6edf3;")
        subtitle = QLabel("全市场 5000+ → 流动性/波动率 → PA结构评分 → TOP10")
        subtitle.setStyleSheet("font-size:12px; color:#8b949e;")
        tl.addWidget(title_lbl)
        tl.addWidget(subtitle)
        top_layout.addWidget(title_area)

        # 参数区
        params = QGroupBox("筛选参数")
        pf = QFormLayout(params)
        pf.setSpacing(4)

        row1 = QHBoxLayout()
        self.最低价 = QDoubleSpinBox(); self.最低价.setRange(2, 100); self.最低价.setValue(5); self.最低价.setPrefix("¥")
        self.最高价 = QDoubleSpinBox(); self.最高价.setRange(5, 200); self.最高价.setValue(60); self.最高价.setPrefix("¥")
        row1.addWidget(QLabel("价格")); row1.addWidget(self.最低价); row1.addWidget(QLabel("—")); row1.addWidget(self.最高价)
        pf.addRow("股价范围", row1)

        row2 = QHBoxLayout()
        self.成交额 = QDoubleSpinBox(); self.成交额.setRange(0.5, 20); self.成交额.setValue(1.5); self.成交额.setSuffix("亿")
        self.振幅 = QDoubleSpinBox(); self.振幅.setRange(2, 15); self.振幅.setValue(4.0); self.振幅.setSuffix("%")
        row2.addWidget(QLabel("成交额≥")); row2.addWidget(self.成交额); row2.addWidget(QLabel("  振幅≥")); row2.addWidget(self.振幅)
        pf.addRow("流动性", row2)

        row3 = QHBoxLayout()
        self.取前N = QSpinBox(); self.取前N.setRange(5, 50); self.取前N.setValue(10)
        row3.addWidget(QLabel("取前")); row3.addWidget(self.取前N); row3.addWidget(QLabel("名"))
        pf.addRow("输出", row3)

        top_layout.addWidget(params)

        # 按钮区
        btn_area = QWidget()
        bl = QVBoxLayout(btn_area)
        bl.setContentsMargins(0, 0, 0, 0)
        self.筛选按钮 = QPushButton("开始筛选")
        self.筛选按钮.setObjectName("主按钮")
        self.筛选按钮.clicked.connect(self._开始筛选)
        bl.addWidget(self.筛选按钮)
        self.进度条 = QProgressBar()
        self.进度条.setVisible(False)
        bl.addWidget(self.进度条)
        top_layout.addWidget(btn_area)

        top_layout.addStretch()
        main_v.addWidget(top)

        # ── 中部: TOP10 结果表格 ──
        self.结果表格 = QTableWidget(0, 11)
        self.结果表格.setHorizontalHeaderLabels([
            "排名", "代码", "名称", "现价", "涨跌%", "成交额(亿)", "振幅%",
            "PA评分", "趋势", "通道", "换手%",
        ])
        self.结果表格.setSelectionBehavior(QTableWidget.SelectRows)
        self.结果表格.setEditTriggers(QTableWidget.NoEditTriggers)
        self.结果表格.setAlternatingRowColors(True)
        self.结果表格.clicked.connect(self._点击结果)
        self.结果表格.verticalHeader().setDefaultSectionSize(28)
        self.结果表格.setColumnWidth(0, 45)
        self.结果表格.setColumnWidth(1, 65)
        self.结果表格.setColumnWidth(2, 75)
        self.结果表格.setColumnWidth(7, 65)
        for i in [3, 4, 5, 6, 8, 9, 10]: self.结果表格.setColumnWidth(i, 70)
        self.结果表格.horizontalHeader().setStretchLastSection(True)
        main_v.addWidget(self.结果表格, stretch=2)

        # ── 底部: 选中股票详情 ──
        bottom = QTabWidget()
        bottom.setMaximumHeight(200)

        # 详情Tab
        detail_tab = QWidget()
        dl = QGridLayout(detail_tab)
        dl.setContentsMargins(10, 10, 10, 10)
        dl.setSpacing(8)
        self.详情标签 = {}
        fields = [("代码","—"), ("名称","—"), ("现价","—"), ("PA评分","—"),
                  ("趋势","—"), ("通道阶段","—"), ("强度","—"),
                  ("支撑位","—"), ("阻力位","—"), ("EMA20","—"), ("ATR14","—"),
                  ("振幅","—"), ("换手","—"), ("市值","—"), ("20日日均成交额","—")]
        for i, (label, _) in enumerate(fields):
            row, col = i // 5, i % 5
            lbl = QLabel(f"<span style='color:#8b949e;font-size:11px;'>{label}</span>")
            val = QLabel("—")
            val.setStyleSheet("font-size:14px; font-weight:bold; color:#e6edf3;")
            dl.addWidget(lbl, row*2, col)
            dl.addWidget(val, row*2+1, col)
            self.详情标签[label] = val
        bottom.addTab(detail_tab, "📋 选中详情")

        # 操作Tab
        action_tab = QWidget()
        al = QVBoxLayout(action_tab)
        al.setContentsMargins(10, 10, 10, 10)
        操作说明 = QLabel("选中TOP10中的标的后，可以：")
        操作说明.setStyleSheet("color:#8b949e; font-size:12px;")
        al.addWidget(操作说明)
        btn_row = QHBoxLayout()
        self.复制按钮 = QPushButton("复制代码到剪贴板")
        self.复制按钮.clicked.connect(self._复制代码)
        self.导出按钮 = QPushButton("导出TOP10 JSON")
        self.导出按钮.clicked.connect(self._导出结果)
        self.回测按钮 = QPushButton("打开PA回测(需先复制代码)")
        self.回测按钮.clicked.connect(self._打开回测)
        for b in [self.复制按钮, self.导出按钮, self.回测按钮]:
            b.setObjectName("小按钮")
            btn_row.addWidget(b)
        al.addLayout(btn_row)
        al.addStretch()
        bottom.addTab(action_tab, "🔧 操作")

        main_v.addWidget(bottom)

    def _构建菜单(self):
        mb = self.menuBar()
        fm = mb.addMenu("文件")
        a = QAction("导出JSON", self); a.triggered.connect(self._导出结果); fm.addAction(a)
        fm.addSeparator()
        a2 = QAction("退出", self); a2.setShortcut("Ctrl+Q"); a2.triggered.connect(self.close); fm.addAction(a2)

    # ════════════════ 事件 ════════════════

    def _开始筛选(self):
        self.结果表格.setRowCount(0)
        self.top10 = []
        self.筛选按钮.setEnabled(False)
        self.筛选按钮.setText("筛选中...")
        self.进度条.setVisible(True)
        self.进度条.setValue(0)
        self.statusBar().showMessage("正在拉取全市场数据...")

        self.工作线程 = ScreenerWorker(
            最低价=self.最低价.value(), 最高价=self.最高价.value(),
            最低成交额亿=self.成交额.value(), 最低振幅=self.振幅.value(),
            取前N=self.取前N.value(),
        )
        self.工作线程.进度.connect(self._更新进度)
        self.工作线程.结果就绪.connect(self._展示结果)
        self.工作线程.完成.connect(self._筛选完成)
        self.工作线程.start()

    def _更新进度(self, pct, msg):
        self.进度条.setValue(pct)
        self.statusBar().showMessage(msg)

    def _展示结果(self, results):
        self.top10 = results
        self.结果表格.setRowCount(0)
        for rank, r in enumerate(results, 1):
            row = self.结果表格.rowCount()
            self.结果表格.insertRow(row)
            items = [
                (str(rank), None),
                (r["code"], None),
                (r["name"], None),
                (f"{r['price']:.2f}", None),
                (f"{r['pct']:+.2f}%", QColor("#3fb950") if r["pct"] >= 0 else QColor("#f85149")),
                (f"{r['amount']/1e8:.1f}", None),
                (f"{r['amplitude']:.1f}%", None),
                (str(r.get("pa_score", "—")), QColor("#d4a017") if r.get("pa_score", 0) >= 70 else None),
                (r.get("trend", "—"), None),
                (r.get("channel", "—"), None),
                (f"{r.get('turnover',0):.1f}%", None),
            ]
            for c, (text, color) in enumerate(items):
                item = QTableWidgetItem(text)
                if color: item.setForeground(color)
                if c == 7:  # PA评分居中加粗
                    item.setTextAlignment(Qt.AlignCenter)
                    f = item.font(); f.setBold(True); item.setFont(f)
                self.结果表格.setItem(row, c, item)

        if results:
            self.结果表格.selectRow(0)
            self._显示详情(results[0])

    def _点击结果(self, idx):
        row = idx.row()
        if row < len(self.top10):
            self._显示详情(self.top10[row])

    def _显示详情(self, r):
        info = {
            "代码": r["code"], "名称": r["name"], "现价": f"¥{r['price']:.2f}",
            "PA评分": str(r.get("pa_score", "—")),
            "趋势": r.get("trend", "—"), "通道阶段": r.get("channel", "—"),
            "强度": f"{r.get('strength', 0):.2f}",
            "支撑位": f"¥{r.get('support', 0):.2f}" if r.get("support") else "—",
            "阻力位": f"¥{r.get('resistance', 0):.2f}" if r.get("resistance") else "—",
            "EMA20": f"¥{r.get('ema20', 0):.2f}", "ATR14": f"{r.get('atr14', 0):.2f}",
            "振幅": f"{r.get('amplitude', 0):.1f}%", "换手": f"{r.get('turnover', 0):.1f}%",
            "市值": f"{r.get('total_mv', 0)/1e8:.0f}亿" if r.get("total_mv") else "—",
            "20日日均成交额": f"{r.get('amount', 0)/1e8:.1f}亿",
        }
        for k, v in info.items():
            if k in self.详情标签:
                self.详情标签[k].setText(v)

    def _筛选完成(self):
        self.筛选按钮.setEnabled(True)
        self.筛选按钮.setText("开始筛选")
        self.进度条.setVisible(False)
        n = len(self.top10)
        self.statusBar().showMessage(f"筛选完成 — TOP{n} 只 | 点击行查看详情 | 操作Tab复制代码")

    def _复制代码(self):
        if not self.top10:
            QMessageBox.information(self, "提示", "请先筛选")
            return
        codes = ",".join(r["code"] for r in self.top10)
        QApplication.clipboard().setText(codes)
        self.statusBar().showMessage(f"已复制 {len(self.top10)} 个代码: {codes}")

    def _导出结果(self):
        if not self.top10:
            QMessageBox.information(self, "提示", "请先筛选")
            return
        out_dir = Path("output/screener")
        out_dir.mkdir(parents=True, exist_ok=True)
        fname = out_dir / f"top10_{date.today().isoformat()}.json"
        fname.write_text(json.dumps(self.top10, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
        self.statusBar().showMessage(f"已导出 → {fname}")

    def _打开回测(self):
        codes = ",".join(r["code"] for r in self.top10) if self.top10 else ""
        QMessageBox.information(self, "代码已就绪",
            f"TOP{len(self.top10)} 代码:\n{codes}\n\n"
            "打开 PA回测系统 → 粘贴代码 → 开始回测")


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("PA筛选器")
    app.setFont(QFont("Microsoft YaHei UI", 10))
    w = 筛选器主窗口()
    w.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()

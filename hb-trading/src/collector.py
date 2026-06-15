"""行情采集模块 — AKShare 国内期货数据 + 微信通知

数据源:  AKShare（新浪财经/东方财富，免费实时）
存储:    SQLite
通知:    Server酱 (微信推送)
"""

import json
import logging
import sqlite3
import threading
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import akshare as ak
import pandas as pd
import requests

from config import (
    DATA_DIR, SYMBOLS, PRIMARY_SYMBOL, ALL_SYMBOLS, MAIN_CONTRACT,
    LOOKBACK_DAYS, POLL_INTERVAL_MINUTES,
    OHLCV_COLUMNS, DATA_FRESHNESS_HOURS,
    PRICE_CHANGE_WARN_PCT, VOLUME_SPIKE_MULTIPLIER,
    LOG_FORMAT, LOG_LEVEL, SERVERCHAN_KEY, NOTIFY_ENABLED, NOTIFY_MIN_INTERVAL_MINUTES,
)

logger = logging.getLogger("collector")
DB_PATH = DATA_DIR / "futures.db"

# ======================================================================
# 微信通知
# ======================================================================

class Notifier:
    """Server酱微信推送"""

    _last_notify: dict[str, float] = {}  # symbol → 上次通知时间

    def send(self, title: str, content: str, symbol: str = "") -> bool:
        """发送微信通知。同品种有间隔限制避免轰炸"""
        if not NOTIFY_ENABLED:
            return False

        now = time.time()
        if symbol:
            last = self._last_notify.get(symbol, 0)
            if now - last < NOTIFY_MIN_INTERVAL_MINUTES * 60:
                logger.debug(f"通知间隔限制，跳过 {symbol}")
                return False
            self._last_notify[symbol] = now

        try:
            resp = requests.post(
                f"https://sctapi.ftqq.com/{SERVERCHAN_KEY}.send",
                data={"title": title, "desp": content},
                timeout=10,
            )
            if resp.status_code == 200 and resp.json().get("code") == 0:
                logger.info(f"通知已发送: {title}")
                return True
            else:
                logger.warning(f"通知失败: {resp.text}")
                return False
        except Exception:
            logger.exception("通知异常")
            return False


_notifier: Optional[Notifier] = None

def notify(title: str, content: str, symbol: str = "") -> bool:
    global _notifier
    if _notifier is None:
        _notifier = Notifier()
    return _notifier.send(title, content, symbol)


# ======================================================================
# SQLite
# ======================================================================

class Database:
    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        self._local = threading.local()

    def _conn(self) -> sqlite3.Connection:
        if not hasattr(self._local, "conn") or self._local.conn is None:
            self._local.conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
            self._local.conn.execute("PRAGMA journal_mode=WAL")
        return self._local.conn

    def execute(self, sql: str, params: tuple = ()):
        with self._lock:
            return self._conn().execute(sql, params)

    def commit(self):
        with self._lock:
            self._conn().commit()

    def init(self):
        self.execute("""
            CREATE TABLE IF NOT EXISTS klines (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT NOT NULL,
                timeframe TEXT NOT NULL,
                dt TEXT NOT NULL,
                open REAL NOT NULL,
                high REAL NOT NULL,
                low REAL NOT NULL,
                close REAL NOT NULL,
                volume REAL NOT NULL,
                UNIQUE(symbol, timeframe, dt)
            )
        """)
        self.execute("""
            CREATE TABLE IF NOT EXISTS warehouse_receipts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT NOT NULL,
                date TEXT NOT NULL,
                amount INTEGER,
                change_pct REAL,
                UNIQUE(symbol, date)
            )
        """)
        self.execute("""
            CREATE TABLE IF NOT EXISTS paper_trades (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT NOT NULL,
                direction TEXT NOT NULL,
                entry_time TEXT NOT NULL,
                exit_time TEXT,
                entry_price REAL NOT NULL,
                exit_price REAL,
                stop_loss REAL NOT NULL,
                take_profit REAL NOT NULL,
                quantity INTEGER DEFAULT 1,
                pnl REAL DEFAULT 0.0,
                pnl_pct REAL DEFAULT 0.0,
                commission REAL DEFAULT 0.0,
                exit_reason TEXT,
                signal_score INTEGER,
                signal_conviction TEXT,
                created_at TEXT DEFAULT (datetime('now', 'localtime'))
            )
        """)
        self.execute("CREATE INDEX IF NOT EXISTS idx_klines_sym_tf ON klines(symbol, timeframe)")
        self.execute("CREATE INDEX IF NOT EXISTS idx_klines_dt ON klines(dt)")
        self.execute("CREATE INDEX IF NOT EXISTS idx_paper_trades_entry ON paper_trades(entry_time)")
        self.commit()

    def upsert_klines(self, symbol: str, timeframe: str, df: pd.DataFrame) -> int:
        count = 0
        for idx, row in df.iterrows():
            dt_str = str(idx)[:19]  # "2026-06-10 14:30:00" or "2026-06-10"
            self.execute(
                "INSERT OR REPLACE INTO klines (symbol, timeframe, dt, open, high, low, close, volume) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (symbol, timeframe, dt_str, float(row["open"]), float(row["high"]),
                 float(row["low"]), float(row["close"]), float(row["volume"])),
            )
            count += 1
        self.commit()
        return count

    def get_klines(self, symbol: str, timeframe: str = "5m", limit: int = None) -> pd.DataFrame:
        sql = "SELECT dt, open, high, low, close, volume FROM klines WHERE symbol=? AND timeframe=? ORDER BY dt ASC"
        if limit:
            sql += f" LIMIT {limit}"
        rows = self.execute(sql, (symbol, timeframe)).fetchall()
        if not rows:
            return pd.DataFrame(columns=OHLCV_COLUMNS)
        df = pd.DataFrame(rows, columns=["dt"] + OHLCV_COLUMNS)
        df["dt"] = pd.to_datetime(df["dt"])
        df.set_index("dt", inplace=True)
        return df

    def total_count(self) -> dict:
        rows = self.execute(
            "SELECT symbol, timeframe, COUNT(*) FROM klines GROUP BY symbol, timeframe"
        ).fetchall()
        return {f"{r[0]}:{r[1]}": r[2] for r in rows}

    # ---- paper_trades ----

    def insert_paper_trade(self, symbol: str, direction: str, entry_time: str,
                           entry_price: float, stop_loss: float, take_profit: float,
                           quantity: int, signal_score: int, signal_conviction: str
                           ) -> int:
        """Insert a new open trade row. Returns row id."""
        cursor = self.execute(
            "INSERT INTO paper_trades (symbol, direction, entry_time, entry_price, "
            "stop_loss, take_profit, quantity, signal_score, signal_conviction) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (symbol, direction, entry_time, entry_price, stop_loss, take_profit,
             quantity, signal_score, signal_conviction),
        )
        self.commit()
        return cursor.lastrowid

    def update_paper_trade(self, trade_id: int, exit_time: str, exit_price: float,
                           pnl: float, pnl_pct: float, commission: float,
                           exit_reason: str):
        """Update a trade row with exit data."""
        self.execute(
            "UPDATE paper_trades SET exit_time=?, exit_price=?, pnl=?, pnl_pct=?, "
            "commission=?, exit_reason=? WHERE id=?",
            (exit_time, exit_price, pnl, pnl_pct, commission, exit_reason, trade_id),
        )
        self.commit()

    def get_paper_trades(self, symbol: str = None, status: str = "all",
                         limit: int = None) -> list[dict]:
        """Get paper trades. status: 'open' (exit_time IS NULL) | 'closed' | 'all'"""
        sql = "SELECT * FROM paper_trades"
        conditions = []
        params: list = []

        if symbol:
            conditions.append("symbol = ?")
            params.append(symbol)

        if status == "open":
            conditions.append("exit_time IS NULL")
        elif status == "closed":
            conditions.append("exit_time IS NOT NULL")

        if conditions:
            sql += " WHERE " + " AND ".join(conditions)

        sql += " ORDER BY entry_time DESC"

        if limit:
            sql += f" LIMIT {limit}"

        rows = self.execute(sql, tuple(params)).fetchall()
        cols = [d[1] for d in self.execute("PRAGMA table_info(paper_trades)").fetchall()]
        return [dict(zip(cols, r)) for r in rows]


# ======================================================================
# 数据拉取 (AKShare)
# ======================================================================

def _fetch_daily(symbol: str, name: str) -> Optional[pd.DataFrame]:
    """拉取期货日线 — AKShare futures_zh_daily_sina（17年历史）"""
    contract = MAIN_CONTRACT.get(symbol)
    if not contract:
        return None
    try:
        df = ak.futures_zh_daily_sina(symbol=contract)
        if df is None or df.empty:
            return None
        df.rename(columns={
            "date": "date", "open": "open", "high": "high",
            "low": "low", "close": "close", "volume": "volume",
        }, inplace=True, errors="ignore")
        df["date"] = pd.to_datetime(df["date"])
        df.set_index("date", inplace=True)
        needed = ["open", "high", "low", "close", "volume"]
        df = df[[c for c in needed if c in df.columns]]
        df = df.astype(float)
        df.sort_index(inplace=True)
        cutoff = pd.Timestamp.now() - pd.Timedelta(days=LOOKBACK_DAYS)
        return df[df.index >= cutoff]
    except Exception:
        logger.exception(f"拉取日线失败: {symbol}")
        return None


def _fetch_5min(symbol: str) -> Optional[pd.DataFrame]:
    """拉取期货5分钟线（最近约1个月数据）"""
    contract = MAIN_CONTRACT.get(symbol)
    if not contract:
        return None
    try:
        df = ak.futures_zh_minute_sina(symbol=contract, period="5")
        if df is None or df.empty:
            return None
        df.rename(columns={
            "datetime": "dt", "open": "open", "high": "high",
            "low": "low", "close": "close", "volume": "volume",
        }, inplace=True, errors="ignore")
        df["dt"] = pd.to_datetime(df["dt"])
        df.set_index("dt", inplace=True)
        df = df[["open", "high", "low", "close", "volume"]]
        df = df.astype(float)
        df.sort_index(inplace=True)
        return df
    except Exception:
        logger.exception(f"拉取5m失败: {symbol}")
        return None


def fetch_and_store(symbol: str, timeframe: str = "5m") -> Optional[pd.DataFrame]:
    """拉取数据并写入数据库"""
    info = SYMBOLS.get(symbol)
    if not info:
        return None

    name = info["name"]
    if timeframe == "daily":
        df = _fetch_daily(symbol, name)
    else:
        df = _fetch_5min(symbol)

    if df is None or df.empty:
        return None

    db = Database()
    n = db.upsert_klines(symbol, timeframe, df)
    logger.info(f"{name}({symbol}) {timeframe}: 拉取 {len(df)} 条, 写入 {n} 条")
    return db.get_klines(symbol, timeframe)


FETCH_TIMEOUT = 20  # 单次 API 调用最大等待秒数


def _fetch_with_timeout(symbol: str, timeframe: str) -> Optional[pd.DataFrame]:
    """在线程中执行 fetch_and_store，超时则取消"""
    result = [None]

    def _target():
        try:
            result[0] = fetch_and_store(symbol, timeframe)
        except Exception as e:
            logger.warning(f"{symbol} {timeframe} fetch exception: {e}")
            result[0] = None

    t = threading.Thread(target=_target, daemon=True)
    t.start()
    t.join(timeout=FETCH_TIMEOUT)

    if t.is_alive():
        logger.warning(f"{symbol} {timeframe} 超时 ({FETCH_TIMEOUT}s)，跳过")
        return None

    return result[0]


def is_data_fresh(symbol: str, timeframe: str, max_age_hours: float = 1.0) -> bool:
    """检查数据库中该品种数据是否足够新鲜，跳过不必要的API调用"""
    db = Database()
    df = db.get_klines(symbol, timeframe, limit=1)
    if df.empty:
        return False
    age = (pd.Timestamp.now(tz=None) - df.index[-1]).total_seconds() / 3600
    return age < max_age_hours


def fill_all(force: bool = False) -> dict:
    """拉取所有品种、所有时间框架历史数据（跳过新鲜数据 + API限速 + 超时保护）"""
    stats = {}
    rate_delay = 0.3  # 调用间隔(秒)
    skipped = 0

    for sym in ALL_SYMBOLS:
        for tf in ["5m", "daily"]:
            key = f"{sym}:{tf}"

            # 跳过已有新鲜数据（除非 force=True）
            if not force and is_data_fresh(sym, tf):
                db = Database()
                df = db.get_klines(sym, tf)
                stats[key] = len(df) if df is not None else 0
                skipped += 1
                continue

            df = _fetch_with_timeout(sym, tf)
            stats[key] = len(df) if df is not None else 0
            time.sleep(rate_delay)

    if skipped:
        logger.info(f"fill_all: 跳过 {skipped} 个已有新鲜数据的请求")
    return stats


# ======================================================================
# 数据质量检查
# ======================================================================

@dataclass
class QualityReport:
    symbol: str
    total_rows: int
    date_range: tuple
    missing_dates: int
    price_anomalies: list[str]
    volume_anomalies: list[str]
    freshness_ok: bool
    freshness_hours: float

    @property
    def healthy(self) -> bool:
        return (self.missing_dates == 0 and len(self.price_anomalies) == 0
                and self.freshness_ok)


def check_quality(symbol: str, timeframe: str = "5m") -> QualityReport:
    """检查指定品种的数据质量"""
    db = Database()
    df = db.get_klines(symbol, timeframe)
    if df.empty:
        return QualityReport(symbol, 0, (None, None), 0, [], [], False, float("inf"))

    dr = (df.index.min(), df.index.max())

    # 缺失数据（5m 用交易时间判断，日线用交易日）
    if timeframe == "daily":
        full_range = pd.date_range(dr[0], dr[1], freq="B")
        missing = len(set(full_range.strftime("%Y-%m-%d")) - set(df.index.strftime("%Y-%m-%d")))
    else:
        missing = 0  # 5m 数据不检查缺失（存在夜盘/休息时段）

    # 价格异常
    price_anomalies = []
    for i in range(len(df)):
        if df["open"].iloc[i] > 0:
            chg = abs(df["close"].iloc[i] / df["open"].iloc[i] - 1) * 100
            if chg > PRICE_CHANGE_WARN_PCT:
                dt = df.index[i]
                price_anomalies.append(f"{dt} 单根涨跌 {chg:.1f}%")

    # 成交量异常
    avg_vol = df["volume"].mean()
    volume_anomalies = []
    for i in range(len(df)):
        if df["volume"].iloc[i] > avg_vol * VOLUME_SPIKE_MULTIPLIER:
            vol = df["volume"].iloc[i]
            volume_anomalies.append(f"{df.index[i]} 量 {vol:.0f} (均值 {avg_vol:.0f})")

    # 新鲜度
    age = (pd.Timestamp.now(tz=None) - df.index[-1]).total_seconds() / 3600
    freshness_ok = age < DATA_FRESHNESS_HOURS

    return QualityReport(
        symbol=symbol, total_rows=len(df), date_range=dr,
        missing_dates=missing, price_anomalies=price_anomalies,
        volume_anomalies=volume_anomalies,
        freshness_ok=freshness_ok, freshness_hours=age,
    )


# ======================================================================
# 轮询采集器
# ======================================================================

class Collector:
    def __init__(self):
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._count = 0

    def start(self):
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        logger.info(f"采集器启动 ({POLL_INTERVAL_MINUTES}min 轮询)")

    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=5)

    def _loop(self):
        rate_delay = 0.8
        while self._running:
            for sym in ALL_SYMBOLS:
                for tf in ["5m", "daily"]:
                    try:
                        fetch_and_store(sym, tf)
                        time.sleep(rate_delay)
                    except Exception:
                        logger.exception(f"轮询失败 {sym} {tf}")
            self._count += 1
            time.sleep(POLL_INTERVAL_MINUTES * 60)


# ======================================================================
# 单例
# ======================================================================

_db: Optional[Database] = None
_collector: Optional[Collector] = None

def get_db() -> Database:
    global _db
    if _db is None:
        _db = Database()
        _db.init()
    return _db

def get_collector() -> Collector:
    global _collector
    if _collector is None:
        _collector = Collector()
    return _collector


# ======================================================================
# 入口
# ======================================================================

def startup():
    logging.basicConfig(level=getattr(logging, LOG_LEVEL), format=LOG_FORMAT)
    get_db()

    stats = fill_all()
    total = sum(stats.values())
    info = SYMBOLS[PRIMARY_SYMBOL]
    logger.info(f"数据填充完成: {total} 条")

    # 检查质量
    for sym in ALL_SYMBOLS:
        q = check_quality(sym, "5m")
        status = "OK" if q.healthy else "WARN"
        logger.info(f"  {sym} 5m: {q.total_rows}条 {status}")

    get_collector().start()

    # 通知
    if total > 0:
        summary = f"品种: {len(ALL_SYMBOLS)}个 | 数据: {total}条"
        notify(
            f"hb-trading 数据就绪 ({len(ALL_SYMBOLS)}品种)",
            f"拉取 {total} 条K线\n{summary}\n"
            f"时间: {datetime.now().strftime('%Y-%m-%d %H:%M')}"
        )

    return stats


if __name__ == "__main__":
    startup()

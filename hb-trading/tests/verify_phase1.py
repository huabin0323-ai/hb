"""阶段1 验证 — 国内期货数据采集"""
import sys
sys.path.insert(0, ".")
import logging
logging.basicConfig(level=logging.WARNING)

from src.collector import (
    get_db, Database, fill_all, check_quality, notify, QualityReport
)

def ok(msg):    print(f"  [OK] {msg}")
def warn(msg):  print(f"  [WARN] {msg}")
def fail(msg):  print(f"  [FAIL] {msg}")

print("=" * 60)
print("验证: 数据采集模块 (collector.py)")
print("=" * 60)

# 1. 数据库
print("\n1. 数据库")
db = Database(); db.init()
tables = [t[0] for t in db.execute(
    "SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
for t in ["klines", "warehouse_receipts"]:
    (ok if t in tables else fail)(f"表 {t}")

# 2. 数据拉取
print("\n2. 期货日线数据 (AKShare)")
stats = fill_all()
total = sum(stats.values())
if total > 100:
    ok(f"总数 {total} 条")
else:
    fail(f"数据太少: {total}")
for sym, n in stats.items():
    print(f"  {sym}: {n} 条")

# 3. 数据质量
print("\n3. 数据质量检查")
all_healthy = True
for sym in stats:
    q = check_quality(sym)
    status = "OK" if q.healthy else "WARN"
    print(f"  {sym}: {q.total_rows}条, 日期 {q.date_range[0].strftime('%Y-%m-%d')}~{q.date_range[1].strftime('%Y-%m-%d')}, 缺失{q.missing_dates}天, 新鲜度{q.freshness_hours:.0f}h")

    if q.missing_dates > 0:
        warn(f"缺失 {q.missing_dates} 天数据")
    if q.price_anomalies:
        warn(f"价格异常: {q.price_anomalies[:3]}")
    if q.volume_anomalies:
        warn(f"量异常: {q.volume_anomalies[:3]}")
    if not q.freshness_ok:
        warn(f"数据延迟 {q.freshness_hours:.0f}h")

    if not q.healthy:
        all_healthy = False
    else:
        ok(f"{sym} 数据质量良好")

# 4. 微信通知
print("\n4. 微信通知 (Server酱)")
ok("通知通道已配置" if notify("验证测试",
    f"如果你看到这条消息，说明微信推送通道正常。\n"
    f"当前数据: {stats}\n系统时间: {__import__('datetime').datetime.now()}") else "通知未启用")
print("  检查微信 →")

# 5. 数据库查询
print("\n5. 数据查询测试")
from config import PRIMARY_SYMBOL
df = db.get_klines(PRIMARY_SYMBOL, limit=5)
print(f"  {PRIMARY_SYMBOL} 最近5天:")
for i, row in df.tail(5).iterrows():
    print(f"  {i.strftime('%Y-%m-%d')} O={row['open']:.0f} H={row['high']:.0f} L={row['low']:.0f} C={row['close']:.0f} V={row['volume']:.0f}")

print(f"\n{'='*60}")
print(f"结果: {'全部通过' if all_healthy else '有告警，需关注'}")
print(f"{'='*60}")

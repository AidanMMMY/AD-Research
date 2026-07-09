"""归一化 adj_factor：每只 ETF 的最新一日因子 = 1.0，所有历史因子按比例缩放。

公式：new_factor = old_factor / latest_factor_for_this_etf
      (使最新日因子 = 1.0，符合"后复权因子"的通用语义)
"""
import sys
sys.path.insert(0, '/app')
import logging
from datetime import date
from sqlalchemy import text
from app.core.database import SessionLocal
from app.models.etf import InstrumentDailyBar

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger("normalize_adj")

db = SessionLocal()

# 1) 找每只 ETF 的最新 adj_factor（最新一日）
latest_rows = db.execute(text("""
    SELECT DISTINCT ON (etf_code) etf_code, trade_date, adj_factor
    FROM instrument_daily_bar
    WHERE adj_factor IS NOT NULL AND adj_factor > 0
    ORDER BY etf_code, trade_date DESC
""")).fetchall()
logger.info(f"Found {len(latest_rows)} distinct ETF codes with adj_factor")

# 2) 对每只 ETF，把所有历史因子除以最新因子
total_updated = 0
for etf_code, latest_date, latest_factor in latest_rows:
    if latest_factor == 1.0:
        continue
    res = db.execute(text("""
        UPDATE instrument_daily_bar
        SET adj_factor = adj_factor / :lf
        WHERE etf_code = :code AND adj_factor IS NOT NULL
    """), {"lf": latest_factor, "code": etf_code})
    total_updated += res.rowcount
    logger.info(f"  {etf_code}: latest={latest_date} factor={latest_factor} -> normalized, {res.rowcount} rows updated")
db.commit()

# 3) 验证
print("\n=== verify 512760.SH ===")
rows = db.execute(text("""
    SELECT trade_date, adj_factor, close, close * adj_factor AS adj_close
    FROM instrument_daily_bar
    WHERE etf_code = '512760.SH' AND adj_factor IS NOT NULL
    ORDER BY trade_date LIMIT 5
""")).fetchall()
for r in rows:
    print(f"  {r.trade_date}  factor={r.adj_factor:.4f}  close={r.close}  adj_close={r.adj_close:.4f}")
print("...")
rows = db.execute(text("""
    SELECT trade_date, adj_factor, close, close * adj_factor AS adj_close
    FROM instrument_daily_bar
    WHERE etf_code = '512760.SH' AND adj_factor IS NOT NULL
    ORDER BY trade_date DESC LIMIT 5
""")).fetchall()
for r in rows:
    print(f"  {r.trade_date}  factor={r.adj_factor:.4f}  close={r.close}  adj_close={r.adj_close:.4f}")
print(f"\nTotal rows normalized: {total_updated}")
db.close()

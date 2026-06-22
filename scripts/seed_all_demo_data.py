"""Seed comprehensive demo data for all new features.

Fills empty tables with realistic demo data so all pages show content.

Usage:
    cd /Users/aidanliu/Documents/vibe-trading/etf-research-platform
    .venv/bin/python scripts/seed_all_demo_data.py
"""

import json
import os
import random
import sys
from datetime import date, datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.config import get_settings

# ── Config ──
settings = get_settings()
engine = create_engine(settings.database_url)
Session = sessionmaker(bind=engine)

# ETFs with daily bar data available
ETF_CODES = ["159915.SZ", "512000.SH", "159928.SZ", "510300.SH", "510050.SH"]
ETF_NAMES = {
    "159915.SZ": "创业板ETF",
    "512000.SH": "券商ETF",
    "159928.SZ": "消费ETF",
    "510300.SH": "沪深300ETF",
    "510050.SH": "上证50ETF",
}

SEED_DATE = date(2025, 10, 27)  # Latest date in etf_daily_bar


def ensure_missing_tables(conn):
    """Create tables that may not exist from earlier Alembic runs."""
    # etf_scan_log
    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS etf_scan_log (
            id SERIAL PRIMARY KEY,
            scan_date DATE NOT NULL,
            new_count INTEGER DEFAULT 0,
            delisted_count INTEGER DEFAULT 0,
            changed_count INTEGER DEFAULT 0,
            details JSONB DEFAULT '{}',
            status VARCHAR(20) DEFAULT 'success',
            error_msg TEXT,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
        )
    """))

    # notification_config
    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS notification_config (
            id SERIAL PRIMARY KEY,
            name VARCHAR(100) NOT NULL,
            channel_type VARCHAR(50) NOT NULL,
            config_json JSONB DEFAULT '{}',
            is_active BOOLEAN DEFAULT true,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
        )
    """))

    # notification_log
    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS notification_log (
            id SERIAL PRIMARY KEY,
            config_id INTEGER,
            report_id INTEGER,
            status VARCHAR(20) DEFAULT 'pending',
            error_msg TEXT,
            sent_at TIMESTAMP WITH TIME ZONE,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
        )
    """))

    conn.commit()
    print("✅ Missing tables created.")


def seed_strategies(db):
    """Insert demo strategy configs."""
    count = db.execute(text("SELECT COUNT(*) FROM strategy_config")).scalar()
    if count > 0:
        print(f"⏭️  strategy_config already has {count} rows, skipping.")
        return []

    strategies = [
        {
            "name": "沪深300动量策略",
            "description": "基于20日动量效应，突破阈值买入",
            "strategy_type": "momentum",
            "params": {"momentum_window": 20, "threshold": 0.05},
            "is_active": True,
        },
        {
            "name": "上证50均值回归",
            "description": "基于Z-Score均值回归，超卖买入",
            "strategy_type": "mean_reversion",
            "params": {"lookback_window": 30, "z_score_threshold": 1.5},
            "is_active": True,
        },
        {
            "name": "创业板RSI策略",
            "description": "RSI超卖买入，超买卖出",
            "strategy_type": "rsi",
            "params": {"rsi_period": 14, "overbought": 70, "oversold": 30},
            "is_active": True,
        },
        {
            "name": "消费ETF趋势跟踪",
            "description": "多均线多头排列趋势跟踪",
            "strategy_type": "momentum",
            "params": {"momentum_window": 10, "threshold": 0.03},
            "is_active": False,
        },
    ]

    ids = []
    for s in strategies:
        result = db.execute(text("""
            INSERT INTO strategy_config (name, description, strategy_type, params, is_active, created_at, updated_at)
            VALUES (:name, :description, :strategy_type, :params, :is_active, NOW(), NOW())
            RETURNING id
        """), {
            "name": s["name"],
            "description": s["description"],
            "strategy_type": s["strategy_type"],
            "params": json.dumps(s["params"]),
            "is_active": s["is_active"],
        })
        ids.append(result.scalar())

    db.commit()
    print(f"✅ Inserted {len(strategies)} strategies: {ids}")
    return ids


def _generate_nav_curve(start_date, end_date, strategy_type, seed=42):
    """Generate a realistic NAV curve."""
    rng = random.Random(seed)
    days = (end_date - start_date).days + 1
    nav = 1.0
    curve = []
    for _i in range(days):
        if strategy_type == "momentum":
            daily_return = rng.gauss(0.0008, 0.012)
        elif strategy_type == "mean_reversion":
            daily_return = rng.gauss(0.0005, 0.010)
        else:  # rsi
            daily_return = rng.gauss(0.0006, 0.011)
        nav *= (1 + daily_return)
        curve.append(round(nav, 4))
    return curve


def _generate_trades(start_date, end_date, strategy_type, seed=42):
    """Generate simulated trade records."""
    rng = random.Random(seed)
    days = (end_date - start_date).days + 1
    trades = []
    position = 0
    for i in range(0, days, rng.randint(5, 15)):
        trade_date = start_date + timedelta(days=i)
        if trade_date > end_date:
            break
        action = "BUY" if position == 0 else "SELL"
        position = 1 if action == "BUY" else 0
        price = round(rng.uniform(0.8, 3.5), 3)
        trades.append({
            "date": trade_date.isoformat(),
            "action": action,
            "price": price,
            "shares": 1000,
            "value": round(price * 1000, 2),
        })
    return trades


def _calc_metrics(nav_curve):
    """Calculate performance metrics from NAV curve."""
    total_return = (nav_curve[-1] - nav_curve[0]) / nav_curve[0]
    annualized = (1 + total_return) ** (252 / len(nav_curve)) - 1

    # Max drawdown
    peak = nav_curve[0]
    max_dd = 0
    for nav in nav_curve:
        if nav > peak:
            peak = nav
        dd = (peak - nav) / peak
        if dd > max_dd:
            max_dd = dd

    # Sharpe (simplified)
    returns = [(nav_curve[i] - nav_curve[i - 1]) / nav_curve[i - 1] for i in range(1, len(nav_curve))]
    avg_return = sum(returns) / len(returns) if returns else 0
    std = (sum((r - avg_return) ** 2 for r in returns) / len(returns)) ** 0.5 if returns else 0.001
    sharpe = (avg_return * 252) / (std * (252 ** 0.5)) if std > 0 else 0

    return {
        "total_return": round(total_return * 100, 2),
        "annualized_return": round(annualized * 100, 2),
        "max_drawdown": round(max_dd * 100, 2),
        "sharpe_ratio": round(sharpe, 2),
        "win_rate": round(random.uniform(45, 65), 1),
        "trade_count": random.randint(8, 25),
        "avg_win": round(random.uniform(2, 8), 2),
        "avg_loss": round(random.uniform(-5, -1), 2),
    }


def seed_backtests(db, strategy_ids):
    """Insert demo backtest results for each strategy + ETF combo."""
    count = db.execute(text("SELECT COUNT(*) FROM backtest_result")).scalar()
    if count > 0:
        print(f"⏭️  backtest_result already has {count} rows, skipping.")
        return

    # Get strategy types
    strategies = db.execute(text("SELECT id, strategy_type FROM strategy_config WHERE id = ANY(:ids)"), {
        "ids": strategy_ids
    }).fetchall()

    start_date = date(2025, 1, 2)
    end_date = date(2025, 10, 27)

    inserted = 0
    for strategy_id, strategy_type in strategies:
        for etf_code in ETF_CODES:
            nav_curve = _generate_nav_curve(start_date, end_date, strategy_type, seed=inserted + 42)
            trades = _generate_trades(start_date, end_date, strategy_type, seed=inserted + 99)
            metrics = _calc_metrics(nav_curve)

            db.execute(text("""
                INSERT INTO backtest_result
                (strategy_id, start_date, end_date, metrics, trades, config_snapshot, created_at)
                VALUES (:strategy_id, :start_date, :end_date, :metrics, :trades, :config_snapshot, NOW())
            """), {
                "strategy_id": strategy_id,
                "start_date": start_date,
                "end_date": end_date,
                "metrics": json.dumps(metrics),
                "trades": json.dumps(trades),
                "config_snapshot": json.dumps({"etf_code": etf_code, "initial_capital": 100000}),
            })
            inserted += 1

    db.commit()
    print(f"✅ Inserted {inserted} backtest results.")


def seed_signals(db, strategy_ids):
    """Insert demo trading signals for recent dates."""
    count = db.execute(text("SELECT COUNT(*) FROM signal")).scalar()
    if count > 0:
        print(f"⏭️  signal already has {count} rows, skipping.")
        return

    signal_types = ["BUY", "SELL", "HOLD"]
    end_date = date(2025, 10, 27)

    inserted = 0
    for strategy_id in strategy_ids:
        for etf_code in ETF_CODES:
            # Generate signals for last 30 trading days
            for day_offset in range(0, 30, 3):
                trade_date = end_date - timedelta(days=day_offset)
                signal_type = random.choice(signal_types)
                strength = round(random.uniform(0.5, 1.0), 2) if signal_type in ["BUY", "SELL"] else round(random.uniform(0.1, 0.4), 2)

                db.execute(text("""
                    INSERT INTO signal
                    (strategy_id, etf_code, trade_date, signal_type, strength, extra_data, created_at)
                    VALUES (:strategy_id, :etf_code, :trade_date, :signal_type, :strength, :extra_data, NOW())
                """), {
                    "strategy_id": strategy_id,
                    "etf_code": etf_code,
                    "trade_date": trade_date,
                    "signal_type": signal_type,
                    "strength": strength,
                    "extra_data": json.dumps({"reason": f"{signal_type} signal generated"}),
                })
                inserted += 1

    db.commit()
    print(f"✅ Inserted {inserted} signals.")


def seed_reports(db):
    """Insert demo report metadata."""
    count = db.execute(text("SELECT COUNT(*) FROM report_metadata")).scalar()
    if count > 0:
        print(f"⏭️  report_metadata already has {count} rows, skipping.")
        return

    # Get actual pool IDs
    pool_rows = db.execute(text("SELECT id FROM etf_pools")).fetchall()
    pool_ids = [r[0] for r in pool_rows]
    pool_ids.append(None)  # Some reports have no pool

    reports = [
        {"report_type": "pool_analysis", "status": "done", "format": "html"},
        {"report_type": "pool_analysis", "status": "done", "format": "html"},
        {"report_type": "score_ranking", "status": "done", "format": "html"},
        {"report_type": "score_ranking", "status": "done", "format": "html"},
        {"report_type": "sector_rotation", "status": "done", "format": "html"},
        {"report_type": "market_scan", "status": "done", "format": "html"},
        {"report_type": "signal_summary", "status": "done", "format": "html"},
        {"report_type": "backtest_report", "status": "done", "format": "html"},
        {"report_type": "pool_analysis", "status": "failed", "format": "html", "error_msg": "Data source timeout"},
        {"report_type": "score_ranking", "status": "pending", "format": "html"},
    ]

    base_date = date(2025, 10, 20)
    for i, r in enumerate(reports):
        report_date = base_date - timedelta(days=i * 2)
        db.execute(text("""
            INSERT INTO report_metadata
            (report_type, report_date, pool_id, template_id, status, format, file_path, file_size, error_msg, started_at, finished_at, created_at)
            VALUES (:report_type, :report_date, :pool_id, :template_id, :status, :format, :file_path, :file_size, :error_msg, :started_at, :finished_at, NOW())
        """), {
            "report_type": r["report_type"],
            "report_date": report_date,
            "pool_id": random.choice(pool_ids),
            "template_id": random.choice([1, 2, 3]),
            "status": r["status"],
            "format": r["format"],
            "file_path": f"/reports/{r['report_type']}_{report_date.strftime('%Y%m%d')}.{r['format']}" if r["status"] == "done" else None,
            "file_size": random.randint(50000, 500000) if r["status"] == "done" else None,
            "error_msg": r.get("error_msg"),
            "started_at": datetime.now() - timedelta(minutes=random.randint(5, 30)) if r["status"] != "pending" else None,
            "finished_at": datetime.now() - timedelta(minutes=random.randint(1, 5)) if r["status"] == "done" else None,
        })

    db.commit()
    print(f"✅ Inserted {len(reports)} reports.")


def seed_pools(db):
    """Add more ETF pools with members."""
    pool_count = db.execute(text("SELECT COUNT(*) FROM etf_pools")).scalar()
    if pool_count >= 4:
        print(f"⏭️  etf_pools already has {pool_count} rows, skipping.")
        return

    # Get some ETF codes from etf_info
    codes_result = db.execute(text("SELECT code FROM etf_info WHERE status = 'active' LIMIT 50")).fetchall()
    all_codes = [r[0] for r in codes_result]

    pools = [
        {"name": "宽基指数池", "description": "大盘宽基ETF组合", "codes": ["510300.SH", "510050.SH", "510500.SH"]},
        {"name": "科技成长池", "description": "科技、新能源、创业板ETF", "codes": ["159915.SZ", "512000.SH", "159928.SZ"]},
        {"name": "稳健防御池", "description": "低波动、红利、债券ETF", "codes": random.sample(all_codes, min(5, len(all_codes)))},
        {"name": "行业轮动池", "description": "周期性行业ETF组合", "codes": random.sample(all_codes, min(8, len(all_codes)))},
    ]

    for pool in pools:
        result = db.execute(text("""
            INSERT INTO etf_pools (name, description, created_at, updated_at)
            VALUES (:name, :description, NOW(), NOW())
            RETURNING id
        """), {"name": pool["name"], "description": pool["description"]})
        pool_id = result.scalar()

        for code in pool["codes"]:
            db.execute(text("""
                INSERT INTO pool_member (pool_id, etf_code, added_at, notes)
                VALUES (:pool_id, :etf_code, NOW(), :notes)
            """), {
                "pool_id": pool_id,
                "etf_code": code,
                "notes": f"Added to {pool['name']}",
            })

    db.commit()
    print(f"✅ Inserted {len(pools)} new pools with members.")


def seed_scan_logs(db):
    """Insert demo ETF scan logs."""
    count = db.execute(text("SELECT COUNT(*) FROM etf_scan_log")).scalar()
    if count > 0:
        print(f"⏭️  etf_scan_log already has {count} rows, skipping.")
        return

    base_date = date(2025, 10, 27)
    for i in range(12):
        scan_date = base_date - timedelta(weeks=i)
        new_count = random.randint(0, 5)
        delisted_count = random.randint(0, 3)
        changed_count = random.randint(0, 10)

        details = {
            "new": [{"code": f"NEW{i}{j}", "name": f"新ETF{j}"} for j in range(new_count)],
            "delisted": [{"code": f"OLD{i}{j}", "name": f"退市ETF{j}"} for j in range(delisted_count)],
            "changed": [{"code": f"CHG{i}{j}", "field": "name", "old": "旧名", "new": "新名"} for j in range(changed_count)],
        }

        db.execute(text("""
            INSERT INTO etf_scan_log (scan_date, new_count, delisted_count, changed_count, details, status, created_at)
            VALUES (:scan_date, :new_count, :delisted_count, :changed_count, :details, 'success', NOW())
        """), {
            "scan_date": scan_date,
            "new_count": new_count,
            "delisted_count": delisted_count,
            "changed_count": changed_count,
            "details": json.dumps(details),
        })

    db.commit()
    print("✅ Inserted 12 scan logs.")


def _infer_etf_metadata(name):
    """Infer category, sub_category, manager, underlying_index from ETF name."""
    name = name or ""

    # Category / sub_category inference
    category = "其他"
    sub_category = ""
    underlying_index = ""

    # 宽基指数
    if "沪深300" in name:
        category, sub_category, underlying_index = "宽基指数", "沪深300", "沪深300指数"
    elif "上证50" in name:
        category, sub_category, underlying_index = "宽基指数", "上证50", "上证50指数"
    elif "创业板" in name or "创业板50" in name:
        category, sub_category, underlying_index = "宽基指数", "创业板", "创业板指数"
    elif "中证500" in name:
        category, sub_category, underlying_index = "宽基指数", "中证500", "中证500指数"
    elif "中证1000" in name:
        category, sub_category, underlying_index = "宽基指数", "中证1000", "中证1000指数"
    elif "科创" in name or "科创板" in name:
        category, sub_category, underlying_index = "宽基指数", "科创板", "科创50指数"
    elif "A50" in name or "A50" in name:
        category, sub_category, underlying_index = "宽基指数", "A50", "MSCI中国A50指数"
    elif "MSCI" in name:
        category, sub_category = "宽基指数", "MSCI"
    # 行业主题
    elif "科技" in name or "科创" in name:
        category, sub_category, underlying_index = "行业主题", "科技", "中证科技指数"
    elif "半导体" in name or "芯片" in name:
        category, sub_category, underlying_index = "行业主题", "半导体", "中华半导体指数"
    elif "医药" in name or "医疗" in name or "生物" in name:
        category, sub_category, underlying_index = "行业主题", "医药医疗", "中证医药卫生指数"
    elif "消费" in name or "食品饮料" in name or "酒" in name or "白酒" in name:
        category, sub_category, underlying_index = "行业主题", "消费", "中证主要消费指数"
    elif "券商" in name or "证券" in name:
        category, sub_category, underlying_index = "行业主题", "金融券商", "中证全指证券公司指数"
    elif "银行" in name:
        category, sub_category, underlying_index = "行业主题", "银行", "中证银行指数"
    elif "保险" in name:
        category, sub_category, underlying_index = "行业主题", "保险", "保险主题指数"
    elif "地产" in name or "房地产" in name:
        category, sub_category, underlying_index = "行业主题", "房地产", "中证800地产指数"
    elif "军工" in name:
        category, sub_category, underlying_index = "行业主题", "军工", "中证军工指数"
    elif "新能源" in name or "光伏" in name or "储能" in name:
        category, sub_category, underlying_index = "行业主题", "新能源", "中证新能源指数"
    elif "有色" in name or "稀土" in name or "材料" in name:
        category, sub_category, underlying_index = "行业主题", "有色金属", "中证有色金属指数"
    elif "煤炭" in name or "能源" in name:
        category, sub_category, underlying_index = "行业主题", "能源", "中证煤炭指数"
    elif "钢铁" in name:
        category, sub_category, underlying_index = "行业主题", "钢铁", "中证钢铁指数"
    elif "基建" in name or "建筑" in name:
        category, sub_category, underlying_index = "行业主题", "基建", "基建工程指数"
    elif "传媒" in name or "游戏" in name or "影视" in name:
        category, sub_category, underlying_index = "行业主题", "传媒游戏", "中证传媒指数"
    elif "计算机" in name or "软件" in name:
        category, sub_category, underlying_index = "行业主题", "计算机", "中证计算机指数"
    elif "通信" in name or "5G" in name:
        category, sub_category, underlying_index = "行业主题", "通信", "中证5G通信主题指数"
    elif "电子" in name:
        category, sub_category, underlying_index = "行业主题", "电子", "中证电子指数"
    elif "汽车" in name or "新能源车" in name:
        category, sub_category, underlying_index = "行业主题", "汽车", "中证800汽车指数"
    elif "农业" in name or "畜牧" in name or "养殖" in name:
        category, sub_category, underlying_index = "行业主题", "农业", "中证农业主题指数"
    elif "旅游" in name or "酒店" in name:
        category, sub_category, underlying_index = "行业主题", "旅游", "中证旅游主题指数"
    elif "物流" in name or "快递" in name:
        category, sub_category, underlying_index = "行业主题", "物流", "中证物流指数"
    elif "教育" in name:
        category, sub_category, underlying_index = "行业主题", "教育", "中证教育指数"
    elif "环保" in name or "碳中和" in name:
        category, sub_category, underlying_index = "行业主题", "环保", "中证环保产业指数"
    elif "创新药" in name:
        category, sub_category, underlying_index = "行业主题", "创新药", "中证创新药产业指数"
    elif "医疗器械" in name:
        category, sub_category, underlying_index = "行业主题", "医疗器械", "中证全指医疗器械指数"
    elif "化工" in name:
        category, sub_category, underlying_index = "行业主题", "化工", "中证细分化工产业主题指数"
    elif "家电" in name:
        category, sub_category, underlying_index = "行业主题", "家电", "中证全指家用电器指数"
    elif "机器人" in name or "人工智能" in name or "AI" in name:
        category, sub_category, underlying_index = "行业主题", "人工智能", "中证人工智能主题指数"
    elif "动漫" in name:
        category, sub_category, underlying_index = "行业主题", "动漫", "中证动漫游戏指数"
    elif "国防" in name:
        category, sub_category, underlying_index = "行业主题", "国防", "中证国防指数"
    elif "钢铁" in name:
        category, sub_category, underlying_index = "行业主题", "钢铁", "中证钢铁指数"
    elif "电力" in name or "电网" in name:
        category, sub_category, underlying_index = "行业主题", "电力", "中证全指电力指数"
    elif "交运" in name or "运输" in name:
        category, sub_category, underlying_index = "行业主题", "交通运输", "中证全指运输指数"
    elif "黄金" in name:
        category, sub_category, underlying_index = "商品ETF", "黄金", "上海黄金交易所AU99.99"
    elif "豆粕" in name or "商品" in name:
        category, sub_category = "商品ETF", "大宗商品"
    elif "石油" in name or "原油" in name:
        category, sub_category, underlying_index = "商品ETF", "原油", "WTI原油价格"
    # 策略因子
    elif "红利" in name:
        category, sub_category, underlying_index = "策略因子", "红利", "中证红利指数"
    elif "低波" in name or "低波动" in name:
        category, sub_category, underlying_index = "策略因子", "低波动", "中证500行业中性低波动指数"
    elif "价值" in name:
        category, sub_category, underlying_index = "策略因子", "价值", "沪深300价值指数"
    elif "成长" in name:
        category, sub_category, underlying_index = "策略因子", "成长", "沪深300成长指数"
    elif "质量" in name:
        category, sub_category, underlying_index = "策略因子", "质量", "中证500质量成长指数"
    elif "动量" in name:
        category, sub_category = "策略因子", "动量"
    elif "等权" in name:
        category, sub_category = "策略因子", "等权重"
    elif "Smart" in name or "smart" in name:
        category, sub_category = "策略因子", "Smart Beta"
    # 跨境指数
    elif "标普" in name or "S&P" in name or "SP" in name:
        category, sub_category, underlying_index = "跨境指数", "美股", "标普500指数"
    elif "纳斯达克" in name or "纳指" in name:
        category, sub_category, underlying_index = "跨境指数", "美股", "纳斯达克100指数"
    elif "恒指" in name or "恒生" in name or "港股" in name or "H股" in name:
        category, sub_category, underlying_index = "跨境指数", "港股", "恒生指数"
    elif "中概" in name or "互联" in name:
        category, sub_category, underlying_index = "跨境指数", "中概互联", "中证海外中国互联网指数"
    elif "日经" in name or "日本" in name:
        category, sub_category, underlying_index = "跨境指数", "日本", "日经225指数"
    elif "德国" in name or "DAX" in name:
        category, sub_category, underlying_index = "跨境指数", "欧洲", "德国DAX指数"
    elif "越南" in name or "印度" in name or "东南亚" in name:
        category, sub_category = "跨境指数", "新兴市场"
    # 债券ETF
    elif "债" in name or "国债" in name or "转债" in name or "信用债" in name or "国开债" in name:
        category, sub_category, underlying_index = "债券ETF", "债券", "中债综合指数"
    elif "货币" in name:
        category, sub_category = "货币ETF", "货币基金"
    # 默认保持宽基
    elif "ETF" in name and category == "其他":
        category = "宽基指数"
        sub_category = "综合"

    # Manager inference from name
    manager_keywords = {
        "华夏": "华夏基金",
        "易方达": "易方达基金",
        "华泰柏瑞": "华泰柏瑞基金",
        "南方": "南方基金",
        "嘉实": "嘉实基金",
        "广发": "广发基金",
        "天弘": "天弘基金",
        "博时": "博时基金",
        "富国": "富国基金",
        "华安": "华安基金",
        "国泰": "国泰基金",
        "华宝": "华宝基金",
        "汇添富": "汇添富基金",
        "鹏华": "鹏华基金",
        "工银瑞信": "工银瑞信基金",
        "银华": "银华基金",
        "建信": "建信基金",
        "平安": "平安基金",
        "招商": "招商基金",
        "景顺长城": "景顺长城基金",
        "交银施罗德": "交银施罗德基金",
        "中欧": "中欧基金",
        "申万菱信": "申万菱信基金",
        "国联安": "国联安基金",
        "中信": "中信基金",
        "民生加银": "民生加银基金",
        "中银": "中银基金",
        "大成": "大成基金",
        "融通": "融通基金",
        "兴全": "兴证全球基金",
        "兴业": "兴业基金",
        "上投摩根": "上投摩根基金",
        "摩根": "摩根资产管理",
        "泰康": "泰康资产",
    }

    manager = ""
    for kw, mgr in manager_keywords.items():
        if kw in name:
            manager = mgr
            break

    if not manager:
        manager_pool = ["华夏基金", "易方达基金", "华泰柏瑞基金", "南方基金", "嘉实基金",
                       "广发基金", "天弘基金", "博时基金", "富国基金", "华安基金"]
        manager = random.choice(manager_pool)

    return category, sub_category, manager, underlying_index


def seed_etf_info_fields(db):
    """Update etf_info category, manager, sub_category, underlying_index for all ETFs."""
    # First: hardcoded accurate data for key ETFs
    etf_details = {
        "159915.SZ": ("宽基指数", "创业板", "易方达基金", "创业板指数"),
        "512000.SH": ("行业主题", "金融券商", "华宝基金", "中证全指证券公司指数"),
        "159928.SZ": ("行业主题", "消费", "汇添富基金", "中证主要消费指数"),
        "510300.SH": ("宽基指数", "沪深300", "华泰柏瑞基金", "沪深300指数"),
        "510050.SH": ("宽基指数", "上证50", "华夏基金", "上证50指数"),
    }

    updated = 0
    for code, (category, sub_category, manager, idx) in etf_details.items():
        result = db.execute(text("""
            UPDATE etf_info
            SET category = :category, sub_category = :sub_category,
                manager = :manager, underlying_index = :idx
            WHERE code = :code
        """), {"code": code, "category": category, "sub_category": sub_category,
                "manager": manager, "idx": idx})
        if result.rowcount > 0:
            updated += 1

    # Then: infer from names for all remaining ETFs
    result = db.execute(text("""
        SELECT code, name FROM etf_info
        WHERE category IS NULL OR manager IS NULL OR underlying_index IS NULL
    """))
    rows = result.fetchall()

    for code, name in rows:
        if code in etf_details:
            continue
        cat, sub, mgr, idx = _infer_etf_metadata(name)
        db.execute(text("""
            UPDATE etf_info
            SET category = :category, sub_category = :sub_category,
                manager = :manager, underlying_index = :idx
            WHERE code = :code
        """), {"code": code, "category": cat, "sub_category": sub or None,
                "manager": mgr, "idx": idx or None})
        updated += 1

    db.commit()
    print(f"✅ Updated {updated} ETF info records with category/manager/sub_category/underlying_index.")


def seed_notification_configs(db):
    """Insert demo notification configs."""
    count = db.execute(text("SELECT COUNT(*) FROM notification_config")).scalar()
    if count > 0:
        print(f"⏭️  notification_config already has {count} rows, skipping.")
        return

    configs = [
        {
            "name": "企业微信推送",
            "channel_type": "wechat_work",
            "config_json": {"webhook_url": "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=xxx"},
            "is_active": True,
        },
        {
            "name": "飞书推送",
            "channel_type": "feishu",
            "config_json": {"webhook_url": "https://open.feishu.cn/open-apis/bot/v2/hook/xxx"},
            "is_active": True,
        },
        {
            "name": "钉钉推送",
            "channel_type": "dingtalk",
            "config_json": {"webhook_url": "https://oapi.dingtalk.com/robot/send?access_token=xxx"},
            "is_active": False,
        },
    ]

    config_ids = []
    for c in configs:
        result = db.execute(text("""
            INSERT INTO notification_config (name, channel_type, config_json, is_active, created_at, updated_at)
            VALUES (:name, :channel_type, :config_json, :is_active, NOW(), NOW())
            RETURNING id
        """), {
            "name": c["name"],
            "channel_type": c["channel_type"],
            "config_json": json.dumps(c["config_json"]),
            "is_active": c["is_active"],
        })
        config_ids.append(result.scalar())

    db.commit()
    print(f"✅ Inserted {len(configs)} notification configs: {config_ids}")
    return config_ids


def seed_notification_logs(db, config_ids):
    """Insert demo notification logs."""
    count = db.execute(text("SELECT COUNT(*) FROM notification_log")).scalar()
    if count > 0:
        print(f"⏭️  notification_log already has {count} rows, skipping.")
        return

    statuses = ["success", "success", "success", "failed", "pending"]
    for i in range(15):
        db.execute(text("""
            INSERT INTO notification_log (config_id, report_id, status, error_msg, sent_at, created_at)
            VALUES (:config_id, :report_id, :status, :error_msg, :sent_at, NOW())
        """), {
            "config_id": random.choice(config_ids),
            "report_id": random.randint(1, 10),
            "status": statuses[i % len(statuses)],
            "error_msg": "Connection timeout" if i % len(statuses) == 3 else None,
            "sent_at": datetime.now() - timedelta(days=i) if i % len(statuses) != 4 else None,
        })

    db.commit()
    print("✅ Inserted 15 notification logs.")


def seed_pool_weights(db):
    """Insert demo pool weights for pools that have members."""
    count = db.execute(text("SELECT COUNT(*) FROM pool_weight")).scalar()
    if count > 0:
        print(f"⏭️  pool_weight already has {count} rows, skipping.")
        return

    # Get all pools with their members
    pools = db.execute(text("""
        SELECT DISTINCT p.id, p.name
        FROM etf_pools p
        JOIN pool_member pm ON p.id = pm.pool_id
        WHERE pm.removed_at IS NULL
    """)).fetchall()

    inserted = 0
    for pool_id, _pool_name in pools:
        members = db.execute(text("""
            SELECT etf_code FROM pool_member
            WHERE pool_id = :pool_id AND removed_at IS NULL
        """), {"pool_id": pool_id}).fetchall()

        n = len(members)
        if n == 0:
            continue

        # Equal weight distribution
        base_weight = round(100.0 / n, 2)
        weights = [base_weight] * n
        # Adjust last one to sum to 100
        weights[-1] = round(100.0 - sum(weights[:-1]), 2)

        for i, (etf_code,) in enumerate(members):
            db.execute(text("""
                INSERT INTO pool_weight (pool_id, etf_code, target_weight, suggested_weight, weight_source, created_at, updated_at)
                VALUES (:pool_id, :etf_code, :target_weight, :suggested_weight, :weight_source, NOW(), NOW())
            """), {
                "pool_id": pool_id,
                "etf_code": etf_code,
                "target_weight": weights[i],
                "suggested_weight": weights[i],
                "weight_source": "equal",
            })
            inserted += 1

    db.commit()
    print(f"✅ Inserted {inserted} pool weights for {len(pools)} pools.")


def seed_data_source_config(db):
    """Insert demo data source configurations."""
    count = db.execute(text("SELECT COUNT(*) FROM data_source_config")).scalar()
    if count > 0:
        print(f"⏭️  data_source_config already has {count} rows, skipping.")
        return

    configs = [
        {
            "source_name": "akshare",
            "provider_class": "app.data_providers.akshare_provider.AKShareProvider",
            "api_key": None,
            "rate_limit": 100,
            "is_active": True,
            "config_json": {"base_url": "https://www.akshare.xyz", "timeout": 30},
        },
        {
            "source_name": "tushare",
            "provider_class": "app.data_providers.tushare_provider.TushareProvider",
            "api_key": "demo_key_placeholder",
            "rate_limit": 200,
            "is_active": False,
            "config_json": {"base_url": "https://api.tushare.pro", "timeout": 30},
        },
        {
            "source_name": "yfinance",
            "provider_class": "app.data_providers.yfinance_provider.YFinanceProvider",
            "api_key": None,
            "rate_limit": 1000,
            "is_active": True,
            "config_json": {"timeout": 30, "cache_dir": "/tmp/yfinance"},
        },
    ]

    for c in configs:
        db.execute(text("""
            INSERT INTO data_source_config (source_name, provider_class, api_key, rate_limit, is_active, config_json, created_at, updated_at)
            VALUES (:source_name, :provider_class, :api_key, :rate_limit, :is_active, :config_json, NOW(), NOW())
        """), {
            "source_name": c["source_name"],
            "provider_class": c["provider_class"],
            "api_key": c["api_key"],
            "rate_limit": c["rate_limit"],
            "is_active": c["is_active"],
            "config_json": json.dumps(c["config_json"]),
        })

    db.commit()
    print(f"✅ Inserted {len(configs)} data source configs.")


def main():
    db = Session()
    try:
        print("=" * 50)
        print("🌱 Seeding demo data for all features")
        print("=" * 50)

        # 0. Ensure missing tables exist
        ensure_missing_tables(db)

        # 0.5. Update ETF info fields (category, manager)
        seed_etf_info_fields(db)

        # 1. Pools
        seed_pools(db)

        # 2. Strategies
        strategy_ids = seed_strategies(db)

        # 3. Backtests (needs strategies)
        if strategy_ids:
            seed_backtests(db, strategy_ids)

        # 4. Signals (needs strategies)
        if strategy_ids:
            seed_signals(db, strategy_ids)

        # 5. Reports
        seed_reports(db)

        # 6. Scan logs
        seed_scan_logs(db)

        # 7. Notification configs
        config_ids = seed_notification_configs(db)

        # 8. Notification logs (needs configs)
        if config_ids:
            seed_notification_logs(db, config_ids)

        # 9. Pool weights
        seed_pool_weights(db)

        # 10. Data source configs
        seed_data_source_config(db)

        # Summary
        print("\n" + "=" * 50)
        print("📊 Demo Data Summary")
        print("=" * 50)
        tables = [
            "etf_pools", "pool_member", "strategy_config", "backtest_result",
            "signal", "report_metadata", "etf_scan_log", "notification_config", "notification_log",
        ]
        for t in tables:
            count = db.execute(text(f'SELECT COUNT(*) FROM "{t}"')).scalar()
            print(f"  {t}: {count} rows")

        print("\n✅ All demo data seeded successfully!")

    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        db.close()


if __name__ == "__main__":
    main()

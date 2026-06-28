"""Initialize demo data for AD-Research.

Generates mock indicator data for all ETFs, creates default score templates,
and calculates composite scores.

Usage:
    cd /Users/aidanliu/Documents/vibe-trading/etf-research-platform
    /opt/homebrew/opt/python@3.12/Frameworks/Python.framework/Versions/3.12/bin/python3.12 -m scripts.init_demo_data
"""

import os
import random
import sys
from datetime import date, timedelta

# Add project to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.config import get_settings
from app.models.etf import ETFIndicator, ETFInfo
from app.models.scoring import ETFScore, ScoreTemplate
from app.services.scoring_service import ScoringService


def generate_mock_indicators(db, trade_date: date):
    """Generate mock indicator data for all ETFs."""
    etfs = db.query(ETFInfo.code).all()
    total = len(etfs)
    print(f"Generating indicators for {total} ETFs on {trade_date}...")

    batch_size = 500
    count = 0

    for _i, (etf_code,) in enumerate(etfs):
        # Generate realistic random values
        base_price = random.uniform(0.5, 5.0)
        indicators = ETFIndicator(
            etf_code=etf_code,
            trade_date=trade_date,
            ma5=round(base_price * random.uniform(0.95, 1.05), 4),
            ma10=round(base_price * random.uniform(0.92, 1.08), 4),
            ma20=round(base_price * random.uniform(0.88, 1.12), 4),
            ma60=round(base_price * random.uniform(0.80, 1.20), 4),
            rsi14=round(random.uniform(20, 80), 4),
            macd_dif=round(random.uniform(-0.5, 0.5), 4),
            macd_dea=round(random.uniform(-0.3, 0.3), 4),
            macd_hist=round(random.uniform(-0.2, 0.2), 4),
            volatility_20d=round(random.uniform(0.05, 0.35), 4),
            volatility_60d=round(random.uniform(0.05, 0.40), 4),
            max_drawdown_1y=round(random.uniform(-0.50, -0.05), 4),
            sharpe_1y=round(random.uniform(-1.5, 2.5), 4),
            return_1w=round(random.uniform(-0.10, 0.10), 4),
            return_1m=round(random.uniform(-0.20, 0.25), 4),
            return_3m=round(random.uniform(-0.30, 0.40), 4),
            return_6m=round(random.uniform(-0.40, 0.60), 4),
            return_1y=round(random.uniform(-0.50, 0.80), 4),
            atr14=round(base_price * random.uniform(0.01, 0.05), 4),
            bb_upper=round(base_price * random.uniform(1.05, 1.20), 4),
            bb_lower=round(base_price * random.uniform(0.80, 0.95), 4),
        )
        db.add(indicators)
        count += 1

        if count % batch_size == 0:
            db.commit()
            print(f"  Committed {count}/{total}...")

    db.commit()
    print(f"Done. Generated {count} indicator records.")
    return count


def create_default_templates(db):
    """Create default score templates if they don't exist."""
    existing = db.query(ScoreTemplate).count()
    if existing > 0:
        print(f"Templates already exist ({existing}), skipping.")
        return

    templates = [
        {
            "name": "保守型",
            "description": "注重风险控制，适合低风险偏好",
            "weights": {
                "return": 0.2,
                "risk": 0.35,
                "sharpe": 0.3,
                "liquidity": 0.1,
                "trend": 0.05,
            },
            "is_default": False,
        },
        {
            "name": "均衡型",
            "description": "收益与风险平衡，适合中等风险偏好",
            "weights": {
                "return": 0.3,
                "risk": 0.25,
                "sharpe": 0.25,
                "liquidity": 0.1,
                "trend": 0.1,
            },
            "is_default": True,
        },
        {
            "name": "进取型",
            "description": "追求高收益，适合高风险偏好",
            "weights": {
                "return": 0.4,
                "risk": 0.15,
                "sharpe": 0.2,
                "liquidity": 0.05,
                "trend": 0.2,
            },
            "is_default": False,
        },
    ]

    for t in templates:
        template = ScoreTemplate(
            name=t["name"],
            description=t["description"],
            weights=t["weights"],
            is_default=t["is_default"],
        )
        db.add(template)

    db.commit()
    print(f"Created {len(templates)} default templates.")


def calculate_scores(db):
    """Run score calculation for the latest indicator date."""
    service = ScoringService(db)
    results = service.calculate_daily_scores()

    if not results:
        print("No scores calculated (no indicators found).")
        return 0

    total = sum(results.values())
    print(f"Calculated {total} scores across {len(results)} templates.")
    for template_id, count in results.items():
        print(f"  Template {template_id}: {count} scores")
    return total


def main():
    settings = get_settings()
    engine = create_engine(settings.database_url)
    session_maker = sessionmaker(bind=engine)
    db = session_maker()

    try:
        # 1. Generate mock indicators
        trade_date = date.today() - timedelta(days=1)
        indicator_count = db.query(ETFIndicator).filter(
            ETFIndicator.trade_date == trade_date
        ).count()

        if indicator_count == 0:
            generate_mock_indicators(db, trade_date)
        else:
            print(f"Indicators already exist for {trade_date} ({indicator_count} records), skipping.")

        # 2. Create default templates
        create_default_templates(db)

        # 3. Calculate scores
        calculate_scores(db)

        print("\n=== Demo data initialization complete ===")
        print(f"Indicators: {db.query(ETFIndicator).count()}")
        print(f"Templates:  {db.query(ScoreTemplate).count()}")
        print(f"Scores:     {db.query(ETFScore).count()}")

    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        db.close()


if __name__ == "__main__":
    main()

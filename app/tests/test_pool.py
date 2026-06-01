"""Tests for pool models.

Covers creation and basic attribute validation of PoolWeight and PoolSnapshot.
"""

from datetime import date, datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.models.pool import ETFPools, PoolMember, PoolWeight, PoolSnapshot
from app.models.etf import ETFInfo
from app.core.database import Base


@pytest.fixture(scope="module")
def db_session():
    """Create an in-memory SQLite database session for testing."""
    engine = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


def test_create_pool_weight(db_session):
    """PoolWeight should be created with correct attributes."""
    # Create prerequisite pool
    pool = ETFPools(name="Core Pool", description="Core ETF pool")
    db_session.add(pool)
    db_session.commit()

    # Create prerequisite ETF
    etf = ETFInfo(
        code="510300",
        name="CSI 300 ETF",
        category="Equity",
    )
    db_session.add(etf)
    db_session.commit()

    weight = PoolWeight(
        pool_id=pool.id,
        etf_code="510300",
        target_weight=25.00,
        suggested_weight=22.50,
        weight_source="score",
    )
    db_session.add(weight)
    db_session.commit()

    assert weight.id is not None
    assert weight.pool_id == pool.id
    assert weight.etf_code == "510300"
    assert float(weight.target_weight) == 25.00
    assert float(weight.suggested_weight) == 22.50
    assert weight.weight_source == "score"
    assert isinstance(weight.created_at, datetime)
    assert isinstance(weight.updated_at, datetime)


def test_create_pool_weight_manual_source(db_session):
    """PoolWeight should support manual weight source."""
    pool = ETFPools(name="Manual Pool", description="Manually weighted pool")
    db_session.add(pool)
    db_session.commit()

    etf = ETFInfo(
        code="510500",
        name="CSI 500 ETF",
        category="Equity",
    )
    db_session.add(etf)
    db_session.commit()

    weight = PoolWeight(
        pool_id=pool.id,
        etf_code="510500",
        target_weight=50.00,
        suggested_weight=50.00,
        weight_source="manual",
    )
    db_session.add(weight)
    db_session.commit()

    assert weight.weight_source == "manual"
    assert float(weight.target_weight) == 50.00


def test_create_pool_snapshot(db_session):
    """PoolSnapshot should be created with JSON data."""
    pool = ETFPools(name="Snapshot Pool", description="Pool for snapshots")
    db_session.add(pool)
    db_session.commit()

    snapshot_data = {
        "holdings": [
            {"etf_code": "510300", "weight": 25.0, "nav": 4.5},
            {"etf_code": "510500", "weight": 25.0, "nav": 6.2},
            {"etf_code": "159915", "weight": 25.0, "nav": 2.8},
            {"etf_code": "518880", "weight": 25.0, "nav": 3.9},
        ],
        "total_value": 1000000.00,
        "currency": "CNY",
        "metrics": {
            "volatility_annual": 15.5,
            "sharpe_ratio": 1.2,
            "max_drawdown": -12.3,
        },
    }

    snapshot = PoolSnapshot(
        pool_id=pool.id,
        snapshot_date=date(2024, 6, 1),
        data=snapshot_data,
    )
    db_session.add(snapshot)
    db_session.commit()

    assert snapshot.id is not None
    assert snapshot.pool_id == pool.id
    assert snapshot.snapshot_date == date(2024, 6, 1)
    assert snapshot.data["total_value"] == 1000000.00
    assert snapshot.data["currency"] == "CNY"
    assert len(snapshot.data["holdings"]) == 4
    assert snapshot.data["holdings"][0]["etf_code"] == "510300"
    assert snapshot.data["metrics"]["sharpe_ratio"] == 1.2
    assert isinstance(snapshot.created_at, datetime)


def test_create_pool_snapshot_minimal_data(db_session):
    """PoolSnapshot should work with minimal JSON data."""
    pool = ETFPools(name="Minimal Pool", description="Minimal snapshot pool")
    db_session.add(pool)
    db_session.commit()

    snapshot = PoolSnapshot(
        pool_id=pool.id,
        snapshot_date=date(2024, 6, 15),
        data={"note": "Initial snapshot"},
    )
    db_session.add(snapshot)
    db_session.commit()

    assert snapshot.data["note"] == "Initial snapshot"
    assert snapshot.snapshot_date == date(2024, 6, 15)


def test_pool_member_soft_delete(db_session):
    """PoolMember should support soft-delete via removed_at."""
    pool = ETFPools(name="Soft Delete Pool", description="Test soft delete")
    db_session.add(pool)
    db_session.commit()

    etf = ETFInfo(
        code="159915",
        name="ChiNext ETF",
        category="Equity",
    )
    db_session.add(etf)
    db_session.commit()

    member = PoolMember(
        pool_id=pool.id,
        etf_code="159915",
        notes="Test member",
    )
    db_session.add(member)
    db_session.commit()

    assert member.id is not None
    assert member.pool_id == pool.id
    assert member.etf_code == "159915"
    assert member.removed_at is None
    assert member.notes == "Test member"
    assert isinstance(member.added_at, datetime)

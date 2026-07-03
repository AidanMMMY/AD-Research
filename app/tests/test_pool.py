"""Tests for pool models and services.

Covers creation, validation, soft-delete, weight constraints, and suggestion
algorithms for pools.

M21-3: adds owner-scoped filtering tests at the bottom of this module
(list/get for regular users vs. admins).
"""

from datetime import date, datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.database import Base
from app.models.etf import ETFInfo
from app.models.pool import ETFPools, PoolMember, PoolSnapshot, PoolWeight
from app.models.user import User
from app.schemas.auth import UserResponse
from app.schemas.pool import PoolMemberCreate
from app.services.pool_enhancement_service import PoolEnhancementService
from app.services.pool_service import PoolService


@pytest.fixture
def db_session():
    """Create an in-memory SQLite database session for testing."""
    engine = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(engine)
    session_maker = sessionmaker(bind=engine)
    session = session_maker()
    yield session
    session.close()


@pytest.fixture
def pool_with_etfs(db_session):
    """Create a pool with three ETFs for service-level tests."""
    pool = ETFPools(name="Service Test Pool", description="For service tests")
    db_session.add(pool)
    db_session.commit()

    codes = ["510300", "510500", "159915"]
    for code in codes:
        etf = ETFInfo(code=code, name=f"ETF {code}", category="Equity")
        db_session.add(etf)
    db_session.commit()

    for code in codes:
        member = PoolMember(pool_id=pool.id, etf_code=code)
        db_session.add(member)
    db_session.commit()

    return pool, codes


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


# ---------------------------------------------------------------------------
# Pool service: member uniqueness and soft-delete
# ---------------------------------------------------------------------------


def test_add_member_idempotent(pool_with_etfs, db_session):
    """Adding the same active ETF twice should not create duplicate members."""
    pool, codes = pool_with_etfs
    service = PoolService(db_session)

    first = service.add_member(pool.id, PoolMemberCreate(etf_code=codes[0], notes="first"))
    second = service.add_member(pool.id, PoolMemberCreate(etf_code=codes[0], notes="second"))

    assert first is not None
    assert second is not None
    assert first.id == second.id

    active_members = (
        db_session.query(PoolMember)
        .filter(PoolMember.pool_id == pool.id, PoolMember.etf_code == codes[0])
        .filter(PoolMember.removed_at.is_(None))
        .all()
    )
    assert len(active_members) == 1


def test_remove_member_soft_deletes_weight(pool_with_etfs, db_session):
    """Removing a member should soft-delete its active PoolWeight records."""
    pool, codes = pool_with_etfs
    target_code = codes[0]

    weight = PoolWeight(
        pool_id=pool.id,
        etf_code=target_code,
        target_weight=30.0,
        weight_source="manual",
    )
    db_session.add(weight)
    db_session.commit()

    service = PoolService(db_session)
    service.remove_member(pool.id, target_code)

    member = (
        db_session.query(PoolMember)
        .filter(
            PoolMember.pool_id == pool.id,
            PoolMember.etf_code == target_code,
        )
        .first()
    )
    assert member.removed_at is not None

    weight_after = (
        db_session.query(PoolWeight)
        .filter(
            PoolWeight.pool_id == pool.id,
            PoolWeight.etf_code == target_code,
        )
        .first()
    )
    assert weight_after.removed_at is not None


# ---------------------------------------------------------------------------
# Weight validation
# ---------------------------------------------------------------------------


def test_update_weight_rejects_negative(pool_with_etfs, db_session):
    """Negative target weights should be rejected."""
    pool, codes = pool_with_etfs
    service = PoolEnhancementService(db_session)

    with pytest.raises(ValueError, match="between 0 and 100"):
        service.update_weight(pool.id, codes[0], -5.0)


def test_update_weight_rejects_over_100(pool_with_etfs, db_session):
    """Weights that push the pool total above 100% should be rejected."""
    pool, codes = pool_with_etfs
    service = PoolEnhancementService(db_session)

    # Set first two weights to 50% each
    service.update_weight(pool.id, codes[0], 50.0)
    service.update_weight(pool.id, codes[1], 50.0)

    # Third weight would exceed 100.01% threshold
    with pytest.raises(ValueError, match="must not exceed 100%"):
        service.update_weight(pool.id, codes[2], 10.0)


def test_update_weight_accepts_near_100(pool_with_etfs, db_session):
    """Weights summing to exactly 100% should be accepted."""
    pool, codes = pool_with_etfs
    service = PoolEnhancementService(db_session)

    result = service.update_weight(pool.id, codes[0], 100.0)
    assert result is not None
    assert result["target_weight"] == 100.0


def test_update_weight_creates_record(pool_with_etfs, db_session):
    """Updating weight for a member without a weight record should create one."""
    pool, codes = pool_with_etfs
    service = PoolEnhancementService(db_session)

    result = service.update_weight(pool.id, codes[0], 25.0)
    assert result is not None
    assert result["etf_code"] == codes[0]
    assert result["target_weight"] == 25.0
    assert result["weight_source"] == "manual"

    stored = (
        db_session.query(PoolWeight)
        .filter(
            PoolWeight.pool_id == pool.id,
            PoolWeight.etf_code == codes[0],
            PoolWeight.removed_at.is_(None),
        )
        .first()
    )
    assert stored is not None
    assert float(stored.target_weight) == 25.0


# ---------------------------------------------------------------------------
# Weight suggestion algorithms
# ---------------------------------------------------------------------------


def test_suggest_equal_weights(pool_with_etfs, db_session):
    """Equal-weight algorithm should split 100% across active members."""
    pool, codes = pool_with_etfs
    service = PoolEnhancementService(db_session)

    suggestions = service.suggest_weights(pool.id, algorithm="equal")
    assert len(suggestions) == len(codes)

    total = sum(s["suggested_weight"] for s in suggestions)
    assert total == 100.0
    assert all(s["algorithm"] == "equal" for s in suggestions)


def test_suggest_weights_stores_values(pool_with_etfs, db_session):
    """Suggested weights should be persisted on PoolWeight rows."""
    pool, codes = pool_with_etfs
    service = PoolEnhancementService(db_session)

    service.suggest_weights(pool.id, algorithm="equal")

    for code in codes:
        weight = (
            db_session.query(PoolWeight)
            .filter(
                PoolWeight.pool_id == pool.id,
                PoolWeight.etf_code == code,
                PoolWeight.removed_at.is_(None),
            )
            .first()
        )
        assert weight is not None
        assert weight.weight_source == "equal"
        assert weight.suggested_weight is not None


# ---------------------------------------------------------------------------
# M21-3: Owner-scoped filtering
# ---------------------------------------------------------------------------


@pytest.fixture
def owner_scoped_db(db_session):
    """Seed two users + three pools (Alice-owned, Bob-owned, shared/NULL)."""
    alice = User(
        username="alice",
        password_hash="x",
        role="user",
        is_active=True,
    )
    bob = User(
        username="bob",
        password_hash="x",
        role="user",
        is_active=True,
    )
    admin = User(
        username="admin",
        password_hash="x",
        role="admin",
        is_active=True,
    )
    db_session.add_all([alice, bob, admin])
    db_session.commit()

    p_alice = ETFPools(name="Alice Pool", user_id=alice.id)
    p_bob = ETFPools(name="Bob Pool", user_id=bob.id)
    p_shared = ETFPools(name="Shared Pool", user_id=None)
    db_session.add_all([p_alice, p_bob, p_shared])
    db_session.commit()

    return {
        "alice": alice,
        "bob": bob,
        "admin": admin,
        "p_alice": p_alice,
        "p_bob": p_bob,
        "p_shared": p_shared,
    }


def _user_resp(u: User) -> UserResponse:
    """Build a UserResponse from an ORM User (the shape the service expects)."""
    return UserResponse(id=u.id, username=u.username, role=u.role)


def test_list_pools_regular_user_sees_own_and_shared(owner_scoped_db, db_session):
    """Regular user list should return own pools + NULL-owner pools only."""
    seeded = owner_scoped_db
    service = PoolService(db_session)

    alice_resp = _user_resp(seeded["alice"])
    visible = service.list_pools(current_user=alice_resp)
    visible_ids = {p.id for p in visible}

    # Alice's pool + the shared pool, but NOT Bob's pool.
    assert seeded["p_alice"].id in visible_ids
    assert seeded["p_shared"].id in visible_ids
    assert seeded["p_bob"].id not in visible_ids


def test_list_pools_admin_sees_everything(owner_scoped_db, db_session):
    """Admin list should return all pools regardless of owner."""
    seeded = owner_scoped_db
    service = PoolService(db_session)

    admin_resp = _user_resp(seeded["admin"])
    visible = service.list_pools(current_user=admin_resp)
    visible_ids = {p.id for p in visible}

    assert seeded["p_alice"].id in visible_ids
    assert seeded["p_bob"].id in visible_ids
    assert seeded["p_shared"].id in visible_ids

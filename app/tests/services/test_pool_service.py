"""Tests for PoolService.

Focuses on lifecycle: create -> add member -> list -> soft-delete.
"""

import pytest

from app.models.etf import ETFInfo
from app.models.pool import ETFPools, PoolMember, PoolWeight
from app.schemas.auth import UserResponse
from app.schemas.pool import PoolCreate, PoolMemberCreate, PoolUpdate
from app.services.pool_service import PoolService

TEST_USER = UserResponse(id=1, username="test", role="user")
ADMIN_USER = UserResponse(id=2, username="admin", role="admin")


def _seed_etfs(db, codes):
    for code in codes:
        db.add(ETFInfo(code=code, name=f"ETF {code}", category="Equity"))
    db.commit()


def test_create_pool_returns_response(db_session):
    svc = PoolService(db_session)
    pool = svc.create_pool(PoolCreate(name="Core", description="Core ETFs"))
    assert pool.id is not None
    assert pool.name == "Core"
    assert pool.members == []


def test_list_pools_excludes_deleted(db_session):
    svc = PoolService(db_session)
    svc.create_pool(PoolCreate(name="A", description=""), current_user=TEST_USER)
    p2 = svc.create_pool(PoolCreate(name="B", description=""), current_user=TEST_USER)
    svc.delete_pool(p2.id, current_user=TEST_USER)
    visible = [p.name for p in svc.list_pools(current_user=TEST_USER)]
    assert visible == ["A"]


def test_get_pool_returns_none_for_missing(db_session):
    svc = PoolService(db_session)
    assert svc.get_pool(9999) is None


def test_update_pool_changes_fields(db_session):
    svc = PoolService(db_session)
    pool = svc.create_pool(PoolCreate(name="Old", description="d"))
    updated = svc.update_pool(pool.id, PoolUpdate(name="New"))
    assert updated is not None
    assert updated.name == "New"


def test_add_member_then_remove_is_idempotent(db_session):
    _seed_etfs(db_session, ["510300", "510500"])
    svc = PoolService(db_session)
    pool = svc.create_pool(PoolCreate(name="P", description=""))
    svc.add_member(pool.id, PoolMemberCreate(etf_code="510300"))
    svc.add_member(pool.id, PoolMemberCreate(etf_code="510300"))  # again
    after = svc.get_pool(pool.id)
    assert after is not None
    codes = [m.etf_code for m in after.members]
    assert codes.count("510300") == 1

    removed = svc.remove_member(pool.id, "510300")
    assert removed is not None
    member = (
        db_session.query(PoolMember)
        .filter(PoolMember.pool_id == pool.id, PoolMember.etf_code == "510300")
        .first()
    )
    assert member.removed_at is not None


def test_delete_pool_soft_deletes(db_session):
    svc = PoolService(db_session)
    pool = svc.create_pool(PoolCreate(name="X", description=""), current_user=TEST_USER)
    assert svc.delete_pool(pool.id, current_user=TEST_USER) is True
    # Second delete is a no-op
    assert svc.delete_pool(pool.id, current_user=TEST_USER) is False
    assert svc.get_pool(pool.id, current_user=TEST_USER) is None


def test_delete_pool_cascades_members_and_weights(db_session):
    """Deleting a pool must soft-delete its active members + weight rows."""
    _seed_etfs(db_session, ["510300"])
    svc = PoolService(db_session)
    pool = svc.create_pool(PoolCreate(name="P", description=""), current_user=TEST_USER)
    svc.add_member(pool.id, PoolMemberCreate(etf_code="510300"), current_user=TEST_USER)

    assert svc.delete_pool(pool.id, current_user=TEST_USER) is True

    member = (
        db_session.query(PoolMember)
        .filter(PoolMember.pool_id == pool.id, PoolMember.etf_code == "510300")
        .first()
    )
    assert member is not None
    assert member.removed_at is not None

    weight = (
        db_session.query(PoolWeight)
        .filter(PoolWeight.pool_id == pool.id, PoolWeight.etf_code == "510300")
        .first()
    )
    assert weight is not None
    assert weight.removed_at is not None


def test_delete_shared_preset_pool_regular_user_forbidden(db_session):
    """NULL-owner (系统预置全局共享) pools must not be deletable by regular users."""
    svc = PoolService(db_session)
    shared = ETFPools(name="行业轮动池", description="preset", user_id=None)
    db_session.add(shared)
    db_session.commit()

    with pytest.raises(PermissionError, match="system_pool"):
        svc.delete_pool(shared.id, current_user=TEST_USER)

    # Pool is untouched.
    db_session.refresh(shared)
    assert shared.deleted_at is None


def test_delete_shared_preset_pool_admin_allowed(db_session):
    """Admins can delete NULL-owner shared/preset pools (with cascade)."""
    _seed_etfs(db_session, ["510300"])
    svc = PoolService(db_session)
    shared = ETFPools(name="行业轮动池", description="preset", user_id=None)
    db_session.add(shared)
    db_session.commit()
    db_session.add(PoolMember(pool_id=shared.id, etf_code="510300"))
    db_session.add(
        PoolWeight(
            pool_id=shared.id,
            etf_code="510300",
            target_weight=0.0,
            weight_source="manual",
        )
    )
    db_session.commit()

    assert svc.delete_pool(shared.id, current_user=ADMIN_USER) is True
    db_session.refresh(shared)
    assert shared.deleted_at is not None

    member = (
        db_session.query(PoolMember)
        .filter(PoolMember.pool_id == shared.id)
        .first()
    )
    assert member.removed_at is not None


def test_delete_other_users_pool_forbidden(db_session):
    """Regular users must not delete pools owned by somebody else."""
    svc = PoolService(db_session)
    foreign = ETFPools(name="Bob Pool", description="", user_id=999)
    db_session.add(foreign)
    db_session.commit()

    with pytest.raises(PermissionError, match="not_owner"):
        svc.delete_pool(foreign.id, current_user=TEST_USER)

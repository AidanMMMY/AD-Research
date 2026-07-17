"""Tests for PoolService.

Focuses on lifecycle: create -> add member -> list -> soft-delete.
"""

from app.models.etf import ETFInfo
from app.models.pool import ETFPools, PoolMember
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
    p1 = svc.create_pool(PoolCreate(name="A", description=""), current_user=TEST_USER)
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

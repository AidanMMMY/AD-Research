"""Tests for AI chat session ownership scoping (security audit 2026-08-06).

Chat sessions contain potentially sensitive research conversations. The
service methods used to operate purely on ``session_id`` — any authenticated
user could read / delete / write into another user's sessions (IDOR). These
tests pin the user-scoped behaviour.
"""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.database import Base
from app.models.research import AIChatMessage, AIChatSession
from app.models.user import User
from app.services.chat_service import ChatService


@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


@pytest.fixture
def two_users_with_sessions(db_session):
    alice = User(username="alice", password_hash="x", role="user", is_active=True)
    bob = User(username="bob", password_hash="x", role="user", is_active=True)
    db_session.add_all([alice, bob])
    db_session.commit()

    s_alice = AIChatSession(user_id=alice.id, title="Alice session")
    s_bob = AIChatSession(user_id=bob.id, title="Bob session")
    db_session.add_all([s_alice, s_bob])
    db_session.commit()
    return alice, bob, s_alice, s_bob


def test_get_session_scoped_by_user(db_session, two_users_with_sessions):
    alice, bob, s_alice, _ = two_users_with_sessions
    svc = ChatService(db_session)

    assert svc.get_session(s_alice.id, user_id=alice.id) is not None
    # Bob must NOT see Alice's session.
    assert svc.get_session(s_alice.id, user_id=bob.id) is None


def test_delete_session_scoped_by_user(db_session, two_users_with_sessions):
    alice, bob, s_alice, _ = two_users_with_sessions
    svc = ChatService(db_session)

    assert svc.delete_session(s_alice.id, user_id=bob.id) is False
    # Still present because Bob couldn't delete it.
    assert svc.get_session(s_alice.id, user_id=alice.id) is not None

    assert svc.delete_session(s_alice.id, user_id=alice.id) is True
    assert svc.get_session(s_alice.id, user_id=alice.id) is None


def test_get_messages_scoped_by_user(db_session, two_users_with_sessions):
    alice, bob, s_alice, _ = two_users_with_sessions
    db_session.add(AIChatMessage(session_id=s_alice.id, role="user", content="secret plan"))
    db_session.commit()
    svc = ChatService(db_session)

    assert len(svc.get_messages(s_alice.id, user_id=alice.id)) == 1
    assert svc.get_messages(s_alice.id, user_id=bob.id) == []


def test_send_message_scoped_by_user(db_session, two_users_with_sessions):
    alice, bob, s_alice, _ = two_users_with_sessions
    svc = ChatService(db_session)

    with pytest.raises(ValueError):
        svc.send_message(s_alice.id, "inject into alice", user_id=bob.id)
    # Nothing persisted for Bob's attempt.
    assert svc.get_messages(s_alice.id, user_id=alice.id) == []

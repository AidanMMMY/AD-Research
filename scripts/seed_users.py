"""Seed user accounts from legacy hardcoded config into the database.

Run once after creating the users table:

    python scripts/seed_users.py

This will bcrypt-hash the legacy credentials from app.config.auth_settings
and insert them into the database users table.
"""

import bcrypt
from sqlalchemy.orm import Session

from app.config import auth_settings
from app.core.database import SessionLocal, engine
from app.models.user import User


def _hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def seed_users(db: Session) -> None:
    """Insert legacy users as hashed database accounts."""
    existing = {u.username for u in db.query(User.username).all()}

    for username, password in auth_settings.USERS.items():
        if username in existing:
            print(f"[seed] User '{username}' already exists, skipping.")
            continue

        role = "admin" if username == "admin" else "user"
        user = User(
            username=username,
            password_hash=_hash_password(password),
            role=role,
            is_active=True,
        )
        db.add(user)
        print(f"[seed] Created user '{username}' with role '{role}'.")

    db.commit()


def main() -> None:
    # Ensure the users table exists before seeding
    User.metadata.create_all(bind=engine, tables=[User.__table__])

    db = SessionLocal()
    try:
        seed_users(db)
        print("[seed] Done.")
    finally:
        db.close()


if __name__ == "__main__":
    main()

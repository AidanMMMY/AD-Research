"""Seed the initial admin user from environment variables into the database.

Run once after creating the users table:

    python scripts/seed_users.py

The admin username and password are read from the AUTH_ADMIN_USERNAME and
AUTH_ADMIN_PASSWORD environment variables (or .env file). The password is
bcrypt-hashed before being stored.
"""
import sys

import bcrypt
from sqlalchemy.orm import Session

from app.config import auth_settings
from app.core.database import SessionLocal, engine
from app.models.user import User


def _hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def seed_admin(db: Session) -> None:
    """Create the initial admin account if it does not already exist."""
    username = auth_settings.ADMIN_USERNAME
    password = auth_settings.ADMIN_PASSWORD

    if not password:
        print(
            "Error: AUTH_ADMIN_PASSWORD is not set. "
            "Set it in the environment or .env file before seeding.",
            file=sys.stderr,
        )
        sys.exit(1)

    existing = db.query(User).filter(User.username == username).first()
    if existing:
        print(f"[seed] Admin user '{username}' already exists, skipping.")
        return

    user = User(
        username=username,
        password_hash=_hash_password(password),
        role="admin",
        is_active=True,
    )
    db.add(user)
    db.commit()
    print(f"[seed] Created admin user '{username}'.")


def main() -> None:
    # Ensure the users table exists before seeding
    User.metadata.create_all(bind=engine, tables=[User.__table__])

    db = SessionLocal()
    try:
        seed_admin(db)
        print("[seed] Done.")
    finally:
        db.close()


if __name__ == "__main__":
    main()

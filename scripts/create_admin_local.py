#!/usr/bin/env python3
"""Create the initial admin user for local visual regression testing.

Run inside the backend container after migrations:
    docker exec -i ad-research-backend-local python - < scripts/create_admin_local.py

Or from host with the local compose network:
    docker compose -f docker-compose.local.yml exec -T backend python - < scripts/create_admin_local.py
"""
import os
import sys

# Support both container (/app) and host (repo root) execution
sys.path.insert(0, os.environ.get("APP_ROOT", os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.models.user import User
from app.api.v1.auth import _hash_password

DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql+psycopg2://etf:etf_local@postgres:5432/ad_research")
ADMIN_USERNAME = os.environ.get("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "kWZK*Ee*%sMZ3r-5")


def main():
    engine = create_engine(DATABASE_URL)
    Session = sessionmaker(bind=engine)
    with Session() as session:
        existing = session.execute(
            select(User).where(User.username == ADMIN_USERNAME)
        ).scalar_one_or_none()
        if existing:
            print(f"Admin user '{ADMIN_USERNAME}' already exists (id={existing.id}).")
            return

        user = User(
            username=ADMIN_USERNAME,
            password_hash=_hash_password(ADMIN_PASSWORD),
            role="admin",
        )
        session.add(user)
        session.commit()
        print(f"Created admin user '{ADMIN_USERNAME}' (id={user.id}).")


if __name__ == "__main__":
    main()

"""Create a user account in the database.

Examples:

    # Interactive mode (prompts for username/password)
    python scripts/create_user.py

    # Non-interactive mode
    python scripts/create_user.py --username Aidan --password 'secure-pass' --role user

The password is bcrypt-hashed before storage.
"""
import argparse
import getpass
import sys

import bcrypt
from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.models.user import User


def _hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def create_user(db: Session, username: str, password: str, role: str = "user") -> User:
    """Create a new user account.

    Raises:
        ValueError: If the username already exists.
    """
    existing = db.query(User).filter(User.username == username).first()
    if existing:
        raise ValueError(f"User '{username}' already exists.")

    user = User(
        username=username,
        password_hash=_hash_password(password),
        role=role,
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _prompt_username() -> str:
    while True:
        username = input("Username: ").strip()
        if username:
            return username
        print("Username cannot be empty.")


def _prompt_password() -> str:
    while True:
        password = getpass.getpass("Password: ")
        if not password:
            print("Password cannot be empty.")
            continue
        confirm = getpass.getpass("Confirm password: ")
        if password != confirm:
            print("Passwords do not match. Try again.")
            continue
        return password


def main() -> int:
    parser = argparse.ArgumentParser(description="Create a platform user account.")
    parser.add_argument("--username", "-u", help="Login username")
    parser.add_argument("--password", "-p", help="Plaintext password (use interactive mode to avoid shell history)")
    parser.add_argument("--role", "-r", default="user", choices=["admin", "user"], help="User role")
    args = parser.parse_args()

    username = args.username or _prompt_username()
    password = args.password or _prompt_password()

    db = SessionLocal()
    try:
        user = create_user(db, username, password, args.role)
        print(f"Created user '{user.username}' with role '{user.role}'.")
        return 0
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())

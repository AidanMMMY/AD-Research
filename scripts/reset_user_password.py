"""Reset password for one or more users.

Run once when admin / Aidan can't log in and the original password is unknown.
Updates the bcrypt hash in-place without touching other columns.

Usage:
    # Interactive (prompts for passwords)
    python scripts/reset_user_password.py admin Aidan

    # Non-interactive
    python scripts/reset_user_password.py admin Aidan --password 'N3w-passw0rd123'
"""

import argparse
import getpass
import sys
from pathlib import Path

import bcrypt
from sqlalchemy.orm import Session

# Make the project root importable whether we're running from /app
# (Docker) or from the project root on the host.
_THIS_DIR = Path(__file__).resolve().parent
_PROJECT_ROOT = _THIS_DIR.parent  # scripts/.. → repo root
sys.path.insert(0, str(_PROJECT_ROOT))
sys.path.insert(0, "/app")  # Docker convention

from app.core.database import SessionLocal
from app.models.refresh_token import RefreshToken
from app.models.user import User
from app.services.password_policy import validate_password


def _hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def reset_password(db: Session, username: str, password: str) -> bool:
    """Reset password for the given username. Returns True on success.

    Raises:
        ValueError: If the password violates the shared password policy.
    """
    error = validate_password(password)
    if error:
        raise ValueError(error)

    user = db.query(User).filter(User.username == username).first()
    if user is None:
        print(f"  ❌ User '{username}' does not exist. Aborting.")
        return False
    user.password_hash = _hash_password(password)
    user.must_change_password = True
    # Password resets invalidate all long-lived sessions. Existing access
    # tokens keep their pre-existing 15-minute JWT lifetime semantics.
    (
        db.query(RefreshToken)
        .filter(RefreshToken.user_id == user.id, RefreshToken.revoked.is_(False))
        .update({"revoked": True})
    )
    db.add(user)
    db.commit()
    print(f"  ✅ Reset password for '{username}' (role={user.role}, active={user.is_active})")
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description="Reset user passwords in place.")
    parser.add_argument(
        "usernames",
        nargs="+",
        help="One or more usernames whose passwords should be reset.",
    )
    parser.add_argument(
        "--password",
        help="Non-interactive mode: use this password for ALL given users. "
        "If omitted, prompts interactively per user.",
    )
    args = parser.parse_args()

    db = SessionLocal()
    try:
        # Verify all usernames exist before touching anything
        existing = {
            u.username for u in db.query(User).filter(User.username.in_(args.usernames)).all()
        }
        missing = set(args.usernames) - existing
        if missing:
            print(f"❌ These users do not exist: {sorted(missing)}")
            print(f"   Existing users: {sorted(existing)}")
            return 2

        if args.password:
            # Non-interactive: same password for everyone. Reject a weak
            # password before changing any account instead of only warning.
            pw = args.password
            error = validate_password(pw)
            if error:
                print(f"Error: {error}", file=sys.stderr)
                return 1
            for username in args.usernames:
                reset_password(db, username, pw)
        else:
            # Interactive: one prompt per user
            for username in args.usernames:
                while True:
                    pw = getpass.getpass(f"New password for '{username}': ")
                    if not pw:
                        print("  (empty password not allowed; try again)")
                        continue
                    confirm = getpass.getpass(f"Confirm password for '{username}': ")
                    if pw != confirm:
                        print("  ❌ Passwords do not match; try again.")
                        continue
                    error = validate_password(pw)
                    if error:
                        print(f"  {error}")
                        continue
                    break
                reset_password(db, username, pw)

        print("\n[reset] Done.")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())

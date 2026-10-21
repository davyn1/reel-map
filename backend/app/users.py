"""Manage logins. There is no sign-up page; accounts are made here.

    python -m app.users add davy --name "Davy"      # asks for the password (typed, not shown)
    python -m app.users add alex --name "Alex"
    python -m app.users passwd davy                  # change a password; logs out their devices
    python -m app.users list
    python -m app.users remove alex                  # keeps their visits in the database

The first account you add takes over the visit log saved before logins existed (user "me").
"""

import argparse
import getpass
import sys
from datetime import datetime, timezone

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.auth import hash_password
from app.models import User, Visit

LEGACY_USER = "me"  # visits.user before logins existed
MIN_PASSWORD = 8


def add_user(session: Session, username: str, display_name: str, password: str) -> tuple[User, int]:
    """Create an account. Returns (user, visits taken over from the pre-login log)."""
    username = username.strip().lower()
    if not username.replace("_", "").replace("-", "").isalnum():
        raise ValueError("username: letters, numbers, - and _ only")
    if session.scalars(select(User).where(func.lower(User.username) == username)).first():
        raise ValueError(f"{username} already exists")
    if len(password) < MIN_PASSWORD:
        raise ValueError(f"password must be at least {MIN_PASSWORD} characters")
    first = session.scalar(select(func.count(User.id))) == 0
    user = User(username=username, display_name=display_name.strip() or username, password_hash=hash_password(password),
                created_at=datetime.now(timezone.utc).replace(tzinfo=None))
    session.add(user)
    taken = 0
    if first:
        taken = session.execute(update(Visit).where(Visit.user == LEGACY_USER).values(user=username)).rowcount
    session.commit()
    return user, taken


def set_password(session: Session, username: str, password: str) -> None:
    user = session.scalars(select(User).where(func.lower(User.username) == username.lower())).first()
    if user is None:
        raise ValueError(f"no user {username}")
    if len(password) < MIN_PASSWORD:
        raise ValueError(f"password must be at least {MIN_PASSWORD} characters")
    user.password_hash = hash_password(password)
    for s in list(user.sessions):  # changing a password logs out every device
        session.delete(s)
    session.commit()


def _ask_password() -> str:
    first = getpass.getpass("Password: ")
    if getpass.getpass("Again: ") != first:
        raise ValueError("passwords didn't match")
    return first


def main(argv=None) -> int:
    from app.db import SessionLocal, init_db

    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("add")
    a.add_argument("username")
    a.add_argument("--name", default="")
    p = sub.add_parser("passwd")
    p.add_argument("username")
    sub.add_parser("list")
    r = sub.add_parser("remove")
    r.add_argument("username")
    args = parser.parse_args(argv)

    init_db()
    with SessionLocal() as session:
        try:
            if args.cmd == "add":
                user, taken = add_user(session, args.username, args.name, _ask_password())
                print(f"Added {user.username} ({user.display_name}).")
                if taken:
                    print(f"  Took over {taken} visit-log entries saved before logins existed.")
            elif args.cmd == "passwd":
                set_password(session, args.username, _ask_password())
                print(f"Password changed for {args.username}; their devices are logged out.")
            elif args.cmd == "list":
                for u in session.scalars(select(User).order_by(User.id)):
                    print(f"{u.username:16} {u.display_name:20} {len(u.sessions)} device(s) logged in")
            elif args.cmd == "remove":
                user = session.scalars(select(User).where(func.lower(User.username) == args.username.lower())).first()
                if user is None:
                    raise ValueError(f"no user {args.username}")
                session.delete(user)
                session.commit()
                print(f"Removed {args.username}. Their visits stay in the database.")
        except ValueError as e:
            print(f"Error: {e}")
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

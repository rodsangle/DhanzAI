"""Administration commands.

python -m app.cli promote someone@example.com     # make an existing account an administrator
python -m app.cli demote someone@example.com
python -m app.cli set-password someone@example.com  # asks for the new password; signs them out everywhere
python -m app.cli maintenance                       # run the retention clean-up once
"""

from __future__ import annotations

import argparse
import asyncio
import getpass
import sys

from sqlalchemy import select

from app.core.config import get_settings
from app.core.security import hash_password
from app.db.session import make_engine, make_sessionmaker
from app.models import User
from app.services.auth_service import revoke_user_sessions
from app.services.maintenance import run_maintenance


async def _set_role(email: str, role: str) -> int:
    settings = get_settings()
    engine = make_engine(settings.database_url)
    try:
        async with make_sessionmaker(engine)() as db:
            user = await db.scalar(select(User).where(User.email == email.lower()))
            if user is None:
                print(f"No account with email {email}", file=sys.stderr)
                return 1
            user.role = role
            await revoke_user_sessions(db, user.id)  # sign in again to get a token with the new role
            await db.commit()
            print(f"{user.email} is now {role}")
            return 0
    finally:
        await engine.dispose()


async def _set_password(email: str, password: str) -> int:
    settings = get_settings()
    engine = make_engine(settings.database_url)
    try:
        async with make_sessionmaker(engine)() as db:
            user = await db.scalar(select(User).where(User.email == email.lower()))
            if user is None:
                print(f"No account with email {email}", file=sys.stderr)
                return 1
            user.password_hash = hash_password(password)
            await revoke_user_sessions(db, user.id)
            await db.commit()
            print(f"Password changed for {user.email}; all their devices were signed out")
            return 0
    finally:
        await engine.dispose()


async def _maintenance() -> int:
    settings = get_settings()
    engine = make_engine(settings.database_url)
    try:
        print(await run_maintenance(make_sessionmaker(engine), settings))
        return 0
    finally:
        await engine.dispose()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.cli", description="DHANZ AI administration")
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("promote", "demote"):
        p = sub.add_parser(name, help=f"{name} an account")
        p.add_argument("email")
    p = sub.add_parser("set-password", help="set a new password for an account (asks for it)")
    p.add_argument("email")
    sub.add_parser("maintenance", help="run the retention clean-up once")
    args = parser.parse_args(argv)
    if args.command == "maintenance":
        return asyncio.run(_maintenance())
    if args.command == "set-password":
        password = getpass.getpass("New password (at least 10 characters): ")
        if len(password) < 10 or password != getpass.getpass("Repeat it: "):
            print("Passwords too short or not the same; nothing changed.", file=sys.stderr)
            return 2
        return asyncio.run(_set_password(args.email, password))
    return asyncio.run(_set_role(args.email, "admin" if args.command == "promote" else "user"))


if __name__ == "__main__":
    raise SystemExit(main())

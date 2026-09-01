#!/usr/bin/env python3
"""Reset the local admin password from the command line.

The in-app change screen asks for the current password, which is no help to someone who has
forgotten it. This is the way back in: it needs filesystem access to the config volume, which is
the right bar -- anyone with that could edit the database anyway.

    docker exec -it franchisarr python scripts/reset_admin_password.py michael
"""

from __future__ import annotations

import argparse
import getpass
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from sqlmodel import Session, col, select  # noqa: E402

from app.auth.passwords import hash_password  # noqa: E402
from app.auth.sessions import delete_sessions_for_user  # noqa: E402
from app.db import get_engine  # noqa: E402
from app.models import User  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("username", nargs="?", help="Local admin username. Omit to list them.")
    parser.add_argument("--password", help="New password. Omitted means prompt (safer: it stays "
                                           "out of your shell history).")
    args = parser.parse_args(argv)

    with Session(get_engine()) as session:
        accounts = session.exec(
            select(User).where(col(User.local_username).is_not(None))
        ).all()

        if not accounts:
            print("There is no local admin account. Set ADMIN_USERNAME and ADMIN_PASSWORD and "
                  "restart to create one.", file=sys.stderr)
            return 1

        if not args.username:
            print("Local admin account(s):")
            for account in accounts:
                print(f"    {account.local_username}")
            print("\nRe-run with a username to reset that account's password.")
            return 0

        user = next(
            (a for a in accounts if a.local_username == args.username.strip().lower()), None
        )
        if user is None:
            print(f"No local admin called {args.username!r}.", file=sys.stderr)
            return 1

        password = args.password or getpass.getpass("New password: ")
        if len(password) < 8:
            print("Use at least 8 characters.", file=sys.stderr)
            return 1

        user.password_hash = hash_password(password)
        session.add(user)
        session.commit()
        # Whoever knew the old password shouldn't keep a live session.
        delete_sessions_for_user(session, user.id)

    print(f"Password reset for {args.username}. Any signed-in browsers have been signed out.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

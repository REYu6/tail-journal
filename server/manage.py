"""Create a local admin/operator without putting passwords in shell history."""

import argparse
from getpass import getpass
from .db import database, initialize, now, password_hash, uid


def main():
    parser = argparse.ArgumentParser()
    command = parser.add_subparsers(dest="command", required=True).add_parser("create-user")
    command.add_argument("--email", required=True)
    command.add_argument("--role", choices=["admin", "operator", "owner"], required=True)
    command.add_argument("--name")
    args = parser.parse_args()
    password = getpass("Password (at least 12 characters): ")
    if len(password) < 12 or password != getpass("Confirm password: "):
        parser.error("Password is too short or does not match")
    initialize()
    with database(True) as db:
        email = args.email.strip().lower()
        if db.one("SELECT id FROM users WHERE email=?", (email,)):
            parser.error("This email is already registered")
        db.execute(
            "INSERT INTO users VALUES(?,?,?,?,?,?)",
            (uid("user"), email, args.name or args.role, args.role, password_hash(password), now()),
        )
    print("Account created.")


if __name__ == "__main__":
    main()

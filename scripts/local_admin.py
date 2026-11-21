"""Bootstrap one private administrator for the local demo on this machine only."""
import os
import secrets
from pathlib import Path

from server.db import database, initialize, now, password_hash, uid


def main():
    initialize()
    with database(write=True) as db:
        if db.one("SELECT id FROM users WHERE role='admin' LIMIT 1"):
            return
        directory = Path(".runtime")
        directory.mkdir(exist_ok=True, mode=0o700)
        credentials = directory / "initial-admin.txt"
        email = "studio@tailjournal.local"
        if credentials.exists():
            # Preserve the same login after a local database reset.
            with credentials.open(encoding="utf8") as stream:
                email, password = [line.rstrip() for line in stream.readlines()[:2]]
        else:
            password = secrets.token_urlsafe(19)
            fd = os.open(credentials, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, "w", encoding="utf8") as stream:
                stream.write(f"{email}\n{password}\n")
        db.execute("INSERT INTO users VALUES(?,?,?,?,?,?)",
                   (uid("user"), email, "工作室管理员", "admin", password_hash(password), now()))
        print("本机管理账号保存在 .runtime/initial-admin.txt，仅当前系统用户可读。")


if __name__ == "__main__":
    main()

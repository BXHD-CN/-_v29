# -*- coding: utf-8 -*-
"""创建/提升管理员账号。

用法： ./.venv/Scripts/python.exe scripts/create_admin.py --username admin --email admin@example.com --password 'StrongPass!23'
已存在则提升为 admin 并重置密码（需 --reset）。
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import select  # noqa: E402

from app.db import SessionLocal, init_db  # noqa: E402
from app.models import User  # noqa: E402
from app.security import hash_password  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--username", required=True)
    ap.add_argument("--email", required=True)
    ap.add_argument("--password", required=True)
    ap.add_argument("--reset", action="store_true")
    args = ap.parse_args()

    init_db()
    db = SessionLocal()
    try:
        user = db.scalar(select(User).where(User.username == args.username))
        if user is None:
            user = User(username=args.username, email=args.email,
                        password_hash=hash_password(args.password),
                        display_name=args.username, role="admin")
            db.add(user)
            print("created admin:", args.username)
        else:
            user.role = "admin"
            if args.reset:
                user.password_hash = hash_password(args.password)
            print("promoted existing user:", args.username)
        db.commit()
    finally:
        db.close()


if __name__ == "__main__":
    main()

import argparse

from sqlalchemy import select

from .database import SessionLocal
from .models import Role, User
from .security import hash_password


def main():
    parser = argparse.ArgumentParser(description="Boshlang‘ich administrator yarating")
    parser.add_argument("--username", required=True)
    parser.add_argument("--password", required=True)
    parser.add_argument("--full-name", default="Tizim administratori")
    args = parser.parse_args()
    if len(args.password) < 8:
        raise SystemExit("Parol kamida 8 belgidan iborat bo‘lishi kerak")
    with SessionLocal() as db:
        if db.scalar(select(User).where(User.username == args.username)):
            raise SystemExit("Bu login allaqachon mavjud")
        db.add(User(username=args.username, full_name=args.full_name,
                    password_hash=hash_password(args.password), role=Role.administrator))
        db.commit()
    print("Administrator yaratildi")


if __name__ == "__main__":
    main()

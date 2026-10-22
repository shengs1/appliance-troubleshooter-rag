"""Script khoi tao hoac nang quyen tai khoan Quan tri vien (Admin).

Cach su dung:
  python scripts/create_admin.py --username admin --email admin@example.com --password "mat_khau_manh"
Hoac chay tuong tac:
  python scripts/create_admin.py
"""

from __future__ import annotations

import argparse
import getpass
import sys
from pathlib import Path

# Them thu muc goc src vao sys.path neu can
src_path = Path(__file__).resolve().parent.parent / "src"
if str(src_path) not in sys.path:
    sys.path.insert(0, str(src_path))

from rag_chatbot.auth import create_admin_user
from rag_chatbot.database import init_db


def main() -> None:
    # Khoi tao co so du lieu neu chua co
    init_db()

    parser = argparse.ArgumentParser(
        description="Script an toan de tao hoac nang quyen tai khoan Admin cho he thong RAG Chatbot."
    )
    parser.add_argument("--username", "-u", type=str, help="Ten dang nhap cua Admin")
    parser.add_argument("--email", "-e", type=str, help="Email cua Admin (dung de nhan email khoi phuc)")
    parser.add_argument("--password", "-p", type=str, help="Mat khau khoi tao cho Admin")

    args = parser.parse_args()

    username = args.username
    email = args.email
    password = args.password

    # Neu chua nhap qua tham so dong lenh, hoi tuong tac
    if not username:
        try:
            username = input("Nhap ten dang nhap Admin: ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\nDa huy thao tac.")
            sys.exit(1)

    if not email:
        try:
            email = input("Nhap email Admin: ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\nDa huy thao tac.")
            sys.exit(1)

    if not password:
        try:
            password = getpass.getpass("Nhap mat khau Admin: ")
            password_confirm = getpass.getpass("Xac nhan lai mat khau: ")
            if password != password_confirm:
                print("Loi: Mat khau xac nhan khong khop!")
                sys.exit(1)
        except (KeyboardInterrupt, EOFError):
            print("\nDa huy thao tac.")
            sys.exit(1)

    try:
        admin_info = create_admin_user(
            username=username,
            email=email,
            password=password,
        )
        print("--------------------------------------------------")
        print("Tao / Nang quyen Admin thanh cong!")
        print(f"ID:       {admin_info['id']}")
        print(f"Username: {admin_info['username']}")
        print(f"Email:    {admin_info['email']}")
        print(f"Role:     {admin_info['role']}")
        print(f"Status:   {admin_info['status']}")
        print("--------------------------------------------------")
    except ValueError as err:
        print(f"Loi: {err}")
        sys.exit(1)


if __name__ == "__main__":
    main()

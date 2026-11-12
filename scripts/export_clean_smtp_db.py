"""Script xuat co so du lieu SQLite mau chi chua cau hinh SMTP ma hoa (Clean DB Template).

Muc dich:
- Tao ra mot file CSDL SQLite sach (mac dinh: data/chat_history_smtp_template.db).
- Khoi tao day du cau truc tat ca cac bang (users, sessions, conversations, messages, v.v.).
- Sao chep nguyen ven cau hinh Brevo SMTP da ma hoa (AES Fernet) tu CSDL hien tai.
- Tuyet doi KHONG kem bat ky tai khoan nguoi dung, lich su chat, token hay audit log nao.
- Ban co the gui file nay cho ban be/dong nghiep de ho chi can dat ten lai thanh
  data/chat_history.db la co the su dung ngay tinh nang gui email khoi phuc mat khau.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import sqlite3
import sys

# Dam bao import duoc rag_chatbot tu thu muc src
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from rag_chatbot.database import init_db


def export_clean_smtp_db(
    source_db_path: str = "data/chat_history.db",
    output_db_path: str = "data/chat_history_smtp_template.db",
) -> None:
    source_path = Path(source_db_path)
    output_path = Path(output_db_path)

    if not source_path.exists():
        print(f"[LOI] Khong tim thay CSDL goc tai: {source_path}")
        return

    # 1. Doc cac ban ghi cau hinh tu system_settings cua CSDL goc
    src_conn = sqlite3.connect(source_path)
    src_conn.row_factory = sqlite3.Row
    settings = src_conn.execute(
        "SELECT key, value, updated_at FROM system_settings WHERE key IN ('smtp_config', 'smtp_admin_pin', 'smtp_wipe_code');"
    ).fetchall()
    src_conn.close()

    if not settings:
        print("[CANH BAO] CSDL goc chua co cau hinh SMTP trong bang system_settings.")
        return

    # 2. Xoa file dich neu da ton tai de tao file moi hoan toan
    if output_path.exists():
        output_path.unlink()

    # 3. Khoi tao schema day du tren file dich
    init_db(db_path=str(output_path))

    # 4. Chep cac ban ghi SMTP ma hoa vao bang system_settings cua file dich
    dst_conn = sqlite3.connect(output_path)
    with dst_conn:
        for row in settings:
            dst_conn.execute(
                "INSERT OR REPLACE INTO system_settings (key, value, updated_at) VALUES (?, ?, ?);",
                (row["key"], row["value"], row["updated_at"]),
            )
    dst_conn.close()

    print("==================================================================")
    print("  XUAT CSDL MAU SMTP (CLEAN DB TEMPLATE) THANH CONG!")
    print("==================================================================")
    print(f"  * File CSDL mau:  {output_path.resolve()}")
    print(f"  * So ban ghi chep: {len(settings)} (smtp_config & ma PIN ma hoa)")
    print("  * Dữ liệu bảo mật:  0 users, 0 messages, 0 tokens (Hoàn toàn sạch)")
    print("\n[Huong dan su dung]:")
    print(f"  1. Gui file '{output_path.name}' cho nguoi can chia se.")
    print("  2. Nguoi nhan dat file nay vao thu muc 'data/' va doi ten thanh 'chat_history.db'.")
    print("  3. Khoi dong he thong, tinh nang Brevo SMTP se san sang hoat dong ngay!")
    print("==================================================================")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Xuat CSDL mau chi chua cau hinh SMTP ma hoa")
    parser.add_argument(
        "--output",
        "-o",
        type=str,
        default="data/chat_history_smtp_template.db",
        help="Duong dan file CSDL dich can tao (mac dinh: data/chat_history_smtp_template.db)",
    )
    args = parser.parse_args()
    export_clean_smtp_db(output_db_path=args.output)


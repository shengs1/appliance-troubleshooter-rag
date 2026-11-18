"""Script sao chep cau hinh SMTP ma hoa vao CSDL SQLite hien tai ma KHONG lam mat tai khoan cu.

Muc dich:
- Khi ban be hoac thanh vien trong nhom da co tai khoan hoac lich su chat trong data/chat_history.db,
  ho KHONG DUOC ghi de file data/chat_history_smtp_template.db len file cu vi se bi mat het tai khoan.
- Script nay se sao chep an toan chi rieng cac ban ghi cau hinh SMTP ma hoa (AES Fernet)
  tu file template (hoac CSDL mau) vao file chat_history.db hien tai.
- Bao toan nguyen ven 100% tat ca tai khoan nguoi dung, phan quyen admin va lich su hoi thoai!

Cach su dung:
  python scripts/import_smtp_config.py
  hoac:
  python scripts/import_smtp_config.py --source data/chat_history_smtp_template.db --target data/chat_history.db
"""

from __future__ import annotations

import argparse
from pathlib import Path
import sqlite3
import sys

# Dam bao import duoc rag_chatbot tu thu muc src
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from rag_chatbot.database import init_db


def import_smtp_config(
    source_db_path: str = "data/chat_history_smtp_template.db",
    target_db_path: str = "data/chat_history.db",
) -> None:
    source_path = Path(source_db_path)
    target_path = Path(target_db_path)

    if not source_path.exists():
        print(f"[LOI] Khong tim thay file CSDL mau chua SMTP tai: {source_path}")
        print("Vui long kiem tra lai duong dan file.")
        return

    # Dam bao file target da co schema day du (neu file chua ton tai se tu tao)
    init_db(db_path=str(target_path))

    # 1. Doc cac ban ghi cau hinh SMTP tu source
    src_conn = sqlite3.connect(source_path)
    src_conn.row_factory = sqlite3.Row
    settings = src_conn.execute(
        "SELECT key, value, updated_at FROM system_settings WHERE key IN ('smtp_config', 'smtp_admin_pin', 'smtp_wipe_code');"
    ).fetchall()
    src_conn.close()

    if not settings:
        print("[CANH BAO] File nguon khong chua cau hinh SMTP nao trong system_settings.")
        return

    # 2. Nap vao file dich ma khong dung den bang users hay messages
    dst_conn = sqlite3.connect(target_path)
    with dst_conn:
        for row in settings:
            dst_conn.execute(
                "INSERT OR REPLACE INTO system_settings (key, value, updated_at) VALUES (?, ?, ?);",
                (row["key"], row["value"], row["updated_at"]),
            )
    
    # Kiem tra tong so user hien co trong target de xac nhan khong bi mat
    user_count = dst_conn.execute("SELECT COUNT(*) FROM users;").fetchone()[0]
    dst_conn.close()

    print("==================================================================")
    print("  NHAP (IMPORT) CAU HINH SMTP VAO CSDL THANH CONG!")
    print("==================================================================")
    print(f"  * Nguon cau hinh:     {source_path.resolve()}")
    print(f"  * CSDL duoc cap nhat: {target_path.resolve()}")
    print(f"  * So muc SMTP da nap: {len(settings)} (smtp_config, PIN, Wipe code)")
    print(f"  * So tai khoan bao toan: {user_count} tai khoan (HOAN TOAN NGUYEN VEN)")
    print("==================================================================")
    print("[Ket qua]: He thong cua ban da co the gui email khoi phuc mat khau ma khong bi mat bat ky tai khoan hay tin nhan nao!")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Sao chep cau hinh SMTP vao CSDL hien tai ma khong lam mat tai khoan cu."
    )
    parser.add_argument(
        "--source",
        "-s",
        type=str,
        default="data/chat_history_smtp_template.db",
        help="Duong dan file chua cau hinh SMTP mau (mac dinh: data/chat_history_smtp_template.db)",
    )
    parser.add_argument(
        "--target",
        "-t",
        type=str,
        default="data/chat_history.db",
        help="Duong dan file CSDL can nap (mac dinh: data/chat_history.db)",
    )
    args = parser.parse_args()
    import_smtp_config(source_db_path=args.source, target_db_path=args.target)

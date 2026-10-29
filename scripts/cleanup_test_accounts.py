"""Script sao lưu và dọn dẹp các tài khoản test tự sinh trong SQLite.

Chỉ xóa các tài khoản do test suite tạo tự động (api_user_*, hacker_*, adm1_*, v.v.).
Bảo tồn 100% tài khoản thật: admin, Thinh.ng, Sheng, abc123.
"""

from datetime import datetime, timezone
import os
from pathlib import Path
import sqlite3
import sys

if sys.stdout:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

DB_PATH = Path("data/chat_history.db")
BACKUP_DIR = Path("data/backups")
BACKUP_DIR.mkdir(parents=True, exist_ok=True)


def backup_database() -> Path:
    """Tạo bản sao lưu toàn vẹn bằng SQLite Backup API."""
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    backup_path = BACKUP_DIR / f"chat_history_backup_{timestamp}.db"
    
    source = sqlite3.connect(DB_PATH)
    target = sqlite3.connect(backup_path)
    with target:
        source.backup(target)
    target.close()
    source.close()
    return backup_path


def cleanup_test_accounts() -> dict[str, int]:
    """Phân loại và dọn dẹp các tài khoản test trong SQLite."""
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON;")
    cursor = conn.cursor()

    # Đếm số lượng ban đầu
    cursor.execute("SELECT COUNT(*) FROM users;")
    initial_users = cursor.fetchone()[0]

    # Danh sách username tài khoản thật BẮT BUỘC giữ lại
    PROTECTED_USERNAMES = {"admin", "Thinh.ng", "Sheng", "abc123"}

    # Lấy danh sách toàn bộ người dùng
    cursor.execute("SELECT id, username, email FROM users;")
    all_users = cursor.fetchall()

    test_user_ids = []
    kept_users = []

    for uid, username, email in all_users:
        if username in PROTECTED_USERNAMES:
            kept_users.append((username, email))
            continue

        email_str = email or ""
        # Kiểm tra dấu hiệu tài khoản test
        is_test = False
        if any(username.startswith(prefix) for prefix in [
            "api_user_", "user_", "test_", "hacker_", "adm1_", "adm2_",
            "alpha_", "beta_", "scope_tester_", "legacy_user_", "admin_"
        ]):
            is_test = True
        elif any(email_str.endswith(domain) for domain in ["@example.com", "@test.com", "@test.vn"]):
            is_test = True

        if is_test:
            test_user_ids.append(uid)
        else:
            kept_users.append((username, email))

    print(f"Tổng số tài khoản ban đầu: {initial_users}")
    print(f"Số tài khoản test được xác định để dọn: {len(test_user_ids)}")
    print(f"Số tài khoản thật được giữ lại: {len(kept_users)}")

    # Thực hiện xóa an toàn trong transaction
    with conn:
        for uid in test_user_ids:
            # 1. Xóa sessions
            cursor.execute("DELETE FROM sessions WHERE user_id = ?;", (uid,))
            # 2. Xóa password_reset_tokens
            cursor.execute("DELETE FROM password_reset_tokens WHERE user_id = ?;", (uid,))
            # 3. Lấy conversations để xóa messages
            cursor.execute("SELECT id FROM conversations WHERE user_id = ?;", (uid,))
            conv_ids = [r[0] for r in cursor.fetchall()]
            for cid in conv_ids:
                cursor.execute("DELETE FROM messages WHERE conversation_id = ?;", (cid,))
            cursor.execute("DELETE FROM conversations WHERE user_id = ?;", (uid,))
            # 4. Xóa user
            cursor.execute("DELETE FROM users WHERE id = ?;", (uid,))

    cursor.execute("SELECT COUNT(*) FROM users;")
    final_users = cursor.fetchone()[0]
    conn.close()

    return {
        "initial": initial_users,
        "deleted": len(test_user_ids),
        "remaining": final_users,
    }


if __name__ == "__main__":
    if not DB_PATH.exists():
        print(f"Không tìm thấy file CSDL tại {DB_PATH}")
        exit(1)

    print("--- 1. BẮT ĐẦU SAO LƯU CSDL ---")
    backup_file = backup_database()
    print(f"Đã sao lưu an toàn CSDL tới: {backup_file}")

    print("\n--- 2. BẮT ĐẦU DỌN DẸP TÀI KHOẢN TEST ---")
    result = cleanup_test_accounts()
    print("\n--- KẾT QUẢ DỌN DẸP ---")
    print(f"Trước khi dọn: {result['initial']} tài khoản")
    print(f"Đã xóa thành công: {result['deleted']} tài khoản test")
    print(f"Còn lại: {result['remaining']} tài khoản thật và quản trị viên")

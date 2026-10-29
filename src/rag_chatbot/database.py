"""Module quan ly co so du lieu SQLite cho nguoi dung va lich su hoi thoai.

Thiet ke toi gian, de hieu phu hop cho bao cao mon hoc / do an:
1. users: luu tru tai khoan nguoi dung va mat khau da hash.
2. sessions: luu tru phien dang nhap voi token da hash (bao mat server-side).
3. conversations: luu tru cac cuoc tro chuyen cua nguoi dung.
4. messages: luu tru tung tin nhan (user va assistant) theo thu tu thoi gian.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import math
from pathlib import Path
import secrets
import sqlite3
from typing import Any
import uuid

from rag_chatbot.config import get_settings


def get_db_path(custom_path: str | None = None) -> str:
    """Lay duong dan file CSDL SQLite tu cau hinh hoac tham so truyen vao."""
    if custom_path:
        return custom_path
    settings = get_settings()
    return getattr(settings, "sqlite_db_path", "data/chat_history.db")


def get_db_connection(db_path: str | None = None) -> sqlite3.Connection:
    """Tao ket noi toi SQLite voi row_factory de tra ve dictionary-like rows va bat foreign keys."""
    path = get_db_path(db_path)
    parent_dir = Path(path).parent
    if parent_dir and not parent_dir.exists():
        parent_dir.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


def init_db(db_path: str | None = None) -> None:
    """Khoi tao cac bang va chi muc trong SQLite neu chua ton tai."""
    with get_db_connection(db_path) as conn:
        cursor = conn.cursor()

        # 1. Bang users (ho tro email, role, status va last_login_at)
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id TEXT PRIMARY KEY,
                username TEXT UNIQUE NOT NULL,
                email TEXT UNIQUE,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT 'user',
                status TEXT NOT NULL DEFAULT 'active',
                created_at TEXT NOT NULL,
                last_login_at TEXT
            );
            """
        )

        # Tu dong cap nhat cac cot neu CSDL da khoi tao tu truoc chua co
        user_cols = [col["name"] for col in cursor.execute("PRAGMA table_info(users);").fetchall()]
        if "email" not in user_cols:
            cursor.execute("ALTER TABLE users ADD COLUMN email TEXT;")
            cursor.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_users_email ON users (email);")
        if "role" not in user_cols:
            cursor.execute("ALTER TABLE users ADD COLUMN role TEXT NOT NULL DEFAULT 'user';")
        if "status" not in user_cols:
            cursor.execute("ALTER TABLE users ADD COLUMN status TEXT NOT NULL DEFAULT 'active';")
        if "last_login_at" not in user_cols:
            cursor.execute("ALTER TABLE users ADD COLUMN last_login_at TEXT;")

        # 2. Bang sessions
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS sessions (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                token_hash TEXT UNIQUE NOT NULL,
                created_at TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
            );
            """
        )

        # 3. Bang conversations
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS conversations (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                title TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
            );
            """
        )

        # 4. Bang messages
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS messages (
                id TEXT PRIMARY KEY,
                conversation_id TEXT NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY (conversation_id) REFERENCES conversations (id) ON DELETE CASCADE
            );
            """
        )

        # 5. Bang password_reset_tokens (luu token khoi phuc mat khau da hash SHA-256)
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS password_reset_tokens (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                token_hash TEXT UNIQUE NOT NULL,
                created_at TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                used_at TEXT,
                FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
            );
            """
        )

        # 6. Bang password_reset_rate_limits (gioi han tan suat gui yeu cau theo email/IP)
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS password_reset_rate_limits (
                id TEXT PRIMARY KEY,
                rate_key TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            """
        )

        # 7. Bang admin_audit_logs (nhat ky kiem toan cac thao tac quan tri)
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS admin_audit_logs (
                id TEXT PRIMARY KEY,
                admin_id TEXT NOT NULL,
                action TEXT NOT NULL,
                target_user_id TEXT NOT NULL,
                details TEXT,
                created_at TEXT NOT NULL,
                FOREIGN KEY (admin_id) REFERENCES users (id) ON DELETE CASCADE
            );
            """
        )

        # Tao chi muc de toi uu toc do tim kiem
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_sessions_token_hash ON sessions (token_hash);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_conversations_user_id ON conversations (user_id);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_messages_conversation_id ON messages (conversation_id);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_reset_token_hash ON password_reset_tokens (token_hash);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_reset_user_id ON password_reset_tokens (user_id);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_rate_limits_key ON password_reset_rate_limits (rate_key, created_at);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_audit_created_at ON admin_audit_logs (created_at);")
        conn.commit()


def create_conversation(user_id: str, title: str, db_path: str | None = None) -> dict[str, Any]:
    """Tao mot cuoc tro chuyen moi cho nguoi dung."""
    conv_id = str(uuid.uuid4())
    now_str = datetime.now(timezone.utc).isoformat()
    clean_title = title.strip() or "Cuộc trò chuyện mới"

    with get_db_connection(db_path) as conn:
        conn.execute(
            """
            INSERT INTO conversations (id, user_id, title, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?);
            """,
            (conv_id, user_id, clean_title, now_str, now_str),
        )
        conn.commit()

    return {
        "id": conv_id,
        "user_id": user_id,
        "title": clean_title,
        "created_at": now_str,
        "updated_at": now_str,
    }


def get_user_conversations(user_id: str, db_path: str | None = None) -> list[dict[str, Any]]:
    """Lay danh sach cuoc tro chuyen cua mot nguoi dung, sap xep theo thoi gian cap nhat moi nhat."""
    with get_db_connection(db_path) as conn:
        rows = conn.execute(
            """
            SELECT id, user_id, title, created_at, updated_at
            FROM conversations
            WHERE user_id = ?
            ORDER BY updated_at DESC;
            """,
            (user_id,),
        ).fetchall()
        return [dict(row) for row in rows]


def get_conversation_by_id(conversation_id: str, user_id: str | None = None, db_path: str | None = None) -> dict[str, Any] | None:
    """Lay thong tin cuoc tro chuyen neu no thuoc ve user_id chi dinh (hoac theo id neu khong truyen user_id)."""
    with get_db_connection(db_path) as conn:
        if user_id:
            row = conn.execute(
                """
                SELECT id, user_id, title, created_at, updated_at
                FROM conversations
                WHERE id = ? AND user_id = ?;
                """,
                (conversation_id, user_id),
            ).fetchone()
        else:
            row = conn.execute(
                """
                SELECT id, user_id, title, created_at, updated_at
                FROM conversations
                WHERE id = ?;
                """,
                (conversation_id,),
            ).fetchone()
        return dict(row) if row else None


def get_conversation_messages(conversation_id: str, db_path: str | None = None) -> list[dict[str, Any]]:
    """Lay toan bo tin nhan cua mot cuoc tro chuyen theo thu tu thoi gian tao tang dan."""
    with get_db_connection(db_path) as conn:
        rows = conn.execute(
            """
            SELECT id, conversation_id, role, content, created_at
            FROM messages
            WHERE conversation_id = ?
            ORDER BY created_at ASC;
            """,
            (conversation_id,),
        ).fetchall()
        return [dict(row) for row in rows]


def save_chat_turn(
    user_id: str,
    question: str,
    answer: str,
    conversation_id: str | None = None,
    db_path: str | None = None,
) -> dict[str, Any]:
    """Luu ca tin nhan user va cau tra loi assistant trong cung mot transaction.
    
    Neu conversation_id chua ton tai: tao cuoc tro chuyen moi voi tieu de tu cau hoi dau tien.
    Neu conversation_id da ton tai: kiem tra quyen so huu truoc khi luu.
    """
    now_str = datetime.now(timezone.utc).isoformat()
    with get_db_connection(db_path) as conn:
        cursor = conn.cursor()

        if conversation_id:
            # Kiem tra quyen so huu cuoc tro chuyen
            row = cursor.execute(
                "SELECT id, title FROM conversations WHERE id = ? AND user_id = ?;",
                (conversation_id, user_id),
            ).fetchone()
            if not row:
                raise ValueError("Cuộc trò chuyện không tồn tại hoặc không thuộc sở hữu của bạn.")
            active_conv_id = conversation_id
            title = row["title"]
            # Cap nhat thoi gian cap nhat
            cursor.execute(
                "UPDATE conversations SET updated_at = ? WHERE id = ?;",
                (now_str, active_conv_id),
            )
        else:
            # Tao cuoc tro chuyen moi voi tieu de cat ngan tu cau hoi
            active_conv_id = str(uuid.uuid4())
            title = question.strip()[:60] or "Cuộc trò chuyện mới"
            cursor.execute(
                """
                INSERT INTO conversations (id, user_id, title, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?);
                """,
                (active_conv_id, user_id, title, now_str, now_str),
            )

        # 1. Luu tin nhan nguoi dung
        user_msg_id = str(uuid.uuid4())
        cursor.execute(
            """
            INSERT INTO messages (id, conversation_id, role, content, created_at)
            VALUES (?, ?, 'user', ?, ?);
            """,
            (user_msg_id, active_conv_id, question, now_str),
        )

        # 2. Luu tin nhan bot tra loi
        bot_msg_id = str(uuid.uuid4())
        # Đảm bảo mốc thời gian của assistant đến sau để duy trì thứ tự ổn định
        now_bot_str = datetime.now(timezone.utc).isoformat()
        cursor.execute(
            """
            INSERT INTO messages (id, conversation_id, role, content, created_at)
            VALUES (?, ?, 'assistant', ?, ?);
            """,
            (bot_msg_id, active_conv_id, answer, now_bot_str),
        )

        conn.commit()

    return {
        "conversation_id": active_conv_id,
        "title": title,
        "user_message_id": user_msg_id,
        "bot_message_id": bot_msg_id,
    }


def delete_conversation(conversation_id: str, user_id: str, db_path: str | None = None) -> bool:
    """Xoa cuoc tro chuyen va cac tin nhan lien quan neu thuoc ve user_id."""
    with get_db_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(
            "DELETE FROM conversations WHERE id = ? AND user_id = ?;",
            (conversation_id, user_id),
        )
        conn.commit()
        return cursor.rowcount > 0


# ==============================================================
# Cac thao tac quan ly Khoi phuc mat khau & Gioi han tan suat
# ==============================================================

def get_user_by_email(email: str, db_path: str | None = None) -> dict[str, Any] | None:
    """Tim kiem nguoi dung dua vao dia chi email (khong phan biet hoa thuong)."""
    clean_email = email.strip()
    if not clean_email:
        return None
    with get_db_connection(db_path) as conn:
        row = conn.execute(
            """
            SELECT id, username, email, password_hash, created_at
            FROM users
            WHERE LOWER(email) = LOWER(?);
            """,
            (clean_email,),
        ).fetchone()
        return dict(row) if row else None


def check_rate_limit_cooldown(
    rate_key: str,
    cooldown_seconds: int = 15,
    db_path: str | None = None,
) -> tuple[bool, int]:
    """Kiem tra khoang cach thoi gian toi thieu (cooldown) giua cac lan gui yeu cau.
    
    Tra ve (True, 0) neu da du thoi gian gian cach.
    Tra ve (False, remaining_seconds) neu gui qua nhanh (chua du cooldown_seconds).
    """
    now = datetime.now(timezone.utc)
    with get_db_connection(db_path) as conn:
        row = conn.execute(
            """
            SELECT created_at
            FROM password_reset_rate_limits
            WHERE rate_key = ?
            ORDER BY created_at DESC
            LIMIT 1;
            """,
            (rate_key,),
        ).fetchone()

        if row:
            last_time = datetime.fromisoformat(row["created_at"])
            elapsed = (now - last_time).total_seconds()
            if elapsed < cooldown_seconds:
                remaining = int(math.ceil(cooldown_seconds - elapsed))
                return False, max(1, remaining)

        return True, 0


def check_and_record_rate_limit(
    rate_key: str,
    max_requests: int = 3,
    window_minutes: int = 15,
    db_path: str | None = None,
) -> bool:
    """Kiem tra va ghi nhan gioi han tan suat (Rate Limiting).
    
    Tra ve True neu yeu cau duoc chap thuan.
    Tra ve False neu vuot qua so luong yeu cau toi da trong khung thoi gian.
    """
    now = datetime.now(timezone.utc)
    cutoff = (now - timedelta(minutes=window_minutes)).isoformat()
    now_str = now.isoformat()

    with get_db_connection(db_path) as conn:
        cursor = conn.cursor()
        row = cursor.execute(
            """
            SELECT COUNT(*) AS req_count
            FROM password_reset_rate_limits
            WHERE rate_key = ? AND created_at > ?;
            """,
            (rate_key, cutoff),
        ).fetchone()

        count = row["req_count"] if row else 0
        if count >= max_requests:
            return False

        # Ghi nhan yeu cau moi
        cursor.execute(
            """
            INSERT INTO password_reset_rate_limits (id, rate_key, created_at)
            VALUES (?, ?, ?);
            """,
            (str(uuid.uuid4()), rate_key, now_str),
        )
        conn.commit()
        return True


def create_password_reset_token(user_id: str, db_path: str | None = None) -> tuple[str, str]:
    """Tao token khoi phuc mat khau an toan, luu hash SHA-256 vao CSDL va tra ve token tho cung han su dung."""
    settings = get_settings()
    expire_minutes = getattr(settings, "password_reset_expire_minutes", 15)

    raw_token = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
    token_id = str(uuid.uuid4())

    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(minutes=expire_minutes)

    now_str = now.isoformat()
    expires_str = expires_at.isoformat()

    with get_db_connection(db_path) as conn:
        conn.execute(
            """
            INSERT INTO password_reset_tokens (id, user_id, token_hash, created_at, expires_at, used_at)
            VALUES (?, ?, ?, ?, ?, NULL);
            """,
            (token_id, user_id, token_hash, now_str, expires_str),
        )
        conn.commit()

    return raw_token, expires_str


def get_valid_password_reset_token(raw_token: str, db_path: str | None = None) -> dict[str, Any] | None:
    """Xac thuc token khoi phuc mat khau.
    
    Yeu cau bat buoc:
    - Token phai ton tai.
    - Token chua tung duoc su dung (used_at IS NULL).
    - Token chua het han (now <= expires_at).
    """
    if not raw_token:
        return None

    token_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
    with get_db_connection(db_path) as conn:
        row = conn.execute(
            """
            SELECT id, user_id, token_hash, created_at, expires_at, used_at
            FROM password_reset_tokens
            WHERE token_hash = ?;
            """,
            (token_hash,),
        ).fetchone()

        if not row:
            return None

        # Kiem tra da su dung chua
        if row["used_at"] is not None:
            return None

        # Kiem tra thoi han
        expires_at = datetime.fromisoformat(row["expires_at"])
        if datetime.now(timezone.utc) > expires_at:
            return None

        return dict(row)


def update_user_password(
    user_id: str,
    new_password_hash: str,
    reset_token_id: str | None = None,
    db_path: str | None = None,
) -> None:
    """Cap nhat mat khau moi cho nguoi dung trong transaction nguyen tu.
    
    Dong thoi:
    1. Danh dau token khoi phuc da duoc su dung (used_at).
    2. Thu hoi (xoa) toan bo session dang hoat dong cua nguoi dung de ngan chan ke xam nhap.
    """
    now_str = datetime.now(timezone.utc).isoformat()
    with get_db_connection(db_path) as conn:
        cursor = conn.cursor()

        # 1. Cap nhat mat khau moi
        cursor.execute(
            "UPDATE users SET password_hash = ? WHERE id = ?;",
            (new_password_hash, user_id),
        )

        # 2. Danh dau token khoi phuc da su dung
        if reset_token_id:
            cursor.execute(
                "UPDATE password_reset_tokens SET used_at = ? WHERE id = ?;",
                (now_str, reset_token_id),
            )

        # 3. Thu hoi toan bo phien dang nhap hien co cua user de bao ve tai khoan
        cursor.execute(
            "DELETE FROM sessions WHERE user_id = ?;",
            (user_id,),
        )

        conn.commit()


def revoke_all_user_sessions(user_id: str, db_path: str | None = None) -> None:
    """Huy toan bo phien dang nhap cua mot user."""
    with get_db_connection(db_path) as conn:
        conn.execute("DELETE FROM sessions WHERE user_id = ?;", (user_id,))
        conn.commit()


# ==============================================================
# Cac thao tac Quan tri tai khoan (Admin Operations)
# ==============================================================

def record_admin_audit_log(
    admin_id: str,
    action: str,
    target_user_id: str,
    details: str | None = None,
    db_path: str | None = None,
) -> None:
    """Ghi log kiem toan toi thieu cho cac thao tac quan tri (khong ghi mat khau/token)."""
    log_id = str(uuid.uuid4())
    now_str = datetime.now(timezone.utc).isoformat()
    with get_db_connection(db_path) as conn:
        conn.execute(
            """
            INSERT INTO admin_audit_logs (id, admin_id, action, target_user_id, details, created_at)
            VALUES (?, ?, ?, ?, ?, ?);
            """,
            (log_id, admin_id, action, target_user_id, details, now_str),
        )
        conn.commit()


def get_admin_stats(db_path: str | None = None) -> dict[str, int]:
    """Lay so lieu tong quan ve tai khoan cho trang Admin Dashboard."""
    with get_db_connection(db_path) as conn:
        row = conn.execute(
            """
            SELECT 
                COUNT(*) AS total_users,
                COALESCE(SUM(CASE WHEN status = 'active' THEN 1 ELSE 0 END), 0) AS active_users,
                COALESCE(SUM(CASE WHEN status = 'locked' THEN 1 ELSE 0 END), 0) AS locked_users
            FROM users;
            """
        ).fetchone()

        conv_row = conn.execute("SELECT COUNT(*) AS total_conversations FROM conversations;").fetchone()

        return {
            "total_users": int(row["total_users"]) if row else 0,
            "active_users": int(row["active_users"]) if row else 0,
            "locked_users": int(row["locked_users"]) if row else 0,
            "total_conversations": int(conv_row["total_conversations"]) if conv_row else 0,
        }


def get_user_by_id(user_id: str, db_path: str | None = None) -> dict[str, Any] | None:
    """Lay thong tin co ban mot user theo id (khong chua password_hash)."""
    with get_db_connection(db_path) as conn:
        row = conn.execute(
            """
            SELECT id, username, email, role, status, created_at, last_login_at
            FROM users
            WHERE id = ?;
            """,
            (user_id,),
        ).fetchone()
        return dict(row) if row else None


def get_user_by_username(username: str, db_path: str | None = None) -> dict[str, Any] | None:
    """Tim kiem nguoi dung dua vao username (khong phan biet hoa thuong)."""
    clean_u = (username or "").strip()
    if not clean_u:
        return None
    with get_db_connection(db_path) as conn:
        row = conn.execute(
            """
            SELECT id, username, email, password_hash, role, status, created_at, last_login_at
            FROM users
            WHERE LOWER(username) = LOWER(?);
            """,
            (clean_u,),
        ).fetchone()
        return dict(row) if row else None


def count_active_admins(db_path: str | None = None) -> int:
    """Dem so luong Admin dang o trang thai active."""
    with get_db_connection(db_path) as conn:
        row = conn.execute(
            "SELECT COUNT(*) AS admin_count FROM users WHERE role = 'admin' AND status = 'active';"
        ).fetchone()
        return int(row["admin_count"]) if row else 0


def get_admin_users(
    search: str | None = None,
    page: int = 1,
    page_size: int = 10,
    db_path: str | None = None,
) -> tuple[list[dict[str, Any]], int]:
    """Lay danh sach tai khoan ho tro tim kiem va phan trang (khong tra password_hash)."""
    p = max(1, page)
    ps = max(1, min(page_size, 100))
    offset = (p - 1) * ps

    clean_search = (search or "").strip().lower()

    with get_db_connection(db_path) as conn:
        if clean_search:
            like_term = f"%{clean_search}%"
            count_row = conn.execute(
                """
                SELECT COUNT(*) FROM users
                WHERE LOWER(username) LIKE ? OR LOWER(email) LIKE ?;
                """,
                (like_term, like_term),
            ).fetchone()
            total = int(count_row[0]) if count_row else 0

            rows = conn.execute(
                """
                SELECT id, username, email, role, status, created_at, last_login_at
                FROM users
                WHERE LOWER(username) LIKE ? OR LOWER(email) LIKE ?
                ORDER BY created_at DESC
                LIMIT ? OFFSET ?;
                """,
                (like_term, like_term, ps, offset),
            ).fetchall()
        else:
            count_row = conn.execute("SELECT COUNT(*) FROM users;").fetchone()
            total = int(count_row[0]) if count_row else 0

            rows = conn.execute(
                """
                SELECT id, username, email, role, status, created_at, last_login_at
                FROM users
                ORDER BY created_at DESC
                LIMIT ? OFFSET ?;
                """,
                (ps, offset),
            ).fetchall()

        return [dict(r) for r in rows], total


def update_user_status(
    target_user_id: str,
    new_status: str,
    admin_id: str,
    db_path: str | None = None,
) -> dict[str, Any]:
    """Khoa hoac mo khoa tai khoan nguoi dung.
    
    Bao ve he thong:
    - Khong cho phep Admin tu khoa chinh minh.
    - Khong cho phep khoa Admin cuoi cung con hoat dong.
    - Neu khoa tai khoan, thu hoi ngay lap tuc tat ca phien dang hoat dong.
    """
    if new_status not in ("active", "locked"):
        raise ValueError("Trạng thái không hợp lệ. Chỉ chấp nhận 'active' hoặc 'locked'.")

    target_user = get_user_by_id(target_user_id, db_path=db_path)
    if not target_user:
        raise ValueError("Không tìm thấy người dùng.")

    # 1. Khong cho Admin tu khoa chinh minh
    if target_user_id == admin_id and new_status == "locked":
        raise ValueError("Không thể tự khóa tài khoản của chính mình.")

    # 2. Khong cho khoa Admin cuoi cung con active
    if new_status == "locked" and target_user.get("role") == "admin":
        if count_active_admins(db_path=db_path) <= 1:
            raise ValueError("Không thể khóa Quản trị viên (Admin) duy nhất còn hoạt động.")

    with get_db_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE users SET status = ? WHERE id = ?;",
            (new_status, target_user_id),
        )

        # 3. Neu khoa tai khoan, lap tuc huy toan bo phien cua user nay
        if new_status == "locked":
            cursor.execute("DELETE FROM sessions WHERE user_id = ?;", (target_user_id,))

        conn.commit()

    record_admin_audit_log(
        admin_id=admin_id,
        action=f"status_change:{new_status}",
        target_user_id=target_user_id,
        details=f"Trạng thái thay đổi từ '{target_user.get('status')}' thành '{new_status}'",
        db_path=db_path,
    )

    return get_user_by_id(target_user_id, db_path=db_path)  # type: ignore[return-value]


def update_user_role(
    target_user_id: str,
    new_role: str,
    admin_id: str,
    db_path: str | None = None,
) -> dict[str, Any]:
    """Thay doi vai tro nguoi dung (user <-> admin).
    
    Bao ve he thong:
    - Khong cho phep Admin tu ha quyen cua chinh minh.
    - Khong cho phep ha quyen Admin cuoi cung con hoat dong.
    """
    if new_role not in ("user", "admin"):
        raise ValueError("Vai trò không hợp lệ. Chỉ chấp nhận 'user' hoặc 'admin'.")

    target_user = get_user_by_id(target_user_id, db_path=db_path)
    if not target_user:
        raise ValueError("Không tìm thấy người dùng.")

    # 1. Khong cho Admin tu ha quyen chinh minh
    if target_user_id == admin_id and new_role != "admin":
        raise ValueError("Không thể tự hạ quyền của chính mình.")

    # 2. Khong cho ha quyen Admin cuoi cung con active
    if target_user.get("role") == "admin" and new_role != "admin":
        if count_active_admins(db_path=db_path) <= 1:
            raise ValueError("Không thể hạ quyền Quản trị viên (Admin) duy nhất còn hoạt động.")

    with get_db_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE users SET role = ? WHERE id = ?;",
            (new_role, target_user_id),
        )
        conn.commit()

    record_admin_audit_log(
        admin_id=admin_id,
        action=f"role_change:{new_role}",
        target_user_id=target_user_id,
        details=f"Vai trò thay đổi từ '{target_user.get('role')}' thành '{new_role}'",
        db_path=db_path,
    )

    return get_user_by_id(target_user_id, db_path=db_path)  # type: ignore[return-value]


def delete_user_permanently(
    target_user_id: str,
    admin_id: str,
    admin_password: str | None = None,
    db_path: str | None = None,
) -> dict[str, Any]:
    """Xóa vĩnh viễn tài khoản người dùng và toàn bộ dữ liệu liên quan (hard delete).
    
    Quy tắc an toàn:
    - Không cho phép Admin tự xóa tài khoản của chính mình.
    - Không cho phép xóa Admin cuối cùng còn hoạt động trong hệ thống.
    - Khi xóa tài khoản Quản trị viên (Admin), bắt buộc phải có mật khẩu xác thực an toàn (123456789).
    - Thực hiện trong một SQLite transaction: xóa sessions, tokens, messages, conversations, và user.
    - Ghi nhận audit log sau khi xóa.
    """
    target_user = get_user_by_id(target_user_id, db_path=db_path)
    if not target_user:
        raise ValueError("Không tìm thấy người dùng.")

    if target_user_id == admin_id:
        raise ValueError("Không thể tự xóa tài khoản của chính mình.")

    if target_user.get("role") == "admin":
        if target_user.get("status") == "active" and count_active_admins(db_path=db_path) <= 1:
            raise ValueError("Không thể xóa Quản trị viên (Admin) duy nhất còn hoạt động.")

        # Yeu cau xac thuc mat khau an toan khi xoa tai khoan Admin
        if admin_password != "123456789":
            raise ValueError("Để xóa tài khoản Quản trị viên (Admin), bạn phải nhập chính xác mật khẩu xác thực bảo mật (123456789).")

    target_username = target_user.get("username", "unknown")
    target_email = target_user.get("email", "")

    with get_db_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM sessions WHERE user_id = ?;", (target_user_id,))
        cursor.execute("DELETE FROM password_reset_tokens WHERE user_id = ?;", (target_user_id,))
        
        cursor.execute("SELECT id FROM conversations WHERE user_id = ?;", (target_user_id,))
        conv_ids = [row[0] for row in cursor.fetchall()]
        for cid in conv_ids:
            cursor.execute("DELETE FROM messages WHERE conversation_id = ?;", (cid,))
        cursor.execute("DELETE FROM conversations WHERE user_id = ?;", (target_user_id,))
        cursor.execute("DELETE FROM users WHERE id = ?;", (target_user_id,))
        conn.commit()

    record_admin_audit_log(
        admin_id=admin_id,
        action="admin_delete_user",
        target_user_id=target_user_id,
        details=f"Xóa vĩnh viễn tài khoản '{target_username}' ({target_email})",
        db_path=db_path,
    )

    return {"message": f"Tài khoản '{target_username}' đã được xóa vĩnh viễn thành công."}


def update_last_login(user_id: str, db_path: str | None = None) -> None:
    """Cap nhat moc thoi gian dang nhap gan nhat."""
    now_str = datetime.now(timezone.utc).isoformat()
    with get_db_connection(db_path) as conn:
        conn.execute(
            "UPDATE users SET last_login_at = ? WHERE id = ?;",
            (now_str, user_id),
        )
        conn.commit()


def get_admin_audit_logs(limit: int = 20, db_path: str | None = None) -> list[dict[str, Any]]:
    """Lay danh sach nhat ky kiem toan cac thao tac quan tri gan nhat."""
    with get_db_connection(db_path) as conn:
        cursor = conn.cursor()
        rows = cursor.execute(
            """
            SELECT l.id, l.admin_id, u.username AS admin_username, l.action, l.target_user_id, l.details, l.created_at
            FROM admin_audit_logs l
            LEFT JOIN users u ON l.admin_id = u.id
            ORDER BY l.created_at DESC
            LIMIT ?;
            """,
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]




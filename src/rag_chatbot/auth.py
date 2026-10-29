"""Module quan ly xac thuc, mat khau va phien lam viec (Authentication & Session Management).

Tuan thu cac nguyen tac:
1. Mat khau duoc hash bang bcrypt voi salt an toan, khong bao gio luu hoac tra ve plaintext.
2. Phien dang nhap duoc quan ly qua bang sessions trong SQLite; chi luu token da hash bang SHA-256.
3. Cookie HttpOnly, SameSite=Lax, tu dong bat Secure khi HTTPS.
4. Cung cap FastAPI dependency ro rang de bao ve endpoint.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import re
import secrets
from typing import Any
import uuid

import bcrypt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError
from fastapi import Depends, Header, HTTPException, Request, status

from rag_chatbot.config import get_settings
from rag_chatbot.database import (
    check_and_record_rate_limit,
    check_rate_limit_cooldown,
    create_password_reset_token,
    get_db_connection,
    get_user_by_email,
    get_valid_password_reset_token,
    update_user_password,
)
from rag_chatbot.email_service import build_reset_password_url, send_password_reset_email


SESSION_COOKIE_NAME = "session_token"

_argon2_hasher = PasswordHasher()


def hash_password(password: str) -> str:
    """Hash mat khau su dung Argon2id (chuan bao mat cao nhat cho authentication)."""
    return _argon2_hasher.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Kiem tra mat khau, ho tro Argon2id va tuong thich nguoc voi bcrypt / SHA-256."""
    if not hashed_password or not plain_password:
        return False

    # 1. Kiem tra Argon2id
    if hashed_password.startswith("$argon2"):
        try:
            return _argon2_hasher.verify(hashed_password, plain_password)
        except (VerifyMismatchError, InvalidHashError):
            return False
        except Exception:
            return False

    # 2. Ho tro legacy bcrypt ($2a$, $2b$, $2y$)
    if hashed_password.startswith(("$2a$", "$2b$", "$2y$")):
        try:
            return bcrypt.checkpw(
                plain_password.encode("utf-8"),
                hashed_password.encode("utf-8"),
            )
        except Exception:
            return False

    # 3. Ho tro legacy SHA-256 dang salt$hash hoac hex
    try:
        if "$" in hashed_password:
            salt, hash_val = hashed_password.split("$", 1)
            computed = hashlib.sha256((salt + plain_password).encode("utf-8")).hexdigest()
            return secrets.compare_digest(computed, hash_val)
    except Exception:
        pass

    return False


def needs_rehash(hashed_password: str) -> bool:
    """Kiem tra xem chuoi hash co can duoc rehash sang Argon2id khong."""
    if not hashed_password.startswith("$argon2"):
        return True
    try:
        return _argon2_hasher.check_needs_rehash(hashed_password)
    except Exception:
        return False


def generate_session_token() -> str:
    """Sinh chuoi token phien ngau nhien co do dai an toan 32 bytes."""
    return secrets.token_urlsafe(32)


def hash_session_token(token: str) -> str:
    """Hash token phien bang SHA-256 de luu vao CSDL (tranh lo token tho neu CSDL bi ro ri)."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def register_user(
    username: str,
    password: str,
    email: str | None = None,
    db_path: str | None = None,
) -> dict[str, Any]:
    """Dang ky tai khoan nguoi dung moi.
    
    Kiem tra:
    - Ten dang nhap toi thieu 3 ky tu.
    - Mat khau toi thieu 6 ky tu.
    - Khong cho phep trung username hoac email.
    """
    clean_username = username.strip()
    if len(clean_username) < 3:
        raise ValueError("Tên đăng nhập phải có ít nhất 3 ký tự.")
    if len(password) < 6:
        raise ValueError("Mật khẩu phải có ít nhất 6 ký tự.")

    # Xu ly va validate email neu duoc truyen vao, hoac tao email fallback hop le
    clean_email = email.strip() if email else f"{clean_username}@example.com"
    email_regex = r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$"
    if not re.match(email_regex, clean_email):
        raise ValueError("Địa chỉ email không đúng định dạng.")

    user_id = str(uuid.uuid4())
    password_hash = hash_password(password)
    created_at = datetime.now(timezone.utc).isoformat()

    with get_db_connection(db_path) as conn:
        cursor = conn.cursor()
        existing = cursor.execute(
            "SELECT id FROM users WHERE LOWER(username) = LOWER(?);",
            (clean_username,),
        ).fetchone()
        if existing:
            raise ValueError(f"Tên đăng nhập hoặc email '{clean_username}' đã tồn tại.")

        if email:
            existing_email = cursor.execute(
                "SELECT id FROM users WHERE LOWER(email) = LOWER(?);",
                (clean_email,),
            ).fetchone()
            if existing_email:
                raise ValueError(f"Địa chỉ email '{clean_email}' đã được đăng ký.")

        cursor.execute(
            """
            INSERT INTO users (id, username, email, password_hash, role, status, created_at, last_login_at)
            VALUES (?, ?, ?, ?, 'user', 'active', ?, NULL);
            """,
            (user_id, clean_username, clean_email, password_hash, created_at),
        )
        conn.commit()

    return {
        "id": user_id,
        "username": clean_username,
        "email": clean_email,
        "role": "user",
        "status": "active",
        "created_at": created_at,
        "last_login_at": None,
    }


def create_admin_user(
    username: str,
    password: str,
    email: str,
    db_path: str | None = None,
) -> dict[str, Any]:
    """Tao tai khoan Admin hoac nang quyen mot tai khoan thanh Admin an toan (dung cho bootstrap script)."""
    clean_u = username.strip()
    clean_e = email.strip()
    if len(clean_u) < 3:
        raise ValueError("Tên đăng nhập phải có ít nhất 3 ký tự.")
    if len(password) < 6:
        raise ValueError("Mật khẩu phải có ít nhất 6 ký tự.")
    if not clean_e or "@" not in clean_e:
        raise ValueError("Địa chỉ email không hợp lệ.")

    password_hash = hash_password(password)
    now_str = datetime.now(timezone.utc).isoformat()

    with get_db_connection(db_path) as conn:
        cursor = conn.cursor()
        existing = cursor.execute(
            "SELECT id FROM users WHERE LOWER(username) = LOWER(?) OR LOWER(email) = LOWER(?);",
            (clean_u, clean_e),
        ).fetchone()

        if existing:
            user_id = existing["id"]
            cursor.execute(
                "UPDATE users SET role = 'admin', status = 'active', password_hash = ? WHERE id = ?;",
                (password_hash, user_id),
            )
        else:
            user_id = str(uuid.uuid4())
            cursor.execute(
                """
                INSERT INTO users (id, username, email, password_hash, role, status, created_at, last_login_at)
                VALUES (?, ?, ?, ?, 'admin', 'active', ?, NULL);
                """,
                (user_id, clean_u, clean_e, password_hash, now_str),
            )
        conn.commit()

    return {
        "id": user_id,
        "username": clean_u,
        "email": clean_e,
        "role": "admin",
        "status": "active",
    }


def authenticate_user(username: str, password: str, db_path: str | None = None) -> dict[str, Any] | None:
    """Xac thuc nguoi dung bang ten dang nhap hoac email va mat khau."""
    clean_username = username.strip()
    if not clean_username or not password:
        return None

    with get_db_connection(db_path) as conn:
        row = conn.execute(
            """
            SELECT id, username, email, role, status, password_hash, created_at, last_login_at
            FROM users
            WHERE LOWER(username) = LOWER(?) OR LOWER(email) = LOWER(?);
            """,
            (clean_username, clean_username),
        ).fetchone()

        if not row:
            return None

        if not verify_password(password, row["password_hash"]):
            return None

        # Kiem tra tai khoan bi khoa
        if row["status"] == "locked":
            raise ValueError("Tài khoản của bạn đã bị khóa. Vui lòng liên hệ quản trị viên.")

        now_str = datetime.now(timezone.utc).isoformat()
        
        # Tu dong rehash sang Argon2id neu dang dung hash cu (legacy bcrypt / sha256)
        if needs_rehash(row["password_hash"]):
            new_argon2_hash = hash_password(password)
            conn.execute(
                "UPDATE users SET last_login_at = ?, password_hash = ? WHERE id = ?;",
                (now_str, new_argon2_hash, row["id"]),
            )
        else:
            conn.execute("UPDATE users SET last_login_at = ? WHERE id = ?;", (now_str, row["id"]))
        conn.commit()

        return {
            "id": row["id"],
            "username": row["username"],
            "email": row["email"],
            "role": row["role"],
            "status": row["status"],
            "created_at": row["created_at"],
            "last_login_at": now_str,
        }


def request_password_reset(
    email: str,
    client_ip: str | None = None,
    db_path: str | None = None,
) -> tuple[bool, str]:
    """Xu ly yeu cau dat lai mat khau qua email.
    
    Bao mat:
    1. Anti-enumeration: Luon tra ve thong bao chung du email co ton tai hay khong.
    2. Rate limiting theo email va IP: gioi han 15 giay giua cac lan gui va gioi han so luong yeu cau.
    3. Token ngau nhien manh, chi luu hash SHA-256 trong CSDL va co han 15 phut.
    """
    clean_email = (email or "").strip()
    if not clean_email or "@" not in clean_email:
        return False, "Địa chỉ email không đúng định dạng."

    generic_success_msg = (
        f"Đã gửi email khôi phục mật khẩu thành công! "
        f"Nếu email thuộc tài khoản hợp lệ, hướng dẫn khôi phục sẽ được gửi đến hộp thư của bạn."
    )

    settings = get_settings()
    cooldown_secs = getattr(settings, "password_reset_cooldown_seconds", 15)
    max_reqs = getattr(settings, "password_reset_rate_limit_count", 3)
    window_mins = getattr(settings, "password_reset_rate_limit_minutes", 15)

    # 1. Kiem tra gioi han 15 giay moi lan gui theo email (Cooldown 15 giay theo yeu cau nguoi dung)
    email_key = f"email:{clean_email.lower()}"
    allowed_email, remaining_email = check_rate_limit_cooldown(email_key, cooldown_seconds=cooldown_secs, db_path=db_path)
    if not allowed_email:
        return False, f"Bạn đã gửi quá nhiều yêu cầu khôi phục. Vui lòng đợi {remaining_email} giây trước khi gửi lại."

    # 2. Kiem tra rate limit tong so luong theo email (Burst protection)
    if not check_and_record_rate_limit(email_key, max_requests=max_reqs, window_minutes=window_mins, db_path=db_path):
        return False, "Bạn đã gửi quá nhiều yêu cầu khôi phục. Vui lòng thử lại sau 15 phút."

    # 3. Kiem tra rate limit theo IP neu co (chong brute force tu 1 IP)
    if client_ip:
        ip_key = f"ip:{client_ip}"
        if not check_and_record_rate_limit(ip_key, max_requests=max_reqs * 3, window_minutes=window_mins, db_path=db_path):
            return False, "Quá nhiều yêu cầu từ địa chỉ mạng của bạn. Vui lòng thử lại sau 15 phút."

    # 5. Tim nguoi dung theo email
    user = get_user_by_email(clean_email, db_path=db_path)
    if not user:
        # Anti-enumeration: Khong tiet lo email khong ton tai
        return True, generic_success_msg

    # 6. Sinh token va gui email
    raw_token, _ = create_password_reset_token(user["id"], db_path=db_path)
    reset_url = build_reset_password_url(raw_token)
    send_password_reset_email(clean_email, reset_url, raw_token)

    return True, generic_success_msg


def reset_password_with_token(
    raw_token: str,
    new_password: str,
    db_path: str | None = None,
) -> tuple[bool, str]:
    """Dat lai mat khau moi bang token khoi phuc tu email.
    
    Quy trinh:
    1. Kiem tra token hop le (ton tai, chua su dung, chua het han).
    2. Validate mat khau moi (do dai toi thieu 6 ky tu).
    3. Hash mat khau moi bang bcrypt.
    4. Cap nhat vao CSDL, danh dau token da dung (used_at) va thu hoi toan bo session hien co.
    """
    clean_token = (raw_token or "").strip()
    if not clean_token:
        return False, "Mã khôi phục không được để trống."

    if not new_password or len(new_password) < 6:
        return False, "Mật khẩu mới phải có ít nhất 6 ký tự."

    token_info = get_valid_password_reset_token(clean_token, db_path=db_path)
    if not token_info:
        return False, "Mã khôi phục không hợp lệ, đã được sử dụng hoặc đã hết hạn."

    new_hash = hash_password(new_password)
    update_user_password(
        user_id=token_info["user_id"],
        new_password_hash=new_hash,
        reset_token_id=token_info["id"],
        db_path=db_path,
    )

    return True, "Đặt lại mật khẩu thành công. Vui lòng đăng nhập bằng mật khẩu mới."


def create_user_session(user_id: str, db_path: str | None = None) -> tuple[str, str]:
    """Tao phien dang nhap moi cho nguoi dung va luu token da hash vao CSDL."""
    settings = get_settings()
    expire_days = getattr(settings, "session_expire_days", 7)

    raw_token = generate_session_token()
    token_hash = hash_session_token(raw_token)
    session_id = str(uuid.uuid4())

    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(days=expire_days)

    now_str = now.isoformat()
    expires_str = expires_at.isoformat()

    with get_db_connection(db_path) as conn:
        conn.execute(
            """
            INSERT INTO sessions (id, user_id, token_hash, created_at, expires_at)
            VALUES (?, ?, ?, ?, ?);
            """,
            (session_id, user_id, token_hash, now_str, expires_str),
        )
        conn.commit()

    return raw_token, expires_str


def get_user_from_token(raw_token: str, db_path: str | None = None) -> dict[str, Any] | None:
    """Xac thuc session token va tra ve thong tin user tuong ung. Neu session het han hoac user bi khoa se huy phien."""
    if not raw_token:
        return None

    token_hash = hash_session_token(raw_token)
    with get_db_connection(db_path) as conn:
        row = conn.execute(
            """
            SELECT u.id, u.username, u.email, u.role, u.status, u.created_at, u.last_login_at, s.id AS session_id, s.expires_at
            FROM sessions s
            JOIN users u ON s.user_id = u.id
            WHERE s.token_hash = ?;
            """,
            (token_hash,),
        ).fetchone()

        if not row:
            return None

        # Kiem tra neu tai khoan da bi khoa: lap tuc xoa phien va tu choi
        if row["status"] == "locked":
            conn.execute("DELETE FROM sessions WHERE id = ?;", (row["session_id"],))
            conn.commit()
            return None

        expires_at = datetime.fromisoformat(row["expires_at"])
        if datetime.now(timezone.utc) > expires_at:
            # Phien da het han, xoa khoi CSDL
            conn.execute("DELETE FROM sessions WHERE id = ?;", (row["session_id"],))
            conn.commit()
            return None

        return {
            "id": row["id"],
            "username": row["username"],
            "email": row["email"],
            "role": row["role"],
            "status": row["status"],
            "created_at": row["created_at"],
            "last_login_at": row["last_login_at"],
        }


def revoke_session(raw_token: str, db_path: str | None = None) -> None:
    """Huy phien dang nhap (xoa session token khoi CSDL)."""
    if not raw_token:
        return
    token_hash = hash_session_token(raw_token)
    with get_db_connection(db_path) as conn:
        conn.execute("DELETE FROM sessions WHERE token_hash = ?;", (token_hash,))
        conn.commit()


def get_current_user_optional(
    request: Request,
    authorization: str | None = Header(default=None),
) -> dict[str, Any] | None:
    """FastAPI dependency: Lay thong tin user dang dang nhap (neu co), ho tro ca Cookie va Header Bearer."""
    token = request.cookies.get(SESSION_COOKIE_NAME)
    if not token and authorization and authorization.startswith("Bearer "):
        token = authorization.split("Bearer ", 1)[1].strip()

    if not token:
        return None

    return get_user_from_token(token)


def get_current_user(
    current_user: dict[str, Any] | None = Depends(get_current_user_optional),
) -> dict[str, Any]:
    """FastAPI dependency: Bat buoc yeu cau user da dang nhap, tra ve 401 neu chua dang nhap, 403 neu bi khoa."""
    if not current_user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Chưa đăng nhập. Vui lòng đăng nhập để tiếp tục.",
        )
    if current_user.get("status") == "locked":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Tài khoản của bạn đã bị khóa. Vui lòng liên hệ quản trị viên.",
        )
    return current_user


def require_admin(
    current_user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    """FastAPI dependency: Bat buoc phai co role=admin."""
    if current_user.get("role") != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Truy cập bị từ chối: Yêu cầu quyền Quản trị viên (Admin).",
        )
    return current_user

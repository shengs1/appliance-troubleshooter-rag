"""Kiem thu chuyen sau ve giai thuat Hash mat khau Argon2id va co che Auto-rehash (Phase 11).

Cac test case bao gom:
1. hash_password tao ra chuoi hash chuan Argon2id ($argon2id$v=19...).
2. verify_password xac thuc thanh cong mat khau dung va tu choi mat khau sai voi Argon2id.
3. verify_password tuong thich nguoc voi cac hash legacy (bcrypt va SHA-256).
4. needs_rehash nhan dien chinh xac hash can nang cap len Argon2id.
5. authenticate_user tu dong rehash mat khau legacy sang Argon2id khi nguoi dung dang nhap thanh cong.
"""

import hashlib
import uuid
import bcrypt
import pytest

from rag_chatbot.auth import (
    authenticate_user,
    hash_password,
    needs_rehash,
    register_user,
    verify_password,
)
from rag_chatbot.database import get_db_connection, get_user_by_id


def test_hash_password_produces_argon2id():
    """Kiem tra hash_password phai sinh chuoi hash Argon2id hop le."""
    pwd = "StrongSecurePassword123!"
    h = hash_password(pwd)

    assert h is not None
    assert h.startswith("$argon2id$")
    assert "m=65536,t=3,p=4" in h


def test_verify_argon2id_password():
    """Kiem tra verify_password voi chuoi hash Argon2id."""
    pwd = "CorrectPassword456!"
    wrong_pwd = "WrongPassword456!"
    h = hash_password(pwd)

    assert verify_password(pwd, h) is True
    assert verify_password(wrong_pwd, h) is False
    assert verify_password("", h) is False
    assert verify_password(pwd, "") is False


def test_verify_legacy_bcrypt_compatibility():
    """Kiem tra tuong thich nguoc voi chuoi hash bcrypt ($2b$)."""
    pwd = "LegacyBcryptPassword789"
    salt = bcrypt.gensalt()
    legacy_bcrypt_hash = bcrypt.hashpw(pwd.encode("utf-8"), salt).decode("utf-8")

    assert legacy_bcrypt_hash.startswith("$2b$")
    assert verify_password(pwd, legacy_bcrypt_hash) is True
    assert verify_password("WrongPassword", legacy_bcrypt_hash) is False
    assert needs_rehash(legacy_bcrypt_hash) is True


def test_verify_legacy_sha256_compatibility():
    """Kiem tra tuong thich nguoc voi chuoi hash SHA-256 kem salt (salt$hash)."""
    pwd = "LegacySha256Password101"
    salt = "randomsalt32bytes"
    hash_val = hashlib.sha256((salt + pwd).encode("utf-8")).hexdigest()
    legacy_sha256_hash = f"{salt}${hash_val}"

    assert verify_password(pwd, legacy_sha256_hash) is True
    assert verify_password("WrongPassword", legacy_sha256_hash) is False
    assert needs_rehash(legacy_sha256_hash) is True


def test_needs_rehash_returns_false_for_fresh_argon2id():
    """Chuoi hash Argon2id vua tao khong can rehash."""
    h = hash_password("ValidPassword999")
    assert needs_rehash(h) is False


def test_auto_rehash_on_successful_login():
    """Khi nguoi dung mang hash legacy dang nhap thanh cong, database phai tu dong nang cap hash len Argon2id."""
    uid = uuid.uuid4().hex[:8]
    username = f"legacy_user_{uid}"
    pwd = "MySecretLegacyPass2026"
    email = f"{username}@example.com"

    # Tao hash legacy bcrypt
    salt = bcrypt.gensalt()
    legacy_hash = bcrypt.hashpw(pwd.encode("utf-8"), salt).decode("utf-8")

    # Chen truc tiep vao database
    with get_db_connection() as conn:
        conn.execute(
            """
            INSERT INTO users (id, username, email, password_hash, role, status, created_at)
            VALUES (?, ?, ?, ?, 'user', 'active', '2026-01-01T00:00:00');
            """,
            (uid, username, email, legacy_hash),
        )
        conn.commit()

    # Kiem tra truoc khi dang nhap: hash dang la bcrypt
    with get_db_connection() as conn:
        row_before = conn.execute("SELECT password_hash FROM users WHERE id = ?;", (uid,)).fetchone()
        assert row_before["password_hash"].startswith("$2b$")

    # Dang nhap thanh cong
    authenticated = authenticate_user(username, pwd)
    assert authenticated is not None
    assert authenticated["username"] == username

    # Kiem tra sau khi dang nhap: hash da duoc tu dong rehash sang Argon2id!
    with get_db_connection() as conn:
        row_after = conn.execute("SELECT password_hash FROM users WHERE id = ?;", (uid,)).fetchone()
        assert row_after["password_hash"].startswith("$argon2id$")
        assert verify_password(pwd, row_after["password_hash"]) is True

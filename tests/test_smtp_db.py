"""Kiem thu chuc nang ma hoa, tu xoa (wipe code) va luu tru cau hinh SMTP Brevo trong CSDL SQLite."""

import sqlite3
import pytest

from rag_chatbot.database import (
    init_db,
    save_smtp_config_to_db,
    get_smtp_config_from_db,
    verify_smtp_admin_pin,
    set_smtp_admin_pin,
    encrypt_setting_value,
    decrypt_setting_value,
    has_smtp_config,
    purge_smtp_config_from_db,
    verify_smtp_wipe_code,
    set_smtp_wipe_code,
)


def test_encryption_roundtrip():
    """Kiem tra ma hoa va giai ma AES Fernet giu nguyen ven noi dung goc."""
    original = "xsmtpsib-my-super-secret-key-123456"
    encrypted = encrypt_setting_value(original)
    
    assert original not in encrypted
    decrypted = decrypt_setting_value(encrypted)
    assert decrypted == original


def test_smtp_pin_verification(tmp_path):
    """Kiem tra xac thuc ma PIN quan tri SMTP (mac dinh 88889999 va doi PIN)."""
    db_file = str(tmp_path / "test_pin.db")
    init_db(db_file)
    
    assert verify_smtp_admin_pin("88889999", db_path=db_file) is True
    assert verify_smtp_admin_pin("000000", db_path=db_file) is False
    
    set_smtp_admin_pin("999888", db_path=db_file)
    assert verify_smtp_admin_pin("999888", db_path=db_file) is True
    assert verify_smtp_admin_pin("88889999", db_path=db_file) is False


def test_smtp_wipe_code_and_purge(tmp_path):
    """Kiem tra co che Ma so xoa khan cap (Wipe Code) tu dong huy cau hinh SMTP khoi CSDL."""
    db_file = str(tmp_path / "test_wipe.db")
    init_db(db_file)

    # 1. Ban dau chua co cau hinh
    assert has_smtp_config(db_path=db_file) is False

    # 2. Luu cau hinh
    save_smtp_config_to_db(
        host="smtp-relay.brevo.com",
        port=587,
        username="user@example.com",
        password="secret_password",
        from_email="user@example.com",
        db_path=db_file,
    )
    assert has_smtp_config(db_path=db_file) is True

    # 3. Kiem tra ma so xoa khan cap mac dinh (123456789)
    assert verify_smtp_wipe_code("123456789", db_path=db_file) is True
    assert verify_smtp_wipe_code("wrong_code", db_path=db_file) is False

    # 4. Thuc hien xoa sach (Purge)
    purge_smtp_config_from_db(db_path=db_file)
    assert has_smtp_config(db_path=db_file) is False
    assert get_smtp_config_from_db(db_path=db_file) is None

    # 5. Kiem tra doi ma so xoa khan cap tuy chinh
    set_smtp_wipe_code("888999111", db_path=db_file)
    assert verify_smtp_wipe_code("888999111", db_path=db_file) is True
    assert verify_smtp_wipe_code("123456789", db_path=db_file) is False


def test_smtp_config_encrypted_in_sqlite(tmp_path):
    """Kiem tra thong tin SMTP luu trong CSDL bi ma hoa hoan toan."""
    db_file = str(tmp_path / "test_smtp.db")
    init_db(db_file)
    
    raw_key = "xsmtpsib-dummy-test-key-for-unit-testing-only-1234567890abcdef"
    save_smtp_config_to_db(
        host="smtp-relay.brevo.com",
        port=587,
        username="user@example.com",
        password=raw_key,
        from_email="noreply@example.com",
        use_tls=True,
        db_path=db_file,
    )
    
    cfg = get_smtp_config_from_db(db_path=db_file)
    assert cfg is not None
    assert cfg["host"] == "smtp-relay.brevo.com"
    assert cfg["port"] == 587
    assert cfg["username"] == "user@example.com"
    assert cfg["password"] == raw_key
    assert cfg["from_email"] == "noreply@example.com"
    
    conn = sqlite3.connect(db_file)
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT value FROM system_settings WHERE key = 'smtp_config';").fetchone()
    assert row is not None
    
    encrypted_in_db = row["value"]
    assert raw_key not in encrypted_in_db
    assert "user@example.com" not in encrypted_in_db
    assert "smtp-relay.brevo.com" not in encrypted_in_db
    conn.close()

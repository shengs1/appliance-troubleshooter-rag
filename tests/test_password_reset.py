"""Kiem thu chuc nang Quen mat khau va Dat lai mat khau qua email.

Bao gom day du cac yeu cau bao mat:
1. Anti-enumeration: Email ton tai va khong ton tai deu nhan thong bao chung giong nhau.
2. Token hop le dat lai mat khau thanh cong.
3. Dang nhap mat khau moi thanh cong, mat khau cu that bai.
4. Mat khau moi duoc hash bcrypt an toan, khong luu plaintext.
5. Token da su dung bi tu choi khi dung lai lan thu hai.
6. Token sai hoac het han bi tu choi voi HTTP 400.
7. Cac phien dang nhap cu bi thu hoi ngay sau khi doi mat khau de bao ve tai khoan.
8. Gioi han tan suat (Rate Limiting) hoat dong dung (tra ve HTTP 429 khi vuot nguong).
9. Token khong the dung de sua mat khau cua tai khoan khac (token rang buoc voi user_id so huu).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import uuid
import pytest
from fastapi.testclient import TestClient

from rag_chatbot.database import (
    create_password_reset_token,
    get_db_connection,
    get_user_by_email,
)
from rag_chatbot.email_service import clear_dev_emails, get_latest_dev_email
from rag_chatbot.main import app


@pytest.fixture(autouse=True)
def clean_emails():
    """Don dep danh sach email test va bang rate limits truoc moi test case de dam bao test isolation."""
    clear_dev_emails()
    with get_db_connection() as conn:
        conn.execute("DELETE FROM password_reset_rate_limits;")
        conn.commit()
    yield
    clear_dev_emails()


@pytest.fixture
def test_user_email() -> tuple[str, str, str]:
    """Dang ky mot user moi va tra ve (username, email, password)."""
    client = TestClient(app)
    uid = uuid.uuid4().hex[:8]
    username = f"user_{uid}"
    email = f"user_{uid}@test.vn"
    password = "originalPassword123"

    res = client.post("/auth/register", json={"username": username, "email": email, "password": password})
    assert res.status_code == 201
    return username, email, password


# 1. Anti-enumeration: Email hop le va email khong ton tai deu nhan thong bao chung
def test_01_generic_response_for_valid_and_nonexistent_email(test_user_email):
    client = TestClient(app)
    _, valid_email, _ = test_user_email

    # Gui yeu cau voi email hop le da dang ky
    res_valid = client.post("/auth/forgot-password", json={"email": valid_email})
    assert res_valid.status_code == 200
    msg_valid = res_valid.json()["message"]
    assert "hướng dẫn khôi phục sẽ được gửi" in msg_valid.lower()

    # Gui yeu cau voi email hoan toan chua tung dang ky
    fake_email = f"unknown_{uuid.uuid4().hex[:8]}@nowhere.com"
    res_fake = client.post("/auth/forgot-password", json={"email": fake_email})
    assert res_fake.status_code == 200
    msg_fake = res_fake.json()["message"]

    # Thong bao phai hoan toan giong nhau de khong tiet lo su ton tai cua email
    assert msg_valid == msg_fake


# 2. Token hop le dat lai mat khau thanh cong
def test_02_valid_token_resets_password_successfully(test_user_email):
    client = TestClient(app)
    _, email, _ = test_user_email

    # 1. Yeu cau quen mat khau
    res_forgot = client.post("/auth/forgot-password", json={"email": email})
    assert res_forgot.status_code == 200

    # 2. Lay token an toan tu email duoc gui
    latest_mail = get_latest_dev_email()
    assert latest_mail is not None
    assert latest_mail["to"] == email
    token = latest_mail["token"]
    assert len(token) >= 32

    # 3. Goi API dat lai mat khau
    new_pass = "brandNewStrongPassword999"
    res_reset = client.post("/auth/reset-password", json={"token": token, "new_password": new_pass})
    assert res_reset.status_code == 200
    assert "thành công" in res_reset.json()["message"].lower()


# 3. Dang nhap bang mat khau moi thanh cong, mat khau cu that bai
def test_03_login_with_new_password_succeeds_and_old_password_fails(test_user_email):
    client = TestClient(app)
    username, email, old_pass = test_user_email

    # Yeu cau va dat lai mat khau
    client.post("/auth/forgot-password", json={"email": email})
    token = get_latest_dev_email()["token"]

    new_pass = "updatedSecretPass456"
    client.post("/auth/reset-password", json={"token": token, "new_password": new_pass})

    # Dang nhap bang mat khau cu phai that bai voi 401
    bad_login = client.post("/auth/login", json={"username": username, "password": old_pass})
    assert bad_login.status_code == 401

    # Dang nhap bang mat khau moi phai thanh cong voi 200
    good_login = client.post("/auth/login", json={"username": username, "password": new_pass})
    assert good_login.status_code == 200
    assert good_login.json()["user"]["username"] == username


# 4. Mat khau moi duoc hash bcrypt an toan, khong luu plaintext
def test_04_new_password_is_hashed_in_db(test_user_email):
    client = TestClient(app)
    _, email, _ = test_user_email

    client.post("/auth/forgot-password", json={"email": email})
    token = get_latest_dev_email()["token"]

    new_pass = "superSecretHashVerification77"
    client.post("/auth/reset-password", json={"token": token, "new_password": new_pass})

    user = get_user_by_email(email)
    assert user is not None
    stored_hash = user["password_hash"]

    # Khong bao gio duoc la chuoi plaintext
    assert stored_hash != new_pass
    # Phai la dinh dang bcrypt ($2b$ hoac $2a$)
    assert stored_hash.startswith("$2b$") or stored_hash.startswith("$2a$")


# 5. Token da su dung khong the dung lai lan thu hai (Single-use token)
def test_05_used_token_cannot_be_reused(test_user_email):
    client = TestClient(app)
    _, email, _ = test_user_email

    client.post("/auth/forgot-password", json={"email": email})
    token = get_latest_dev_email()["token"]

    # Lan 1: Dat lai mat khau thanh cong
    res1 = client.post("/auth/reset-password", json={"token": token, "new_password": "firstChange123"})
    assert res1.status_code == 200

    # Lan 2: Dung lai token cu phai bi tu choi HTTP 400
    res2 = client.post("/auth/reset-password", json={"token": token, "new_password": "secondChange123"})
    assert res2.status_code == 400
    assert "không hợp lệ" in res2.json()["detail"].lower() or "đã được sử dụng" in res2.json()["detail"].lower()


# 6. Token khong ton tai hoac da het han bi tu choi voi HTTP 400
def test_06_invalid_and_expired_token_rejected(test_user_email):
    client = TestClient(app)
    _, email, _ = test_user_email

    # Truong hop 1: Token gia mao / ngau nhien
    res_fake = client.post("/auth/reset-password", json={"token": "completely_fake_token_12345", "new_password": "newPass123"})
    assert res_fake.status_code == 400

    # Truong hop 2: Token da het han (expired)
    user = get_user_by_email(email)
    expired_token, _ = create_password_reset_token(user["id"])

    # Can thiep vao CSDL de set thoi diem expires_at ve qua khu
    past_iso = (datetime.now(timezone.utc) - timedelta(minutes=30)).isoformat()
    with get_db_connection() as conn:
        conn.execute(
            "UPDATE password_reset_tokens SET expires_at = ? WHERE user_id = ?;",
            (past_iso, user["id"]),
        )
        conn.commit()

    res_expired = client.post("/auth/reset-password", json={"token": expired_token, "new_password": "newPass123"})
    assert res_expired.status_code == 400
    assert "hết hạn" in res_expired.json()["detail"].lower() or "không hợp lệ" in res_expired.json()["detail"].lower()


# 7. Cac phien dang nhap hien co bi thu hoi ngay sau khi doi mat khau
def test_07_existing_sessions_revoked_after_password_reset(test_user_email):
    # User dang nhap tren mot thiet bi/trinh duyet
    client_session = TestClient(app)
    username, email, password = test_user_email

    login_res = client_session.post("/auth/login", json={"username": username, "password": password})
    assert login_res.status_code == 200

    # Kiem tra phien hoat dong tot
    me_res_before = client_session.get("/auth/me")
    assert me_res_before.status_code == 200

    # User yeu cau va doi mat khau tren thiet bi khac
    client_other = TestClient(app)
    client_other.post("/auth/forgot-password", json={"email": email})
    token = get_latest_dev_email()["token"]
    client_other.post("/auth/reset-password", json={"token": token, "new_password": "brandNewSecret99"})

    # Quay lai client_session cu: Session phai bi tu choi HTTP 401 vi da bi thu hoi
    me_res_after = client_session.get("/auth/me")
    assert me_res_after.status_code == 401


# 8. Gioi han tan suat (Rate Limiting) 15 giay giua cac lan gui
def test_08_rate_limiting_protects_forgot_password():
    client = TestClient(app)
    target_email = f"victim_{uuid.uuid4().hex[:6]}@example.com"

    # Gui yeu cau lan dau thanh cong
    res1 = client.post("/auth/forgot-password", json={"email": target_email})
    assert res1.status_code == 200

    # Gui yeu cau ngay lap tuc lan thu 2 (< 15 giay) phai bi chan boi Rate Limiter (HTTP 429)
    res_blocked = client.post("/auth/forgot-password", json={"email": target_email})
    assert res_blocked.status_code == 429
    assert "quá nhiều" in res_blocked.json()["detail"].lower()
    assert "giây" in res_blocked.json()["detail"].lower()


# 9. Token rang buoc dung tai khoan nguoi dung, khong the sua tai khoan khac
def test_09_token_cannot_modify_another_user_account():
    # User A va User B
    client = TestClient(app)
    uid_a, uid_b = uuid.uuid4().hex[:6], uuid.uuid4().hex[:6]
    client.post("/auth/register", json={"username": f"user_a_{uid_a}", "email": f"a_{uid_a}@mail.com", "password": "passA123"})
    client.post("/auth/register", json={"username": f"user_b_{uid_b}", "email": f"b_{uid_b}@mail.com", "password": "passB123"})

    # User A yeu cau token
    client.post("/auth/forgot-password", json={"email": f"a_{uid_a}@mail.com"})
    token_a = get_latest_dev_email()["token"]

    # Su dung token cua A de doi mat khau
    client.post("/auth/reset-password", json={"token": token_a, "new_password": "newPassForA999"})

    # User B van dang nhap binh thuong voi mat khau goc cua B
    login_b = client.post("/auth/login", json={"username": f"user_b_{uid_b}", "password": "passB123"})
    assert login_b.status_code == 200

    # User B khong the dang nhap bang mat khau moi cua A
    login_b_new = client.post("/auth/login", json={"username": f"user_b_{uid_b}", "password": "newPassForA999"})
    assert login_b_new.status_code == 401

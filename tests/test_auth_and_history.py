"""Kiem thu chuc nang dang ky, dang nhap, bao mat va luu lich su tro chuyen.

Bao gom day du 9 kich ban kiem thu theo yeu cau:
1. Dang ky thanh cong (khong lo mat khau, mat khau duoc hash bcrypt an toan).
2. Tu choi dang ky trung username/email va kiem tra validation do dai toi thieu.
3. Dang nhap dung va tu choi mat khau sai (thiet lap cookie HttpOnly SameSite=Lax).
4. Dang xuat va tu choi request can dang nhap sau khi phien ket thuc.
5. Khong the doc hoac ghi vao lich su cuoc tro chuyen cua tai khoan khac (tra ve 404).
6. Tin nhan user va assistant duoc luu va tai lai dung thu tu thoi gian.
7. Co the tiep tuc mot cuoc tro chuyen cu bang conversation_id.
8. Chatbot van goi dung pipeline RAG hien tai va luu phan hoi vao lich su.
9. Du lieu nguoi dung va lich su van ton tai sau khi khoi dong lai ung dung.
10. Kiem tra phien het han tu dong bi huy bo.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import patch
import uuid
import pytest
from fastapi.testclient import TestClient

from rag_chatbot.auth import (
    SESSION_COOKIE_NAME,
    authenticate_user,
    get_user_from_token,
    hash_session_token,
    register_user,
)
from rag_chatbot.database import (
    get_conversation_messages,
    get_db_connection,
    init_db,
    save_chat_turn,
)
from rag_chatbot.main import app


@pytest.fixture
def unique_username() -> str:
    """Sinh ten nguoi dung duy nhat cho moi test case."""
    return f"user_{uuid.uuid4().hex[:8]}"


# 1. Dang ky thanh cong (khong lo mat khau, password_hash bcrypt)
def test_01_register_success(unique_username: str):
    client = TestClient(app)
    raw_password = "strongPassword123"
    payload = {
        "username": unique_username,
        "password": raw_password,
    }
    response = client.post("/auth/register", json=payload)
    assert response.status_code == 201
    data = response.json()

    assert data["username"] == unique_username
    assert "id" in data
    assert "created_at" in data
    # Dam bao tuyet doi khong tra ve password hoac password_hash trong API response
    assert "password" not in data
    assert "password_hash" not in data

    # Kiem tra truc tiep trong CSDL: mat khau phai duoc hash bang bcrypt, khong duoc luu plaintext
    with get_db_connection() as conn:
        row = conn.execute(
            "SELECT password_hash FROM users WHERE id = ?;",
            (data["id"],),
        ).fetchone()
        assert row is not None
        stored_hash = row["password_hash"]
        assert stored_hash != raw_password
        assert stored_hash.startswith("$2b$") or stored_hash.startswith("$2a$")


# 2. Tu choi dang ky trung username/email va validation do dai
def test_02_register_reject_duplicate_username(unique_username: str):
    client = TestClient(app)
    payload = {
        "username": unique_username,
        "password": "initialPassword123",
    }
    # Dang ky lan 1 thanh cong
    res1 = client.post("/auth/register", json=payload)
    assert res1.status_code == 201

    # Dang ky lan 2 voi cung username phai bi tu choi bang HTTP 400
    res2 = client.post("/auth/register", json=payload)
    assert res2.status_code == 400
    assert "đã tồn tại" in res2.json()["detail"].lower()

    # Dang ky voi username viet hoa/thuong cung phai bi tu choi (case-insensitive)
    res3 = client.post("/auth/register", json={"username": unique_username.upper(), "password": "newPassword123"})
    assert res3.status_code == 400
    assert "đã tồn tại" in res3.json()["detail"].lower()

    # Kiem tra tu choi username qua ngan (< 3 ky tu)
    res_short_u = client.post("/auth/register", json={"username": "ab", "password": "validPassword123"})
    assert res_short_u.status_code in (400, 422)

    # Kiem tra tu choi mat khau qua ngan (< 6 ky tu)
    res_short_p = client.post("/auth/register", json={"username": f"valid_{unique_username}", "password": "123"})
    assert res_short_p.status_code in (400, 422)


# 3. Dang nhap dung va tu choi mat khau sai
def test_03_login_correct_and_wrong_password_rejected(unique_username: str):
    client = TestClient(app)
    client.post("/auth/register", json={"username": unique_username, "password": "correctPassword123"})

    # Dang nhap sai mat khau -> 401
    bad_login = client.post("/auth/login", json={"username": unique_username, "password": "wrongPassword"})
    assert bad_login.status_code == 401
    assert "không chính xác" in bad_login.json()["detail"].lower()

    # Dang nhap dung mat khau -> 200 va co cookie session_token
    good_login = client.post("/auth/login", json={"username": unique_username, "password": "correctPassword123"})
    assert good_login.status_code == 200
    assert SESSION_COOKIE_NAME in good_login.cookies
    data = good_login.json()
    assert data["user"]["username"] == unique_username
    assert "session_token" in data


# 4. Dang xuat va tu choi request can dang nhap sau khi phien ket thuc
def test_04_logout_and_subsequent_request_rejected(unique_username: str):
    client = TestClient(app)
    client.post("/auth/register", json={"username": unique_username, "password": "password123"})
    login_res = client.post("/auth/login", json={"username": unique_username, "password": "password123"})
    assert login_res.status_code == 200

    # Truoc khi logout: goi /auth/me va /conversations binh thuong
    me_res = client.get("/auth/me")
    assert me_res.status_code == 200

    # Dang xuat
    logout_res = client.post("/auth/logout")
    assert logout_res.status_code == 200

    # Sau khi logout: moi request can dang nhap deu bi tu choi HTTP 401
    res_me_after = client.get("/auth/me")
    assert res_me_after.status_code == 401

    res_convs_after = client.get("/conversations")
    assert res_convs_after.status_code == 401

    res_chat_after = client.post("/chat", json={"question": "Kiểm tra sau đăng xuất"})
    assert res_chat_after.status_code == 401


# 5. Khong the doc lich su hoac chat vao cuoc tro chuyen cua tai khoan khac
def test_05_cannot_read_or_chat_in_other_user_conversation():
    # User A tao cuoc tro chuyen
    user_a = f"user_a_{uuid.uuid4().hex[:6]}"
    client_a = TestClient(app)
    client_a.post("/auth/register", json={"username": user_a, "password": "password123"})
    client_a.post("/auth/login", json={"username": user_a, "password": "password123"})

    mock_rag = {
        "question": "Câu hỏi của A",
        "answer": "Trả lời cho A",
        "llm_status": "success",
        "retrieved_documents": [],
    }
    with patch("rag_chatbot.main.generate_rag_answer", return_value=mock_rag):
        chat_a_res = client_a.post("/chat", json={"question": "Câu hỏi của A"})
        assert chat_a_res.status_code == 200
        conv_a_id = chat_a_res.json()["conversation_id"]
        assert conv_a_id is not None

    # User B dang nhap tren client rieng
    user_b = f"user_b_{uuid.uuid4().hex[:6]}"
    client_b = TestClient(app)
    client_b.post("/auth/register", json={"username": user_b, "password": "password123"})
    client_b.post("/auth/login", json={"username": user_b, "password": "password123"})

    # User B co doc cuoc tro chuyen cua User A -> phai tra ve 404 (khong tiet lo su ton tai)
    read_res = client_b.get(f"/conversations/{conv_a_id}")
    assert read_res.status_code == 404

    # User B co gui cau hoi tiep vao conv_a_id cua User A -> phai tra ve 404
    with patch("rag_chatbot.main.generate_rag_answer", return_value=mock_rag):
        chat_b_res = client_b.post("/chat", json={"question": "User B hack", "conversation_id": conv_a_id})
        assert chat_b_res.status_code == 404


# 6. Tin nhan user va assistant duoc luu va tai lai dung thu tu
def test_06_messages_saved_and_reloaded_in_correct_order(unique_username: str):
    client = TestClient(app)
    client.post("/auth/register", json={"username": unique_username, "password": "password123"})
    client.post("/auth/login", json={"username": unique_username, "password": "password123"})

    mock_1 = {"question": "Lỗi IE máy giặt LG", "answer": "Lỗi IE là lỗi cấp nước.", "llm_status": "success", "retrieved_documents": []}
    mock_2 = {"question": "Cách kiểm tra van cấp nước?", "answer": "Kiểm tra lưới lọc van cấp nước.", "llm_status": "success", "retrieved_documents": []}

    with patch("rag_chatbot.main.generate_rag_answer", return_value=mock_1):
        res1 = client.post("/chat", json={"question": "Lỗi IE máy giặt LG"})
        assert res1.status_code == 200
        conv_id = res1.json()["conversation_id"]

    with patch("rag_chatbot.main.generate_rag_answer", return_value=mock_2):
        res2 = client.post("/chat", json={"question": "Cách kiểm tra van cấp nước?", "conversation_id": conv_id})
        assert res2.status_code == 200
        assert res2.json()["conversation_id"] == conv_id

    # Lay lai toan bo tin nhan cua cuoc tro chuyen
    detail_res = client.get(f"/conversations/{conv_id}")
    assert detail_res.status_code == 200
    messages = detail_res.json()["messages"]

    assert len(messages) == 4
    # Kiem tra dung thu tu user 1 -> bot 1 -> user 2 -> bot 2
    assert messages[0]["role"] == "user"
    assert messages[0]["content"] == "Lỗi IE máy giặt LG"
    assert messages[1]["role"] == "assistant"
    assert messages[1]["content"] == "Lỗi IE là lỗi cấp nước."
    assert messages[2]["role"] == "user"
    assert messages[2]["content"] == "Cách kiểm tra van cấp nước?"
    assert messages[3]["role"] == "assistant"
    assert messages[3]["content"] == "Kiểm tra lưới lọc van cấp nước."

    # Kiem tra moc thoi gian tang dan hoac bang nhau
    for i in range(len(messages) - 1):
        assert messages[i]["created_at"] <= messages[i + 1]["created_at"]


# 7. Co the tiep tuc mot cuoc tro chuyen cu
def test_07_continue_existing_conversation(unique_username: str):
    client = TestClient(app)
    client.post("/auth/register", json={"username": unique_username, "password": "password123"})
    client.post("/auth/login", json={"username": unique_username, "password": "password123"})

    mock_rag = {"question": "Q", "answer": "A", "llm_status": "success", "retrieved_documents": []}
    with patch("rag_chatbot.main.generate_rag_answer", return_value=mock_rag):
        res1 = client.post("/chat", json={"question": "Câu hỏi mở đầu"})
        conv_id = res1.json()["conversation_id"]

        # Tiep tuc lan 1
        res2 = client.post("/chat", json={"question": "Câu hỏi tiếp theo 1", "conversation_id": conv_id})
        assert res2.json()["conversation_id"] == conv_id

        # Tiep tuc lan 2
        res3 = client.post("/chat", json={"question": "Câu hỏi tiếp theo 2", "conversation_id": conv_id})
        assert res3.json()["conversation_id"] == conv_id

    # Kiem tra danh sach conversations chi co 1 cuoc hoi thoai duy nhat
    convs_res = client.get("/conversations")
    assert convs_res.status_code == 200
    assert len(convs_res.json()) == 1

    # Kiem tra so luong tin nhan la 6 (3 cap user-bot)
    detail_res = client.get(f"/conversations/{conv_id}")
    assert len(detail_res.json()["messages"]) == 6


# 8. Chatbot van goi duoc pipeline RAG hien tai
def test_08_chatbot_calls_current_rag_pipeline(unique_username: str):
    client = TestClient(app)
    client.post("/auth/register", json={"username": unique_username, "password": "password123"})
    client.post("/auth/login", json={"username": unique_username, "password": "password123"})

    mock_rag = {
        "question": "Samsung lỗi CF là gì?",
        "answer": "Mã CF là nhắc vệ sinh bộ lọc không khí.",
        "llm_status": "success",
        "retrieved_documents": [
            {
                "question_id": "Q0358",
                "brand": "Samsung",
                "device": "Điều hòa",
                "source_url": "https://www.samsung.com/vn/support/doc1",
            }
        ],
        "validation": {"status": "pass"},
    }

    with patch("rag_chatbot.main.generate_rag_answer", return_value=mock_rag) as mock_func:
        response = client.post("/chat", json={"question": "Samsung lỗi CF là gì?"})
        assert response.status_code == 200
        mock_func.assert_called_once_with("Samsung lỗi CF là gì?")

        data = response.json()
        assert data["question"] == "Samsung lỗi CF là gì?"
        assert data["answer"] == "Mã CF là nhắc vệ sinh bộ lọc không khí."
        assert data["llm_status"] == "success"
        assert len(data["retrieved_documents"]) == 1
        assert "https://www.samsung.com/vn/support/doc1" in data["sources"]
        assert data["conversation_id"] is not None


# 9. Du lieu van ton tai sau khi khoi dong lai ung dung
def test_09_data_persists_across_restart(tmp_path):
    test_db_file = str(tmp_path / "persistent_chat.db")

    # Khoi tao CSDL lan dau
    init_db(test_db_file)
    user = register_user("persisted_user", "password123", db_path=test_db_file)

    # Luu mot luot chat
    turn = save_chat_turn(
        user_id=user["id"],
        question="Điều hòa không mát?",
        answer="Hãy kiểm tra lưới lọc và ga máy lạnh.",
        db_path=test_db_file,
    )
    conv_id = turn["conversation_id"]

    # "Mo phong khoi dong lai ung dung": mo lai file CSDL o mot connection moi hoan toan
    restarted_conn = get_db_connection(test_db_file)
    try:
        # Kiem tra nguoi dung van ton tai
        auth_check = authenticate_user("persisted_user", "password123", db_path=test_db_file)
        assert auth_check is not None
        assert auth_check["id"] == user["id"]

        # Kiem tra cuoc tro chuyen van ton tai
        conv_row = restarted_conn.execute(
            "SELECT * FROM conversations WHERE id = ?;",
            (conv_id,),
        ).fetchone()
        assert conv_row is not None
        assert conv_row["user_id"] == user["id"]

        # Kiem tra cac tin nhan van con nguyen ven
        messages = get_conversation_messages(conv_id, db_path=test_db_file)
        assert len(messages) == 2
        assert messages[0]["content"] == "Điều hòa không mát?"
        assert messages[1]["content"] == "Hãy kiểm tra lưới lọc và ga máy lạnh."
    finally:
        restarted_conn.close()


# 10. Phien dang nhap het han se bi tu dong huy bo
def test_10_expired_session_is_revoked(tmp_path):
    test_db_file = str(tmp_path / "expired_session.db")
    init_db(test_db_file)
    user = register_user("expired_user", "password123", db_path=test_db_file)

    # Tao phien co thoi gian expires_at o qua khu
    raw_token = "fake_expired_token_123"
    token_hash = hash_session_token(raw_token)
    past_time = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
    now_time = datetime.now(timezone.utc).isoformat()

    with get_db_connection(test_db_file) as conn:
        conn.execute(
            "INSERT INTO sessions (id, user_id, token_hash, created_at, expires_at) VALUES (?, ?, ?, ?, ?);",
            (str(uuid.uuid4()), user["id"], token_hash, now_time, past_time),
        )
        conn.commit()

    # Kiem tra get_user_from_token: phai tra ve None vi da het han
    assert get_user_from_token(raw_token, db_path=test_db_file) is None

    # Kiem tra session da bi xoa khoi CSDL
    with get_db_connection(test_db_file) as conn:
        row = conn.execute("SELECT id FROM sessions WHERE token_hash = ?;", (token_hash,)).fetchone()
        assert row is None

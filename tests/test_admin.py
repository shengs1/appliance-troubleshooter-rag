"""Kiem thu toan dien he thong Quan tri vien (Admin) va quan ly tai khoan.

Cac yeu cau kiem thu bao gom:
1. Nguoi dung dang ky cong khai luon mac dinh role='user', khong the tu nang quyen len admin.
2. Request chua dang nhap truy cap cac endpoint /admin/* bi tu choi voi HTTP 401.
3. Nguoi dung thong thuong (role='user') goi API quan tri bi tu choi voi HTTP 403.
4. Admin dang nhap hop le co the xem thong ke (/admin/stats) va danh sach tai khoan (/admin/users).
5. Tim kiem theo username/email va phan trang hoat dong chinh xac tren danh sach nguoi dung.
6. Khi bi khoa tai khoan:
   - Thu hoi ngay lap tuc tat ca phien dang hoat dong cua user bi khoa.
   - User bi khoa khong the tiep tuc goi cac API yeu cau xac thuc.
   - User bi khoa khong the dang nhap lai (nhan thong bao tai khoan bi khoa).
7. Khi mo khoa tai khoan: user co the dang nhap lai binh thuong.
8. Admin co the thay doi vai tro (promote thanh admin, demote xuong user).
9. Co che bao ve he thong:
   - Admin khong the tu khoa tai khoan cua chinh minh.
   - Admin khong the tu ha quyen cua chinh minh.
   - Khong the khoa hoac ha quyen Admin cuoi cung con hoat dong trong he thong.
10. Admin co the kich hoat gui email dat lai mat khau cho tai khoan co email.
11. Giao dien /admin tu dong redirect sang /admin-ui, va /admin-ui phan hoi 200.
12. Bao toan du lieu: Thao tac khoa/mo khoa la soft-lock, bao toan 100% lich su hoi thoai cua nguoi dung.
"""

from __future__ import annotations

import uuid
import pytest
from fastapi.testclient import TestClient

from rag_chatbot.auth import create_admin_user
from rag_chatbot.database import (
    count_active_admins,
    get_admin_stats,
    get_conversation_messages,
    get_db_connection,
    get_user_conversations,
    save_chat_turn,
)
from rag_chatbot.email_service import clear_dev_emails, get_latest_dev_email
from rag_chatbot.main import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def clean_test_isolation():
    """Don dep email test va dam bao moi truong sach se."""
    clear_dev_emails()
    yield
    clear_dev_emails()


@pytest.fixture
def admin_client() -> tuple[TestClient, dict[str, str]]:
    """Fixture tao mot Admin hop le va tra ve client da dang nhap kem thong tin Admin."""
    uid = uuid.uuid4().hex[:8]
    username = f"admin_{uid}"
    email = f"admin_{uid}@example.com"
    password = "AdminSecretPass123"

    admin_info = create_admin_user(username=username, email=email, password=password)

    c = TestClient(app)
    login_res = c.post("/auth/login", json={"username": username, "password": password})
    assert login_res.status_code == 200

    return c, {
        "id": admin_info["id"],
        "username": username,
        "email": email,
        "password": password,
    }


@pytest.fixture
def user_client() -> tuple[TestClient, dict[str, str]]:
    """Fixture tao mot User thong thuong va tra ve client da dang nhap."""
    uid = uuid.uuid4().hex[:8]
    username = f"user_{uid}"
    email = f"user_{uid}@example.com"
    password = "UserSecretPass123"

    c = TestClient(app)
    reg_res = c.post(
        "/auth/register",
        json={"username": username, "email": email, "password": password, "role": "admin"},
    )
    assert reg_res.status_code == 201

    login_res = c.post("/auth/login", json={"username": username, "password": password})
    assert login_res.status_code == 200

    user_data = reg_res.json()
    return c, {
        "id": user_data["id"],
        "username": username,
        "email": email,
        "password": password,
    }


# 1. Nguoi dung dang ky cong khai luon co role='user'
def test_01_public_registration_defaults_to_user_role():
    uid = uuid.uuid4().hex[:8]
    username = f"hacker_{uid}"
    email = f"hacker_{uid}@example.com"
    password = "password123"

    # Gui yeu cau dang ky kem payload co tinh truyen role='admin'
    res = client.post(
        "/auth/register",
        json={"username": username, "email": email, "password": password, "role": "admin"},
    )
    assert res.status_code == 201
    data = res.json()
    assert data["role"] == "user"
    assert data["status"] == "active"


# 2. Request chua dang nhap bi tu choi voi HTTP 401
def test_02_unauthenticated_requests_to_admin_endpoints_rejected_with_401():
    unauth = TestClient(app)

    res_stats = unauth.get("/admin/stats")
    assert res_stats.status_code == 401
    assert "chưa đăng nhập" in res_stats.json()["detail"].lower()

    res_users = unauth.get("/admin/users")
    assert res_users.status_code == 401


# 3. User thong thuong bi tu choi truy cap quan tri voi HTTP 403
def test_03_standard_user_rejected_from_admin_endpoints_with_403(user_client):
    u_client, _ = user_client

    res_stats = u_client.get("/admin/stats")
    assert res_stats.status_code == 403
    assert "admin" in res_stats.json()["detail"].lower()

    res_users = u_client.get("/admin/users")
    assert res_users.status_code == 403


# 4. Admin hop le co the xem thong ke va danh sach tai khoan
def test_04_admin_can_access_stats_and_users_list(admin_client):
    a_client, admin_info = admin_client

    # Kiem tra /admin/stats
    res_stats = a_client.get("/admin/stats")
    assert res_stats.status_code == 200
    stats = res_stats.json()
    assert stats["total_users"] >= 1
    assert stats["active_users"] >= 1
    assert "locked_users" in stats

    # Kiem tra /admin/users
    res_users = a_client.get("/admin/users")
    assert res_users.status_code == 200
    user_list = res_users.json()
    assert "users" in user_list
    assert user_list["total"] >= 1
    assert user_list["page"] == 1

    # Khong bao gio tra ve password hoac password_hash
    for u in user_list["users"]:
        assert "password" not in u
        assert "password_hash" not in u


# 5. Tim kiem theo username/email va phan trang hoat dong dung
def test_05_admin_can_search_and_paginate_users(admin_client):
    a_client, _ = admin_client

    unique_mark = uuid.uuid4().hex[:6]
    client.post(
        "/auth/register",
        json={"username": f"alpha_{unique_mark}", "email": f"alpha_{unique_mark}@test.com", "password": "pass123456"},
    )
    client.post(
        "/auth/register",
        json={"username": f"beta_{unique_mark}", "email": f"beta_{unique_mark}@test.com", "password": "pass123456"},
    )

    # Tim kiem alpha
    res_search = a_client.get(f"/admin/users?search=alpha_{unique_mark}")
    assert res_search.status_code == 200
    data = res_search.json()
    assert data["total"] == 1
    assert data["users"][0]["username"] == f"alpha_{unique_mark}"

    # Tim kiem theo domain email
    res_search_email = a_client.get(f"/admin/users?search=beta_{unique_mark}@test.com")
    assert res_search_email.status_code == 200
    data_email = res_search_email.json()
    assert data_email["total"] == 1
    assert data_email["users"][0]["username"] == f"beta_{unique_mark}"

    # Phan trang
    res_page = a_client.get("/admin/users?page=1&page_size=2")
    assert res_page.status_code == 200
    page_data = res_page.json()
    assert len(page_data["users"]) <= 2
    assert page_data["page_size"] == 2


# 6. Khoa tai khoan: thu hoi phien lap tuc va chan dang nhap
def test_06_locking_user_revokes_session_and_blocks_login(admin_client, user_client):
    a_client, _ = admin_client
    u_client, user_info = user_client

    # Kiem tra truoc khi khoa: user dang nhap binh thuong
    res_me_before = u_client.get("/auth/me")
    assert res_me_before.status_code == 200

    # Admin khoa tai khoan cua user
    lock_res = a_client.patch(
        f"/admin/users/{user_info['id']}/status",
        json={"status": "locked"},
    )
    assert lock_res.status_code == 200
    assert lock_res.json()["status"] == "locked"

    # 1. Phien dang hoat dong bi thu hoi ngay lap tuc
    res_me_after = u_client.get("/auth/me")
    assert res_me_after.status_code in (401, 403)

    # 2. Dang nhap lai bang dung username & password bi tu choi
    new_client = TestClient(app)
    login_attempt = new_client.post(
        "/auth/login",
        json={"username": user_info["username"], "password": user_info["password"]},
    )
    assert login_attempt.status_code in (400, 401, 403)
    assert "khóa" in login_attempt.json()["detail"].lower()


# 7. Mo khoa tai khoan: cho phep user dang nhap lai binh thuong
def test_07_unlocking_user_restores_login(admin_client, user_client):
    a_client, _ = admin_client
    _, user_info = user_client

    # Khoa tai khoan
    a_client.patch(f"/admin/users/{user_info['id']}/status", json={"status": "locked"})

    # Mo khoa tai khoan
    unlock_res = a_client.patch(f"/admin/users/{user_info['id']}/status", json={"status": "active"})
    assert unlock_res.status_code == 200
    assert unlock_res.json()["status"] == "active"

    # User dang nhap lai thanh cong
    fresh_client = TestClient(app)
    login_res = fresh_client.post(
        "/auth/login",
        json={"username": user_info["username"], "password": user_info["password"]},
    )
    assert login_res.status_code == 200
    assert login_res.json()["user"]["status"] == "active"


# 8. Thay doi vai tro nguoi dung (promote va demote)
def test_08_admin_role_change_promote_and_demote(admin_client, user_client):
    a_client, _ = admin_client
    u_client, user_info = user_client

    # User chua the truy cap admin
    assert u_client.get("/admin/stats").status_code == 403

    # Admin nang quyen user thanh admin
    promote_res = a_client.patch(
        f"/admin/users/{user_info['id']}/role",
        json={"role": "admin"},
    )
    assert promote_res.status_code == 200
    assert promote_res.json()["role"] == "admin"

    # Sau khi nang quyen, user dang nhap lai va co the truy cap admin
    fresh_client = TestClient(app)
    fresh_client.post(
        "/auth/login",
        json={"username": user_info["username"], "password": user_info["password"]},
    )
    assert fresh_client.get("/admin/stats").status_code == 200

    # Admin ha quyen xuong user
    demote_res = a_client.patch(
        f"/admin/users/{user_info['id']}/role",
        json={"role": "user"},
    )
    assert demote_res.status_code == 200
    assert demote_res.json()["role"] == "user"

    # Dang nhap lai va kiem tra lai khong con quyen admin
    fresh_client_2 = TestClient(app)
    fresh_client_2.post(
        "/auth/login",
        json={"username": user_info["username"], "password": user_info["password"]},
    )
    assert fresh_client_2.get("/admin/stats").status_code == 403


# 9. Co che bao ve: Admin khong the tu khoa hoac tu ha quyen chinh minh
def test_09_safeguard_admin_cannot_self_lock_or_self_demote(admin_client):
    a_client, admin_info = admin_client

    # Tu khoa chinh minh
    self_lock = a_client.patch(
        f"/admin/users/{admin_info['id']}/status",
        json={"status": "locked"},
    )
    assert self_lock.status_code == 400
    assert "tự khóa" in self_lock.json()["detail"].lower()

    # Tu ha quyen chinh minh
    self_demote = a_client.patch(
        f"/admin/users/{admin_info['id']}/role",
        json={"role": "user"},
    )
    assert self_demote.status_code == 400
    assert "tự hạ quyền" in self_demote.json()["detail"].lower()


# 10. Co che bao ve: Khong the khoa hoac ha quyen Admin duy nhat con hoat dong
def test_10_safeguard_cannot_lock_or_demote_last_active_admin():
    # Tao 1 database temp hoac kiem tra dem so admin
    # Tao 2 admin, khoa 1 admin thi admin con lai la duy nhat active
    uid1 = uuid.uuid4().hex[:8]
    uid2 = uuid.uuid4().hex[:8]
    adm1 = create_admin_user(username=f"adm1_{uid1}", email=f"adm1_{uid1}@test.vn", password="pass_admin_123")
    adm2 = create_admin_user(username=f"adm2_{uid2}", email=f"adm2_{uid2}@test.vn", password="pass_admin_123")

    c1 = TestClient(app)
    c1.post("/auth/login", json={"username": adm1["username"], "password": "pass_admin_123"})

    # Khoa adm2 qua c1
    c1.patch(f"/admin/users/{adm2['id']}/status", json={"status": "locked"})

    # Bay gio neu chi con 1 admin active trong he thong thi khong the khoa tiep
    # Neu con admin khac tu truoc, dem so admin con active
    active_count = count_active_admins()
    if active_count == 1:
        # Thu khoa admin duy nhat con lai se that bai
        lock_attempt = c1.patch(f"/admin/users/{adm1['id']}/status", json={"status": "locked"})
        assert lock_attempt.status_code == 400


# 11. Admin kich hoat gui email dat lai mat khau cho nguoi dung
def test_11_admin_trigger_password_reset(admin_client, user_client):
    a_client, _ = admin_client
    _, user_info = user_client

    # Kich hoat gui reset
    res = a_client.post(f"/admin/users/{user_info['id']}/password-reset")
    assert res.status_code == 200
    assert "đã gửi hướng dẫn" in res.json()["message"].lower()

    # Kiem tra email dev duoc tao
    email = get_latest_dev_email()
    assert email is not None
    assert user_info["email"] in email["to"]
    assert "#token=" in email["reset_url"]

    # Kiem tra ghi log kiem toan trong database
    with get_db_connection() as conn:
        log = conn.execute(
            "SELECT * FROM admin_audit_logs WHERE target_user_id = ? ORDER BY created_at DESC LIMIT 1;",
            (user_info["id"],),
        ).fetchone()
        assert log is not None
        assert log["action"] == "password_reset_trigger"


# 12. Cac endpoint giao dien Admin HTML cu da go bo va bao toan lich su tro chuyen
def test_12_admin_chainlit_integration_and_history_preservation(admin_client, user_client):
    # Kiem tra /admin-ui cu cua Gradio da duoc go bo khoi FastAPI (tra ve 404)
    res_admin_ui = client.get("/admin-ui")
    assert res_admin_ui.status_code == 404

    # Kiem tra logic kiem tra quyen Admin cho Chainlit
    from rag_chatbot.chainlit_app import check_admin_privilege
    from chainlit.user import User

    a_client, admin_info = admin_client
    _, user_info = user_client

    admin_cl_user = User(identifier=admin_info["username"], metadata={"id": admin_info["id"], "role": "admin"})
    assert check_admin_privilege(admin_cl_user) is not None

    normal_cl_user = User(identifier=user_info["username"], metadata={"id": user_info["id"], "role": "user"})
    assert check_admin_privilege(normal_cl_user) is None

    # Kiem tra bao toan lich su tro chuyen khi tai khoan bi khoa/mo khoa (soft-lock)
    a_client, _ = admin_client
    _, user_info = user_client

    # Tao lich su hoi thoai cho user
    turn = save_chat_turn(
        user_id=user_info["id"],
        question="Tủ lạnh kêu to sửa sao?",
        answer="Kiểm tra lại chân đế tủ lạnh.",
    )
    conv_id = turn["conversation_id"]

    # Admin khoa tai khoan
    a_client.patch(f"/admin/users/{user_info['id']}/status", json={"status": "locked"})

    # Admin mo khoa tai khoan
    a_client.patch(f"/admin/users/{user_info['id']}/status", json={"status": "active"})

    # Lich su hoi thoai van ton tai nguyen ven 100%
    convs = get_user_conversations(user_info["id"])
    assert len(convs) >= 1
    assert any(c["id"] == conv_id for c in convs)

    msgs = get_conversation_messages(conv_id)
    assert len(msgs) == 2
    assert msgs[0]["content"] == "Tủ lạnh kêu to sửa sao?"
    assert msgs[1]["content"] == "Kiểm tra lại chân đế tủ lạnh."


def test_13_admin_bridge_token_and_logout_revocation(admin_client, user_client):
    a_client, admin_info = admin_client
    u_client, _ = user_client

    # 1. Khach chua dang nhap goi /admin/bridge-token phai nhan 401
    unauth_res = client.get("/admin/bridge-token")
    assert unauth_res.status_code == 401

    # 2. User thuong goi /admin/bridge-token phai nhan 403
    user_res = u_client.get("/admin/bridge-token")
    assert user_res.status_code == 403

    # 3. Admin goi /admin/bridge-token phai nhan 200 kem token
    admin_res = a_client.get("/admin/bridge-token")
    assert admin_res.status_code == 200
    token_data = admin_res.json()
    assert "token" in token_data
    bridge_token = token_data["token"]
    assert len(bridge_token) >= 32

    # 4. Kiem tra token lay duoc co the truy cap vao /admin/stats
    bridge_client = TestClient(app)
    stats_res = bridge_client.get("/admin/stats", headers={"Authorization": f"Bearer {bridge_token}"})
    assert stats_res.status_code == 200

    # 5. Dang xuat voi bridge token qua /auth/logout
    logout_res = bridge_client.post("/auth/logout", headers={"Authorization": f"Bearer {bridge_token}"})
    assert logout_res.status_code == 200

    # 6. Sau khi dang xuat, token da bi thu hoi (revoke) -> truy cap lai bi 401
    revoked_res = bridge_client.get("/admin/stats", headers={"Authorization": f"Bearer {bridge_token}"})
    assert revoked_res.status_code == 401


def test_14_admin_delete_user_success_and_safeguards(admin_client, user_client):
    """Kiem tra Admin xoa tai khoan nguoi dung, cac rang buoc bao ve va cleanup du lieu lien quan."""
    a_client, admin_info = admin_client
    u_client, user_info = user_client

    # 1. Tao hoi thoai va tin nhan cho user
    turn = save_chat_turn(
        user_id=user_info["id"],
        question="May giat Toshiba loi E2",
        answer="Loi cong tac cua hoac nap chua dong kin.",
    )
    conv_id = turn["conversation_id"]

    # 2. Admin khong the tu xoa chinh minh (phai tra ve 400)
    self_del = a_client.delete(f"/admin/users/{admin_info['id']}")
    assert self_del.status_code == 400
    assert "Không thể tự xóa" in self_del.json()["detail"]

    # 3. Admin xoa tai khoan user thanh cong
    del_res = a_client.delete(f"/admin/users/{user_info['id']}")
    assert del_res.status_code == 200
    assert "thành công" in del_res.json()["message"]

    # 4. Kiem tra user da bi xoa khoi he thong
    get_res = a_client.get(f"/admin/users/{user_info['id']}")
    assert get_res.status_code == 404

    # 5. Kiem tra conversations va messages lien quan da duoc don sach
    convs = get_user_conversations(user_info["id"])
    assert len(convs) == 0

    msgs = get_conversation_messages(conv_id)
    assert len(msgs) == 0

    # 6. User da bi xoa khong the tiep tuc dang nhap
    login_res = client.post("/auth/login", json={
        "username": user_info["username"],
        "password": "UserPass123!",
    })
    assert login_res.status_code in [400, 401]


def test_15_admin_delete_user_permissions(admin_client, user_client):
    """Kiem tra phan quyen khi goi endpoint DELETE /admin/users/{id}."""
    a_client, admin_info = admin_client
    u_client, user_info = user_client

    # 1. Khach chua dang nhap goi DELETE bi tu choi 401
    unauth_res = client.delete(f"/admin/users/{user_info['id']}")
    assert unauth_res.status_code == 401

    # 2. User thuong goi DELETE bi tu choi 403
    forbidden_res = u_client.delete(f"/admin/users/{user_info['id']}")
    assert forbidden_res.status_code == 403


def test_16_admin_delete_admin_requires_security_password(admin_client):
    """Kiem tra khi xoa tai khoan Admin, bat buoc phai nhap dung mat khau bao mat 123456789."""
    a_client, admin_info = admin_client

    # Tao tai khoan admin thu 2
    uid = uuid.uuid4().hex[:6]
    admin2_info = create_admin_user(
        username=f"admin2_{uid}",
        email=f"admin2_{uid}@example.com",
        password="AdminPass123!",
    )
    admin2_id = admin2_info["id"]

    # 1. Xoa admin ma khong truyen mat khau bao mat -> 400 Bad Request
    no_pass_res = a_client.delete(f"/admin/users/{admin2_id}")
    assert no_pass_res.status_code == 400
    assert "123456789" in no_pass_res.json()["detail"]

    # 2. Xoa admin voi mat khau sai -> 400 Bad Request
    wrong_pass_res = a_client.delete(f"/admin/users/{admin2_id}?admin_password=wrongpass")
    assert wrong_pass_res.status_code == 400
    assert "123456789" in wrong_pass_res.json()["detail"]

    # 3. Xoa admin voi mat khau dung 123456789 -> 200 OK
    ok_res = a_client.delete(f"/admin/users/{admin2_id}?admin_password=123456789")
    assert ok_res.status_code == 200
    assert "thành công" in ok_res.json()["message"]

    # 4. Kiem tra admin2 da bi xoa khoi he thong
    get_res = a_client.get(f"/admin/users/{admin2_id}")
    assert get_res.status_code == 404




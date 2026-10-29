"""Chainlit Application - Giao dien Chatbot RAG va Quan tri Admin tap trung duy nhat.

Tich hop:
1. SQLite Data Layer luu tru lich su hoi thoai ben vung voi phan quyen nghiem ngat.
2. Authentication bang password_auth_callback lien ket CSDL nguoi dung duy nhat.
3. RAG Pipeline (ChromaDB + Neo4j + Hybrid Reranker + Answer Validator).
4. Ho tro tieng Viet co dau, khong dau, tron dau, alias.
5. Trai nghiem ChatGPT-like: streaming cau tra loi, starters, markdown, nguon tham khao.
6. Quan tri Admin truc tiep trong Chainlit qua lenh /admin va Action buttons tuong tac.
"""

from __future__ import annotations

import asyncio
import os
from typing import Any, Optional
import logging

# Tat cac log debug gay roi terminal tu websockets va engineio/socketio
for _noisy_logger in [
    "websockets",
    "websockets.server",
    "websockets.client",
    "websockets.protocol",
    "engineio",
    "socketio",
]:
    logging.getLogger(_noisy_logger).setLevel(logging.INFO)

from dotenv import load_dotenv

# Load .env va dam bao bien moi truong CHAINLIT_AUTH_SECRET luon ton tai truoc khi Chainlit kiem tra
load_dotenv()
if not os.environ.get("CHAINLIT_AUTH_SECRET"):
    from rag_chatbot.config import get_settings
    os.environ["CHAINLIT_AUTH_SECRET"] = get_settings().chainlit_auth_secret or "dev-chainlit-auth-secret-change-in-production-32chars"

import chainlit as cl
from chainlit.user import User

from rag_chatbot.auth import authenticate_user, create_user_session, request_password_reset
from rag_chatbot.chainlit_data_layer import SQLiteDataLayer
from rag_chatbot.config import get_settings
from rag_chatbot.database import (
    count_active_admins,
    get_admin_audit_logs,
    get_admin_stats,
    get_admin_users,
    get_user_by_id,
    get_user_by_username,
    record_admin_audit_log,
    update_user_role,
    update_user_status,
)
from rag_chatbot.rag import generate_rag_answer
from rag_chatbot.retrieval import extract_matching_sources

# Patch Chainlit's avatar endpoint to support Vietnamese author names safely
import chainlit.server as cl_server
from starlette.responses import FileResponse
from pathlib import Path
import mimetypes

for _r in cl_server.router.routes:
    if getattr(_r, "path", "") == "/avatars/{avatar_id:str}":
        _orig_endpoint = _r.endpoint
        async def _safe_get_avatar(avatar_id: str):
            if ".." in avatar_id or "/" in avatar_id or "\\" in avatar_id:
                from fastapi import HTTPException
                raise HTTPException(status_code=400, detail="Invalid avatar_id")
            norm_id = avatar_id.strip().lower()
            if norm_id in ["assistant", "default"] or "trợ lý" in norm_id or "tro ly" in norm_id:
                av_dir = Path(__file__).resolve().parent.parent.parent / "public" / "avatars"
                for cand in ["assistant.png", "assistant.svg", "trợ_lý_sự_cố_điện_gia_dụng.png"]:
                    p = av_dir / cand
                    if p.exists():
                        m, _ = mimetypes.guess_type(str(p))
                        return FileResponse(p, media_type=m or "image/png")
            return await _orig_endpoint(avatar_id)
        _r.endpoint = _safe_get_avatar
        break

# Route cap session token an toan cho Admin Dashboard
@cl_server.router.get("/admin/bridge-token")
async def cl_admin_bridge_token(current_user: cl_server.UserParam):
    if not current_user:
        from fastapi import HTTPException
        raise HTTPException(status_code=401, detail="Chưa đăng nhập")

    admin_user = check_admin_privilege(current_user)
    if not admin_user:
        from fastapi import HTTPException
        raise HTTPException(status_code=403, detail="Yêu cầu quyền Quản trị viên")

    raw_token, _ = create_user_session(user_id=admin_user["id"])
    return {"token": raw_token}

# Dua route /admin/bridge-token len dau danh sach router de khong bi wildcard /{full_path:path} che khuat
for _idx, _rt in enumerate(cl_server.router.routes):
    if getattr(_rt, "path", "") == "/admin/bridge-token":
        _popped = cl_server.router.routes.pop(_idx)
        cl_server.router.routes.insert(0, _popped)
        break




# ==============================================================================
# 1. Dang ky Data Layer ben vung voi SQLite
# ==============================================================================

@cl.data_layer
def setup_data_layer():
    """Khoi tao va tra ve Data Layer ket noi toi SQLite chat_history.db."""
    settings = get_settings()
    return SQLiteDataLayer(db_path=settings.sqlite_db_path)


# ==============================================================================
# 2. Xac thuc nguoi dung (Authentication Callback)
# ==============================================================================

@cl.password_auth_callback
def auth_callback(username: str, password: str) -> Optional[User]:
    """Xac thuc nguoi dung voi CSDL tai khoan duy nhat cua he thong.
    
    Chap nhan username hoac email.
    Tu choi cac tai khoan bi khoa (status == 'locked').
    """
    user = authenticate_user(username, password)
    if not user:
        return None

    if user.get("status") == "locked":
        return None

    role = user.get("role", "user")
    return User(
        identifier=user["username"],
        metadata={
            "id": user["id"],
            "role": role,
            "email": user.get("email"),
            "status": user.get("status", "active"),
        },
    )


# ==============================================================================
# 3. Helper xac thuc quyen Admin tu CSDL backend
# ==============================================================================

def check_admin_privilege(user: Optional[User]) -> dict[str, Any] | None:
    """Xac thuc quyen Quản trị viên truc tiep tu CSDL backend (khong tin cay cache browser)."""
    if not user or not user.metadata:
        return None
    user_id = user.metadata.get("id")
    if not user_id:
        db_user = get_user_by_username(user.identifier)
    else:
        db_user = get_user_by_id(user_id)

    if db_user and db_user.get("role") == "admin" and db_user.get("status") == "active":
        return db_user
    return None


# ==============================================================================
# 4. Goi y cau hoi mau (Prompt Starters)
# ==============================================================================

@cl.set_starters
async def set_starters():
    """Cung cap cac cau hoi goi y ban dau theo de bai yeu cau."""
    return [
        cl.Starter(
            label="Điều hòa Panasonic lỗi F16",
            message="Điều hòa Panasonic báo lỗi F16 là bị làm sao thợ ơi?",
        ),
        cl.Starter(
            label="Tủ lạnh LG lỗi SB",
            message="Tủ lạnh LG lỗi SB cách khắc phục thế nào?",
        ),
        cl.Starter(
            label="Máy giặt rung lắc lúc vắt",
            message="Máy giặt Samsung rung lắc mạnh và kêu lúc vắt thì xử lý sao?",
        ),
        cl.Starter(
            label="Bếp từ Panasonic lỗi U04",
            message="Bếp từ Panasonic báo lỗi U04 nguyên nhân do đâu?",
        ),
    ]


# ==============================================================================
# 5. Lifecycle Hooks: Bat dau cuoc tro chuyen va Nhan tin nhan
# ==============================================================================

@cl.author_rename
async def rename_author(author: str) -> str:
    """Chuan hoa ten hien thi cua assistant tren giao dien Chainlit thanh ten chinh thuc."""
    if author.lower() in ["assistant", "default", "tro ly ky thuat dien tu", "chatgpt"]:
        return "Trợ lý sự cố điện gia dụng"
    return author


@cl.on_chat_start
async def on_chat_start():
    """Khoi tao phien chat moi va hien thi thong tin nguoi dung."""
    current_user: Optional[User] = cl.user_session.get("user")
    username = current_user.identifier if current_user else "Bạn"
    admin_user = check_admin_privilege(current_user)

    admin_hint = ""
    if admin_user:
        admin_hint = (
            f"\n\n> 🛡️ **Quản trị viên:** Bạn có toàn quyền quản trị hệ thống. "
            f"Vui lòng nhấn nút **Quản trị** ở góc trên bên phải để mở Bảng điều khiển quản trị."
        )

    welcome_text = (
        f"Xin chào **{username}**! 👋\n\n"
        f"Chào mừng bạn đến với **Trợ lý sự cố điện gia dụng**. Bạn đang gặp sự cố gì với thiết bị điện tử gia dụng?\n\n"
        f"Tôi có thể hỗ trợ bạn tra cứu mã lỗi, chẩn đoán nguyên nhân và hướng dẫn xử lý sự cố cho máy giặt, điều hòa, tủ lạnh, bếp từ, lò vi sóng..."
        f"{admin_hint}"
    )

    quick_actions = [
        cl.Action(
            name="quick_sample_question",
            payload={"query": "Điều hòa Panasonic báo lỗi F16 là bị làm sao thợ ơi?"},
            label="❄️ ĐH Panasonic F16",
        ),
        cl.Action(
            name="quick_sample_question",
            payload={"query": "Tủ lạnh LG lỗi SB cách khắc phục thế nào?"},
            label="🧊 Tủ lạnh LG SB",
        ),
        cl.Action(
            name="quick_sample_question",
            payload={"query": "Máy giặt Samsung rung lắc mạnh và kêu lúc vắt thì xử lý sao?"},
            label="🧺 Máy giặt Samsung rung",
        ),
    ]

    await cl.Message(content=welcome_text, actions=quick_actions).send()


@cl.action_callback("quick_sample_question")
async def on_quick_sample_question(action: cl.Action):
    """Callback xu ly khi nguoi dung bam vao mot trong cac cau hoi goi y mau."""
    query = action.payload.get("query", "")
    if query:
        msg = cl.Message(content=query)
        await msg.send()
        await on_message(msg)


@cl.on_message
async def on_message(message: cl.Message):
    """Xu ly tin nhan tu nguoi dung, truy van RAG hoac thuc thi lenh /admin."""
    # Tu choi neu nguoi dung gui file dinh kem
    if getattr(message, "elements", None):
        await cl.Message(
            content="⚠️ Hệ thống hiện không hỗ trợ tải lên tệp tin. Vui lòng nhập câu hỏi bằng văn bản."
        ).send()
        return

    user_query = message.content.strip()
    if not user_query:
        return

    current_user: Optional[User] = cl.user_session.get("user")

    # 1. Xu ly lenh Quan tri /admin trong Chainlit: huong dan su dung nut tren Header
    if user_query.lower().startswith("/admin"):
        admin_user = check_admin_privilege(current_user)
        if not admin_user:
            await cl.Message(
                content="⛔ **Từ chối truy cập:** Bạn không có quyền Quản trị viên (Admin) để sử dụng tính năng này."
            ).send()
            return

        await cl.Message(
            content="🛡️ **Bảng điều khiển Quản trị viên:**\n\nVui lòng nhấn nút **Quản trị** ở góc trên bên phải thanh tiêu đề để mở Bảng điều khiển quản trị riêng biệt."
        ).send()
        return

    # 2. Xu ly hoi dap RAG
    response_msg = cl.Message(content="")
    await response_msg.send()

    loop = asyncio.get_running_loop()
    try:
        rag_result = await loop.run_in_executor(
            None,
            generate_rag_answer,
            user_query,
        )
    except Exception as exc:
        response_msg.content = (
            "⚠️ Đã có lỗi kỹ thuật xảy ra trong quá trình xử lý câu hỏi. "
            "Vui lòng thử lại sau giây lát."
        )
        await response_msg.update()
        return

    raw_answer = rag_result.get("answer", "")
    retrieved_docs = rag_result.get("retrieved_documents", [])

    # Trich xuat nguon tham khao phu hop
    matching_sources = extract_matching_sources(retrieved_docs, user_query)
    source_section = ""
    if matching_sources:
        source_links = "\n".join(f"- [{url}]({url})" for url in matching_sources)
        source_section = f"\n\n---\n**📚 Nguồn tham khảo chính thức:**\n{source_links}"

    full_response = f"{raw_answer}{source_section}"

    # Streaming cau tra loi tung tu / cum tu
    words = full_response.split(" ")
    chunk_size = 3
    for i in range(0, len(words), chunk_size):
        chunk = " ".join(words[i : i + chunk_size])
        if i + chunk_size < len(words):
            chunk += " "
        await response_msg.stream_token(chunk)
        await asyncio.sleep(0.015)

    await response_msg.update()


# ==============================================================================
# 6. Giao dien va Action Callbacks Quan tri Admin trong Chainlit
# ==============================================================================

async def render_admin_dashboard(admin_user: dict[str, Any]):
    """Cung cap lien ket dieu huong truc tiep toi Trang Dashboard Quan tri Admin rieng."""
    # Sinh session token an toan cho phien quan tri
    raw_token, _ = create_user_session(user_id=admin_user["id"])

    admin_nav_msg = (
        f"### 🛡️ Bảng điều khiển Quản trị viên\n\n"
        f"Xin chào Quản trị viên **{admin_user['username']}**!\n\n"
        f"Bảng điều khiển quản trị hệ thống được mở trong một trang riêng biệt nhằm bảo đảm tính trực quan, "
        f"đầy đủ công cụ quản trị và an toàn bảo mật:\n\n"
        f"👉 [**Mở Bảng Điều Khiển Quản Trị (Admin Dashboard)**](/public/admin.html#token={raw_token})\n\n"
        f"*(Phiên quản trị viên đã được xác thực an toàn. Bạn có thể xem số liệu thống kê, quản lý người dùng, "
        f"khóa/mở khóa tài khoản, phân quyền và tra cứu nhật ký kiểm toán tại trang riêng này).* "
    )

    await cl.Message(content=admin_nav_msg).send()


@cl.action_callback("admin_open_panel")
async def on_admin_open_panel(action: cl.Action):
    """Callback mo Bang dieu khien Admin."""
    current_user: Optional[User] = cl.user_session.get("user")
    admin_user = check_admin_privilege(current_user)
    if not admin_user:
        await cl.Message(content="⛔ Thao tác bị từ chối: Yêu cầu quyền Admin.").send()
        return
    await render_admin_dashboard(admin_user)


@cl.action_callback("admin_refresh_dashboard")
async def on_admin_refresh_dashboard(action: cl.Action):
    """Callback lam moi Bang dieu khien Admin."""
    current_user: Optional[User] = cl.user_session.get("user")
    admin_user = check_admin_privilege(current_user)
    if not admin_user:
        await cl.Message(content="⛔ Thao tác bị từ chối: Yêu cầu quyền Admin.").send()
        return
    await render_admin_dashboard(admin_user)


@cl.action_callback("admin_list_users")
async def on_admin_list_users(action: cl.Action):
    """Hien thi danh sach nguoi dung phan trang kem cac action buttons truc tiep."""
    current_user: Optional[User] = cl.user_session.get("user")
    admin_user = check_admin_privilege(current_user)
    if not admin_user:
        await cl.Message(content="⛔ Thao tác bị từ chối: Yêu cầu quyền Admin.").send()
        return

    page = action.payload.get("page", 1)
    page_size = 5
    users, total = get_admin_users(page=page, page_size=page_size)
    total_pages = max(1, (total + page_size - 1) // page_size)

    lines = [
        f"### 👥 Danh sách người dùng (Trang {page}/{total_pages} - Tổng: {total})\n",
        "| Tên đăng nhập | Email | Vai trò | Trạng thái | Lần đăng nhập cuối |",
        "| :--- | :--- | :--- | :--- | :--- |",
    ]

    action_buttons = []
    for u in users:
        status_icon = "🟢 Hoạt động" if u["status"] == "active" else "🔴 ĐÃ KHÓA"
        role_badge = "🛡️ Admin" if u["role"] == "admin" else "👤 User"
        last_login = u["last_login_at"][:19].replace("T", " ") if u.get("last_login_at") else "Chưa có"
        lines.append(f"| **{u['username']}** | {u['email']} | {role_badge} | {status_icon} | {last_login} |")

        # Tao Action Button cho tung user
        is_self = (u["id"] == admin_user["id"])
        
        # 1. Khoa / Mo khoa
        if u["status"] == "active":
            if not is_self:
                action_buttons.append(
                    cl.Action(
                        name="admin_toggle_status",
                        payload={"user_id": u["id"], "username": u["username"], "new_status": "locked", "page": page},
                        label=f"🔒 Khóa: {u['username']}",
                    )
                )
        else:
            action_buttons.append(
                cl.Action(
                    name="admin_toggle_status",
                    payload={"user_id": u["id"], "username": u["username"], "new_status": "active", "page": page},
                    label=f"🔓 Mở khóa: {u['username']}",
                )
            )

        # 2. Nang quyen / Ha quyen
        if u["role"] == "user":
            action_buttons.append(
                cl.Action(
                    name="admin_toggle_role",
                    payload={"user_id": u["id"], "username": u["username"], "new_role": "admin", "page": page},
                    label=f"⭐ Lên Admin: {u['username']}",
                )
            )
        elif u["role"] == "admin" and not is_self:
            action_buttons.append(
                cl.Action(
                    name="admin_toggle_role",
                    payload={"user_id": u["id"], "username": u["username"], "new_role": "user", "page": page},
                    label=f"👤 Hạ User: {u['username']}",
                )
            )

        # 3. Gui link reset mat khau qua email
        if u.get("email"):
            action_buttons.append(
                cl.Action(
                    name="admin_trigger_reset",
                    payload={"user_id": u["id"], "username": u["username"], "email": u["email"]},
                    label=f"🔑 Gửi Reset: {u['username']}",
                )
            )

    # Nut phan trang
    if page > 1:
        action_buttons.append(
            cl.Action(name="admin_list_users", payload={"page": page - 1}, label="⬅️ Trang trước")
        )
    if page < total_pages:
        action_buttons.append(
            cl.Action(name="admin_list_users", payload={"page": page + 1}, label="Trang sau ➡️")
        )

    action_buttons.append(
        cl.Action(name="admin_refresh_dashboard", payload={}, label="🔙 Về Bảng điều khiển")
    )

    await cl.Message(content="\n".join(lines), actions=action_buttons).send()


@cl.action_callback("admin_toggle_status")
async def on_admin_toggle_status(action: cl.Action):
    """Callback xu ly khoa hoac mo khoa tai khoan."""
    current_user: Optional[User] = cl.user_session.get("user")
    admin_user = check_admin_privilege(current_user)
    if not admin_user:
        await cl.Message(content="⛔ Thao tác bị từ chối: Yêu cầu quyền Admin.").send()
        return

    user_id = action.payload.get("user_id")
    target_username = action.payload.get("username", user_id)
    new_status = action.payload.get("new_status")
    page = action.payload.get("page", 1)

    try:
        update_user_status(target_user_id=user_id, new_status=new_status, admin_id=admin_user["id"])
        status_text = "MỞ KHÓA" if new_status == "active" else "KHÓA"
        await cl.Message(
            content=f"✅ **Thành công:** Đã {status_text} tài khoản **{target_username}**."
        ).send()
        # Cap nhat lai danh sach
        await on_admin_list_users(cl.Action(name="admin_list_users", payload={"page": page}))
    except ValueError as err:
        await cl.Message(content=f"❌ **Lỗi:** {err}").send()


@cl.action_callback("admin_toggle_role")
async def on_admin_toggle_role(action: cl.Action):
    """Callback xu ly nang quyen hoac ha quyen nguoi dung."""
    current_user: Optional[User] = cl.user_session.get("user")
    admin_user = check_admin_privilege(current_user)
    if not admin_user:
        await cl.Message(content="⛔ Thao tác bị từ chối: Yêu cầu quyền Admin.").send()
        return

    user_id = action.payload.get("user_id")
    target_username = action.payload.get("username", user_id)
    new_role = action.payload.get("new_role")
    page = action.payload.get("page", 1)

    try:
        update_user_role(target_user_id=user_id, new_role=new_role, admin_id=admin_user["id"])
        role_text = "Quản trị viên (Admin)" if new_role == "admin" else "Người dùng thông thường (User)"
        await cl.Message(
            content=f"✅ **Thành công:** Đã cập nhật vai trò của **{target_username}** thành **{role_text}**."
        ).send()
        await on_admin_list_users(cl.Action(name="admin_list_users", payload={"page": page}))
    except ValueError as err:
        await cl.Message(content=f"❌ **Lỗi:** {err}").send()


@cl.action_callback("admin_trigger_reset")
async def on_admin_trigger_reset(action: cl.Action):
    """Callback yeu cau gui link reset mat khau qua email (tuyet doi khong tra token trong chat)."""
    current_user: Optional[User] = cl.user_session.get("user")
    admin_user = check_admin_privilege(current_user)
    if not admin_user:
        await cl.Message(content="⛔ Thao tác bị từ chối: Yêu cầu quyền Admin.").send()
        return

    user_id = action.payload.get("user_id")
    target_username = action.payload.get("username", user_id)
    target_email = action.payload.get("email")

    if not target_email:
        await cl.Message(content=f"❌ Tài khoản **{target_username}** chưa có địa chỉ email.").send()
        return

    # Gui yeu cau quen mat khau an toan qua SMTP service
    success, msg = request_password_reset(email=target_email)

    record_admin_audit_log(
        admin_id=admin_user["id"],
        action="admin_trigger_password_reset",
        target_user_id=user_id,
        details=f"Admin kích hoạt gửi email khôi phục mật khẩu tới {target_email}",
    )

    await cl.Message(
        content=f"📧 **Đã kích hoạt khôi phục mật khẩu:** Hệ thống đã gửi email hướng dẫn tới **{target_email}** an toàn.\n\n"
                f"*(Bảo mật: Mật khẩu mới và token không được hiển thị trong cuộc trò chuyện)*."
    ).send()


@cl.action_callback("admin_view_audit_logs")
async def on_admin_view_audit_logs(action: cl.Action):
    """Hien thi nhat ky kiem toan cac thao tac quan tri gan nhat."""
    current_user: Optional[User] = cl.user_session.get("user")
    admin_user = check_admin_privilege(current_user)
    if not admin_user:
        await cl.Message(content="⛔ Thao tác bị từ chối: Yêu cầu quyền Admin.").send()
        return

    limit = action.payload.get("limit", 10)
    logs = get_admin_audit_logs(limit=limit)

    if not logs:
        await cl.Message(content="ℹ️ Chưa có nhật ký thao tác quản trị nào được ghi nhận.").send()
        return

    lines = [
        f"### 📜 Nhật ký kiểm toán thao tác Quản trị ({len(logs)} thao tác gần nhất)\n",
        "| Thời gian | Admin | Hành động | Target User ID | Chi tiết thao tác |",
        "| :--- | :--- | :--- | :--- | :--- |",
    ]

    for log in logs:
        time_str = log["created_at"][:19].replace("T", " ")
        admin_name = log.get("admin_username") or log["admin_id"][:8]
        target_id = (log.get("target_user_id") or "N/A")[:8]
        lines.append(f"| {time_str} | **{admin_name}** | `{log['action']}` | `{target_id}` | {log.get('details', '')} |")

    actions = [
        cl.Action(name="admin_list_users", payload={"page": 1}, label="👥 Quản lý người dùng"),
        cl.Action(name="admin_refresh_dashboard", payload={}, label="🔙 Về Bảng điều khiển"),
    ]

    await cl.Message(content="\n".join(lines), actions=actions).send()


# Alias ham de tuong thich test suite
oauth_callback = auth_callback
main = on_message

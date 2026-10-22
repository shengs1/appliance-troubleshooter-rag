"""Gradio Admin UI for managing accounts, roles, statuses, and security."""

from __future__ import annotations

import math
from typing import Any
import gradio as gr

from rag_chatbot.auth import (
    SESSION_COOKIE_NAME,
    get_user_from_token,
    request_password_reset,
)
from rag_chatbot.database import (
    get_admin_stats,
    get_admin_users,
    get_user_by_id,
    record_admin_audit_log,
    update_user_role,
    update_user_status,
)


CUSTOM_ADMIN_CSS = """
body {
    background: #0b0f19 !important;
    color: #e2e8f0 !important;
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif !important;
}

#admin-shell {
    width: 1180px !important;
    max-width: calc(100vw - 32px) !important;
    margin: 20px auto !important;
}

#access-denied-card {
    max-width: 520px !important;
    margin: 80px auto !important;
    background: #111827 !important;
    padding: 32px !important;
    border-radius: 12px !important;
    border: 1px solid #ef4444 !important;
    text-align: center !important;
    box-shadow: 0 10px 25px -5px rgba(0, 0, 0, 0.5) !important;
}

.panel-card {
    background: #111827 !important;
    border: 1px solid #1f2937 !important;
    border-radius: 10px !important;
    padding: 16px !important;
    margin-bottom: 16px !important;
}

.status-success {
    color: #10b981 !important;
    font-weight: 600 !important;
}

.status-error {
    color: #ef4444 !important;
    font-weight: 600 !important;
}
"""

PAGE_SIZE = 10


def format_stats_html(stats: dict[str, int]) -> str:
    """Sinh ma HTML the thong ke tong quan."""
    total = stats.get("total_users", 0)
    active = stats.get("active_users", 0)
    locked = stats.get("locked_users", 0)
    return f"""
    <div style="display: flex; gap: 16px; margin-bottom: 16px;">
        <div style="flex: 1; background: #1e293b; border: 1px solid #334155; border-radius: 10px; padding: 14px; text-align: center;">
            <div style="font-size: 0.85rem; color: #94a3b8; margin-bottom: 4px;">👥 TỔNG SỐ TÀI KHOẢN</div>
            <div style="font-size: 1.8rem; font-weight: 700; color: #f8fafc;">{total}</div>
        </div>
        <div style="flex: 1; background: #1e293b; border: 1px solid #059669; border-radius: 10px; padding: 14px; text-align: center;">
            <div style="font-size: 0.85rem; color: #34d399; margin-bottom: 4px;">🟢 ĐANG HOẠT ĐỘNG</div>
            <div style="font-size: 1.8rem; font-weight: 700; color: #34d399;">{active}</div>
        </div>
        <div style="flex: 1; background: #1e293b; border: 1px solid #dc2626; border-radius: 10px; padding: 14px; text-align: center;">
            <div style="font-size: 0.85rem; color: #f87171; margin-bottom: 4px;">🔒 BỊ KHÓA</div>
            <div style="font-size: 1.8rem; font-weight: 700; color: #f87171;">{locked}</div>
        </div>
    </div>
    """


def format_table_rows(users: list[dict[str, Any]]) -> list[list[str]]:
    """Dinh dang danh sach user thanh cac dong cho bang gr.Dataframe."""
    rows = []
    for u in users:
        created = u.get("created_at") or ""
        created_display = created[:19].replace("T", " ") if created else ""

        last_login = u.get("last_login_at") or ""
        login_display = last_login[:19].replace("T", " ") if last_login else "Chưa đăng nhập"

        role_display = "⭐ Admin" if u.get("role") == "admin" else "👤 User"
        status_display = "🟢 Active" if u.get("status") == "active" else "🔴 Locked"

        rows.append([
            str(u.get("id", "")),
            str(u.get("username", "")),
            str(u.get("email") or "(Chưa có)"),
            role_display,
            status_display,
            created_display,
            login_display,
        ])
    return rows


def format_user_choices(users: list[dict[str, Any]]) -> list[tuple[str, str]]:
    """Dinh dang danh sach de hien thi trong Dropdown chon nguoi dung."""
    choices: list[tuple[str, str]] = []
    for u in users:
        label = f"{u['username']} ({u.get('role', 'user')}, {u.get('status', 'active')})"
        choices.append((label, str(u["id"])))
    return choices


def build_admin_demo() -> gr.Blocks:
    """Xay dung giao dien Quan tri vien (Admin UI) voi Gradio."""
    with gr.Blocks(title="Quản trị Hệ thống - RAG Chatbot") as demo:
        gr.HTML(f"<style>{CUSTOM_ADMIN_CSS}</style>")
        # State luu tru session cua Admin va trang thai phan trang
        admin_state = gr.State(None)
        page_state = gr.State(1)
        search_state = gr.State("")

        # 1. Man hinh tu choi truy cap (neu chua dang nhap hoac khong phai Admin)
        with gr.Column(elem_id="access-denied-card", visible=False) as access_denied_card:
            gr.Markdown("## 🚫 Truy cập bị từ chối")
            gr.Markdown(
                "Bạn cần đăng nhập bằng tài khoản có quyền **Quản trị viên (Admin)** để truy cập trang này."
            )
            gr.HTML(
                """
                <div style="margin-top: 16px;">
                    <a href="/chat-ui" style="display: inline-block; padding: 8px 18px; background: #3b82f6; color: white; text-decoration: none; border-radius: 6px; font-weight: 600;">
                        ← Về trang Chatbot / Đăng nhập
                    </a>
                </div>
                """
            )

        # 2. Khung quan tri chinh (chi hien khi la Admin hop le)
        with gr.Column(elem_id="admin-shell", visible=False) as admin_shell:
            # Header
            with gr.Row(variant="compact", equal_height=True):
                with gr.Column(scale=3):
                    gr.HTML(
                        """
                        <div style="margin-bottom: 12px;">
                            <h2 style="margin: 0; color: #f8fafc; font-size: 1.5rem;">⚙️ Bảng Điều Khiển Quản Trị (Admin Dashboard)</h2>
                            <p style="margin: 4px 0 0 0; color: #94a3b8; font-size: 0.9rem;">
                                Quản lý danh sách tài khoản, phân quyền vai trò, khóa tài khoản và hỗ trợ khôi phục mật khẩu.
                            </p>
                        </div>
                        """
                    )
                with gr.Column(scale=1):
                    admin_badge = gr.Markdown("👤 **Admin**", elem_id="admin-badge")
                    gr.HTML(
                        """
                        <div style="text-align: right; margin-top: 4px;">
                            <a href="/chat-ui" style="color: #38bdf8; text-decoration: none; font-size: 0.85rem; font-weight: 500;">
                                💬 Quay lại Chatbot
                            </a>
                        </div>
                        """
                    )

            # The thong ke tong quan
            stats_html = gr.HTML(format_stats_html({"total_users": 0, "active_users": 0, "locked_users": 0}))

            # Khu vuc danh sach tai khoan
            with gr.Column(elem_classes=["panel-card"]):
                gr.Markdown("### 📋 Danh sách tài khoản")

                # Thanh tim kiem
                with gr.Row(equal_height=True):
                    search_box = gr.Textbox(
                        placeholder="🔍 Tìm kiếm theo Username hoặc Email...",
                        show_label=False,
                        container=False,
                        scale=4,
                    )
                    search_btn = gr.Button("Tìm kiếm", variant="primary", scale=1)
                    reset_search_btn = gr.Button("Làm mới", variant="secondary", scale=1)

                # Bang danh sach nguoi dung
                table_headers = [
                    "ID",
                    "Username",
                    "Email",
                    "Vai trò",
                    "Trạng thái",
                    "Ngày tạo",
                    "Lần đăng nhập cuối",
                ]
                user_table = gr.Dataframe(
                    headers=table_headers,
                    datatype=["str", "str", "str", "str", "str", "str", "str"],
                    value=[],
                    interactive=False,
                    wrap=True,
                )

                empty_notice = gr.Markdown("Không tìm thấy tài khoản nào phù hợp.", visible=False)

                # Dieu khien phan trang
                with gr.Row(equal_height=True):
                    prev_btn = gr.Button("◀ Trang trước", size="sm", scale=1)
                    page_info = gr.Markdown("**Trang 1 / 1** (Tổng: 0 tài khoản)", scale=2)
                    next_btn = gr.Button("Trang sau ▶", size="sm", scale=1)

            # Khu vuc thao tac quan tri tren mot tai khoan
            with gr.Column(elem_classes=["panel-card"]):
                gr.Markdown("### 🛠️ Thao tác Quản trị Tài khoản")

                with gr.Row():
                    user_select = gr.Dropdown(
                        choices=[],
                        label="Chọn tài khoản để thực hiện thao tác",
                        scale=3,
                        interactive=True,
                    )

                selected_user_detail = gr.Markdown("*(Chọn một tài khoản ở trên để xem chi tiết)*")

                gr.Markdown("#### Thao tác bảo mật và phân quyền:")
                with gr.Row():
                    lock_btn = gr.Button("🔒 Khóa tài khoản", variant="stop")
                    unlock_btn = gr.Button("🔓 Mở khóa tài khoản", variant="secondary")
                    promote_btn = gr.Button("⭐ Nâng lên Admin", variant="primary")
                    demote_btn = gr.Button("👤 Hạ xuống User", variant="secondary")
                    reset_btn = gr.Button("📧 Gửi email đặt lại mật khẩu", variant="secondary")

                confirm_cb = gr.Checkbox(
                    label="Tôi xác nhận thực hiện thao tác quản trị đối với tài khoản được chọn",
                    value=False,
                )
                action_status = gr.Markdown("")

        # ==============================================================
        # Logic su kien (Event Handlers)
        # ==============================================================

        def refresh_admin_view(search_query: str, page: int, admin_user: dict[str, Any] | None):
            """Tai lai toan bo du lieu bang, thong ke va dropdown."""
            if not admin_user or admin_user.get("role") != "admin":
                return (
                    gr.update(visible=True),   # access_denied_card
                    gr.update(visible=False),  # admin_shell
                    "",                        # admin_badge
                    "",                        # stats_html
                    [],                        # user_table
                    gr.update(visible=False),  # empty_notice
                    "",                        # page_info
                    gr.update(choices=[], value=None),  # user_select
                    page,
                    search_query,
                )

            # 1. Thong ke tong quan
            stats = get_admin_stats()
            stats_content = format_stats_html(stats)

            # 2. Danh sach nguoi dung phan trang
            users, total = get_admin_users(search=search_query, page=page, page_size=PAGE_SIZE)
            total_pages = max(1, math.ceil(total / PAGE_SIZE))
            current_page = min(max(1, page), total_pages)

            # Neu trang hien tai vuot qua tong trang do loc tim kiem, truy van lai trang 1
            if current_page != page:
                users, total = get_admin_users(search=search_query, page=current_page, page_size=PAGE_SIZE)

            rows = format_table_rows(users)
            choices = format_user_choices(users)

            is_empty = len(rows) == 0
            page_text = f"**Trang {current_page} / {total_pages}** (Tổng: {total} tài khoản)"

            return (
                gr.update(visible=False),  # access_denied_card
                gr.update(visible=True),   # admin_shell
                f"👤 Quản trị viên: **{admin_user['username']}**",
                stats_content,
                rows,
                gr.update(visible=is_empty),
                page_text,
                gr.update(choices=choices, value=None),
                current_page,
                search_query,
            )

        # 1. Kiem tra xac thuc khi mo trang
        def on_admin_page_load(request: gr.Request | None):
            token = None
            if request and hasattr(request, "cookies"):
                token = request.cookies.get(SESSION_COOKIE_NAME)

            if not token:
                return (
                    gr.update(visible=True),
                    gr.update(visible=False),
                    "",
                    "",
                    [],
                    gr.update(visible=False),
                    "",
                    gr.update(choices=[]),
                    1,
                    "",
                    None,
                )

            user = get_user_from_token(token)
            if not user or user.get("role") != "admin" or user.get("status") == "locked":
                return (
                    gr.update(visible=True),
                    gr.update(visible=False),
                    "",
                    "",
                    [],
                    gr.update(visible=False),
                    "",
                    gr.update(choices=[]),
                    1,
                    "",
                    None,
                )

            res = refresh_admin_view("", 1, user)
            return (*res, user)

        demo.load(
            fn=on_admin_page_load,
            inputs=None,
            outputs=[
                access_denied_card,
                admin_shell,
                admin_badge,
                stats_html,
                user_table,
                empty_notice,
                page_info,
                user_select,
                page_state,
                search_state,
                admin_state,
            ],
        )

        # 2. Tim kiem
        def on_search(query: str, admin_user: dict[str, Any] | None):
            return refresh_admin_view(query.strip(), 1, admin_user)

        search_btn.click(
            fn=on_search,
            inputs=[search_box, admin_state],
            outputs=[
                access_denied_card,
                admin_shell,
                admin_badge,
                stats_html,
                user_table,
                empty_notice,
                page_info,
                user_select,
                page_state,
                search_state,
            ],
        )
        search_box.submit(
            fn=on_search,
            inputs=[search_box, admin_state],
            outputs=[
                access_denied_card,
                admin_shell,
                admin_badge,
                stats_html,
                user_table,
                empty_notice,
                page_info,
                user_select,
                page_state,
                search_state,
            ],
        )

        def on_reset_search(admin_user: dict[str, Any] | None):
            res = refresh_admin_view("", 1, admin_user)
            return ("", *res)

        reset_search_btn.click(
            fn=on_reset_search,
            inputs=[admin_state],
            outputs=[
                search_box,
                access_denied_card,
                admin_shell,
                admin_badge,
                stats_html,
                user_table,
                empty_notice,
                page_info,
                user_select,
                page_state,
                search_state,
            ],
        )

        # 3. Chuyen trang
        def on_prev_page(curr_page: int, search_q: str, admin_user: dict[str, Any] | None):
            new_p = max(1, curr_page - 1)
            return refresh_admin_view(search_q, new_p, admin_user)

        def on_next_page(curr_page: int, search_q: str, admin_user: dict[str, Any] | None):
            new_p = curr_page + 1
            return refresh_admin_view(search_q, new_p, admin_user)

        prev_btn.click(
            fn=on_prev_page,
            inputs=[page_state, search_state, admin_state],
            outputs=[
                access_denied_card,
                admin_shell,
                admin_badge,
                stats_html,
                user_table,
                empty_notice,
                page_info,
                user_select,
                page_state,
                search_state,
            ],
        )
        next_btn.click(
            fn=on_next_page,
            inputs=[page_state, search_state, admin_state],
            outputs=[
                access_denied_card,
                admin_shell,
                admin_badge,
                stats_html,
                user_table,
                empty_notice,
                page_info,
                user_select,
                page_state,
                search_state,
            ],
        )

        # 4. Chon tai khoan de xem chi tiet
        def on_select_user(user_id: str | None):
            if not user_id:
                return "*(Chưa chọn tài khoản nào)*", gr.update(value=False)
            u = get_user_by_id(user_id)
            if not u:
                return "Không tìm thấy thông tin tài khoản.", gr.update(value=False)

            created = u.get("created_at") or ""
            last_login = u.get("last_login_at") or "Chưa từng đăng nhập"

            card = f"""
            **Thông tin tài khoản được chọn:**
            - **ID:** `{u['id']}`
            - **Tên đăng nhập:** `{u['username']}`
            - **Email:** `{u.get('email') or 'Chưa thiết lập'}`
            - **Vai trò hiện tại:** `{'Admin' if u.get('role') == 'admin' else 'User'}`
            - **Trạng thái:** `{'🟢 Hoạt động (active)' if u.get('status') == 'active' else '🔴 Đã khóa (locked)'}`
            - **Ngày đăng ký:** `{created}`
            - **Lần đăng nhập gần nhất:** `{last_login}`
            """
            return card, gr.update(value=False)

        user_select.change(
            fn=on_select_user,
            inputs=[user_select],
            outputs=[selected_user_detail, confirm_cb],
        )

        # 5. Thao tac khoa / mo khoa
        def handle_status_change(
            new_status: str,
            user_id: str | None,
            confirmed: bool,
            admin_user: dict[str, Any] | None,
            search_q: str,
            curr_p: int,
        ):
            if not admin_user or admin_user.get("role") != "admin":
                return "<span class='status-error'>Phiên làm việc hết hạn hoặc không có quyền Admin.</span>", gr.update()

            if not user_id:
                return "<span class='status-error'>Vui lòng chọn một tài khoản để thực hiện.</span>", gr.update()

            if not confirmed:
                return "<span class='status-error'>Vui lòng đánh dấu xác nhận thao tác trước khi thực hiện.</span>", gr.update()

            try:
                update_user_status(
                    target_user_id=user_id,
                    new_status=new_status,
                    admin_id=admin_user["id"],
                )
                action_name = "khóa" if new_status == "locked" else "mở khóa"
                msg = f"<span class='status-success'>Đã {action_name} tài khoản thành công!</span>"
                return msg, gr.update(value=False)
            except ValueError as err:
                return f"<span class='status-error'>Lỗi: {err}</span>", gr.update(value=False)

        def on_lock_click(uid: str | None, conf: bool, adm: dict | None, sq: str, cp: int):
            msg, reset_cb = handle_status_change("locked", uid, conf, adm, sq, cp)
            view_res = refresh_admin_view(sq, cp, adm)
            detail_res, _ = on_select_user(uid)
            return (msg, reset_cb, detail_res, *view_res[2:])

        def on_unlock_click(uid: str | None, conf: bool, adm: dict | None, sq: str, cp: int):
            msg, reset_cb = handle_status_change("active", uid, conf, adm, sq, cp)
            view_res = refresh_admin_view(sq, cp, adm)
            detail_res, _ = on_select_user(uid)
            return (msg, reset_cb, detail_res, *view_res[2:])

        lock_btn.click(
            fn=on_lock_click,
            inputs=[user_select, confirm_cb, admin_state, search_state, page_state],
            outputs=[
                action_status,
                confirm_cb,
                selected_user_detail,
                admin_badge,
                stats_html,
                user_table,
                empty_notice,
                page_info,
                user_select,
                page_state,
                search_state,
            ],
        )

        unlock_btn.click(
            fn=on_unlock_click,
            inputs=[user_select, confirm_cb, admin_state, search_state, page_state],
            outputs=[
                action_status,
                confirm_cb,
                selected_user_detail,
                admin_badge,
                stats_html,
                user_table,
                empty_notice,
                page_info,
                user_select,
                page_state,
                search_state,
            ],
        )

        # 6. Thao tac thay doi vai tro (Admin <-> User)
        def handle_role_change(
            new_role: str,
            user_id: str | None,
            confirmed: bool,
            admin_user: dict[str, Any] | None,
            search_q: str,
            curr_p: int,
        ):
            if not admin_user or admin_user.get("role") != "admin":
                return "<span class='status-error'>Phiên làm việc hết hạn hoặc không có quyền Admin.</span>", gr.update()

            if not user_id:
                return "<span class='status-error'>Vui lòng chọn một tài khoản để thực hiện.</span>", gr.update()

            if not confirmed:
                return "<span class='status-error'>Vui lòng đánh dấu xác nhận thao tác trước khi thực hiện.</span>", gr.update()

            try:
                update_user_role(
                    target_user_id=user_id,
                    new_role=new_role,
                    admin_id=admin_user["id"],
                )
                role_name = "Quản trị viên (Admin)" if new_role == "admin" else "Người dùng thông thường (User)"
                msg = f"<span class='status-success'>Đã cập nhật vai trò thành {role_name} thành công!</span>"
                return msg, gr.update(value=False)
            except ValueError as err:
                return f"<span class='status-error'>Lỗi: {err}</span>", gr.update(value=False)

        def on_promote_click(uid: str | None, conf: bool, adm: dict | None, sq: str, cp: int):
            msg, reset_cb = handle_role_change("admin", uid, conf, adm, sq, cp)
            view_res = refresh_admin_view(sq, cp, adm)
            detail_res, _ = on_select_user(uid)
            return (msg, reset_cb, detail_res, *view_res[2:])

        def on_demote_click(uid: str | None, conf: bool, adm: dict | None, sq: str, cp: int):
            msg, reset_cb = handle_role_change("user", uid, conf, adm, sq, cp)
            view_res = refresh_admin_view(sq, cp, adm)
            detail_res, _ = on_select_user(uid)
            return (msg, reset_cb, detail_res, *view_res[2:])

        promote_btn.click(
            fn=on_promote_click,
            inputs=[user_select, confirm_cb, admin_state, search_state, page_state],
            outputs=[
                action_status,
                confirm_cb,
                selected_user_detail,
                admin_badge,
                stats_html,
                user_table,
                empty_notice,
                page_info,
                user_select,
                page_state,
                search_state,
            ],
        )

        demote_btn.click(
            fn=on_demote_click,
            inputs=[user_select, confirm_cb, admin_state, search_state, page_state],
            outputs=[
                action_status,
                confirm_cb,
                selected_user_detail,
                admin_badge,
                stats_html,
                user_table,
                empty_notice,
                page_info,
                user_select,
                page_state,
                search_state,
            ],
        )

        # 7. Thao tac gui email dat lai mat khau
        def on_reset_email_click(
            user_id: str | None,
            confirmed: bool,
            admin_user: dict[str, Any] | None,
        ):
            if not admin_user or admin_user.get("role") != "admin":
                return "<span class='status-error'>Phiên làm việc hết hạn hoặc không có quyền Admin.</span>", gr.update()

            if not user_id:
                return "<span class='status-error'>Vui lòng chọn một tài khoản để thực hiện.</span>", gr.update()

            if not confirmed:
                return "<span class='status-error'>Vui lòng đánh dấu xác nhận thao tác trước khi thực hiện.</span>", gr.update()

            target_user = get_user_by_id(user_id)
            if not target_user:
                return "<span class='status-error'>Không tìm thấy người dùng.</span>", gr.update(value=False)

            if not target_user.get("email"):
                return "<span class='status-error'>Tài khoản này chưa có email để gửi hướng dẫn đặt lại mật khẩu.</span>", gr.update(value=False)

            # Goi quy trinh khoi phuc mat khau an toan
            request_password_reset(target_user["email"])

            # Ghi nhat ky kiem toan
            record_admin_audit_log(
                admin_id=admin_user["id"],
                action="password_reset_trigger",
                target_user_id=user_id,
                details=f"Admin kích hoạt gửi email đặt lại mật khẩu đến {target_user['email']}",
            )

            msg = f"<span class='status-success'>Đã gửi email hướng dẫn đặt lại mật khẩu đến <b>{target_user['email']}</b>!</span>"
            return msg, gr.update(value=False)

        reset_btn.click(
            fn=on_reset_email_click,
            inputs=[user_select, confirm_cb, admin_state],
            outputs=[action_status, confirm_cb],
        )

    return demo

"""Gradio UI for the appliance troubleshooting RAG chatbot with Auth and Chat History."""

from __future__ import annotations

from typing import Any
from fastapi import HTTPException
import gradio as gr

from rag_chatbot.auth import (
    SESSION_COOKIE_NAME,
    authenticate_user,
    create_user_session,
    get_user_from_token,
    register_user,
    request_password_reset,
    reset_password_with_token,
    revoke_session,
)
from rag_chatbot.database import (
    get_conversation_by_id,
    get_conversation_messages,
    get_user_conversations,
    save_chat_turn,
)
from rag_chatbot.rag import generate_rag_answer
from rag_chatbot.retrieval import extract_matching_sources


SUGGESTIONS = [
    "Samsung lỗi CF là gì?",
    "LG lỗi IE xử lý thế nào?",
    "Panasonic lỗi F11 là gì?",
]

WELCOME_MESSAGE = (
    "Chào bạn! Tôi có thể hỗ trợ tra cứu mã lỗi và khắc phục sự cố "
    "thiết bị điện tử gia dụng.\n\n"
    "Nhập câu hỏi hoặc chọn một câu hỏi mẫu để bắt đầu."
)

CUSTOM_CSS = """
body {
    background: #0b0f19 !important;
    color: #e2e8f0 !important;
}

/* App container */
#app-shell {
    width: 1080px !important;
    max-width: calc(100vw - 32px) !important;
    margin: 0 auto !important;
}

/* Auth container */
#auth-card {
    max-width: 440px !important;
    margin: 60px auto !important;
    background: #111827 !important;
    padding: 28px !important;
    border-radius: 12px !important;
    border: 1px solid #1f2937 !important;
    box-shadow: 0 10px 25px -5px rgba(0, 0, 0, 0.5) !important;
}

#auth-header h2 {
    margin: 0 0 6px 0 !important;
    color: #f8fafc !important;
    font-size: 1.4rem !important;
    text-align: center !important;
}

#auth-header p {
    margin: 0 0 16px 0 !important;
    color: #94a3b8 !important;
    font-size: 0.88rem !important;
    text-align: center !important;
}

/* Header */
#header-row {
    margin-bottom: 12px !important;
    border-bottom: 1px solid #1e293b !important;
    padding-bottom: 8px !important;
}

#app-header h1 {
    margin: 0 0 4px 0 !important;
    color: #f8fafc !important;
    font-size: 1.45rem !important;
    font-weight: 700 !important;
}

#app-header p {
    margin: 0 !important;
    color: #94a3b8 !important;
    font-size: 0.85rem !important;
}

#user-badge {
    text-align: right !important;
    font-size: 0.9rem !important;
    color: #38bdf8 !important;
    font-weight: 500 !important;
}

/* Sidebar */
#sidebar-col {
    background: #111827 !important;
    border: 1px solid #1f2937 !important;
    border-radius: 10px !important;
    padding: 12px !important;
}

#new-chat-btn button {
    width: 100% !important;
    background: #1e293b !important;
    border: 1px solid #334155 !important;
    color: #f8fafc !important;
    font-weight: 600 !important;
    border-radius: 8px !important;
}

#new-chat-btn button:hover {
    background: #334155 !important;
}

#conv-list label {
    display: none !important;
}

#conv-list .wrap {
    gap: 4px !important;
}

#conv-list span {
    font-size: 0.85rem !important;
    color: #cbd5e1 !important;
    white-space: nowrap !important;
    overflow: hidden !important;
    text-overflow: ellipsis !important;
}

/* Chatbot */
#chat-window {
    height: 400px !important;
    min-height: 400px !important;
    border-radius: 10px !important;
    margin-bottom: 10px !important;
    background: #111827 !important;
    border: 1px solid #1f2937 !important;
}

/* Examples / Suggestions */
#suggestions {
    margin: 0 0 10px 0 !important;
    background: transparent !important;
    border: none !important;
}

#suggestions table,
#suggestions tbody {
    display: flex !important;
    flex-wrap: wrap !important;
    gap: 8px !important;
    background: transparent !important;
    border: none !important;
}

#suggestions tr {
    display: inline-flex !important;
    width: auto !important;
    cursor: pointer !important;
    border: 1px solid #334155 !important;
    border-radius: 9999px !important;
    background: #1e293b !important;
    padding: 4px 14px !important;
    transition: all 0.15s ease !important;
}

#suggestions tr:hover {
    background: #334155 !important;
    border-color: #f97316 !important;
}

#suggestions td {
    padding: 0 !important;
    border: none !important;
    white-space: nowrap !important;
    font-size: 0.85rem !important;
    color: #cbd5e1 !important;
}

/* Input */
#msg-input textarea {
    min-height: 48px !important;
    height: 48px !important;
    max-height: 48px !important;
    resize: none !important;
    background: #1e293b !important;
    color: #f8fafc !important;
    border: 1px solid #334155 !important;
}

#send-btn button {
    min-height: 48px !important;
    height: 48px !important;
    width: 100% !important;
    border-radius: 8px !important;
    background: #f97316 !important;
    border-color: #ea580c !important;
    color: #ffffff !important;
    font-weight: 600 !important;
}

#send-btn button:hover {
    background: #ea580c !important;
}

/* Status messages */
.status-success {
    color: #34d399 !important;
    font-size: 0.88rem !important;
}

.status-error {
    color: #f87171 !important;
    font-size: 0.88rem !important;
}

/* Hide Gradio footer */
footer,
.gradio-footer {
    display: none !important;
}

/* An nut ba cham (...) tren tabs va menu header goc phai */
.overflow-menu,
.overflow-dropdown,
button[aria-label="More tabs"],
button[aria-label="More"],
button[aria-label="Options"],
button[aria-label="Dropdown menu"],
.menu-toggle-button,
.options-btn,
.show-api,
.gradio-container > header {
    display: none !important;
}

/* An nut tab Thu 3 va Thu 4 tren thanh tieu de tabs de khong lam tran giao dien */
#auth-tabs div[role="tablist"] > button:nth-child(3),
#auth-tabs div[role="tablist"] > button:nth-child(4),
#auth-tabs .tab-container > button:nth-child(3),
#auth-tabs .tab-container > button:nth-child(4),
#auth-tabs .tab-nav > button:nth-child(3),
#auth-tabs .tab-nav > button:nth-child(4) {
    display: none !important;
}
"""


def chat_fn(
    message: str,
    history: list[dict[str, str]] | None = None,
) -> tuple[list[dict[str, str]], str]:
    """Process one user question and append the RAG response.
    
    Ham nay duoc giu lai de dam bao tuong thich hoan toan voi test_ui.py.
    """
    clean_message = message.strip()
    current_history = list(history or [])

    if not clean_message:
        return current_history, ""

    result = generate_rag_answer(clean_message)
    answer = result.get("answer", "")

    # Trich xuat nguon tham khao tu tai lieu phu hop nhat neu khong bi tu choi
    sources: list[str] = []
    retrieved_docs = result.get("retrieved_documents", [])
    if result.get("llm_status") != "refused_scope" and retrieved_docs:
        sources = extract_matching_sources(retrieved_docs, clean_message)

    validation = result.get("validation")
    if validation and validation.get("status") == "pass" and result.get("llm_status") == "success":
        answer += "\n\n*(Đã kiểm tra câu trả lời theo tài liệu nguồn)*"

    if sources:
        answer += "\n\n**Nguồn tham khảo:**\n" + "\n".join(
            f"- {source}" for source in sources
        )

    current_history.extend(
        [
            {"role": "user", "content": clean_message},
            {"role": "assistant", "content": answer},
        ]
    )

    return current_history, ""


def format_conversation_choices(conversations: list[dict[str, Any]]) -> list[tuple[str, str]]:
    """Chuyen danh sach cuoc tro chuyen thanh danh sach lua chon (label, value) cho Gradio Radio."""
    choices = []
    for conv in conversations:
        # Gioi han do dai tieu de hien thi trong sidebar
        label = conv["title"]
        if len(label) > 30:
            label = label[:28] + "..."
        choices.append((label, conv["id"]))
    return choices


def build_demo() -> gr.Blocks:
    """Build the Gradio interface with authentication and chat history."""
    with gr.Blocks(
        title="Trợ lý Sự cố Điện gia dụng",
        fill_width=False,
    ) as demo:
        # State quan ly phien va cuoc tro chuyen hien tai cua nguoi dung tren tab nay
        user_state = gr.State(None)  # Luu dict {"id": ..., "username": ..., "token": ...}
        conv_state = gr.State(None)  # Luu active conversation_id

        # ==============================================================
        # 1. Man hinh xac thuc (Dang nhap / Dang ky)
        # ==============================================================
        with gr.Column(elem_id="auth-card", visible=True) as auth_card:
            gr.HTML(
                """
                <div id="auth-header">
                    <h2>Trợ lý Sự cố Điện gia dụng</h2>
                    <p>Vui lòng đăng nhập hoặc tạo tài khoản để sử dụng trợ lý và lưu lịch sử trò chuyện.</p>
                </div>
                """
            )

            with gr.Tabs(elem_id="auth-tabs", overflow_behavior="wrap") as auth_tabs:
                # Tab 1: Dang nhap
                with gr.TabItem("Đăng nhập", id="tab-login"):
                    login_username = gr.Textbox(
                        label="Tên đăng nhập hoặc Email",
                        placeholder="Nhập tên đăng nhập hoặc email...",
                        lines=1,
                    )
                    login_password = gr.Textbox(
                        label="Mật khẩu",
                        type="password",
                        placeholder="Nhập mật khẩu...",
                        lines=1,
                    )
                    with gr.Row():
                        forgot_link_btn = gr.Button("🔑 Quên mật khẩu?", variant="secondary", size="sm")
                        login_btn = gr.Button("Đăng nhập", variant="primary", scale=2)
                    login_status = gr.Markdown("", elem_classes=["status-error"])

                # Tab 2: Dang ky
                with gr.TabItem("Đăng ký tài khoản", id="tab-register"):
                    reg_username = gr.Textbox(
                        label="Tên đăng nhập",
                        placeholder="Chọn tên đăng nhập (tối thiểu 3 ký tự)...",
                        lines=1,
                    )
                    reg_email = gr.Textbox(
                        label="Địa chỉ Email (dùng để khôi phục mật khẩu)",
                        placeholder="email@example.com",
                        lines=1,
                    )
                    reg_password = gr.Textbox(
                        label="Mật khẩu",
                        type="password",
                        placeholder="Mật khẩu tối thiểu 6 ký tự...",
                        lines=1,
                    )
                    reg_confirm = gr.Textbox(
                        label="Xác nhận mật khẩu",
                        type="password",
                        placeholder="Nhập lại mật khẩu...",
                        lines=1,
                    )
                    reg_status = gr.Markdown("", elem_classes=["status-error"])
                    reg_btn = gr.Button("Đăng ký", variant="primary")

                # Tab 3: Quen mat khau
                with gr.TabItem("Quên mật khẩu", id="tab-forgot"):
                    gr.Markdown("### 🔑 Quên mật khẩu\nNhập email đã đăng ký. Hệ thống sẽ gửi hướng dẫn và liên kết khôi phục mật khẩu.")
                    forgot_email = gr.Textbox(
                        label="Địa chỉ Email",
                        placeholder="email@example.com",
                        lines=1,
                    )
                    forgot_submit_btn = gr.Button("Gửi yêu cầu khôi phục", variant="primary")
                    forgot_status = gr.Markdown("")
                    with gr.Row():
                        forgot_to_reset_btn = gr.Button("👉 Nhập mã khôi phục (Token)", variant="secondary", size="sm")
                        forgot_back_btn = gr.Button("← Quay lại Đăng nhập", variant="secondary", size="sm")

                # Tab 4: Dat lai mat khau
                with gr.TabItem("Đặt lại mật khẩu", id="tab-reset"):
                    gr.Markdown("### 🔐 Đặt lại mật khẩu\nNhập mã khôi phục (token từ email) và tạo mật khẩu mới.")
                    reset_token_input = gr.Textbox(
                        label="Mã khôi phục (Token)",
                        placeholder="Dán mã khôi phục từ email...",
                        lines=1,
                    )
                    reset_new_password = gr.Textbox(
                        label="Mật khẩu mới",
                        type="password",
                        placeholder="Mật khẩu mới tối thiểu 6 ký tự...",
                        lines=1,
                    )
                    reset_confirm_password = gr.Textbox(
                        label="Xác nhận mật khẩu mới",
                        type="password",
                        placeholder="Nhập lại mật khẩu mới...",
                        lines=1,
                    )
                    reset_submit_btn = gr.Button("Cập nhật mật khẩu mới", variant="primary")
                    reset_status = gr.Markdown("")
                    reset_back_btn = gr.Button("← Quay lại Đăng nhập", variant="secondary", size="sm")

        # ==============================================================
        # 2. Man hinh chinh (Chatbot + Thanh ben Lich su tro chuyen)
        # ==============================================================
        with gr.Column(elem_id="app-shell", visible=False) as main_shell:
            # Header
            with gr.Row(elem_id="header-row", variant="compact", equal_height=True):
                with gr.Column(scale=3):
                    gr.HTML(
                        """
                        <div id="app-header">
                            <h1>Trợ lý Sự cố Điện gia dụng</h1>
                            <p>Tra cứu mã lỗi và hỗ trợ khắc phục sự cố thiết bị điện tử gia dụng.</p>
                        </div>
                        """
                    )
                with gr.Column(scale=1):
                    user_badge = gr.Markdown("👤 **Đang tải...**", elem_id="user-badge")
                    logout_btn = gr.Button(
                        "Đăng xuất",
                        variant="secondary",
                        size="sm",
                    )

            # Khung noi dung chinh: Thanh ben lich su + Cua so chat
            with gr.Row(equal_height=False):
                # Thanh ben: Danh sach cuoc tro chuyen
                with gr.Column(scale=1, min_width=240, elem_id="sidebar-col"):
                    new_chat_btn = gr.Button("➕ Cuộc trò chuyện mới", elem_id="new-chat-btn")
                    gr.Markdown("### 💬 Lịch sử trò chuyện")
                    conv_selector = gr.Radio(
                        choices=[],
                        label="Các cuộc trò chuyện",
                        elem_id="conv-list",
                        interactive=True,
                    )
                    sidebar_status = gr.Markdown("")

                # Khung chinh: Chatbot + Input
                with gr.Column(scale=3):
                    chatbot = gr.Chatbot(
                        placeholder=WELCOME_MESSAGE,
                        height=400,
                        show_label=False,
                        elem_id="chat-window",
                    )

                    msg_input = gr.Textbox(
                        placeholder="Nhập câu hỏi của bạn...",
                        show_label=False,
                        container=False,
                        lines=1,
                        max_lines=1,
                        elem_id="msg-input",
                    )

                    gr.Examples(
                        examples=[[q] for q in SUGGESTIONS],
                        inputs=msg_input,
                        label="Gợi ý câu hỏi",
                        examples_per_page=3,
                        elem_id="suggestions",
                    )

                    with gr.Row(elem_id="input-row", variant="compact", equal_height=True):
                        clear_btn = gr.Button("🗑️", size="sm", variant="secondary", scale=0, min_width=38)
                        send_btn = gr.Button("Gửi", variant="primary", scale=0, min_width=80, elem_id="send-btn")

                    chat_status = gr.Markdown("")

        # ==============================================================
        # 3. Logic su kien va xu ly (Event Handlers)
        # ==============================================================

        # 3.1. Kiem tra cookie session_token hoac token khoi phuc mat khau khi load trang
        def on_page_load(request: gr.Request | None):
            token = None
            if request and hasattr(request, "cookies"):
                token = request.cookies.get(SESSION_COOKIE_NAME)

            if token:
                user = get_user_from_token(token)
                if user:
                    convs = get_user_conversations(user["id"])
                    choices = format_conversation_choices(convs)
                    badge_text = f"👤 **{user['username']}**"
                    if user.get("role") == "admin":
                        badge_text += " *(Admin)* &nbsp;|&nbsp; <a href='/admin-ui' style='color:#38bdf8;text-decoration:none;font-weight:600;'>⚙️ Quản trị</a>"

                    return (
                        gr.update(visible=False),  # auth_card
                        gr.update(visible=True),   # main_shell
                        badge_text,  # user_badge
                        gr.update(choices=choices, value=None),  # conv_selector
                        [],  # chatbot
                        {"id": user["id"], "username": user["username"], "token": token},  # user_state
                        None,  # conv_state
                        gr.update(),  # auth_tabs
                        gr.update(),  # reset_token_input
                        gr.update(),  # reset_status
                    )

            # Kiem tra neu nguoi dung mo lien ket email chua reset_token
            query_reset_token = ""
            if request and hasattr(request, "query_params"):
                query_reset_token = request.query_params.get("reset_token", "")

            if query_reset_token:
                return (
                    gr.update(visible=True),
                    gr.update(visible=False),
                    "",
                    gr.update(choices=[], value=None),
                    [],
                    None,
                    None,
                    gr.update(selected="tab-reset"),
                    query_reset_token,
                    "<span class='status-success'>Đã nạp mã khôi phục từ email. Vui lòng nhập mật khẩu mới.</span>",
                )

            # Neu chua dang nhap
            return (
                gr.update(visible=True),
                gr.update(visible=False),
                "",
                gr.update(choices=[], value=None),
                [],
                None,
                None,
                gr.update(selected="tab-login"),
                "",
                "",
            )

        demo.load(
            fn=on_page_load,
            inputs=None,
            outputs=[auth_card, main_shell, user_badge, conv_selector, chatbot, user_state, conv_state, auth_tabs, reset_token_input, reset_status],
        )

        # 3.2. Xu ly dang nhap
        def on_login(username: str, password: str):
            clean_u = (username or "").strip()
            clean_p = (password or "").strip()
            if not clean_u or not clean_p:
                return (
                    gr.update(visible=True),   # auth_card
                    gr.update(visible=False),  # main_shell
                    "",                        # user_badge
                    gr.update(choices=[]),     # conv_selector
                    [],                        # chatbot
                    "<span class='status-error'>Vui lòng nhập tên đăng nhập và mật khẩu.</span>",  # login_status
                    None,                      # user_state
                    None,                      # conv_state
                )

            try:
                user = authenticate_user(clean_u, clean_p)
            except ValueError as exc:
                return (
                    gr.update(visible=True),
                    gr.update(visible=False),
                    "",
                    gr.update(choices=[]),
                    [],
                    f"<span class='status-error'>{exc}</span>",
                    None,
                    None,
                )

            if not user:
                return (
                    gr.update(visible=True),
                    gr.update(visible=False),
                    "",
                    gr.update(choices=[]),
                    [],
                    "<span class='status-error'>Tên đăng nhập / Email hoặc mật khẩu không chính xác.</span>",
                    None,
                    None,
                )

            raw_token, _ = create_user_session(user["id"])
            convs = get_user_conversations(user["id"])
            choices = format_conversation_choices(convs)

            badge_text = f"👤 **{user['username']}**"
            if user.get("role") == "admin":
                badge_text += " *(Admin)* &nbsp;|&nbsp; <a href='/admin-ui' style='color:#38bdf8;text-decoration:none;font-weight:600;'>⚙️ Quản trị</a>"

            return (
                gr.update(visible=False),
                gr.update(visible=True),
                badge_text,
                gr.update(choices=choices, value=None),
                [],
                "",
                {"id": user["id"], "username": user["username"], "token": raw_token},
                None,
            )

        login_js = """
        async (u, p) => {
            try {
                await fetch('/auth/login', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({username: u, password: p})
                });
            } catch (err) {
                console.error("Login fetch error:", err);
            }
            return [u, p];
        }
        """

        login_btn.click(
            fn=on_login,
            inputs=[login_username, login_password],
            outputs=[auth_card, main_shell, user_badge, conv_selector, chatbot, login_status, user_state, conv_state],
            js=login_js,
        )

        login_password.submit(
            fn=on_login,
            inputs=[login_username, login_password],
            outputs=[auth_card, main_shell, user_badge, conv_selector, chatbot, login_status, user_state, conv_state],
            js=login_js,
        )

        login_username.submit(
            fn=on_login,
            inputs=[login_username, login_password],
            outputs=[auth_card, main_shell, user_badge, conv_selector, chatbot, login_status, user_state, conv_state],
            js=login_js,
        )

        # 3.3. Xu ly dang ky tai khoan
        def on_register(username: str, email: str, password: str, confirm_pass: str):
            clean_u = (username or "").strip()
            clean_email = (email or "").strip()
            if not clean_u:
                return "<span class='status-error'>Vui lòng nhập tên đăng nhập.</span>", ""
            if len(clean_u) < 3:
                return "<span class='status-error'>Tên đăng nhập phải có ít nhất 3 ký tự.</span>", ""
            if not clean_email or "@" not in clean_email:
                return "<span class='status-error'>Vui lòng nhập email hợp lệ để khôi phục tài khoản khi cần.</span>", ""
            if not password or len(password) < 6:
                return "<span class='status-error'>Mật khẩu phải có ít nhất 6 ký tự.</span>", ""
            if password != confirm_pass:
                return "<span class='status-error'>Mật khẩu xác nhận không trùng khớp.</span>", ""

            try:
                register_user(clean_u, password, email=clean_email)
                return "<span class='status-success'>Đăng ký thành công! Vui lòng chuyển sang tab Đăng nhập.</span>", clean_u
            except ValueError as err:
                return f"<span class='status-error'>{err}</span>", ""

        reg_btn.click(
            fn=on_register,
            inputs=[reg_username, reg_email, reg_password, reg_confirm],
            outputs=[reg_status, login_username],
        )

        reg_confirm.submit(
            fn=on_register,
            inputs=[reg_username, reg_email, reg_password, reg_confirm],
            outputs=[reg_status, login_username],
        )

        # 3.4. Xu ly Quen mat khau va Dat lai mat khau
        forgot_link_btn.click(
            fn=lambda: gr.update(selected="tab-forgot"),
            inputs=None,
            outputs=[auth_tabs],
        )

        forgot_to_reset_btn.click(
            fn=lambda: gr.update(selected="tab-reset"),
            inputs=None,
            outputs=[auth_tabs],
        )

        forgot_back_btn.click(
            fn=lambda: gr.update(selected="tab-login"),
            inputs=None,
            outputs=[auth_tabs],
        )

        reset_back_btn.click(
            fn=lambda: gr.update(selected="tab-login"),
            inputs=None,
            outputs=[auth_tabs],
        )

        def on_forgot_submit(email: str, request: gr.Request | None = None):
            clean_email = (email or "").strip()
            if not clean_email or "@" not in clean_email:
                return "<div style='background:rgba(239,68,68,0.15);border:1px solid #ef4444;border-radius:8px;padding:12px;margin-top:10px;color:#f87171;'>⚠️ <b>Vui lòng nhập địa chỉ email hợp lệ.</b></div>"

            client_ip = None
            if request and hasattr(request, "client") and request.client:
                client_ip = request.client.host

            try:
                success, msg = request_password_reset(clean_email, client_ip=client_ip)
            except HTTPException as exc:
                return f"""
                <div style="background: rgba(239, 68, 68, 0.15); border: 1px solid #ef4444; border-radius: 8px; padding: 14px; margin-top: 10px; color: #f87171; font-size: 0.95rem;">
                    <b>⏳ {exc.detail}</b>
                </div>
                """
            except Exception as exc:
                return f"""
                <div style="background: rgba(239, 68, 68, 0.15); border: 1px solid #ef4444; border-radius: 8px; padding: 14px; margin-top: 10px; color: #f87171; font-size: 0.95rem;">
                    <b>⚠️ Lỗi: {exc}</b>
                </div>
                """

            if success:
                return f"""
                <div style="background: rgba(16, 185, 129, 0.15); border: 1px solid #10b981; border-radius: 8px; padding: 14px; margin-top: 10px; color: #34d399; font-size: 0.95rem;">
                    <b>✅ {msg}</b>
                </div>
                """
            return f"""
            <div style="background: rgba(239, 68, 68, 0.15); border: 1px solid #ef4444; border-radius: 8px; padding: 14px; margin-top: 10px; color: #f87171; font-size: 0.95rem;">
                <b>⚠️ {msg}</b>
            </div>
            """

        forgot_submit_btn.click(
            fn=on_forgot_submit,
            inputs=[forgot_email],
            outputs=[forgot_status],
        )

        forgot_email.submit(
            fn=on_forgot_submit,
            inputs=[forgot_email],
            outputs=[forgot_status],
        )

        def on_reset_submit(token: str, new_pass: str, confirm_pass: str):
            clean_token = (token or "").strip()
            if not clean_token:
                return "<div style='background:rgba(239,68,68,0.15);border:1px solid #ef4444;border-radius:8px;padding:12px;margin-top:10px;color:#f87171;'>⚠️ <b>Vui lòng nhập mã khôi phục (token).</b></div>"
            if not new_pass or len(new_pass) < 6:
                return "<div style='background:rgba(239,68,68,0.15);border:1px solid #ef4444;border-radius:8px;padding:12px;margin-top:10px;color:#f87171;'>⚠️ <b>Mật khẩu mới phải có ít nhất 6 ký tự.</b></div>"
            if new_pass != confirm_pass:
                return "<div style='background:rgba(239,68,68,0.15);border:1px solid #ef4444;border-radius:8px;padding:12px;margin-top:10px;color:#f87171;'>⚠️ <b>Mật khẩu xác nhận không trùng khớp.</b></div>"

            try:
                success, msg = reset_password_with_token(clean_token, new_pass)
            except Exception as exc:
                return f"""
                <div style="background: rgba(239, 68, 68, 0.15); border: 1px solid #ef4444; border-radius: 8px; padding: 14px; margin-top: 10px; color: #f87171; font-size: 0.95rem;">
                    <b>⚠️ Lỗi: {exc}</b>
                </div>
                """

            if success:
                return f"""
                <div style="background: rgba(16, 185, 129, 0.15); border: 1px solid #10b981; border-radius: 8px; padding: 14px; margin-top: 10px; color: #34d399; font-size: 0.95rem;">
                    <b>✅ {msg}</b>
                </div>
                """
            return f"""
            <div style="background: rgba(239, 68, 68, 0.15); border: 1px solid #ef4444; border-radius: 8px; padding: 14px; margin-top: 10px; color: #f87171; font-size: 0.95rem;">
                <b>⚠️ {msg}</b>
            </div>
            """

        reset_submit_btn.click(
            fn=on_reset_submit,
            inputs=[reset_token_input, reset_new_password, reset_confirm_password],
            outputs=[reset_status],
        )

        reset_confirm_password.submit(
            fn=on_reset_submit,
            inputs=[reset_token_input, reset_new_password, reset_confirm_password],
            outputs=[reset_status],
        )

        # 3.4. Xu ly dang xuat
        def on_logout(user_data: dict[str, Any] | None):
            if user_data and user_data.get("token"):
                revoke_session(user_data["token"])
            return (
                gr.update(visible=True),   # auth_card
                gr.update(visible=False),  # main_shell
                None,                      # user_state
                None,                      # conv_state
                [],                        # chatbot
                gr.update(choices=[], value=None),  # conv_selector
                "<span class='status-success'>Bạn đã đăng xuất thành công.</span>",
            )

        logout_js = """
        async () => {
            try {
                await fetch('/auth/logout', {method: 'POST'});
            } catch (err) {
                console.error("Logout fetch error:", err);
            }
        }
        """

        logout_btn.click(
            fn=on_logout,
            inputs=[user_state],
            outputs=[auth_card, main_shell, user_state, conv_state, chatbot, conv_selector, login_status],
            js=logout_js,
        )

        # 3.5. Xu ly Tao cuoc tro chuyen moi
        def on_new_chat():
            return (
                None,  # conv_state
                [],    # chatbot
                gr.update(value=None),  # conv_selector
                "",    # msg_input
                "",    # chat_status
            )

        new_chat_btn.click(
            fn=on_new_chat,
            inputs=None,
            outputs=[conv_state, chatbot, conv_selector, msg_input, chat_status],
        )

        # 3.6. Chon cuoc tro chuyen tu danh sach thanh ben
        def on_select_conversation(selected_id: str | None, user_data: dict[str, Any] | None):
            if not selected_id or not user_data:
                return None, [], ""

            # Kiem tra cuoc tro chuyen thuoc so huu cua user
            conv = get_conversation_by_id(selected_id, user_data["id"])
            if not conv:
                return None, [], "<span class='status-error'>Không tìm thấy cuộc trò chuyện.</span>"

            messages = get_conversation_messages(selected_id)
            chat_history = [
                {"role": m["role"], "content": m["content"]}
                for m in messages
            ]
            return selected_id, chat_history, ""

        conv_selector.change(
            fn=on_select_conversation,
            inputs=[conv_selector, user_state],
            outputs=[conv_state, chatbot, chat_status],
        )

        # 3.7. Gui tin nhan va luu lich su vao CSDL
        def on_chat_submit(
            message: str,
            history: list[dict[str, str]] | None,
            user_data: dict[str, Any] | None,
            active_conv_id: str | None,
        ):
            clean_message = (message or "").strip()
            current_history = list(history or [])

            if not clean_message:
                return current_history, "", active_conv_id, gr.update(), ""

            if not user_data:
                return current_history, "", active_conv_id, gr.update(), "<span class='status-error'>Vui lòng đăng nhập để tiếp tục.</span>"

            # 1. Goi quy trinh RAG
            rag_result = generate_rag_answer(clean_message)
            answer = rag_result.get("answer", "")

            # 2. Trich xuat nguon tham khao
            sources: list[str] = []
            retrieved_docs = rag_result.get("retrieved_documents", [])
            if rag_result.get("llm_status") != "refused_scope" and retrieved_docs:
                sources = extract_matching_sources(retrieved_docs, clean_message)

            validation = rag_result.get("validation")
            if validation and validation.get("status") == "pass" and rag_result.get("llm_status") == "success":
                answer += "\n\n*(Đã kiểm tra câu trả lời theo tài liệu nguồn)*"

            if sources:
                answer += "\n\n**Nguồn tham khảo:**\n" + "\n".join(
                    f"- {source}" for source in sources
                )

            # 3. Luu tin nhan user va bot vao CSDL
            try:
                turn = save_chat_turn(
                    user_id=user_data["id"],
                    question=clean_message,
                    answer=answer,
                    conversation_id=active_conv_id,
                )
                saved_conv_id = turn["conversation_id"]
            except Exception as exc:
                return current_history, "", active_conv_id, gr.update(), f"<span class='status-error'>Lỗi lưu dữ liệu: {exc}</span>"

            # 4. Cap nhat lich su hien thi
            current_history.extend(
                [
                    {"role": "user", "content": clean_message},
                    {"role": "assistant", "content": answer},
                ]
            )

            # 5. Cap nhat lai danh sach cuoc tro chuyen o sidebar
            all_convs = get_user_conversations(user_data["id"])
            choices = format_conversation_choices(all_convs)

            return (
                current_history,
                "",
                saved_conv_id,
                gr.update(choices=choices, value=saved_conv_id),
                "",
            )

        send_btn.click(
            fn=on_chat_submit,
            inputs=[msg_input, chatbot, user_state, conv_state],
            outputs=[chatbot, msg_input, conv_state, conv_selector, chat_status],
        )

        msg_input.submit(
            fn=on_chat_submit,
            inputs=[msg_input, chatbot, user_state, conv_state],
            outputs=[chatbot, msg_input, conv_state, conv_selector, chat_status],
        )

        clear_btn.click(
            fn=lambda: ([], ""),
            inputs=None,
            outputs=[chatbot, msg_input],
        )

    return demo


if __name__ == "__main__":
    build_demo().launch()

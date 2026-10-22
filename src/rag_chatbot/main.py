"""Diem khoi dau va API layer cua ung dung RAG Chatbot (FastAPI).

Nhiem vu:
1. Cung cap cac endpoint xac thuc:
   - POST /auth/register: Dang ky tai khoan nguoi dung.
   - POST /auth/login: Dang nhap va thiet lap cookie HttpOnly session_token.
   - POST /auth/logout: Dang xuat va huy phien lam viec.
   - GET /auth/me: Lay thong tin tai khoan dang dang nhap.
2. Cung cap cac endpoint quan ly lich su hoi thoai:
   - GET /conversations: Danh sach cuoc tro chuyen cua user hien tai.
   - GET /conversations/{conversation_id}: Chi tiet cuoc tro chuyen va danh sach tin nhan.
3. Endpoint RAG Chat:
   - POST /chat: Nhan cau hoi, goi pipeline RAG va luu lich su vao SQLite trong transaction.
4. Tich hop giao dien Gradio tai /chat-ui.
"""

from __future__ import annotations

from typing import Any
from fastapi import Depends, FastAPI, HTTPException, Request, Response, status
from pydantic import BaseModel, Field
import gradio as gr

from rag_chatbot.admin_ui import CUSTOM_ADMIN_CSS, build_admin_demo
from rag_chatbot.auth import (
    SESSION_COOKIE_NAME,
    authenticate_user,
    create_user_session,
    get_current_user,
    register_user,
    require_admin,
    request_password_reset,
    reset_password_with_token,
    revoke_session,
)
from rag_chatbot.database import (
    get_admin_stats,
    get_admin_users,
    get_conversation_by_id,
    get_conversation_messages,
    get_user_by_id,
    get_user_conversations,
    init_db,
    record_admin_audit_log,
    save_chat_turn,
    update_user_role,
    update_user_status,
)
from rag_chatbot.rag import generate_rag_answer
from rag_chatbot.retrieval import extract_matching_sources
from rag_chatbot.ui import CUSTOM_CSS, build_demo


# Khoi tao CSDL SQLite cho nguoi dung va lich su hoi thoai
init_db()

# 1. Khoi tao ung dung FastAPI
app = FastAPI(
    title="Vietnamese Electronics Troubleshooting RAG API",
    description="API tra cuu huong dan xu ly su co thiet bi dien tu gia dung su dung RAG",
    version="0.2.0",
)


# 2. Mo hinh du lieu Pydantic (Request / Response)

class RegisterRequest(BaseModel):
    """Du lieu dau vao cho endpoint POST /auth/register."""
    username: str = Field(..., min_length=3, description="Ten dang nhap (toi thieu 3 ky tu)")
    email: str | None = Field(None, description="Email dung de khoi phuc mat khau")
    password: str = Field(..., min_length=6, description="Mat khau (toi thieu 6 ky tu)")


class LoginRequest(BaseModel):
    """Du lieu dau vao cho endpoint POST /auth/login."""
    username: str = Field(..., description="Ten dang nhap hoac email")
    password: str = Field(..., description="Mat khau")


class UserResponse(BaseModel):
    """Thong tin nguoi dung tra ve cho frontend (tuyet doi khong kem mat khau hoac hash)."""
    id: str
    username: str
    email: str | None = None
    role: str = "user"
    status: str = "active"
    created_at: str
    last_login_at: str | None = None


class AdminStatsResponse(BaseModel):
    """So lieu thong ke tong quan cho Admin Dashboard."""
    total_users: int
    active_users: int
    locked_users: int


class AdminUserResponse(BaseModel):
    """Thong tin chi tiet tai khoan hien thi tren Admin Dashboard (khong chua password_hash)."""
    id: str
    username: str
    email: str | None = None
    role: str
    status: str
    created_at: str
    last_login_at: str | None = None


class AdminUserListResponse(BaseModel):
    """Danh sach tai khoan phan trang cho Admin."""
    users: list[AdminUserResponse]
    total: int
    page: int
    page_size: int


class UpdateStatusRequest(BaseModel):
    """Yeu cau cap nhat trang thai tai khoan."""
    status: str = Field(..., description="Trạng thái mới: 'active' hoặc 'locked'")


class UpdateRoleRequest(BaseModel):
    """Yeu cau cap nhat vai tro tai khoan."""
    role: str = Field(..., description="Vai trò mới: 'user' hoặc 'admin'")


class ForgotPasswordRequest(BaseModel):
    """Du lieu dau vao cho endpoint POST /auth/forgot-password."""
    email: str = Field(..., description="Email da dang ky de nhan huong dan khoi phuc")


class ResetPasswordRequest(BaseModel):
    """Du lieu dau vao cho endpoint POST /auth/reset-password."""
    token: str = Field(..., description="Ma token khoi phuc nhan duoc tu email")
    new_password: str = Field(..., min_length=6, description="Mat khau moi (toi thieu 6 ky tu)")


class GenericMessageResponse(BaseModel):
    """Phan hoi thong bao chung."""
    message: str


class LoginResponse(BaseModel):
    """Phan hoi khi dang nhap thanh cong."""
    message: str
    user: UserResponse
    session_token: str | None = None


class MessageItem(BaseModel):
    """Chi tiet mot tin nhan trong cuoc tro chuyen."""
    id: str
    role: str
    content: str
    created_at: str


class ConversationSummary(BaseModel):
    """Thong tin tom tat mot cuoc tro chuyen."""
    id: str
    user_id: str
    title: str
    created_at: str
    updated_at: str


class ConversationDetail(BaseModel):
    """Thong tin chi tiet cuoc tro chuyen kem toan bo tin nhan."""
    id: str
    user_id: str
    title: str
    created_at: str
    updated_at: str
    messages: list[MessageItem]


class ChatRequest(BaseModel):
    """Du lieu dau vao cho endpoint POST /chat."""
    question: str = Field(..., description="Cau hoi cua nguoi dung")
    conversation_id: str | None = Field(None, description="ID cuoc tro chuyen neu muon tiep tuc")


class ChatResponse(BaseModel):
    """Du lieu phan hoi cho endpoint POST /chat."""
    question: str
    answer: str
    llm_status: str
    retrieved_documents: list[dict[str, Any]]
    sources: list[str]
    validation: dict[str, Any] | None = None
    conversation_id: str | None = None


# 3. Cac endpoint he thong co ban

@app.get("/", summary="Root endpoint")
def root() -> dict[str, str]:
    """Endpoint goc thong bao trang thai he thong."""
    return {"message": "RAG Chatbot API is running"}


@app.get("/health", summary="Health check endpoint")
def health() -> dict[str, str]:
    """Endpoint kiem tra suc khoe he thong."""
    return {"status": "ok"}


# 4. Cac endpoint xac thuc (Authentication)

@app.post(
    "/auth/register",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Dang ky tai khoan moi",
)
def register(request: RegisterRequest) -> UserResponse:
    """Dang ky tai khoan moi voi username, password va email khuc phuc."""
    try:
        user = register_user(request.username, request.password, email=request.email)
        return UserResponse(
            id=user["id"],
            username=user["username"],
            email=user.get("email"),
            role=user.get("role", "user"),
            status=user.get("status", "active"),
            created_at=user["created_at"],
            last_login_at=user.get("last_login_at"),
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )


@app.post(
    "/auth/login",
    response_model=LoginResponse,
    summary="Dang nhap va tao phien lam viec",
)
def login(request: LoginRequest, req: Request, response: Response) -> LoginResponse:
    """Xac thuc username/password va thiet lap cookie HttpOnly SameSite=Lax."""
    try:
        user = authenticate_user(request.username, request.password)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(exc),
        )

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Tên đăng nhập hoặc mật khẩu không chính xác.",
        )

    raw_token, _ = create_user_session(user["id"])

    # Thiet lap cookie HttpOnly an toan
    is_secure = req.url.scheme == "https"
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=raw_token,
        httponly=True,
        samesite="lax",
        secure=is_secure,
        max_age=7 * 24 * 3600,
        path="/",
    )

    return LoginResponse(
        message="Đăng nhập thành công.",
        user=UserResponse(
            id=user["id"],
            username=user["username"],
            email=user.get("email"),
            role=user.get("role", "user"),
            status=user.get("status", "active"),
            created_at=user["created_at"],
            last_login_at=user.get("last_login_at"),
        ),
        session_token=raw_token,
    )


@app.post(
    "/auth/forgot-password",
    response_model=GenericMessageResponse,
    summary="Yeu cau khoi phuc mat khau qua email",
)
def forgot_password(request: ForgotPasswordRequest, req: Request) -> GenericMessageResponse:
    """Yeu cau dat lai mat khau qua email. Luon tra ve thong bao chung (anti-enumeration)."""
    client_ip = req.client.host if req.client else None
    success, message = request_password_reset(request.email, client_ip=client_ip)
    if not success:
        if "quá nhiều" in message.lower():
            raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail=message)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=message)
    return GenericMessageResponse(message=message)


@app.post(
    "/auth/reset-password",
    response_model=GenericMessageResponse,
    summary="Dat lai mat khau moi voi token",
)
def reset_password(request: ResetPasswordRequest) -> GenericMessageResponse:
    """Dat lai mat khau moi voi token nhan duoc tu email va vo hieu hoa cac phien dang hoat dong."""
    success, message = reset_password_with_token(request.token, request.new_password)
    if not success:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=message)
    return GenericMessageResponse(message=message)


@app.post(
    "/auth/logout",
    summary="Dang xuat va huy phien",
)
def logout(req: Request, response: Response) -> dict[str, str]:
    """Dang xuat, xoa session trong CSDL va go bo cookie session_token."""
    token = req.cookies.get(SESSION_COOKIE_NAME)
    if not token:
        # Kiem tra header Authorization neu co
        auth_hdr = req.headers.get("Authorization")
        if auth_hdr and auth_hdr.startswith("Bearer "):
            token = auth_hdr.split("Bearer ", 1)[1].strip()

    if token:
        revoke_session(token)

    response.delete_cookie(key=SESSION_COOKIE_NAME, path="/")
    return {"message": "Đăng xuất thành công."}


@app.get(
    "/auth/me",
    response_model=UserResponse,
    summary="Lay thong tin tai khoan hien tai",
)
def me(current_user: dict[str, Any] = Depends(get_current_user)) -> UserResponse:
    """Kiem tra tai khoan dang dang nhap."""
    return UserResponse(
        id=current_user["id"],
        username=current_user["username"],
        email=current_user.get("email"),
        role=current_user.get("role", "user"),
        status=current_user.get("status", "active"),
        created_at=current_user["created_at"],
        last_login_at=current_user.get("last_login_at"),
    )


# 5. Cac endpoint quan ly cuoc tro chuyen (Conversations)

@app.get(
    "/conversations",
    response_model=list[ConversationSummary],
    summary="Liet ke cac cuoc tro chuyen cua user dang dang nhap",
)
def list_conversations(
    current_user: dict[str, Any] = Depends(get_current_user),
) -> list[ConversationSummary]:
    """Lay danh sach cuoc tro chuyen cua tai khoan hien tai."""
    convs = get_user_conversations(current_user["id"])
    return [
        ConversationSummary(
            id=c["id"],
            user_id=c["user_id"],
            title=c["title"],
            created_at=c["created_at"],
            updated_at=c["updated_at"],
        )
        for c in convs
    ]


@app.get(
    "/conversations/{conversation_id}",
    response_model=ConversationDetail,
    summary="Xem chi tiet cuoc tro chuyen va lich su tin nhan",
)
def get_conversation(
    conversation_id: str,
    current_user: dict[str, Any] = Depends(get_current_user),
) -> ConversationDetail:
    """Lay toan bo tin nhan cua mot cuoc tro chuyen. Neu thuoc ve user khac tra ve 404 de bao mat."""
    conv = get_conversation_by_id(conversation_id, current_user["id"])
    if not conv:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Cuộc trò chuyện không tồn tại.",
        )

    raw_messages = get_conversation_messages(conversation_id)
    messages = [
        MessageItem(
            id=m["id"],
            role=m["role"],
            content=m["content"],
            created_at=m["created_at"],
        )
        for m in raw_messages
    ]

    return ConversationDetail(
        id=conv["id"],
        user_id=conv["user_id"],
        title=conv["title"],
        created_at=conv["created_at"],
        updated_at=conv["updated_at"],
        messages=messages,
    )


# 6. Endpoint RAG Chat (co kiem tra xac thuc va luu lich su)

@app.post(
    "/chat",
    response_model=ChatResponse,
    summary="Chat endpoint - Truy van RAG va luu lich su",
)
def chat(
    request: ChatRequest,
    current_user: dict[str, Any] = Depends(get_current_user),
) -> ChatResponse:
    """Tiep nhan cau hoi cua nguoi dung, truy van RAG va luu tin nhan vao lich su cuoc tro chuyen."""
    clean_question = request.question.strip()
    if not clean_question:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Câu hỏi không được để trống.",
        )

    # Neu chi dinh conversation_id, kiem tra quyen so huu truoc khi chay RAG
    if request.conversation_id:
        existing_conv = get_conversation_by_id(request.conversation_id, current_user["id"])
        if not existing_conv:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Cuộc trò chuyện không tồn tại.",
            )

    try:
        # Goi pipeline RAG hien co
        rag_result = generate_rag_answer(clean_question)

        # Trich xuat nguon tham khao neu khong phai rejected scope
        sources: list[str] = []
        retrieved_docs = rag_result.get("retrieved_documents", [])
        if rag_result.get("llm_status") != "refused_scope" and retrieved_docs:
            sources = extract_matching_sources(retrieved_docs, clean_question)

        # Luu ca cau hoi cua user va cau tra loi cua bot trong cung mot transaction
        turn_result = save_chat_turn(
            user_id=current_user["id"],
            question=clean_question,
            answer=rag_result["answer"],
            conversation_id=request.conversation_id,
        )

        return ChatResponse(
            question=rag_result["question"],
            answer=rag_result["answer"],
            llm_status=rag_result["llm_status"],
            retrieved_documents=rag_result.get("retrieved_documents", []),
            sources=sources,
            validation=rag_result.get("validation"),
            conversation_id=turn_result["conversation_id"],
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Lỗi hệ thống khi xử lý câu hỏi: {exc}",
        )


# 7. Cac endpoint Quan tri he thong (Admin API)

@app.get(
    "/admin/stats",
    response_model=AdminStatsResponse,
    summary="Thống kê tổng quan người dùng cho Quản trị viên",
)
def admin_get_stats(
    current_admin: dict[str, Any] = Depends(require_admin),
) -> AdminStatsResponse:
    """Tra ve thong ke tong so tai khoan, so tai khoan hoat dong va bi khoa."""
    stats = get_admin_stats()
    return AdminStatsResponse(**stats)


@app.get(
    "/admin/users",
    response_model=AdminUserListResponse,
    summary="Lấy danh sách người dùng phân trang và tìm kiếm",
)
def admin_get_users(
    search: str | None = None,
    page: int = 1,
    page_size: int = 10,
    current_admin: dict[str, Any] = Depends(require_admin),
) -> AdminUserListResponse:
    """Tra ve danh sach nguoi dung duoc phan trang, tim kiem theo ten dang nhap hoac email."""
    users, total = get_admin_users(search=search, page=page, page_size=page_size)
    return AdminUserListResponse(
        users=[AdminUserResponse(**u) for u in users],
        total=total,
        page=page,
        page_size=page_size,
    )


@app.get(
    "/admin/users/{user_id}",
    response_model=AdminUserResponse,
    summary="Xem chi tiết thông tin cơ bản một người dùng",
)
def admin_get_user(
    user_id: str,
    current_admin: dict[str, Any] = Depends(require_admin),
) -> AdminUserResponse:
    """Tra ve thong tin co ban cua mot nguoi dung (khong co password_hash)."""
    user = get_user_by_id(user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Người dùng không tồn tại.",
        )
    return AdminUserResponse(**user)


@app.patch(
    "/admin/users/{user_id}/status",
    response_model=AdminUserResponse,
    summary="Khóa hoặc mở khóa tài khoản người dùng",
)
def admin_update_user_status(
    user_id: str,
    payload: UpdateStatusRequest,
    current_admin: dict[str, Any] = Depends(require_admin),
) -> AdminUserResponse:
    """Cap nhat trang thai tai khoan: 'active' hoac 'locked'.
    Tu dong kiem tra chong tu khoa va chong khoa Admin cuoi cung."""
    try:
        updated = update_user_status(
            target_user_id=user_id,
            new_status=payload.status,
            admin_id=current_admin["id"],
        )
        return AdminUserResponse(**updated)
    except ValueError as err:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(err),
        )


@app.patch(
    "/admin/users/{user_id}/role",
    response_model=AdminUserResponse,
    summary="Thay đổi vai trò người dùng (user <-> admin)",
)
def admin_update_user_role(
    user_id: str,
    payload: UpdateRoleRequest,
    current_admin: dict[str, Any] = Depends(require_admin),
) -> AdminUserResponse:
    """Thay doi vai tro cua tai khoan giua 'user' va 'admin'.
    Tu dong kiem tra chong tu ha quyen va chong ha quyen Admin cuoi cung."""
    try:
        updated = update_user_role(
            target_user_id=user_id,
            new_role=payload.role,
            admin_id=current_admin["id"],
        )
        return AdminUserResponse(**updated)
    except ValueError as err:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(err),
        )


@app.post(
    "/admin/users/{user_id}/password-reset",
    response_model=GenericMessageResponse,
    summary="Admin kích hoạt gửi email đặt lại mật khẩu cho người dùng",
)
def admin_trigger_password_reset(
    user_id: str,
    current_admin: dict[str, Any] = Depends(require_admin),
) -> GenericMessageResponse:
    """Admin gui huong dan dat lai mat khau toi email cua tai khoan qua luong quen mat khau an toan."""
    target_user = get_user_by_id(user_id)
    if not target_user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Người dùng không tồn tại.",
        )
    if not target_user.get("email"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Tài khoản này chưa có email để gửi liên kết đặt lại mật khẩu.",
        )

    # Goi quy trinh quen mat khau an toan
    request_password_reset(email=target_user["email"])

    # Ghi nhat ky kiem toan thao tac quan tri
    record_admin_audit_log(
        admin_id=current_admin["id"],
        action="password_reset_trigger",
        target_user_id=user_id,
        details=f"Admin kích hoạt gửi email đặt lại mật khẩu tới {target_user['email']}",
    )
    return GenericMessageResponse(
        message=f"Đã gửi hướng dẫn đặt lại mật khẩu đến email {target_user['email']} thành công."
    )


@app.get("/admin", include_in_schema=False)
def redirect_to_admin_ui():
    """Chuyen huong tu /admin sang /admin-ui."""
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url="/admin-ui", status_code=status.HTTP_307_TEMPORARY_REDIRECT)


# 8. Tich hop giao dien web Gradio vao FastAPI
# Giao dien Chatbot tai /chat-ui
demo = build_demo()
gr.mount_gradio_app(
    app,
    demo,
    path="/chat-ui",
    css=CUSTOM_CSS,
)

# Giao dien Quan tri tai /admin-ui
admin_demo = build_admin_demo()
gr.mount_gradio_app(
    app,
    admin_demo,
    path="/admin-ui",
    css=CUSTOM_ADMIN_CSS,
)

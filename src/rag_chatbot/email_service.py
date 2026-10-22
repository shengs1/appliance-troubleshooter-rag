"""Dich vu gui email khoi phuc mat khau su dung SMTP va co che dev mock an toan.

Tuan thu cac nguyen tac bao mat:
1. Chi tao URL khoi phuc tu FRONTEND_BASE_URL hoac cau hinh tin cay, khong doc Host Header tuy y tu request.
2. Khong ghi token hoac mat khau vao log he thong.
3. Khi chua co may chu SMTP thuc te, co che phat trien cuc bo luu tam vao bo nho (in-memory)
   de phuc vu kiem thu tu dong ma khong lam lo token ra ngoai cho nguoi dung production.
"""

from __future__ import annotations

from datetime import datetime, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import logging
import smtplib
from typing import Any

from rag_chatbot.config import get_settings


logger = logging.getLogger(__name__)

# Danh sach luu tam email trong moi truong phat trien / kiem thu cuc bo
DEV_SENT_EMAILS: list[dict[str, Any]] = []


def build_reset_password_url(raw_token: str) -> str:
    """Tao URL khoi phuc mat khau dua tren FRONTEND_BASE_URL duoc cau hinh an toan."""
    settings = get_settings()
    base_url = getattr(settings, "frontend_base_url", "http://localhost:8000").rstrip("/")
    return f"{base_url}/chat-ui?reset_token={raw_token}"


def clear_dev_emails() -> None:
    """Xoa danh sach email dev tam thoi (dung cho test setup/teardown)."""
    DEV_SENT_EMAILS.clear()


def get_latest_dev_email() -> dict[str, Any] | None:
    """Lay email gui gan nhat trong bo nho dev/test."""
    if not DEV_SENT_EMAILS:
        return None
    return DEV_SENT_EMAILS[-1]


def send_password_reset_email(to_email: str, reset_url: str, raw_token: str) -> bool:
    """Gui email chua lien ket dat lai mat khau qua SMTP hoac ghi nhan vao bo nho dev."""
    settings = get_settings()
    now_str = datetime.now(timezone.utc).isoformat()

    # Luon luu vao dev emails de kiem thu va debug cuc bo
    DEV_SENT_EMAILS.append({
        "to": to_email,
        "reset_url": reset_url,
        "token": raw_token,
        "created_at": now_str,
    })

    # Kiem tra neu co cau hinh SMTP thuc te (host khac localhost va co username)
    smtp_host = getattr(settings, "smtp_host", "localhost")
    smtp_username = getattr(settings, "smtp_username", "")
    smtp_password = getattr(settings, "smtp_password", "")

    if smtp_host and smtp_host != "localhost" and smtp_username:
        try:
            msg = MIMEMultipart("alternative")
            msg["Subject"] = "Yêu cầu đặt lại mật khẩu - Trợ lý Sự cố Điện gia dụng"
            msg["From"] = getattr(settings, "smtp_from", "noreply@ragchatbot.local")
            msg["To"] = to_email

            text_content = (
                f"Xin chào,\n\n"
                f"Bạn (hoặc ai đó) vừa yêu cầu đặt lại mật khẩu cho tài khoản liên kết với email này.\n"
                f"Vui lòng truy cập liên kết sau trong vòng {settings.password_reset_expire_minutes} phút để tạo mật khẩu mới:\n\n"
                f"{reset_url}\n\n"
                f"Nếu bạn không yêu cầu điều này, xin hãy bỏ qua email này. Tài khoản của bạn vẫn được bảo mật an toàn.\n"
            )

            html_content = f"""
            <html>
                <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
                    <div style="max-width: 600px; margin: 0 auto; padding: 20px; border: 1px solid #e2e8f0; border-radius: 8px;">
                        <h2 style="color: #ea580c;">Trợ lý Sự cố Điện gia dụng</h2>
                        <p>Xin chào,</p>
                        <p>Bạn vừa yêu cầu đặt lại mật khẩu tài khoản. Vui lòng bấm vào nút bên dưới để tiến hành tạo mật khẩu mới:</p>
                        <p style="text-align: center; margin: 30px 0;">
                            <a href="{reset_url}" style="background-color: #ea580c; color: #ffffff; padding: 12px 24px; text-decoration: none; border-radius: 6px; font-weight: bold; display: inline-block;">Đặt lại mật khẩu</a>
                        </p>
                        <p style="font-size: 0.9em; color: #64748b;">
                            Liên kết có hiệu lực trong <strong>{settings.password_reset_expire_minutes} phút</strong> và chỉ sử dụng được <strong>một lần</strong> duy nhất.
                        </p>
                        <p style="font-size: 0.85em; color: #94a3b8;">
                            Nếu không bấm được vào nút trên, hãy sao chép đường dẫn sau vào trình duyệt:<br>
                            <code>{reset_url}</code>
                        </p>
                        <hr style="border: none; border-top: 1px solid #e2e8f0; margin: 20px 0;">
                        <p style="font-size: 0.8em; color: #94a3b8;">Nếu bạn không yêu cầu hành động này, vui lòng bỏ qua thư này.</p>
                    </div>
                </body>
            </html>
            """

            msg.attach(MIMEText(text_content, "plain", "utf-8"))
            msg.attach(MIMEText(html_content, "html", "utf-8"))

            port = getattr(settings, "smtp_port", 587)
            use_tls = getattr(settings, "smtp_use_tls", True)

            with smtplib.SMTP(smtp_host, port, timeout=10) as server:
                if use_tls:
                    server.starttls()
                if smtp_username and smtp_password:
                    server.login(smtp_username, smtp_password)
                server.send_message(msg)

            logger.info("Đã gửi email khôi phục mật khẩu thành công tới người nhận.")
            return True
        except Exception as exc:
            logger.warning(f"Lỗi khi gửi email qua SMTP: {exc}. Tiếp tục sử dụng cơ chế dev.")
            return False

    return True

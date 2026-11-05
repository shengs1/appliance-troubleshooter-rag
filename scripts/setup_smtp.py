"""Script quan tri va bao mat cau hinh Brevo SMTP trong Co so du lieu SQLite.

Tuan thu cac co che bao mat:
1. Ma hoa doi xung AES Fernet truoc khi luu vao SQLite (khong bao gio luu plaintext trong DB).
2. Co che Ma so tu xoa khan cap (Master Wipe Code): Khi nhap ma nay, he thong tu dong xoa sach
   tai khoan SMTP va cho phep dieu chinh ngay ma khong can mat khau cu.
3. Sau khi dieu chinh xong, he thong yeu cau thiet lap ma PIN bao ve moi cho cac lan sua sau.
4. An ky tu mat khau / SMTP key khi nhap qua terminal (getpass).
"""

from __future__ import annotations

import argparse
import getpass
import smtplib
import sys
from pathlib import Path

# Them thu muc goc src vao sys.path de import cac module du an
src_path = Path(__file__).resolve().parent.parent / "src"
if str(src_path) not in sys.path:
    sys.path.insert(0, str(src_path))

from rag_chatbot.database import (
    get_smtp_config_from_db,
    has_smtp_config,
    init_db,
    purge_smtp_config_from_db,
    save_smtp_config_to_db,
    set_smtp_admin_pin,
    set_smtp_wipe_code,
    verify_smtp_admin_pin,
    verify_smtp_wipe_code,
)


def mask_secret(secret: str) -> str:
    """Che bot ky tu cua mat khau / API key de hien thi an toan."""
    if not secret:
        return "(chưa thiết lập)"
    if len(secret) <= 10:
        return "••••••••"
    return secret[:6] + "••••••••" + secret[-4:]


def test_smtp_connection(host: str, port: int, username: str, password: str, use_tls: bool = True) -> tuple[bool, str]:
    """Kiem tra ket noi va xac thuc voi may chu SMTP Brevo."""
    try:
        with smtplib.SMTP(host, port, timeout=10) as server:
            if use_tls:
                server.starttls()
            server.login(username, password)
            return True, "Xác thực tài khoản Brevo SMTP thành công 100%!"
    except Exception as exc:
        return False, f"Lỗi xác thực: {exc}"


def show_current_config() -> None:
    """Hien thi trang thai cau hinh SMTP hien tai trong CSDL."""
    cfg = get_smtp_config_from_db()
    print("\n" + "=" * 65)
    print("        TRẠNG THÁI CẤU HÌNH SMTP HIỆN TẠI TRONG CSDL")
    print("=" * 65)
    if not cfg:
        print("  Trạng thái: CHƯA THIẾT LẬP (Đang dùng chế độ Dev Mock)")
    else:
        print("  Trạng thái: ĐÃ CẤU HÌNH (Mã hóa an toàn bằng AES Fernet)")
        print(f"  Máy chủ (Host):     {cfg.get('host')}")
        print(f"  Cổng (Port):        {cfg.get('port')}")
        print(f"  Tên đăng nhập:      {cfg.get('username')}")
        print(f"  Email gửi (From):   {cfg.get('from_email')}")
        print(f"  Khóa SMTP (Key):    {mask_secret(cfg.get('password', ''))}")
        print(f"  Bật TLS:            {'Có' if cfg.get('use_tls') else 'Không'}")
    print("=" * 65 + "\n")


def interactive_setup_flow() -> None:
    """Quy trinh nhap thong tin SMTP moi va thiet lap ma PIN bao ve cho lan sau."""
    print("\n--- BẮT ĐẦU THIẾT LẬP CẤU HÌNH SMTP MỚI ---")
    host = input("Máy chủ SMTP Host [mặc định: smtp-relay.brevo.com]: ").strip() or "smtp-relay.brevo.com"
    port_str = input("Cổng Port [mặc định: 587]: ").strip() or "587"
    try:
        port = int(port_str)
    except ValueError:
        port = 587

    username = input("Tên đăng nhập / Email Brevo: ").strip()
    if not username:
        print("[LỖI] Tên đăng nhập không được để trống.")
        return

    key = getpass.getpass("Mã khóa SMTP Key (ký tự được ẩn): ").strip()
    if not key:
        print("[LỖI] SMTP Key không được để trống.")
        return

    from_email = input(f"Email người gửi (Verified Sender) [mặc định: {username}]: ").strip() or username

    print(f"\nĐang kiểm tra kết nối với {host}:{port}...")
    ok, msg = test_smtp_connection(host, port, username, key)
    if ok:
        print(f"[THÀNH CÔNG] {msg}")
    else:
        print(f"[CẢNH BÁO] {msg}")
        confirm = input("Vẫn muốn lưu cấu hình này vào CSDL? (y/n): ").strip().lower()
        if confirm != "y":
            print("Đã hủy lưu cấu hình.")
            return

    # Luu cau hinh ma hoa vao CSDL
    save_smtp_config_to_db(host, port, username, key, from_email, use_tls=True)
    print("\n[THÀNH CÔNG] Đã mã hóa và lưu thông tin Brevo SMTP vào CSDL SQLite an toàn!")

    # Yeu cau dat ma PIN bao ve cho cac lan sua sau
    print("\n--- THIẾT LẬP MÃ PIN BẢO VỆ CHO CÁC LẦN CHỈNH SỬA SAU ---")
    new_pin = getpass.getpass("Nhập mã PIN bảo vệ mới [mặc định 88889999]: ").strip() or "88889999"
    confirm_pin = getpass.getpass(f"Xác nhận lại mã PIN mới [{new_pin}]: ").strip() or new_pin
    if new_pin != confirm_pin:
        print("[CẢNH BÁO] Xác nhận không khớp, hệ thống áp dụng mã PIN mặc định 88889999.")
        new_pin = "88889999"

    set_smtp_admin_pin(new_pin)
    print(f"[HOÀN TẤT] Đã thiết lập mã PIN bảo vệ thành công! Từ lần sau, bạn cần nhập mã PIN này để chỉnh sửa.")


def main() -> None:
    init_db()

    parser = argparse.ArgumentParser(description="Script quan ly cau hinh Brevo SMTP an toan trong SQLite.")
    parser.add_argument("--pin", "-p", type=str, help="Ma PIN bao ve quan tri (mac dinh: 88889999)")
    parser.add_argument("--wipe-code", "-w", type=str, help="Ma so xoa khan cap de tu dong xoa cau hinh cu (mac dinh: 123456789)")
    parser.add_argument("--purge", action="store_true", help="Yeu cau xoa sach cau hinh SMTP cu")
    parser.add_argument("--host", type=str, default="smtp-relay.brevo.com", help="Dia chi SMTP Host")
    parser.add_argument("--port", type=int, default=587, help="Cong ket noi SMTP (587)")
    parser.add_argument("--username", "-u", type=str, help="Email / Ten dang nhap Brevo")
    parser.add_argument("--key", "-k", type=str, help="Khoa SMTP Key cua Brevo")
    parser.add_argument("--from-email", "-f", type=str, help="Email nguoi gui (Verified Sender)")
    parser.add_argument("--test", action="store_true", help="Kiem tra ket noi voi thong tin da luu")
    parser.add_argument("--set-pin", type=str, help="Doi ma PIN bao ve moi")

    args = parser.parse_args()

    # Kiem tra neu nguoi dung truyen ma so xoa khan cap qua CLI
    if args.wipe_code or args.purge:
        input_code = args.wipe_code or args.pin
        if input_code and verify_smtp_wipe_code(input_code):
            purge_smtp_config_from_db()
            print("[THÀNH CÔNG] Đã tự động xóa sạch tài khoản SMTP cũ khỏi CSDL bằng Mã số xóa khẩn cấp!")
            if not args.username:
                sys.exit(0)
        else:
            print("[LỖI BẢO MẬT] Mã số xóa khẩn cấp không chính xác!")
            sys.exit(1)

    # TRƯỜNG HỢP 1: Chua co cau hinh SMTP trong CSDL (hoac vua bi xoa sach)
    # Khong yeu cau mat khau, cho phep thiet lap truc tiep ngay
    if not has_smtp_config():
        print("\n" + "=" * 65)
        print(" [CHẾ ĐỘ THIẾT LẬP BAN ĐẦU - CHƯA CÓ CẤU HÌNH SMTP TRONG CSDL]")
        print(" Bạn có thể thiết lập ngay tài khoản mới mà KHÔNG CẦN mật khẩu cũ.")
        print("=" * 65)

        if args.username and args.key:
            from_email = args.from_email or args.username
            save_smtp_config_to_db(args.host, args.port, args.username, args.key, from_email, use_tls=True)
            new_pin = args.set_pin or "88889999"
            set_smtp_admin_pin(new_pin)
            print(f"[THÀNH CÔNG] Đã lưu cấu hình Brevo SMTP và thiết lập mã PIN bảo mật: {new_pin}")
            sys.exit(0)

        interactive_setup_flow()
        sys.exit(0)

    # TRƯỜNG HỢP 2: Da co cau hinh SMTP trong CSDL
    # Yeu cau nhap PIN quan tri HOAC nhap Ma so xoa khan cap (Wipe Code)
    pin = args.pin
    if not pin:
        try:
            print("\n" + "=" * 65)
            print(" HỆ THỐNG ĐÃ CÓ CẤU HÌNH SMTP ĐƯỢC MÃ HÓA BẢO VỆ")
            print(" - Nhập mã PIN (88889999) để vào Menu điều chỉnh.")
            print(" - Hoặc nhập Mã số xóa khẩn cấp (123456789) để TỰ ĐỘNG XÓA SẠCH.")
            print("=" * 65)
            pin = getpass.getpass("Nhập mã PIN hoặc Mã số xóa khẩn cấp: ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\nĐã hủy thao tác.")
            sys.exit(1)

    # Kiem tra xem co phai Ma so xoa khan cap khong
    if verify_smtp_wipe_code(pin):
        print("\n" + "*" * 65)
        print(" [XÁC NHẬN MÃ SỐ XÓA KHẨN CẤP THÀNH CÔNG!]")
        print(" Toàn bộ tài khoản SMTP cũ đã được tự động xóa hoàn toàn khỏi CSDL.")
        print(" Bạn có thể thiết lập cấu hình mới ngay bây giờ mà KHÔNG CẦN mật khẩu cũ.")
        print("*" * 65)
        purge_smtp_config_from_db()

        if args.username and args.key:
            from_email = args.from_email or args.username
            save_smtp_config_to_db(args.host, args.port, args.username, args.key, from_email, use_tls=True)
            new_pin = args.set_pin or "88889999"
            set_smtp_admin_pin(new_pin)
            print(f"[THÀNH CÔNG] Đã lưu cấu hình mới và thiết lập mã PIN bảo mật: {new_pin}")
            sys.exit(0)

        interactive_setup_flow()
        sys.exit(0)

    # Neu khong phai ma xoa, kiem tra ma PIN quan tri binh thuong
    if not verify_smtp_admin_pin(pin):
        print("\n[LỖI BẢO MẬT] Mã PIN hoặc Mã xóa khẩn cấp không chính xác! Quyền truy cập bị từ chối.")
        sys.exit(1)

    print("\n[XÁC THỰC THÀNH CÔNG] Quyền quản trị SMTP đã được mở khóa.")

    # Xu ly doi PIN qua CLI
    if args.set_pin:
        set_smtp_admin_pin(args.set_pin)
        print(f"[THÀNH CÔNG] Đã cập nhật mã PIN bảo vệ mới thành công!")
        sys.exit(0)

    # Menu tuong tac quan tri
    while True:
        show_current_config()
        print("CÁC TÙY CHỌN QUẢN TRỊ:")
        print("  1. Cập nhật cấu hình Brevo SMTP")
        print("  2. Kiểm tra kết nối máy chủ Brevo")
        print("  3. Đổi mã PIN bảo vệ quản trị")
        print("  4. Đổi Mã số xóa khẩn cấp (Wipe Code)")
        print("  5. Tự xóa cấu hình SMTP (Hủy tài khoản khỏi CSDL)")
        print("  0. Thoát")

        try:
            choice = input("\nChọn thao tác (0-5): ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\nĐã thoát.")
            break

        if choice == "0":
            print("Đã thoát công cụ quản trị.")
            break
        elif choice == "1":
            interactive_setup_flow()
        elif choice == "2":
            cfg = get_smtp_config_from_db()
            if not cfg:
                print("\n[THÔNG BÁO] Chưa có cấu hình SMTP trong CSDL.")
                continue
            print(f"\nĐang kiểm tra kết nối tới {cfg['host']}:{cfg['port']}...")
            ok, msg = test_smtp_connection(cfg["host"], cfg["port"], cfg["username"], cfg["password"], cfg.get("use_tls", True))
            if ok:
                print(f"[THÀNH CÔNG] {msg}")
            else:
                print(f"[THẤT BẠI] {msg}")
        elif choice == "3":
            try:
                new_p = getpass.getpass("Nhập mã PIN bảo vệ mới: ").strip()
                confirm_p = getpass.getpass("Xác nhận lại mã PIN mới: ").strip()
                if new_p != confirm_p:
                    print("[LỖI] Hai lần nhập mã PIN không khớp nhau.")
                    continue
                if len(new_p) < 4:
                    print("[LỖI] Mã PIN phải có ít nhất 4 ký tự.")
                    continue
                set_smtp_admin_pin(new_p)
                print("[THÀNH CÔNG] Đã đổi mã PIN bảo vệ thành công!")
            except Exception as e:
                print(f"[LỖI] Không thể đổi mã PIN: {e}")
        elif choice == "4":
            try:
                new_w = getpass.getpass("Nhập Mã số xóa khẩn cấp mới (mặc định 123456789): ").strip()
                confirm_w = getpass.getpass("Xác nhận lại Mã số xóa khẩn cấp mới: ").strip()
                if new_w != confirm_w:
                    print("[LỖI] Hai lần nhập mã không khớp nhau.")
                    continue
                if len(new_w) < 6:
                    print("[LỖI] Mã số xóa khẩn cấp phải có ít nhất 6 ký tự.")
                    continue
                set_smtp_wipe_code(new_w)
                print("[THÀNH CÔNG] Đã cập nhật Mã số xóa khẩn cấp mới thành công!")
            except Exception as e:
                print(f"[LỖI] Không thể đổi mã xóa: {e}")
        elif choice == "5":
            confirm = input("Bạn có chắc chắn muốn XÓA SẠCH cấu hình SMTP khỏi CSDL? (y/n): ").strip().lower()
            if confirm == "y":
                purge_smtp_config_from_db()
                print("[THÀNH CÔNG] Đã xóa sạch cấu hình SMTP khỏi CSDL!")
                break
        else:
            print("Lựa chọn không hợp lệ. Vui lòng chọn lại.")


if __name__ == "__main__":
    main()

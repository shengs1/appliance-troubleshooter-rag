# Kế hoạch kỹ thuật: Nâng cấp Chainlit, Auth, Chat History, Admin & Tiếng Việt

**Dự án:** Appliance Troubleshooter RAG Chatbot  
**Ngày:** 2026-10-28  
**Tác giả:** Senior RAG / Python / Security Engineer  

---

## 1. Mục tiêu và phạm vi

1. **Giao diện Chainlit thay Gradio:**
   - Cài đặt Chainlit 2.12.0 tương thích với môi trường Python 3.12.
   - Xây dựng giao diện ChatGPT-style với nhận diện thương hiệu riêng của dự án.
   - Tích hợp luồng trò chuyện, streaming, nút tạo cuộc trò chuyện mới, thanh bên lịch sử hội thoại (sidebar threads), màn hình chào có câu hỏi gợi ý, hỗ trợ Markdown, bảng, code block.
   - Quản lý phiên và đăng xuất ngay trong thanh bên của Chainlit.
   - Giữ Gradio trong giai đoạn chuyển đổi, sau khi Chainlit hoàn tất thì chuyển đổi mềm sang Chainlit làm UI chính, điều hướng `/chat-ui` phù hợp.

2. **Authentication & Session Management:**
   - Dùng chung một nguồn dữ liệu tài khoản (`data/chat_history.db` SQLite): bảng `users`, `sessions`, `password_reset_tokens`.
   - Chainlit `@cl.password_auth_callback` xác thực với `authenticate_user()` trong `rag_chatbot.auth`.
   - Hỗ trợ đăng ký (role mặc định `user`, kiểm tra mật khẩu an toàn, cấm tự nâng quyền `admin`), đăng nhập bằng username hoặc email, đăng xuất xóa phiên.
   - Kiểm tra trạng thái khóa tài khoản (`status == 'locked'`).

3. **Quên mật khẩu & SMTP:**
   - Luồng bảo mật token: token ngẫu nhiên sinh từ `secrets.token_urlsafe(32)`, lưu hash SHA-256 trong DB, hết hạn sau 15-30 phút, chỉ dùng 1 lần.
   - Giao diện đặt lại mật khẩu an toàn (`/auth/reset-password-page`), token truyền qua URL fragment (`#token=...`), tự động đọc và gửi bằng POST, xóa token khỏi URL history.
   - Xử lý gửi email qua SMTP: nếu cấu hình SMTP thực tế khả dụng thì gửi thật; nếu chưa cấu hình thì ghi log cảnh báo an toàn và không làm sập ứng dụng.

4. **Lưu và khôi phục lịch sử chat (Chat History Persistence):**
   - Triển khai Chainlit `BaseDataLayer` liên kết trực tiếp với các bảng `conversations` và `messages` trong SQLite.
   - Đảm bảo tính bền vững: khởi động lại server hoặc reload trang web vẫn giữ nguyên lịch sử hội thoại.
   - Phân quyền nghiêm ngặt: người dùng chỉ xem và thao tác trên cuộc trò chuyện của chính mình (kiểm tra `user_id == current_user.id`).

5. **Trang Admin quản lý tài khoản:**
   - Trang quản trị bảo mật tại `/admin-ui` (kèm API backend `/admin/*` có dependency `require_admin`).
   - Thống kê tài khoản (tổng số, hoạt động, bị khóa).
   - Danh sách tài khoản có tìm kiếm, phân trang.
   - Thao tác khóa/mở khóa tài khoản, đổi vai trò, kích hoạt đặt lại mật khẩu, đổi mật khẩu Admin.
   - Ghi audit log cho mọi thao tác của Admin.
   - Hiển thị liên kết Admin trong thanh bên Chainlit đối với tài khoản có role `admin`.

6. **Xử lý tiếng Việt có dấu, không dấu và trộn dấu:**
   - Xây dựng module chuẩn hóa câu hỏi: Unicode NFC, đồng nhất dấu thanh kiểu mới (`hòa`/`hoà`), xử lý khoảng trắng.
   - Loại bỏ dấu tiếng Việt an toàn (`remove_vietnamese_accents`, xử lý cả `đ/Đ` -> `d/D`).
   - Chuẩn hóa mã lỗi có khoảng trắng (`F 16` -> `F16`, `H 97` -> `H97`).
   - Xử lý alias có token boundary (`pana` -> `Panasonic`, `máy lạnh` <-> `điều hòa`, `lò vi ba` <-> `lò vi sóng`, lỗi gõ `máy giặc` -> `máy giặt`, `máy xấy` -> `máy sấy`).
   - Trích xuất thực thể hỗ trợ cả tiếng Việt không dấu (`dieu hoa`, `tu lanh`, `may giat`, `loi CF`...).
   - Query expansion có kiểm soát: tìm kiếm semantic & graph với các biến thể, deduplicate theo `question_id`, giữ nguyên candidate tốt nhất mà không cộng dồn bonus lặp.
   - Bộ test suite 30-50 câu hỏi tiếng Việt có dấu/không dấu/trộn dấu/negative control cases.

7. **Bảo tồn Pipeline RAG:**
   - Giữ nguyên ChromaDB, BGE-M3, Neo4j, Ollama/Qwen2.5 7B, rule-based reranker với `exact_bonus = 0.02`, `fetch_k = 5`.
   - Không phá vỡ schema response của endpoint `/chat`.

8. **Launcher & Bàn giao:**
   - Viết script `scripts/run_dev.ps1` khởi chạy cả FastAPI và Chainlit, kiểm tra port, hỗ trợ dừng tiến trình.
   - Báo cáo hoàn chỉnh tại `docs/CHAINLIT_MIGRATION_REPORT.md`.

---

## 2. Các file tác động

- `pyproject.toml` & `uv.lock`: Thêm `chainlit`.
- `src/rag_chatbot/vietnamese.py`: Module chuẩn hóa tiếng Việt, alias, unaccent, mở rộng mã lỗi.
- `src/rag_chatbot/retrieval.py`: Tích hợp xử lý thực thể không dấu và query expansion có kiểm soát.
- `src/rag_chatbot/scope.py`: Hỗ trợ nhận diện tín hiệu sự cố không dấu.
- `src/rag_chatbot/chainlit_app.py`: Entry point chính cho giao diện Chainlit.
- `src/rag_chatbot/chainlit_data_layer.py`: Data layer cho Chainlit lưu trữ vào SQLite.
- `src/rag_chatbot/main.py`: Giữ REST APIs, phục vụ giao diện Admin UI và Reset Password Page, redirect `/chat-ui`.
- `src/rag_chatbot/admin_ui.py`: Giao diện Admin quản trị tài khoản hiện đại.
- `scripts/run_dev.ps1`: Script PowerShell khởi chạy và quản lý vòng đời ứng dụng.
- `tests/test_vietnamese.py`: Bộ kiểm thử toàn diện tiếng Việt (có dấu, không dấu, trộn dấu, alias, mã lỗi).
- `tests/test_chainlit_data_layer.py`: Kiểm thử data layer, tính bền vững và phân quyền người dùng.
- `docs/CHAINLIT_MIGRATION_REPORT.md`: Báo cáo bàn giao chi tiết.

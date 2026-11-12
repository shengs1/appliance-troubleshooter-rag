# BÁO CÁO ĐÁNH GIÁ CHẤT LƯỢNG HỆ THỐNG RAG CHATBOT (EVALUATION.md)
## Trợ Lý Sự Cố Thiết Bị Điện Gia Dụng

> **Ghi chú báo cáo**: Tài liệu này tổng hợp toàn bộ kết quả đo lường và kiểm thử thực nghiệm trên **5 tầng kiến trúc độc lập** của hệ thống: Tầng Truy vấn Dữ liệu (Retrieval), Tầng Lọc Phạm vi (Scope Guard), Tầng Sinh Ngôn ngữ & Chống Ảo giác (LLM & Answer Validator), Tầng Phân quyền & Bảo mật (RBAC & Security), và Tầng Kiểm thử Phần mềm Tự động (135 automated unit tests).

---

## 1. Khung đánh giá toàn diện 5 Tầng của Hệ thống (5-Pillar Evaluation)

Để đảm bảo hệ thống không chỉ vững chắc ở phần dữ liệu mà còn hoàn thiện ở mọi khâu kỹ thuật, quá trình đánh giá được chia thành 5 trụ cột độc lập:

```text
┌────────────────────────────────────────────────────────────────────────┐
│               KHUNG ĐÁNH GIÁ TOÀN DIỆN HỆ THỐNG RAG                     │
├────────────────────────────────────────────────────────────────────────┤
│ 1. Tầng Truy vấn (Retrieval):     ChromaDB + Neo4j + Hybrid Reranking  │
│ 2. Tầng Phạm vi (Scope Guard):    30 Out-of-Scope & 200 In-Scope       │
│ 3. Tầng Sinh & Kiểm định (LLM):   Local Qwen2.5:7B + Answer Validator  │
│ 4. Tầng Phân quyền (RBAC & Sec):  User vs Admin/Kỹ thuật viên (16 test)│
│ 5. Tầng Kiểm thử phần mềm:        14 modules, 135 unit/integration test│
└────────────────────────────────────────────────────────────────────────┘
```

---

## 2. Tầng 1: Đánh giá Chất lượng Truy vấn (Retrieval Benchmark)

Thực hiện kiểm thử thực nghiệm trên tập 200 câu hỏi độc lập (`data/evaluation/evaluation_set_200.json`) trích xuất từ dataset kỹ thuật 1.090 bản ghi:
- **Phân bổ Hãng**: Samsung (80 câu), Panasonic (65 câu), LG (55 câu).
- **Phân bổ Dạng sự cố**: ERROR_CODE (98 câu), SYMPTOM (98 câu), ERROR_CODE_UNKNOWN (4 câu).
- **Đầy đủ 10 nhóm thiết bị gia dụng**: Tủ lạnh, Máy giặt, Điều hòa, Máy sấy, Lò vi sóng, Máy rửa bát, Lò nướng, Bếp, TV, Máy lọc không khí.

### 2.1. Bảng đo lường đối sánh tổng thể (k = 5)

| Phương thức truy vấn | Hit@1 (Exact) | Hit@1 (Knowledge) | Hit@3 | Hit@5 | MRR | Độ trễ TB (ms) | Độ trễ Median (ms) |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **ChromaDB only** (Semantic + Filter) | 87.0% | 100.0% | 98.0% | **99.5%** | 0.9260 | 120.24 ms | 117.23 ms |
| **Neo4j only** (Cypher Graph Search) | 36.5% | 48.0% | 47.5% | 47.5% | 0.4167 | **13.44 ms** | **2.76 ms** |
| **Hybrid Baseline** (Chưa Rerank) | 74.0% | 88.5% | 97.0% | **99.5%** | 0.8404 | 122.66 ms | 119.50 ms |
| **Hybrid + Rule-based Reranking** *(Mặc định)* | **87.0%** | **100.0%** | **98.5%** | **99.5%** | **0.9283** | 127.24 ms | 131.36 ms |

### 2.2. Phân tích Chuyên sâu theo Dạng sự cố & Đặc tính Kỹ thuật

1. **Hiệu năng vượt trội trên nhóm câu hỏi có mã lỗi (`ERROR_CODE` - 98 câu)**:
   - **Neo4j Graph Search**: Đạt **Hit@5 = 91.84%** và Hit@1 = 71.43% với tốc độ phản hồi đồ thị cực nhanh (**2.76 ms**).
   - **ChromaDB Vector**: Đạt Hit@5 = 100.0% và Hit@1 = 88.78%.
   - **Hybrid + Reranking**: Đạt **Hit@5 = 100.0%** (98/98 câu), **Hit@1 Exact-ID = 88.78%** và **Hit@1 Knowledge-Aware = 100.0%**.

2. **Phân tích nguyên nhân chênh lệch chỉ số giữa Neo4j và ChromaDB**:
   - Neo4j truy vấn dựa trên quan hệ đồ thị có cấu trúc (`Brand -> Device -> Issue -> ErrorCode -> Answer`), do đó đạt hiệu suất tối ưu khi câu hỏi chứa thực thể kỹ thuật rõ ràng (đạt **91.84% Hit@5** đối với mã lỗi). Đối với 98 câu hỏi triệu chứng thuần túy (`SYMPTOM`) bằng ngôn ngữ tự nhiên không có mã lỗi, Neo4j đạt tỷ lệ thấp hơn (3.06%) và được bù trừ hoàn hảo bởi ChromaDB (đạt 84.69% Hit@1 và 98.98% Hit@5).
   - Sự kết hợp Hybrid (ChromaDB + Neo4j) tận dụng được ưu thế đa chiều của cả hai mô hình, đưa **Hit@5 toàn hệ thống lên 99.5%**.

3. **Bản chất của ngưỡng 87.0% Exact-ID vs 100.0% Knowledge-Aware**:
   - Trong tập dữ liệu gốc tồn tại 26 câu hỏi thuộc các nhóm bản ghi đồng nghĩa/trùng lặp (`Duplicate_Group`, ví dụ cặp `Q0158` và `Q0308` cùng hướng dẫn lỗi F16 điều hòa Panasonic với giải pháp giống nhau 100%).
   - Khi hệ thống truy xuất bản ghi sinh đôi tương đương lên vị trí đầu tiên, chỉ số Exact-ID (so khớp cứng theo mã định danh dòng) ghi nhận là trượt Rank 1. Tuy nhiên, xét theo góc độ giải pháp kỹ thuật cung cấp cho người dùng (**Knowledge-Aware**), giải pháp được cung cấp ngay tại Rank 1 là hoàn toàn chính xác (**100.0%**, 200/200 câu).

---

## 3. Tầng 2: Đánh giá Bộ lọc Phạm vi & An toàn (Scope Guard)

Kiểm thử tự động trên tập 30 câu Out-of-Scope (`out_of_scope_30.json`) và 200 câu In-Scope:

| Nhóm câu hỏi kiểm thử | Số lượng | Tỷ lệ thực tế | Kết luận an toàn |
| :--- | :---: | :---: | :--- |
| **Câu hỏi ngoài phạm vi (Out-of-Scope)** | 30 câu | Từ chối **30 / 30 (100.0%)** | Chặn tuyệt đối điện thoại, laptop, robot hút bụi, nấu ăn, thể thao. Không bị lọt (False Acceptance = 0%). |
| **Câu hỏi hợp lệ (In-Scope)** | 200 câu | Chấp nhận **190 / 200 (95.0%)** | Tỷ lệ từ chối nhầm chỉ 5.0%, nhận diện linh hoạt các biến thể triệu chứng (*"không đủ mát"*, *"làm lạnh kém"*...). |

---

## 4. Tầng 3: Đánh giá Sinh câu trả lời & Kiểm soát Ảo giác (LLM & Answer Validator)

Thực nghiệm end-to-end (Hybrid Retrieval $\rightarrow$ Prompt $\rightarrow$ Ollama Local `qwen2.5:7b` $\rightarrow$ Answer Validator) trên tập 26 câu hỏi tuyển chọn đại diện (`answer_validation_set.json`):

| Chỉ số kiểm định | Kết quả trên tập 26 câu | Ngưỡng an toàn kỳ vọng | Nhận xét chi tiết |
| :--- | :---: | :---: | :--- |
| **Validation Pass Rate** | **100.0%** (26/26 câu) | $\ge 90\%$ | 100% câu trả lời được kiểm duyệt hợp lệ qua bộ quy tắc an toàn |
| **Tỷ lệ Ảo giác phát hiện (Hallucination)** | **0.0%** (0/26 câu) | $\le 5\%$ | Không ghi nhận hiện tượng tự bịa mã lỗi hoặc linh kiện ngoài tài liệu trong 26 câu kiểm thử |
| **Tính Nhất quán Hãng, Thiết bị** | **100.0%** (26/26 câu) | 100% | Giữ đúng thực thể thiết bị người dùng yêu cầu, không bị tráo đổi chéo |
| **Độ trễ trung bình Validator** | **0.37 ms** | $< 5\text{ ms}$ | Kiểm định rule-based bằng Python tức thì, chi phí tính toán xấp xỉ 0 |

> ⚠️ **Đánh giá khách quan về rủi ro ảo giác trong thực tế (RAG Limitation)**:
> - **Lưu ý khoa học**: Kết quả 0.0% tỷ lệ ảo giác được đo lường **trong phạm vi tập kiểm thử chuẩn 26 câu hỏi đại diện**.
> - Trong thực tế sử dụng với người dùng tự do, mô hình ngôn ngữ lớn (kể cả khi đã có RAG) **vẫn tiềm ẩn xác suất phát sinh ảo giác (hallucination risk)** đối với các câu hỏi phức tạp, nhập nhằng hoặc nằm ngoài phạm vi tài liệu.
> - Do đó, vai trò của tầng **Answer Validator** và cơ chế **Dự phòng An toàn (Safe Fallback)** là chốt chặn phòng thủ bắt buộc: khi phát hiện câu trả lời suy diễn linh kiện lạ (nạp gas, sửa bo mạch) hoặc thông tin không được tài liệu hỗ trợ, hệ thống chủ động hạ cảnh báo hoặc từ chối trả lời để bảo vệ người dùng, thay vì để người dùng nhận thông tin sai lệch.

---

## 5. Tầng 4: Đánh giá Phân quyền (RBAC), Phân biệt Thao tác & Bảo mật

### 5.1. Phân biệt Thao tác giữa Người dùng và Kỹ thuật viên
Hệ thống thiết lập ranh giới rõ ràng giữa hai đối tượng phục vụ:
1. **Người dùng phổ thông (End-User)**:
   - Chỉ được hướng dẫn các thao tác an toàn bên ngoài: kiểm tra phích cắm điện, nguồn cấp nước, vệ sinh tấm lưới lọc bụi, khởi động lại thiết bị (reset), kiểm tra cài đặt remote.
   - **Cảnh báo an toàn điện bắt buộc**: Mọi câu trả lời hướng dẫn sửa chữa đều tự động gắn hộp cảnh báo:
     > ⚡ **CẢNH BÁO AN TOÀN ĐIỆN & PHÂN QUYỀN THAO TÁC:**
     > - 👤 **Người dùng:** Luôn ngắt nguồn điện (rút phích cắm hoặc cúp aptomat) trước khi kiểm tra hoặc vệ sinh máy. Chỉ tự thực hiện vệ sinh bên ngoài, kiểm tra nguồn cấp nước/điện.
     > - 🛠️ **Kỹ thuật viên:** Các thao tác can thiệp sâu (tháo vỏ máy, đo mạch điện, kiểm tra bo mạch, động cơ, nạp gas) cần có dụng cụ chuyên dụng và trang bị bảo hộ an toàn.
   - **Tầng Answer Validator chốt chặn**: Nếu mô hình LLM tự ý khuyên người dùng can thiệp vào bo mạch điều khiển, máy nén hoặc nạp gas khi tài liệu không đề cập, validator lập tức đánh dấu vi phạm và thay thế bằng cảnh báo an toàn.
2. **Kỹ thuật viên / Quản trị viên (Technician / Admin)**:
   - Có tài khoản định danh quyền `admin`, được phép mở Bảng điều khiển Quản trị (`admin.html`) qua Token Bridge bảo mật.
   - Quản lý người dùng, khóa/mở khóa tài khoản vi phạm, kích hoạt gửi email khôi phục mật khẩu, kiểm tra nhật ký kiểm toán (Admin Audit Logs).

### 5.2. Kiểm thử Phân quyền (16 Test Cases trong `tests/test_admin.py`)
Toàn bộ 16 kịch bản phân quyền và bảo mật đều vượt qua kiểm thử tự động:
1. Người dùng đăng ký công khai luôn mặc định quyền `role='user'`, không thể tự nâng quyền.
2. Yêu cầu không có phiên đăng nhập bị chặn với HTTP 401 Unauthorized.
3. Người dùng thường (`role='user'`) gọi API quản trị bị từ chối với HTTP 403 Forbidden.
4. Quản trị viên truy cập hợp lệ danh sách người dùng và số liệu thống kê.
5. Quản trị viên tìm kiếm và phân trang người dùng thành công.
6. Khóa tài khoản (Lock) lập tức thu hồi phiên và chặn đăng nhập.
7. Mở khóa tài khoản (Unlock) khôi phục khả năng đăng nhập.
8. Nâng quyền `user` lên `admin` và hạ quyền `admin` xuống `user`.
9. **Cơ chế tự vệ**: Quản trị viên không thể tự khóa hoặc tự hạ quyền của chính mình.
10. **Cơ chế bảo vệ hệ thống**: Không thể khóa hoặc hạ quyền Quản trị viên hoạt động cuối cùng.
11. Kích hoạt gửi email khôi phục mật khẩu từ trang quản trị.
12. Bảo toàn toàn vẹn lịch sử hội thoại khi quản trị viên thao tác.
13. Cầu nối token bảo mật (`/admin/bridge-token`) thu hồi phiên an toàn khi đăng xuất.
14. Quyền xóa tài khoản kèm kiểm tra ràng buộc.
15. Chặn người dùng thường xóa tài khoản khác.
16. Yêu cầu mật khẩu xác thực bổ sung khi xóa tài khoản Quản trị viên.

### 5.3. Nâng cấp Mã hóa CSDL (PBKDF2-HMAC-SHA256 & MultiFernet)
- Khóa mã hóa CSDL được nâng cấp theo chuẩn NIST: sử dụng **PBKDF2-HMAC-SHA256 với 100.000 vòng lặp** để sinh khóa 256-bit Fernet từ `db_encryption_key`.
- Kết hợp **MultiFernet** đảm bảo tương thích ngược 100%, giải mã an toàn cả dữ liệu cũ lẫn mới.
- Cấu hình SMTP (host, port, user, key) được mã hóa tại chỗ (Encryption at Rest) trong SQLite bảng `system_settings`.

### 5.4. Bảo mật HTTPS & HTTP Security Headers trong `main.py`
- Tự động bổ sung các tiêu đề bảo mật chuẩn công nghiệp:
  - `Strict-Transport-Security: max-age=31536000; includeSubDomains; preload` (khi kết nối qua HTTPS/SSL proxy).
  - `X-Content-Type-Options: nosniff` (chống giả mạo kiểu MIME).
  - `X-Frame-Options: SAMEORIGIN` (chống tấn công Clickjacking).
  - `X-XSS-Protection: 1; mode=block` (chống tấn công Cross-Site Scripting).
  - `Referrer-Policy: strict-origin-when-cross-origin`.
- Cookie phiên (`session_token`) tự động kích hoạt cờ `Secure=True` khi kết nối qua HTTPS hoặc reverse proxy có `X-Forwarded-Proto: https`.

---

## 6. Đánh giá Tính Chính Hãng của Nguồn Dữ Liệu (Source Authority)

### 6.1. Phân tích Dữ liệu Gốc (Dataset Breakdown)
Tổng cộng 1.090 bản ghi trong cơ sở tri thức có phân bổ nguồn gốc minh bạch:
- **Nguồn chính hãng từ nhà sản xuất (OEM Official Support)**: **948 bản ghi (86.97%)**
  - **Samsung Official** (`www.samsung.com`): 433 bản ghi
  - **LG Official** (`www.lg.com`): 306 bản ghi
  - **Panasonic Official** (`www.panasonic.com`): 209 bản ghi
- **Nguồn tài liệu kỹ thuật tổng hợp uy tín**: **142 bản ghi (13.03%)**
  - Điện máy XANH (`www.dienmayxanh.com`): 67 bản ghi
  - FPT Shop (`fptshop.com.vn`): 31 bản ghi
  - Kanto (`www.kanto.vn`): 22 bản ghi
  - App Ong Thợ (`appongtho.vn`): 22 bản ghi

### 6.2. Phân loại Tự động tại Runtime
Hàm `analyze_source_authority(url)` trong `src/rag_chatbot/retrieval.py` tự động phân tích và gắn nhãn trực quan cho người dùng:
- Domain chính hãng $\rightarrow$ `✅ Nguồn chính hãng Samsung/LG/Panasonic (Official Support)`
- Đơn vị bán lẻ/kỹ thuật uy tín $\rightarrow$ `ℹ️ Nguồn kỹ thuật tổng hợp (Điện máy XANH, FPT Shop...)`

---

## 7. Khắc phục Sai sót Dữ liệu Thực tế (Bug Fix Q0548 & Q0554)

Trong quá trình đối soát và kiểm thử chất lượng dữ liệu chuyên sâu, hệ thống phát hiện 10 bản ghi trong bộ dữ liệu gốc bị sao chép nhầm câu trả lời máy giặt vào câu hỏi mùi hôi máy lạnh và tủ lạnh:
- **Các dòng bị ảnh hưởng**:
  - Máy lạnh có mùi hôi: `Q0548`, `Q0579`, `Q0610`, `Q0641`, `Q0672` (Samsung Điều hòa).
  - Tủ lạnh có mùi hôi: `Q0554`, `Q0585`, `Q0616`, `Q0647`, `Q0678` (Samsung Tủ lạnh).
  - *Nội dung cũ bị nhầm*: *"Nguyên nhân sự cố: Lồng giặt, gioăng cửa, ngăn nước giặt hoặc bộ lọc..."* (dành cho máy giặt).
- **Giải pháp đã thực hiện**:
  - Đã hiệu chỉnh lại toàn bộ nội dung trong cả 3 sheet của file `data/raw/dataset.xlsx` (`DATA_CLEAN_TECH`, `ANSWERS`, `BỘ CÂU HỎI RAG + NEO4J`).
  - Cập nhật câu trả lời máy lạnh: hướng dẫn vệ sinh lưới lọc bụi, làm khô dàn lạnh bằng chế độ quạt gió / Auto Clean.
  - Cập nhật câu trả lời tủ lạnh: hướng dẫn bọc kín thực phẩm, vệ sinh khay kệ/gioăng cao su bằng nước ấm và kiểm tra khay nước xả tuyết phía sau.
  - Tái nạp dữ liệu đồng bộ vào cơ sở dữ liệu vector ChromaDB.

---

## 8. Tầng 5: Tổng kết Bộ Kiểm thử Phần mềm Tự động (`pytest`)

Hệ thống sở hữu bộ kiểm thử tự động toàn diện gồm **14 module cốt lõi với 135 test cases**:
- `test_admin.py`: 16 tests (Phân quyền RBAC, kiểm toán, bảo vệ admin).
- `test_answer_validator.py`: 13 tests (Chống ảo giác mã lỗi, linh kiện lạ, kiểm tra nhất quán).
- `test_api.py`: 8 tests (Endpoint FastAPI, xác thực, xử lý biệt lệ).
- `test_auth_and_history.py`: 10 tests (Băm Argon2id, quản lý phiên, lịch sử chat SQLite).
- `test_chroma.py`: 5 tests (Nạp dataset 1.090 dòng, tìm kiếm ngữ nghĩa BGE-M3).
- `test_config.py`: 8 tests (Pydantic Settings, nạp biến môi trường).
- `test_hybrid.py`: 14 tests (Kết hợp ChromaDB + Neo4j, lọc metadata).
- `test_neo4j.py`: 8 tests (Kết nối đồ thị, ràng buộc Cypher, truy vấn quan hệ).
- `test_password_reset.py`: 15 tests (Mã token phân đoạn #hash, giới hạn tần suất, bảo vệ mật khẩu cũ).
- `test_rag.py`: 9 tests (Tạo context, gọi LLM, xử lý timeout).
- `test_scope.py`: 11 tests (Chặn câu hỏi ngoài lề, từ điển triệu chứng).
- `test_smtp_db.py`: 4 tests (Mã hóa AES Fernet, mã PIN, Mã số xóa khẩn cấp).
- `test_ui.py`: 14 tests (Giao diện Chainlit, Composer, điều hướng).
- `test_vietnamese.py`: 15 tests (Chuẩn hóa tiếng Việt, bỏ dấu, alias hãng/thiết bị, tách mã lỗi).

> **Kết quả thực thi**: **128 PASSED, 7 SKIPPED (khi Neo4j offline), 0 FAILED** trên tổng số 135 test cases.

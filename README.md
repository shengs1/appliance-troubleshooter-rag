# RAG Chatbot - Hỗ trợ sửa chữa thiết bị điện tử

Dự án học tập xây dựng chatbot hỗ trợ chẩn đoán và khắc phục sự cố thiết bị điện tử (điều hòa, máy giặt, TV, bo mạch nguồn...) sử dụng kỹ thuật **Hybrid RAG** (kết hợp đồ thị tri thức và tìm kiếm ngữ nghĩa vector).

---

## 1. Công nghệ chính sử dụng

- **Ngôn ngữ**: Python 3.12 (quản lý môi trường và gói bằng `uv`)
- **Quản lý cấu hình**: `pydantic-settings`
- **Vector Database**: `ChromaDB` (tìm kiếm đoạn văn bản hướng dẫn tương đồng)
- **Knowledge Graph**: `Neo4j` (lưu trữ quan hệ: Thiết bị → Mã lỗi → Triệu chứng → Nguyên nhân → Hướng dẫn sửa chữa)
- **Điều phối RAG**: `LangChain`
- **Giao diện API**: `FastAPI`
- **Mô hình ngôn ngữ**: Local LLM (qua Ollama / vLLM)
- **Kiểm thử**: `pytest`

---

## 2. Trạng thái hiện tại của dự án

- **Giai đoạn hoàn thành**: **Phase 1 - Khởi tạo nền tảng & Cấu hình (Foundation & Scaffolding)**
  - Đã thiết lập môi trường chuẩn Python 3.12 với công cụ `uv`.
  - Đã xây dựng cấu trúc gói nguồn `rag_chatbot`.
  - Đã hoàn thiện module cấu hình tập trung `config.py` đọc từ file `.env` với giá trị mặc định an toàn.
  - Đã thiết lập bộ kiểm thử tự động với `pytest`.
- **Các giai đoạn tiếp theo**:
  - Phase 2: Kết nối cơ sở dữ liệu (ChromaDB + Neo4j) và mô hình dữ liệu.
  - Phase 3: Pipeline nạp và tiền xử lý dữ liệu tài liệu kỹ thuật.
  - Phase 4: Cơ chế truy vấn kết hợp (Hybrid Retrieval) và sinh câu trả lời (RAG).
  - Phase 5: Xây dựng REST API bằng FastAPI và kiểm thử toàn diện.

---

## 3. Cấu trúc thư mục dự án

```text
rag-chatbot/
├── data/                      # Lưu trữ dữ liệu
│   ├── raw/                   # Tài liệu kỹ thuật thô (chưa xử lý)
│   ├── processed/             # Dữ liệu đã làm sạch và chia đoạn
│   └── samples/               # Dữ liệu mẫu dùng cho kiểm thử
├── scripts/                   # Các script tiện ích (khởi tạo CSDL, migrate dữ liệu)
├── src/
│   └── rag_chatbot/           # Mã nguồn chính của ứng dụng
│       ├── __init__.py        # Khai báo package và phiên bản
│       ├── config.py          # Quản lý cấu hình hệ thống bằng Pydantic Settings
│       ├── ingest.py          # Pipeline nạp dữ liệu (Phase 3)
│       ├── chroma_db.py       # Kết nối và thao tác ChromaDB (Phase 2)
│       ├── neo4j_db.py        # Kết nối và truy vấn Cypher Neo4j (Phase 2)
│       ├── retrieval.py       # Truy vấn kết hợp Hybrid Retrieval (Phase 4)
│       ├── rag.py             # Điều phối sinh câu trả lời RAG (Phase 4)
│       └── main.py            # Điểm khởi chạy kiểm tra hệ thống
├── tests/                     # Thư mục kiểm thử tự động
│   └── test_config.py         # Kiểm thử module cấu hình
├── .env.example               # Mẫu file biến môi trường
├── .python-version            # Ghim phiên bản Python (3.12)
├── pyproject.toml             # Khai báo thông tin dự án và dependencies
└── README.md                  # Tài liệu giới thiệu dự án
```

---

## 4. Hướng dẫn cài đặt và sử dụng với `uv`

Dự án sử dụng công cụ quản lý `uv` để đảm bảo cài đặt nhanh chóng, độc lập và chính xác phiên bản Python.

### 4.1. Cài đặt môi trường ảo và dependencies

Trong thư mục gốc của dự án, chạy lệnh:

```bash
uv sync
```

Lệnh này sẽ tự động:
1. Sử dụng đúng phiên bản Python 3.12.
2. Tạo thư mục môi trường ảo `.venv/`.
3. Cài đặt các thư viện cần thiết (`pydantic`, `pydantic-settings`, `pytest`).
4. Cài đặt package `rag-chatbot` ở chế độ chỉnh sửa (editable mode).

### 4.2. Thiết lập biến môi trường (tùy chọn)

Sao chép file `.env.example` thành `.env` để tùy chỉnh thông số kết nối nếu cần:

```bash
cp .env.example .env
```

### 4.3. Chạy thử kiểm tra cấu hình hệ thống

Chạy trực tiếp module chính qua `uv`:

```bash
uv run python -m rag_chatbot.main
```

---

## 5. Hướng dẫn chạy kiểm thử (Tests)

Chạy toàn bộ unit test với `pytest` qua `uv`:

```bash
uv run pytest -q
```

Kết quả hiển thị `3 passed` cho thấy hệ thống cấu hình nền tảng hoạt động chính xác và sẵn sàng cho các giai đoạn tiếp theo.

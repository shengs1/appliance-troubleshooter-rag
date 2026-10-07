# RAG Chatbot - Hệ Thống Hỗ Trợ Khắc Phục Sự Cố Thiết Bị Điện Tử

Dự án học thuật xây dựng hệ thống **RAG Chatbot (Retrieval-Augmented Generation)** hỗ trợ chẩn đoán và hướng dẫn xử lý sự cố thiết bị điện tử gia dụng (Điều hòa, Tủ lạnh, Máy giặt, Máy sấy, Lò vi sóng, Máy lọc không khí...).

Hệ thống kết hợp kỹ thuật **Hybrid Retrieval** giữa cơ sở dữ liệu vector (**ChromaDB**) và đồ thị tri thức (**Neo4j**), cùng mô hình ngôn ngữ lớn chạy cục bộ (**Local LLM - Qwen2.5:7B qua Ollama**) và giao diện lập trình ứng dụng REST API (**FastAPI**).

---

## 1. Quick Start (Khởi động nhanh trong 10 bước)

1. **Sao chép mã nguồn (Clone repository)**:
   ```powershell
   git clone https://github.com/<USERNAME>/<REPOSITORY>.git
   cd rag-chatbot
   ```

2. **Cài đặt môi trường và thư viện với `uv`**:
   ```powershell
   uv sync
   ```

3. **Cấu hình biến môi trường**:
   ```powershell
   Copy-Item .env.example .env
   # Mở file .env và cập nhật NEO4J_PASSWORD theo mật khẩu CSDL của bạn
   ```

4. **Khởi động Neo4j Desktop / Server**:
   Đảm bảo dịch vụ Neo4j đang hoạt động tại cổng `7687` (kiểm tra: `Test-NetConnection localhost -Port 7687`).

5. **Nạp dữ liệu vào ChromaDB (Vector Store)**:
   ```powershell
   uv run python -m rag_chatbot.ingest
   ```

6. **Nạp dữ liệu vào Neo4j (Knowledge Graph)**:
   ```powershell
   uv run python -m rag_chatbot.neo4j_db
   ```

7. **Khởi động Ollama và tải mô hình Local LLM**:
   ```powershell
   ollama pull qwen2.5:7b
   ```

8. **Khởi chạy máy chủ FastAPI**:
   ```powershell
   uv run uvicorn rag_chatbot.main:app --reload --port 8000
   ```

9. **Mở tài liệu API tương tác (Swagger UI)**:
   Truy cập trình duyệt: [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)

10. **Gửi câu hỏi thử nghiệm qua API**:
    Gửi request tới `POST /chat` với câu hỏi:
    ```json
    {
      "question": "Máy điều hòa Samsung lỗi CF là gì?"
    }
    ```

---

## 2. Mục tiêu dự án & Đặc thù đồ án học thuật

Dự án này là một đồ án học thuật dành cho người mới bắt đầu tiếp cận RAG. Toàn bộ mã nguồn được thiết kế xoay quanh 5 tiêu chí cốt lõi:
1. **Đơn giản (Simplicity)**: Viết mã nguồn Python thuần, dễ đọc, luồng điều khiển rõ ràng.
2. **Dễ giải thích (Explainability)**: Từng module, hàm và truy vấn đều minh bạch, phục vụ tốt cho buổi thi vấn đáp (oral examination).
3. **Độ chính xác & Chống ảo giác (Grounding)**: Mô hình chỉ trả lời dựa DUY NHẤT vào dữ liệu kỹ thuật truy vấn được, tuyệt đối không tự bịa đặt mã lỗi, nguyên nhân hay khuyến nghị ngoài tài liệu.
4. **Kiểm thử đầy đủ (Testability)**: Toàn bộ các tầng (config, vector, graph, hybrid, rag, api, evaluation) đều có unit test tự động với `pytest`.
5. **Không over-engineering**: Không sử dụng kiến trúc microservices phức tạp, không áp dụng dependency injection đa tầng, không dùng các giải thuật xếp hạng trừu tượng quá mức khi chưa cần thiết.

---

## 3. Kiến trúc tổng thể hệ thống

```
+-------------------------------------------------------------+
|                      Client / Người dùng                    |
+-------------------------------------------------------------+
                              |
                     POST /chat (JSON)
                              v
+-------------------------------------------------------------+
|                  FastAPI Application (main.py)              |
+-------------------------------------------------------------+
                              |
                  generate_rag_answer(question)
                              v
+-------------------------------------------------------------+
|                  RAG Pipeline (rag.py)                      |
|  1. Nhận câu hỏi                                            |
|  2. Điều phối Hybrid Retrieval                              |
|  3. Xây dựng Context kỹ thuật có cấu trúc                   |
|  4. Tạo Grounding Prompt nghiêm ngặt                        |
|  5. Gọi Local LLM sinh câu trả lời                          |
+-------------------------------------------------------------+
                              |
               search_hybrid(question, k=5)
                              v
+-------------------------------------------------------------+
|              Hybrid Retrieval (retrieval.py)                |
|  - Trích xuất thực thể: Hãng, Thiết bị, Mã lỗi              |
|  - Hợp nhất kết quả từ 2 nguồn theo question_id             |
|  - Đánh dấu tài liệu tìm thấy từ cả hai nguồn ('both')      |
+-------------------------------------------------------------+
             /                                   \
            /                                     \
           v                                       v
+-----------------------+              +-----------------------+
|  ChromaDB (chroma_db) |              |   Neo4j (neo4j_db)    |
| - Vector Semantic     |              | - Cypher Graph Query  |
| - Model: BAAI/bge-m3  |              | - Quan hệ thực thể    |
| - 1.090 documents     |              | - 3.188 nodes         |
|                       |              | - 4.391 relationships |
+-----------------------+              +-----------------------+
                              |
                   Ngữ cảnh trích xuất (Context)
                              v
+-------------------------------------------------------------+
|                 Grounding Prompt (rag.py)                   |
+-------------------------------------------------------------+
                              |
                   POST /api/generate (HTTP)
                              v
+-------------------------------------------------------------+
|              Local LLM Service (Ollama)                     |
|              Mô hình: Qwen2.5:7B                            |
+-------------------------------------------------------------+
                              |
                     Câu trả lời chuẩn hóa
                              v
+-------------------------------------------------------------+
|                 Kết quả JSON trả về Client                  |
+-------------------------------------------------------------+
```

---

## 4. Công nghệ chính sử dụng

- **Ngôn ngữ**: Python 3.12 (quản lý môi trường và gói thư viện bằng `uv`).
- **Quản lý cấu hình**: `pydantic-settings` (đọc biến môi trường `.env`, cung cấp giá trị mặc định an toàn).
- **Vector Database**: `ChromaDB` (`v1.5.9+`) lưu trữ vector embedding trên ổ đĩa cục bộ.
- **Mô hình Embedding**: `BAAI/bge-m3` (qua `sentence-transformers`), hỗ trợ xuất sắc ngữ nghĩa tiếng Việt kỹ thuật.
- **Knowledge Graph**: `Neo4j` (`v5.x / Community / Desktop` qua thư viện chính thức `neo4j` Python driver).
- **Giao diện API**: `FastAPI` + `uvicorn` (cung cấp REST API và tài liệu tương tác Swagger).
- **Mô hình Ngôn ngữ cục bộ (Local LLM)**: `Qwen2.5:7B` chạy thông qua `Ollama` qua cổng HTTP `11434`.
- **Kiểm thử tự động**: `pytest` (toàn bộ 36 bài kiểm thử tự động).

---

## 5. Quy trình dữ liệu (Data Pipeline)

Dữ liệu nguồn được thu thập và làm sạch trong file Excel kỹ thuật `data/raw/dataset.xlsx`:
- **Tổng số bản ghi**: **1.090 câu hỏi - đáp (Q&A)** kỹ thuật.
- **3 Thương hiệu (Brands)**: LG, Panasonic, Samsung.
- **10 Loại thiết bị (Devices)**: Điều hòa, Tủ lạnh, Máy giặt, Máy sấy, Lò nướng, Lò vi sóng, Máy rửa bát, Máy lọc không khí, Bếp, TV.
- **632 Sự cố kỹ thuật (Issues)**.
- **332 Mã lỗi (ErrorCodes)**.
- **31 Nguồn tài liệu kỹ thuật (Sources)** từ các trang hỗ trợ chính hãng và bên thứ ba uy tín.

### Các nguyên tắc bảo toàn dữ liệu nghiêm ngặt:
- **Bảo tồn mã lỗi bị thiếu**: Nếu câu hỏi về triệu chứng thuần không có mã lỗi, trường `error_code` để trống, không tự ý gán bừa.
- **Bảo tồn mã lỗi chưa xác định (`ERROR_CODE_UNKNOWN`)**: Giữ nguyên vẹn 16 bản ghi sự cố có đèn báo/âm thanh nhưng tài liệu gốc không đặt tên mã lỗi.
- **Bảo tồn bản ghi nhiều mã lỗi (`MULTIPLE_ERROR_CODES`)**: Giữ nguyên danh sách các bản ghi chứa đồng thời nhiều mã lỗi (ví dụ: `ER CH, ER CL`).
- **Bảo tồn các biến thể câu hỏi trùng lặp**: Giữ lại 118 bản ghi thuộc 59 nhóm biến thể nhằm đa dạng hóa mẫu câu hỏi thực tế từ người dùng.
- **Bảo tồn cờ nguồn bên thứ ba**: Đánh dấu rõ nguồn chính thức (`official: YES`) và nguồn bên thứ ba (`official: NO`).
- **Không tự bịa đặt Nguyên nhân / Cách khắc phục**: Với 357 bản ghi mang nhãn `Loại_câu_trả_lời = 'ANSWER'`, hệ thống giữ nguyên văn bản trả lời kỹ thuật gốc, không dùng AI để tự suy đoán tách rời cause/solution khi dữ liệu gốc không có nhãn.

*(Chi tiết ánh xạ dữ liệu xem tại [DATA_MODEL.md](DATA_MODEL.md)).*

---

## 6. Cơ sở dữ liệu Vector (ChromaDB)

- **Collection**: `electronics_troubleshooting`
- **Embedding Model**: `BAAI/bge-m3`
- **Thư mục lưu trữ**: `./chroma_data`

### Chiến lược Chunking & Mapping:
Trong dự án này, hệ thống áp dụng nguyên tắc thiết kế đơn giản, rõ ràng:
$$\text{1 Bản ghi Q\&A} \longrightarrow \text{1 ChromaDB Document}$$
Không sử dụng các thuật toán chia nhỏ văn bản (chunking) phức tạp vì mỗi dòng câu hỏi - giải pháp kỹ thuật đã là một đơn vị tri thức hoàn chỉnh và độc lập.

- **Document Content (`page_content`)**: Đoạn văn bản tổng hợp chứa Hãng, Thiết bị, Mã lỗi, Câu hỏi đã làm sạch, Nguyên nhân, Cách khắc phục và Toàn văn câu trả lời. Đoạn văn bản này được mô hình `bge-m3` mã hóa thành vector không gian đa chiều.
- **Metadata**: Lưu trữ các trường dữ liệu định danh vô hướng (scalar) phục vụ bộ lọc:
  `question_id`, `brand`, `device`, `error_code`, `issue_type`, `issue_id`, `answer_type`, `source_id`, `source_url`, `domain`.
- **Semantic Search**: Khi người dùng hỏi, câu hỏi được chuyển đổi thành vector embedding và tìm kiếm các tài liệu có khoảng cách cosine nhỏ nhất trong ChromaDB.

---

## 7. Cơ sở dữ liệu Đồ thị (Neo4j)

Neo4j lưu trữ tri thức dưới dạng đồ thị (Knowledge Graph) để thể hiện các mối quan hệ cấu trúc nhiều cấp:

### Mô hình Đồ thị (Schema):
```
                       (:Brand)
                          |
                          | [:HAS_DEVICE]
                          v
                       (:Device)
                          |
                          | [:HAS_ISSUE]
                          v
                       (:Issue) --------[:HAS_ERROR_CODE]-------> (:ErrorCode)
                          ^
                          | [:ABOUT]
                          |
                      (:Question)
                     /           \
     [:ANSWERED_BY] /             \ [:SOURCED_FROM]
                   v               v
               (:Answer)       (:Source)
```

### Số lượng đối tượng thực tế trên đồ thị:
- **Node Labels**:
  - `Brand`: 3 nodes
  - `Device`: 10 nodes
  - `Issue`: 632 nodes
  - `ErrorCode`: 332 nodes
  - `Question`: 1.090 nodes
  - `Answer`: 1.090 nodes
  - `Source`: 31 nodes
  - **Tổng số nodes**: **3.188 nodes**
- **Relationships**:
  - `[:HAS_DEVICE]`: 20 cạnh
  - `[:HAS_ISSUE]`: 632 cạnh
  - `[:HAS_ERROR_CODE]`: 469 cạnh
  - `[:ABOUT]`: 1.090 cạnh
  - `[:ANSWERED_BY]`: 1.090 cạnh
  - `[:SOURCED_FROM]`: 1.090 cạnh
  - **Tổng số relationships**: **4.391 cạnh**

---

## 8. Truy vấn kết hợp (Hybrid Retrieval)

Hệ thống kết hợp ưu điểm của cả hai phương pháp truy vấn:
1. **ChromaDB**: Tìm kiếm ngữ nghĩa tương đồng (Semantic Similarity Search) dựa trên khoảng cách vector, rất mạnh với câu hỏi ngôn ngữ tự nhiên và miêu tả triệu chứng.
2. **Neo4j**: Tìm kiếm theo thực thể đồ thị (Graph Entity Retrieval) sử dụng Cypher query có tham số, đạt độ chính xác 100% đối với các mã lỗi kỹ thuật tường minh.

### Cơ chế kết hợp đơn giản, minh bạch:
- Hệ thống trích xuất thực thể cơ bản từ câu hỏi: Hãng (`Brand`), Loại thiết bị (`Device`), Mã lỗi (`ErrorCode`).
- Thực thi đồng thời truy vấn `search_similar_documents()` từ ChromaDB và `search_graph()` từ Neo4j.
- Hợp nhất danh sách kết quả dựa trên khóa chính `question_id`:
  - Nếu tài liệu được tìm thấy bởi **cả hai nguồn**: gán nhãn `retrieval_source = "both"` và **ưu tiên đưa lên đầu danh sách ngữ cảnh**.
  - Nếu chỉ tìm thấy từ một nguồn: gán nhãn `chroma` hoặc `neo4j`.

> **Lưu ý học thuật**: Hệ thống **không** sử dụng Reciprocal Rank Fusion (RRF), cross-encoder hay các mô hình reranking phức tạp nhằm đảm bảo thuật toán dễ hiểu, dễ trình bày trước hội đồng thi.

---

## 9. Điều phối RAG & Local LLM

### Luồng xử lý câu hỏi:
$$\text{User Question} \longrightarrow \text{search\_hybrid()} \longrightarrow \text{build\_context()} \longrightarrow \text{create\_prompt()} \longrightarrow \text{call\_local\_llm()} \longrightarrow \text{generate\_rag\_answer()}$$

- **Mô hình LLM**: `Qwen2.5:7B` chạy thông qua Ollama cục bộ.
- **API Endpoint**: `http://localhost:11434/api/generate`

### Grounding Prompt (Kỹ thuật khống chế chống ảo giác):
Khi chạy trực tiếp mô hình ngôn ngữ không qua RAG, mô hình thường tự suy diễn thêm các chi tiết ngoài thực tế (như *"bộ lọc bị bẩn"*, *"cần vệ sinh bằng bàn chải mềm"*, *"liên hệ trung tâm kỹ thuật"*...). Để ngăn chặn điều này, hàm `create_prompt()` áp dụng các nguyên tắc bắt buộc:
1. **Chỉ sử dụng thông tin kỹ thuật có trong ngữ cảnh**: Tuyệt đối không tự suy diễn nguyên nhân từ kiến thức phổ thông, không tự sáng tác sự kiện kỹ thuật mới, không thêm lời khuyên chung chung hay khuyến cáo an toàn nếu tài liệu không nhắc tới.
2. **Trả lời ngắn gọn, trực tiếp**: Giữ nguyên đúng ý nghĩa của dữ liệu được cung cấp.
3. **Từ chối thông minh khi thiếu dữ liệu**: Nếu ngữ cảnh không có thông tin hoặc không đủ dữ liệu, thông báo rõ ràng rằng cơ sở tri thức chưa có đủ thông tin xử lý cho trường hợp này.
4. **Bảo tồn thực thể**: Giữ chính xác tên hãng, loại thiết bị và mã lỗi kỹ thuật.
5. **Dẫn nguồn kiểm chứng**: Đính kèm đường link nguồn tham khảo chính thức ở cuối câu trả lời.

---

## 10. Giao diện REST API (FastAPI)

FastAPI đóng vai trò là tầng giao diện API nhẹ nhàng kết nối người dùng với hệ thống RAG, không sao chép lại logic nghiệp vụ:

### Danh sách Endpoint:
- `GET /`: Kiểm tra trạng thái hoạt động cơ bản của API (`{"message": "RAG Chatbot API is running"}`).
- `GET /health`: Kiểm tra sức khỏe hệ thống nhanh chóng, không truy vấn database (`{"status": "ok"}`).
- `POST /chat`: Tiếp nhận câu hỏi kỹ thuật, thực thi RAG và trả về kết quả JSON.

### Ví dụ Request & Response:

**Request (`POST /chat`)**:
```json
{
  "question": "Máy điều hòa Samsung lỗi CF là gì?"
}
```

**Response (`HTTP 200 OK`)**:
```json
{
  "question": "Máy điều hòa Samsung lỗi CF là gì?",
  "answer": "Máy điều hòa Samsung lỗi CF là mã lỗi cảnh báo bạn cần vệ sinh bộ lọc. Cách khắc phục là vệ sinh hoặc thay bộ lọc rồi đặt lại máy.",
  "llm_status": "success",
  "retrieved_documents": [
    {
      "question_id": "Q0358",
      "question": "Máy điều hòa Samsung lỗi CF",
      "answer": "Nguyên nhân sự cố: Mã CF là nhắc vệ sinh bộ lọc. Cách khắc phục: Hãy vệ sinh hoặc thay bộ lọc rồi đặt lại nhắc lọc.",
      "brand": "Samsung",
      "device": "Điều hòa",
      "error_code": "CF",
      "source_url": "https://www.samsung.com/vn/support/home-appliances/check-out-the-displayed-error-codes-on-the-indoor-unit-air-conditioner/",
      "retrieval_source": "both"
    }
  ],
  "sources": [
    "https://www.samsung.com/vn/support/home-appliances/check-out-the-displayed-error-codes-on-the-indoor-unit-air-conditioner/"
  ]
}
```

- **Tài liệu Swagger UI**: [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)

---

## 11. Cấu trúc thư mục dự án (Project Structure)

```text
rag-chatbot/
├── .agents/
│   └── skills/
│       └── rag-engineering/
│           └── SKILL.md                 # Chỉ dẫn quy trình kỹ thuật RAG
├── data/
│   ├── evaluation/
│   │   ├── evaluation_set.json          # Tập 30 câu hỏi đánh giá chuẩn
│   │   └── rag_eval_results.json        # Kết quả chi tiết đánh giá RAG + LLM
│   ├── processed/                       # Thư mục dữ liệu đã qua tiền xử lý
│   ├── raw/
│   │   └── dataset.xlsx                 # Bộ dữ liệu gốc 1.090 bản ghi Excel
│   └── samples/                         # Dữ liệu mẫu kiểm thử
├── scripts/                             # Các script tiện ích
├── src/
│   └── rag_chatbot/
│       ├── __init__.py                  # Khởi tạo package
│       ├── config.py                    # Cấu hình Pydantic Settings
│       ├── ingest.py                    # Nạp dữ liệu vào ChromaDB
│       ├── chroma_db.py                 # Kết nối và truy vấn ChromaDB
│       ├── neo4j_db.py                  # Kết nối, nạp dữ liệu và truy vấn Neo4j
│       ├── retrieval.py                 # Module truy vấn kết hợp Hybrid Retrieval
│       ├── rag.py                       # Điều phối Prompt, Context và gọi Local LLM
│       ├── evaluation.py                # Module tính toán chỉ số đánh giá hệ thống
│       └── main.py                      # Ứng dụng FastAPI phục vụ REST API
├── tests/
│   ├── test_api.py                      # Kiểm thử tầng API FastAPI (7 tests)
│   ├── test_chroma.py                   # Kiểm thử tầng ChromaDB (5 tests)
│   ├── test_config.py                   # Kiểm thử tầng Cấu hình (3 tests)
│   ├── test_evaluation.py               # Kiểm thử module Đánh giá (5 tests)
│   ├── test_hybrid.py                   # Kiểm thử tầng Hybrid Retrieval (5 tests)
│   ├── test_neo4j.py                    # Kiểm thử tầng Neo4j Graph (5 tests)
│   └── test_rag.py                      # Kiểm thử tầng RAG & Grounding (6 tests)
├── .env.example                         # File mẫu cấu hình biến môi trường
├── .gitignore                           # Các tệp và thư mục loại trừ khỏi Git
├── .python-version                      # Ghim phiên bản Python (3.12)
├── AGENTS.md                            # Quy tắc và hướng dẫn đồ án học thuật
├── DATA_MODEL.md                        # Đặc tả mô hình dữ liệu chi tiết
├── EVALUATION.md                        # Báo cáo đánh giá chất lượng hệ thống
├── pyproject.toml                       # Khai báo cấu hình dự án và dependencies
├── README.md                            # Tài liệu hướng dẫn toàn diện dự án
└── uv.lock                              # Khóa phiên bản dependencies chính xác
```

---

## 12. Hướng dẫn cài đặt chi tiết trên Windows

### Bước 1: Sao chép mã nguồn (Clone repository)
Mở PowerShell và chạy lệnh:
```powershell
git clone https://github.com/<USERNAME>/<REPOSITORY>.git
cd rag-chatbot
```

### Bước 2: Cài đặt Python 3.12
Dự án được ghim cố định cho phiên bản **Python 3.12**. Đảm bảo máy tính đã cài đặt Python 3.12 (tải từ [python.org](https://www.python.org/downloads/)).

### Bước 3: Cài đặt công cụ quản lý gói `uv`
Nếu chưa có `uv`, cài đặt nhanh qua PowerShell:
```powershell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

### Bước 4: Đồng bộ môi trường và dependencies
Chạy lệnh đồng bộ gói:
```powershell
uv sync
```
*Lệnh này sẽ tự động khởi tạo môi trường ảo `.venv`, cài đặt chính xác các thư viện cần thiết theo `pyproject.toml` và `uv.lock`.*

### Bước 5: Cấu hình file môi trường `.env`
Sao chép từ file mẫu `.env.example`:
```powershell
Copy-Item .env.example .env
```
Mở file `.env` bằng trình soạn thảo và cập nhật thông số kết nối:
```ini
APP_NAME=rag-chatbot
APP_ENV=development
DEBUG=True

# Cấu hình Neo4j (Nhập mật khẩu bạn đã đặt trong Neo4j Desktop)
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=your_password_here

# Cấu hình ChromaDB
CHROMA_PERSIST_DIRECTORY=./chroma_data
CHROMA_COLLECTION_NAME=electronics_troubleshooting

# Cấu hình Embedding Model
EMBEDDING_MODEL_NAME=BAAI/bge-m3

# Cấu hình Local LLM (Ollama)
OLLAMA_BASE_URL=http://localhost:11434
LLM_MODEL_NAME=qwen2.5:7b
```

---

## 13. Cài đặt và Chuẩn bị Neo4j

1. Tải và cài đặt **Neo4j Desktop** (hoặc Neo4j Community Server) từ [neo4j.com](https://neo4j.com/download/).
2. Tạo một Database mới, đặt Username là `neo4j` và đặt mật khẩu (ghi nhớ mật khẩu này để điền vào `.env`).
3. Khởi động (Start) cơ sở dữ liệu trên cổng mặc định `7687`.
4. Kiểm tra cổng kết nối từ PowerShell:
   ```powershell
   Test-NetConnection localhost -Port 7687
   ```
   *Kết quả mong đợi: `TcpTestSucceeded : True`*.
5. Truy cập Neo4j Browser để trực quan hóa đồ thị: [http://localhost:7474](http://localhost:7474).

---

## 14. Nạp dữ liệu vào Hệ thống (Data Ingestion)

### 14.1. Nạp dữ liệu vào ChromaDB
Chạy module nạp dữ liệu vector từ `dataset.xlsx`:
```powershell
uv run python -m rag_chatbot.ingest
```
*Quy trình: Đọc sheet `DATA_CLEAN_TECH` $\rightarrow$ Chuẩn bị văn bản và metadata $\rightarrow$ Tính toán embedding vector $\rightarrow$ Nạp 1.090 documents vào thư mục `./chroma_data`.*

### 14.2. Nạp dữ liệu vào Neo4j
Chạy module nạp dữ liệu đồ thị:
```powershell
uv run python -m rag_chatbot.neo4j_db
```
*Quy trình: Khởi tạo ràng buộc duy nhất (Constraints) $\rightarrow$ Đọc các sheet thực thể và quan hệ $\rightarrow$ Thực thi các lệnh `MERGE` theo batch $\rightarrow$ Tạo đủ 3.188 nodes và 4.391 relationships.*

---

## 15. Cài đặt và Chạy Ollama (Local LLM)

1. Tải và cài đặt **Ollama** từ [ollama.com](https://ollama.com/).
2. Kiểm tra phiên bản Ollama:
   ```powershell
   ollama --version
   ```
3. Tải mô hình mã nguồn mở `Qwen2.5:7B` (hỗ trợ tiếng Việt xuất sắc):
   ```powershell
   ollama pull qwen2.5:7b
   ```
4. Kiểm tra danh sách mô hình đã tải:
   ```powershell
   ollama list
   ```
5. Đảm bảo dịch vụ Ollama đang chạy tại địa chỉ: [http://localhost:11434](http://localhost:11434). Mô hình sẽ tự động tận dụng CPU hoặc GPU có sẵn của máy tính.

---

## 16. Khởi chạy Ứng dụng

### Kiểm tra thử nghiệm RAG qua CLI:
Chạy trực tiếp module RAG để kiểm tra phản hồi mẫu với câu hỏi mã lỗi `CF`:
```powershell
$env:PYTHONIOENCODING="utf-8"; uv run python -m rag_chatbot.rag
```

### Khởi chạy máy chủ Web API (FastAPI):
Khởi chạy dịch vụ API cục bộ:
```powershell
uv run uvicorn rag_chatbot.main:app --reload --port 8000
```
- API Root: [http://127.0.0.1:8000/](http://127.0.0.1:8000/)
- Health Check: [http://127.0.0.1:8000/health](http://127.0.0.1:8000/health)
- Swagger UI: [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)

*(Yêu cầu tiên quyết: Dịch vụ Neo4j và Ollama đã được bật, dữ liệu ChromaDB đã được nạp).*

---

## 17. Kiểm thử tự động (Testing)

Chạy toàn bộ bộ kiểm thử tự động của dự án:
```powershell
uv run pytest
```

### Kết quả kiểm thử thực tế:
**36 / 36 tests PASSED (100%)** trên 7 nhóm kiểm thử:
- `tests/test_api.py`: 7 tests (kiểm tra các endpoint `/`, `/health`, `/chat`, mã lỗi HTTP 400, 500 và trạng thái LLM).
- `tests/test_chroma.py`: 5 tests (kiểm tra kết nối, tính embedding, tạo collection và tìm kiếm ngữ nghĩa).
- `tests/test_config.py`: 3 tests (kiểm tra đọc biến môi trường và giá trị mặc định).
- `tests/test_evaluation.py`: 5 tests (kiểm tra tập đánh giá, tính toán Hit@k và mock evaluation).
- `tests/test_hybrid.py`: 5 tests (kiểm tra trích xuất thực thể và logic hợp nhất nguồn).
- `tests/test_neo4j.py`: 5 tests (kiểm tra kết nối Cypher, ràng buộc duy nhất và số lượng đồ thị).
- `tests/test_rag.py`: 6 tests (kiểm tra tạo context, grounding prompt, xử lý mất kết nối LLM và câu hỏi mẫu).

*(Lưu ý: Một cảnh báo `StarletteDeprecationWarning` có thể xuất hiện do phiên bản `TestClient` của bên thứ ba, nhưng không ảnh hưởng đến tính đúng đắn và toàn bộ 36 tests đều vượt qua).*

---

## 18. Kết quả Đánh giá Thực tế (Phase 8 Results)

Các chỉ số dưới đây được đo lường thực tế trên tập kiểm thử 30 câu hỏi đại diện từ dữ liệu gốc:

| Thành phần đo lường | Chỉ số đo được | Ý nghĩa kết quả |
| :--- | :---: | :--- |
| **Quy mô tập test** | 30 câu hỏi | Trích xuất xác định từ dữ liệu gốc, bao phủ 3 hãng, 6 loại thiết bị. |
| **ChromaDB Hit@1** | **73.3%** (22/30) | Tỷ lệ tìm đúng tài liệu ngay vị trí đầu tiên qua vector search. |
| **ChromaDB Hit@5** | **96.7%** (29/30) | Tỷ lệ tài liệu chuẩn xuất hiện trong top 5 kết quả vector. |
| **ChromaDB Latency** | **718.0 ms** | Tốc độ tìm kiếm ngữ nghĩa nhanh và ổn định. |
| **Neo4j Hit@1 / Hit@5**| **50.0%** (15/30) | Đạt 100% đối với câu hỏi có mã lỗi kỹ thuật tường minh. |
| **Neo4j Latency** | **2,067.8 ms** | Tốc độ thực thi truy vấn Cypher quan hệ. |
| **Hybrid Hit@1** | **66.7%** (20/30) | Tỷ lệ tìm đúng vị trí đầu tiên sau khi hợp nhất. |
| **Hybrid Hit@5** | **96.7%** (29/30) | Đạt độ phủ cao tương đương ChromaDB, đảm bảo có tài liệu đúng trong top 5. |
| **Số tài liệu `both`**| **40 lượt** | Số tài liệu được đồng thời cả Vector và Graph bảo chứng tin cậy. |
| **Tỷ lệ gọi LLM thành công** | **100%** (10/10) | Mô hình Qwen2.5:7B phản hồi ổn định qua Ollama. |
| **Độ trễ sinh từ LLM**| **31.77 giây** | Thời gian sinh câu trả lời trung bình trên phần cứng cục bộ. |
| **Đánh giá Grounding** | **10 / 10 (100%)** | Toàn bộ 10 câu trả lời rà soát đều bám sát 100% ngữ cảnh, không có ảo giác. |

> **Lưu ý minh bạch học thuật**:
> - Các số liệu trên là kết quả đo lường trên tập mẫu 30 câu hỏi đánh giá, không mang nghĩa toàn bộ hệ thống đạt độ chính xác 100% trên mọi trường hợp đời thực.
> - Trong thử nghiệm này, `Hybrid Hit@1` (66.7%) thấp hơn `ChromaDB Hit@1` (73.3%) do cơ chế ưu tiên tài liệu tìm thấy từ cả hai nguồn (`both`) đôi khi đưa một tài liệu liên quan khác cùng mã lỗi lên trên tài liệu câu hỏi mục tiêu. Đây là một điểm đánh đổi thực tế giữa độ phủ tri thức và độ xếp hạng chính xác đơn lẻ.

---

## 19. Ví dụ Thực tế: Luồng Dữ liệu Q0358

Xem xét bản ghi thực tế **Q0358** từ tập dữ liệu:
- **Câu hỏi**: *"Máy điều hòa Samsung lỗi CF là gì?"*
- **Hãng**: Samsung | **Thiết bị**: Điều hòa | **Mã lỗi**: CF
- **Bản ghi đồ thị**: Node `Question` (`Q0358`) $\rightarrow$ Node `Issue` (`I0249`) $\rightarrow$ Node `Answer` (`A0358`)
- **Nguyên nhân**: *"Mã CF là nhắc vệ sinh bộ lọc."*
- **Cách khắc phục**: *"Hãy vệ sinh hoặc thay bộ lọc rồi đặt lại nhắc lọc."*
- **Nguồn tài liệu**: [Trang hỗ trợ chính thức của Samsung](https://www.samsung.com/vn/support/home-appliances/check-out-the-displayed-error-codes-on-the-indoor-unit-air-conditioner/)

### Luồng xử lý qua hệ thống:
1. **Excel $\rightarrow$ Databases**: Bản ghi được nạp thành 1 vector document trong ChromaDB và 7 nodes kết nối trên đồ thị Neo4j.
2. **Hybrid Retrieval**: Trích xuất thực thể `Samsung`, `Điều hòa`, `CF`. Cả ChromaDB và Neo4j đều tìm thấy Q0358 $\rightarrow$ Gán nhãn `retrieval_source: "both"` và xếp vị trí số 1.
3. **Context Construction**: Ghép dữ liệu thành đoạn văn bản kỹ thuật có cấu trúc rõ ràng.
4. **Prompting & LLM**: Đưa vào Prompt với nguyên tắc cấm suy diễn. Mô hình `Qwen2.5:7B` sinh câu trả lời ngắn gọn:
   > *"Máy điều hòa Samsung lỗi CF là mã lỗi cảnh báo bạn cần vệ sinh bộ lọc. Cách khắc phục là vệ sinh hoặc thay bộ lọc rồi đặt lại máy."*
5. **API Response**: Trả về client qua endpoint `/chat` với đầy đủ câu trả lời, trạng thái LLM, danh sách tài liệu tham khảo và đường link dẫn chứng.

---

## 20. Giới hạn của Hệ thống (Limitations)

1. **Độ trễ của mô hình ngôn ngữ lớn cục bộ**: Do chạy mô hình 7 tỷ tham số (`Qwen2.5:7B`) trực tiếp trên phần cứng máy tính cá nhân qua Ollama mà không dùng hạ tầng đám mây chuyên dụng, thời gian sinh câu trả lời dao động từ 20 đến 55 giây.
2. **Kích thước tập mẫu đánh giá**: Tập kiểm thử gồm 30 câu hỏi được chọn lọc đại diện từ 1.090 bản ghi, phản ánh xu hướng chất lượng nhưng chưa thể bao quát hết toàn bộ các biến thể câu hỏi phức tạp trong thực tế.
3. **Truy vấn triệu chứng trên Neo4j**: Bộ trích xuất thực thể hiện tại phát huy hiệu quả cao nhất với các câu hỏi có mã lỗi kỹ thuật cụ thể. Các câu hỏi miêu tả triệu chứng chung chưa có mã lỗi vẫn dựa nhiều vào khả năng so khớp ngữ nghĩa của ChromaDB.
4. **Thuật toán Hybrid đơn giản**: Hệ thống sử dụng phép hợp nhất trực tiếp theo ID thay vì áp dụng thuật toán chấm điểm và tái xếp hạng nâng cao (reranking).

---

## 21. An toàn Dữ liệu & Bảo mật Git

- File `.env` chứa mật khẩu cục bộ được liệt kê trong `.gitignore` và **tuyệt đối không được commit lên kho mã nguồn**.
- Sử dụng `.env.example` làm mẫu cấu hình với các giá trị placeholder an toàn (`your_password_here`).
- Thư mục dữ liệu vector cục bộ `chroma_data/` được loại trừ trong `.gitignore`.
- Tuyệt đối không lưu trữ khóa bí mật, token hay mật khẩu thực tế trong bất kỳ tệp tài liệu nào.

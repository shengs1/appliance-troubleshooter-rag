# appliance-troubleshooter-rag

Chatbot hỗ trợ tra cứu và hướng dẫn xử lý sự cố thiết bị điện tử gia dụng (điều hòa, tủ lạnh, máy giặt, máy sấy, lò vi sóng, máy lọc không khí) sử dụng kỹ thuật RAG (Retrieval-Augmented Generation).

---

## Giới thiệu

Đây là project xây dựng chatbot hỗ trợ tra cứu và hướng dẫn xử lý sự cố thiết bị điện tử gia dụng bằng kỹ thuật RAG.

Hệ thống giúp người dùng tìm kiếm nguyên nhân và cách khắc phục khi thiết bị gặp trục trặc hoặc báo mã lỗi, áp dụng cho 3 hãng phổ biến: Samsung, LG và Panasonic.

Để tránh hiện tượng mô hình ngôn ngữ tự bịa ra thông tin kỹ thuật sai lệch, chatbot áp dụng cơ chế truy vấn thông tin trước từ cơ sở dữ liệu (ChromaDB và Neo4j), sau đó mới đưa dữ liệu thực tế vào ngữ cảnh để mô hình ngôn ngữ cục bộ (Local LLM) tổng hợp câu trả lời cho người dùng.

---

## Công nghệ sử dụng

- **Python 3.12**: Ngôn ngữ lập trình chính của dự án.
- **ChromaDB**: Cơ sở dữ liệu vector (Vector Database) dùng để lưu trữ vector nhúng của các tài liệu kỹ thuật và thực hiện tìm kiếm tương đồng ngữ nghĩa (semantic search).
- **BAAI/bge-m3**: Mô hình embedding đa ngữ hỗ trợ tốt tiếng Việt, chạy qua thư viện `sentence-transformers`.
- **Neo4j**: Cơ sở dữ liệu đồ thị (Graph Database) lưu trữ các mối quan hệ có cấu trúc giữa Hãng, Thiết bị, Sự cố, Mã lỗi, Câu hỏi, Câu trả lời và Nguồn tài liệu.
- **Ollama & Qwen2.5:7B**: Nền tảng chạy mô hình ngôn ngữ lớn cục bộ trên máy tính cá nhân, giúp xử lý và trả lời câu hỏi mà không cần gửi dữ liệu ra dịch vụ bên ngoài.
- **FastAPI**: Web framework xây dựng REST API để cung cấp giao diện kết nối cho chatbot.
- **uv & pytest**: Công cụ quản lý môi trường ảo, dependencies và thực thi unit tests.

---

## Kiến trúc hệ thống

Quy trình xử lý một câu hỏi của người dùng diễn ra theo các bước:

```text
Người dùng / Client
       │
       ▼ (HTTP POST /chat)
   FastAPI
       │
       ▼
generate_rag_answer()
       │
       ├────────────────────────┬────────────────────────┐
       ▼                        ▼                        ▼
ChromaDB (Vector Search)   Neo4j (Graph Search)    Từ khóa mã lỗi/hãng
       │                        │                        │
       └────────────────────────┴────────────────────────┘
                                │
                                ▼
                        Hybrid Retrieval
                    (Gộp kết quả & xếp hạng)
                                │
                                ▼
                          build_context()
                     (Tạo ngữ cảnh kỹ thuật)
                                │
                                ▼
                       Prompt bám sát dữ liệu
                                │
                                ▼
                     Ollama (Qwen2.5:7B Local)
                                │
                                ▼
                        Phản hồi JSON
```

1. **Tiếp nhận câu hỏi**: Client gửi câu hỏi dạng JSON tới endpoint `POST /chat` của FastAPI.
2. **Truy vấn đa nguồn (Hybrid Retrieval)**:
   - ChromaDB tìm kiếm các đoạn văn bản có ý nghĩa gần nhất với câu hỏi.
   - Neo4j trích xuất mã lỗi hoặc tên hãng để truy vấn các nút và mối quan hệ tương ứng trên đồ thị.
3. **Tổng hợp ngữ cảnh**: Ghép các kết quả tìm thấy thành một đoạn ngữ cảnh rõ ràng, ưu tiên các bản ghi được cả hai nguồn xác nhận.
4. **Sinh câu trả lời**: Đưa ngữ cảnh và câu hỏi vào prompt, gửi tới Ollama (Qwen2.5:7B) để mô hình sinh câu trả lời ngắn gọn, bám sát tài liệu.
5. **Trả kết quả**: Trả về cho client câu trả lời kèm thông tin trích dẫn nguồn và trạng thái thực thi.

---

## Dataset

Dữ liệu được lưu trong file `data/raw/dataset.xlsx` gồm 1.090 bản ghi hỏi đáp về sự cố thiết bị điện tử.

Cấu trúc các cột chính:
- `ID`: Mã định danh bản ghi (ví dụ `Q0001`, `Q0358`).
- `Hãng`: Samsung, LG, Panasonic.
- `Thiết_bị`: Điều hòa, Tủ lạnh, Máy giặt, Máy sấy, Lò vi sóng, Máy lọc không khí,...
- `Mã_lỗi`: Mã báo lỗi trên màn hình hoặc đèn tín hiệu (ví dụ: `CF`, `E1`, `dE`, `F11`).
- `Sự_cố`: Mô tả ngắn về hiện tượng hoặc tên sự cố.
- `Câu_hỏi_làm_sạch`: Câu hỏi chuẩn hóa của người dùng.
- `Nguyên_nhân`: Nguyên nhân kỹ thuật gây ra lỗi.
- `Cách_khắc_phục`: Các bước xử lý hoặc khuyến cáo khắc phục.
- `Trả_lời`: Nội dung hướng dẫn chi tiết hoặc câu trả lời tổng hợp.
- `Nguồn`: Đường dẫn trang hỗ trợ kỹ thuật chính hãng hoặc nguồn tài liệu tham khảo.

File Excel này được dùng làm nguồn để nạp dữ liệu vào cả ChromaDB và Neo4j.

---

## ChromaDB

ChromaDB đảm nhiệm việc tìm kiếm ngữ nghĩa theo nội dung câu hỏi.

- **Collection name**: `electronics_troubleshooting`
- **Thư mục lưu trữ**: `./chroma_data`
- **Embedding model**: `BAAI/bge-m3`
- **Cơ chế biểu diễn**: Mỗi dòng dữ liệu trong dataset tương ứng với 1 document trong ChromaDB. Nội dung document được ghép từ Hãng, Thiết bị, Mã lỗi, Sự cố, Câu hỏi, Nguyên nhân và Cách khắc phục.
- **Metadata**: Lưu các thông tin phụ trợ như `question_id`, `brand`, `device`, `error_code`, `issue_type`, `url` để phục vụ lọc và trích xuất nguồn.

Khi người dùng đặt câu hỏi bằng ngôn ngữ tự nhiên (kể cả khi không nhớ chính xác mã lỗi), ChromaDB tính toán khoảng cách vector và trả về top-k tài liệu liên quan nhất.

---

## Neo4j

Neo4j đảm nhiệm việc truy vấn quan hệ có cấu trúc giữa các thực thể kỹ thuật.

### Các loại Node trong đồ thị:
- `Brand` (3 nodes): Samsung, LG, Panasonic.
- `Device` (10 nodes): Điều hòa, Tủ lạnh, Máy giặt, Máy sấy, Máy lọc không khí, Lò vi sóng,...
- `Issue` (632 nodes): Các vấn đề, sự cố kỹ thuật cụ thể.
- `ErrorCode` (332 nodes): Các mã lỗi hiển thị trên thiết bị.
- `Question` (1090 nodes): Nội dung câu hỏi.
- `Answer` (1090 nodes): Chi tiết nguyên nhân và cách khắc phục.
- `Source` (31 nodes): Nguồn trang web tài liệu tham khảo.

### Các mối quan hệ (Relationships):
- `(:Brand)-[:HAS_DEVICE]->(:Device)`
- `(:Device)-[:HAS_ISSUE]->(:Issue)`
- `(:Issue)-[:HAS_ERROR_CODE]->(:ErrorCode)`
- `(:Question)-[:ABOUT]->(:Issue)`
- `(:Question)-[:ANSWERED_BY]->(:Answer)`
- `(:Answer)-[:SOURCED_FROM]->(:Source)`

Tổng số nút trên đồ thị: **3.188 nodes** và **4.391 relationships**.

Truy vấn được thực hiện bằng Cypher có truyền tham số để lọc nhanh theo mã lỗi hoặc tên thiết bị và hãng.

---

## Hybrid Retrieval

Hybrid Retrieval kết hợp điểm mạnh của cả ChromaDB và Neo4j:

- **ChromaDB**: Hiệu quả với câu hỏi miêu tả triệu chứng tự nhiên, tìm kiếm theo ngữ nghĩa.
- **Neo4j**: Hiệu quả với câu hỏi chứa mã lỗi cụ thể hoặc cần tra cứu chính xác quan hệ giữa hãng và thiết bị.

Quy trình kết hợp:
1. Trích xuất mã lỗi và tên hãng từ câu hỏi của người dùng bằng biểu thức chính quy và từ khóa.
2. Thực hiện song song truy vấn vector trên ChromaDB và truy vấn đồ thị trên Neo4j.
3. Gộp danh sách kết quả, chuẩn hóa dữ liệu theo định dạng chung và loại bỏ trùng lặp dựa trên `question_id`.
4. Nếu một tài liệu xuất hiện ở cả hai nguồn (`retrieval_source = "both"`), tài liệu đó sẽ được ưu tiên xếp lên đầu danh sách để đưa vào ngữ cảnh.

---

## RAG + Local LLM

Sau khi có danh sách tài liệu từ bước tìm kiếm kết hợp:

1. **Tạo Context (`build_context`)**: Chuẩn hóa thông tin từng tài liệu gồm mã câu hỏi, hãng, thiết bị, mã lỗi/sự cố, nguyên nhân, cách khắc phục và đường dẫn nguồn.
2. **Cấu hình Prompt**: Prompt yêu cầu mô hình:
   - Chỉ sử dụng các thông tin có trong ngữ cảnh được cung cấp.
   - Không tự ý suy diễn nguyên nhân kỹ thuật hoặc thêm các khuyến cáo chung chung khi tài liệu không đề cập.
   - Trả lời rõ ràng, trực diện vào nguyên nhân và cách khắc phục.
   - Nếu ngữ cảnh không có thông tin phù hợp, trả lời rõ ràng là cơ sở dữ liệu hiện chưa có thông tin này.
3. **Gọi Ollama**: Gửi prompt tới mô hình `qwen2.5:7b` chạy qua Ollama API cục bộ (`http://localhost:11434/api/generate`).

---

## FastAPI

Ứng dụng cung cấp API thông qua FastAPI tại file `src/rag_chatbot/main.py`.

### Các endpoints:

- `GET /`: Trả về thông tin cơ bản về dịch vụ.
- `GET /health`: Kiểm tra trạng thái hoạt động của server.
- `POST /chat`: Tiếp nhận câu hỏi và trả về kết quả RAG.

### Ví dụ Request:

```bash
curl -X POST "http://localhost:8000/chat" \
  -H "Content-Type: application/json" \
  -d '{"question": "Máy điều hòa Samsung lỗi CF là gì?"}'
```

### Ví dụ Response:

```json
{
  "question": "Máy điều hòa Samsung lỗi CF là gì?",
  "answer": "Mã lỗi CF trên điều hòa Samsung là nhắc vệ sinh bộ lọc.\n\nCách khắc phục: Hãy vệ sinh hoặc thay bộ lọc rồi đặt lại nhắc lọc.",
  "llm_status": "success",
  "retrieved_documents": [
    {
      "question_id": "Q0358",
      "brand": "Samsung",
      "device": "Máy điều hòa",
      "error_code": "CF",
      "cause": "Mã CF là nhắc vệ sinh bộ lọc.",
      "solution": "Hãy vệ sinh hoặc thay bộ lọc rồi đặt lại nhắc lọc.",
      "retrieval_source": "both",
      "url": "https://www.samsung.com/vn/support/home-appliances/what-does-a-blinking-filter-light-or-cf-code-mean-on-my-room-air-conditioner/"
    }
  ],
  "sources": [
    "https://www.samsung.com/vn/support/home-appliances/what-does-a-blinking-filter-light-or-cf-code-mean-on-my-room-air-conditioner/"
  ]
}
```

---

## Cài đặt và chạy project

### Yêu cầu môi trường:
- Windows / Linux / macOS
- Python 3.12
- Công cụ quản lý gói `uv`
- Neo4j Desktop hoặc Neo4j Community Server
- Ollama đã cài đặt mô hình `qwen2.5:7b`

### Các bước cài đặt:

1. **Clone repository**:
   ```powershell
   git clone https://github.com/<USERNAME>/appliance-troubleshooter-rag.git
   cd appliance-troubleshooter-rag
   ```

2. **Cài đặt thư viện với `uv`**:
   ```powershell
   uv sync
   ```

3. **Cấu hình file `.env`**:
   Sao chép file mẫu:
   ```powershell
   Copy-Item .env.example .env
   ```
   Mở file `.env` và điền mật khẩu Neo4j thực tế của bạn:
   ```ini
   APP_NAME=appliance-troubleshooter-rag
   APP_ENV=development
   DEBUG=True

   NEO4J_URI=bolt://localhost:7687
   NEO4J_USER=neo4j
   NEO4J_PASSWORD=your_password_here

   CHROMA_PERSIST_DIRECTORY=./chroma_data
   CHROMA_COLLECTION_NAME=electronics_troubleshooting

   EMBEDDING_MODEL_NAME=BAAI/bge-m3
   OLLAMA_BASE_URL=http://localhost:11434
   LLM_MODEL_NAME=qwen2.5:7b
   ```

4. **Khởi động dịch vụ hỗ trợ**:
   - Mở Neo4j và khởi động database (port 7687).
   - Mở Ollama và tải model:
     ```powershell
     ollama pull qwen2.5:7b
     ```

5. **Nạp dữ liệu vào cơ sở dữ liệu**:
   - Nạp dữ liệu vào Neo4j:
     ```powershell
     uv run python -m rag_chatbot.neo4j_db
     ```
   - Nạp dữ liệu vào ChromaDB:
     ```powershell
     uv run python -m rag_chatbot.ingest
     ```

6. **Chạy thử nghiệm RAG từ terminal**:
   ```powershell
   $env:PYTHONIOENCODING="utf-8"; uv run python -m rag_chatbot.rag
   ```

7. **Chạy server FastAPI**:
   ```powershell
   uv run uvicorn rag_chatbot.main:app --reload --port 8000
   ```
   Xem tài liệu API tự động tại: `http://localhost:8000/docs`.

---

## Cấu trúc thư mục

```text
appliance-troubleshooter-rag/
├── chroma_data/                         # Thư mục lưu trữ dữ liệu ChromaDB
├── data/
│   ├── evaluation/
│   │   ├── evaluation_set.json          # Tập 30 câu hỏi kiểm thử
│   │   └── rag_eval_results.json        # Kết quả chi tiết đánh giá RAG + LLM
│   ├── processed/                       # Dữ liệu qua xử lý trung gian
│   ├── raw/
│   │   └── dataset.xlsx                 # Bộ dữ liệu gốc 1.090 bản ghi
│   └── samples/
├── scripts/                             # Các script tiện ích
├── src/
│   └── rag_chatbot/
│       ├── __init__.py
│       ├── chroma_db.py                 # Kết nối và cấu hình ChromaDB
│       ├── config.py                    # Quản lý cấu hình qua pydantic-settings
│       ├── evaluation.py                # Đo lường và đánh giá hiệu năng
│       ├── ingest.py                    # Nạp dữ liệu vào ChromaDB
│       ├── main.py                      # Ứng dụng FastAPI REST API
│       ├── neo4j_db.py                  # Kết nối và nạp dữ liệu Neo4j
│       ├── rag.py                       # Xử lý Prompt, Context và gọi LLM
│       └── retrieval.py                 # Logic tìm kiếm ChromaDB, Neo4j, Hybrid
├── tests/
│   ├── test_api.py                      # Test các API endpoints của FastAPI
│   ├── test_chroma.py                   # Test kết nối và tìm kiếm ChromaDB
│   ├── test_config.py                   # Test nạp biến môi trường
│   ├── test_evaluation.py               # Test các hàm tính chỉ số đánh giá
│   ├── test_hybrid.py                   # Test thuật toán tìm kiếm kết hợp
│   ├── test_neo4j.py                    # Test kết nối và truy vấn Neo4j
│   └── test_rag.py                      # Test prompt, context và luồng RAG
├── .env.example                         # File mẫu cấu hình môi trường
├── .gitignore                           # Danh sách bỏ qua của Git
├── EVALUATION.md                        # Báo cáo chi tiết kết quả đánh giá
├── pyproject.toml                       # Cấu hình dự án và dependencies
├── README.md                            # Tài liệu hướng dẫn sử dụng dự án
└── uv.lock                              # Khóa phiên bản thư viện chính xác
```

---

## Kiểm thử

Dự án có 36 unit tests bao quát các thành phần từ cấu hình, truy vấn database, pipeline RAG cho tới các endpoint FastAPI.

Chạy toàn bộ kiểm thử bằng lệnh:

```powershell
uv run pytest
```

Kết quả:
```text
36 passed, 1 warning in ~2 phút
```

---

## Kết quả đánh giá

Hệ thống được đánh giá trên tập dữ liệu chuẩn gồm **30 câu hỏi thực tế** trích xuất từ dataset, đại diện cho cả 3 hãng và 6 nhóm thiết bị khác nhau.

Chi tiết báo cáo được ghi nhận tại file `EVALUATION.md`.

### 1. Hiệu năng truy vấn (Retrieval Metrics trên 30 câu hỏi, k = 5):

| Phương pháp tìm kiếm | Hit@1 | Hit@5 | Độ trễ trung bình |
| :--- | :---: | :---: | :---: |
| **ChromaDB** (Semantic Search) | 22 / 30 (**73.3%**) | 29 / 30 (**96.7%**) | ~718 ms |
| **Neo4j** (Graph Search) | 15 / 30 (**50.0%**) | 15 / 30 (**50.0%**) | ~2.068 ms |
| **Hybrid Retrieval** (ChromaDB + Neo4j) | 20 / 30 (**66.7%**) | 29 / 30 (**96.7%**) | ~2.210 ms |

- **ChromaDB**: Hiểu tốt câu hỏi triệu chứng hư hỏng bằng ngôn ngữ tự nhiên.
- **Neo4j**: Tìm kiếm chính xác với các câu hỏi có mã lỗi cụ thể (15/15 câu hỏi có mã lỗi đều tìm thấy), nhưng hạn chế hơn với các câu hỏi chỉ miêu tả triệu chứng chung.
- **Hybrid Retrieval**: Giữ được độ bao phủ Hit@5 ở mức **96.7%**, đồng thời ưu tiên được 40 lượt tài liệu được xác thực bởi cả hai cơ sở dữ liệu (`both`).

### 2. Đánh giá sinh câu trả lời RAG + Local LLM (trên 10 câu hỏi):

- **Tỷ lệ gọi LLM thành công**: **10 / 10** (không có lượt nào bị ngắt kết nối hay lỗi timeout).
- **Thời gian phản hồi sinh câu trả lời (Latency)**:
  - Trung bình: **31.77 giây**.
  - Nhanh nhất: **22.22 giây**.
  - Lâu nhất: **55.21 giây**.

### 3. Đánh giá tính bám sát ngữ cảnh (Grounding Review):

Qua kiểm tra đối chiếu thủ công 10 câu trả lời sinh ra từ LLM so với ngữ cảnh tài liệu:
- **10 / 10 câu trả lời** bám sát nội dung ngữ cảnh được trích xuất.
- Mô hình không tự ý thêm các thao tác sửa chữa hoặc suy đoán ngoài phạm vi tài liệu.
- Khi gặp câu hỏi chung chung không đủ thông tin, mô hình phản hồi rõ ràng rằng cơ sở tri thức hiện tại chưa đủ dữ liệu thay vì tự đưa ra giả định.

---

## Ví dụ Q0358

Một ví dụ điển hình minh họa luồng xử lý của hệ thống:

- **Câu hỏi**: `"Máy điều hòa Samsung lỗi CF là gì?"`
- **Tài liệu truy vấn được**:
  - Hãng: Samsung | Thiết bị: Máy điều hòa | Mã lỗi: CF
  - Nguyên nhân: *Mã CF là nhắc vệ sinh bộ lọc.*
  - Cách khắc phục: *Hãy vệ sinh hoặc thay bộ lọc rồi đặt lại nhắc lọc.*
  - Nguồn: Trang hỗ trợ chính thức của Samsung.
- **Câu trả lời từ Chatbot**:
  > Mã lỗi CF trên điều hòa Samsung là nhắc vệ sinh bộ lọc.
  >
  > Cách khắc phục: Hãy vệ sinh hoặc thay bộ lọc rồi đặt lại nhắc lọc.
- **Nhận xét**: Câu trả lời truyền đạt đúng bản chất sự cố và hướng xử lý theo tài liệu của nhà sản xuất, không thêm các chi tiết ngoài như "bộ lọc bị bẩn" hay "liên hệ thợ kỹ thuật".

---

## Giới hạn

- **Thời gian phản hồi của LLM**: Khi chạy mô hình 7B cục bộ trên phần cứng máy tính cá nhân thông thường, thời gian sinh câu trả lời trung bình khoảng 31.8 giây, chưa phù hợp cho các kịch bản cần phản hồi tức thì.
- **Truy vấn triệu chứng trên Neo4j**: Tìm kiếm đồ thị hiện tại chủ yếu phụ thuộc vào việc bóc tách mã lỗi và tên hãng. Khi người dùng chỉ hỏi triệu chứng hư hỏng chung mà không có mã lỗi, Neo4j khó so khớp hơn so với tìm kiếm vector của ChromaDB.
- **Phạm vi dữ liệu**: Tập dữ liệu hiện có 1.090 bản ghi tập trung vào 3 hãng sản xuất chính (Samsung, LG, Panasonic). Khi người dùng hỏi về các hãng khác hoặc model quá đặc thù chưa có trong dữ liệu, hệ thống sẽ thông báo chưa có thông tin.

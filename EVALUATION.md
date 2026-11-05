# BÁO CÁO ĐÁNH GIÁ CHẤT LƯỢNG HỆ THỐNG RAG CHATBOT (EVALUATION.md)
## Trợ Lý Sự Cố Thiết Bị Điện Gia Dụng

> **Ghi chú tài liệu**: Báo cáo này tổng hợp kết quả đo lường thực nghiệm của hệ thống trên tập 200 câu hỏi trong phạm vi (in-scope), 30 câu hỏi ngoài phạm vi (out-of-scope) và 26 câu hỏi kiểm thử toàn trình Local LLM kết hợp Answer Validator. Toàn bộ số liệu được trích xuất từ quá trình chạy thực tế nhằm đối chiếu minh bạch trong quá trình bảo vệ đồ án.

---

## 1. Mục tiêu đánh giá

Hệ thống thực hiện đánh giá định lượng và đối sánh công bằng giữa các thành phần cốt lõi trong kiến trúc RAG:
1. **ChromaDB only**: Truy vấn tương đồng ngữ nghĩa (Semantic Search với `BAAI/bge-m3`) kết hợp lọc metadata theo Hãng (`brand`) và Loại thiết bị (`device`).
2. **Neo4j only**: Truy vấn đồ thị quan hệ tri thức (Cypher Graph Search) kết hợp thực thể Hãng, Thiết bị, Mã lỗi và Triệu chứng.
3. **Hybrid Retrieval (ChromaDB + Neo4j + Rule-based Reranking)**: Hợp nhất kết quả từ cả hai nguồn với cơ chế đánh dấu xác thực kép (`retrieval_source = "both"`) và xếp hạng lại theo trọng số thực thể.
4. **Bộ lọc phạm vi (Scope Guard)**: Đo lường tỷ lệ từ chối câu hỏi ngoài phạm vi (Out-of-Scope Refusal Rate) và tỷ lệ từ chối nhầm câu hỏi hợp lệ (In-Scope False Refusal Rate).
5. **Local LLM & Answer Validator**: Đánh giá độ bám sát ngữ cảnh (**Groundedness**), chống ảo giác mã lỗi/linh kiện (**Anti-hallucination**), độ trễ phản hồi và trích dẫn nguồn tham khảo (**Source Attribution**).

---

## 2. Tập dữ liệu đánh giá (`data/evaluation/`)

### 2.1. Tập kiểm thử In-Scope (`data/evaluation/evaluation_set_200.json`)
Được lấy mẫu phân tầng có kiểm soát từ dữ liệu gốc `data/raw/dataset.xlsx`:
- **Tổng số**: 200 câu hỏi độc lập có nhãn chuẩn `question_id`.
- **Phân bổ theo Hãng (Brand)**:
  - **Samsung**: 80 câu (40.0%)
  - **Panasonic**: 65 câu (32.5%)
  - **LG**: 55 câu (27.5%)
- **Phân bổ theo Loại vấn đề (Issue Type)**:
  - **ERROR_CODE**: 98 câu (49.0%)
  - **SYMPTOM**: 98 câu (49.0%)
  - **ERROR_CODE_UNKNOWN**: 4 câu (2.0%)
- **Phân bổ theo Loại thiết bị (Device)**:
  - Đầy đủ 10 nhóm thiết bị: Tủ lạnh (47), Máy giặt (43), Điều hòa (41), Máy sấy (26), Lò vi sóng (23), Máy rửa bát (6), Lò nướng (5), Bếp (4), TV (3), Máy lọc không khí (2).

### 2.2. Tập kiểm thử Out-of-Scope (`data/evaluation/out_of_scope_30.json`)
Gồm 30 câu hỏi thuộc các chủ đề nằm ngoài phạm vi kỹ thuật của hệ thống:
- Thiết bị công nghệ cá nhân (điện thoại, laptop, iPhone, MacBook)
- Sản phẩm gia dụng không có trong CSDL (robot hút bụi, máy ép, nồi chiên không dầu)
- Thương hiệu ngoài phạm vi dữ liệu gốc hoặc câu hỏi mua bán, giá cả, bảo hành thương mại
- Kiến thức phổ thông, lập trình, thời tiết, nấu ăn, tài chính, thể thao

### 2.3. Tập kiểm thử toàn trình LLM & Validator (`data/evaluation/answer_validation_set.json`)
Gồm 26 câu hỏi đại diện bao phủ cả 3 hãng (Samsung, LG, Panasonic), 7 chủng loại thiết bị và đầy đủ các nhóm sự cố (`ERROR_CODE`, `SYMPTOM`, `ERROR_CODE_UNKNOWN`).

---

## 3. Định nghĩa các chỉ số đo lường

- **Hit@k ($k \in \{1, 3, 5\}$)**: Tỷ lệ phần trăm câu hỏi mà tài liệu đúng chuẩn (`expected_question_id`) xuất hiện trong top-$k$ kết quả truy vấn trả về.
- **MRR (Mean Reciprocal Rank)**:
  $$\text{MRR} = \frac{1}{|Q|} \sum_{i=1}^{|Q|} \frac{1}{\text{rank}_i}$$
  Trong đó $\text{rank}_i$ là thứ hạng xuất hiện đầu tiên của tài liệu đúng trong top-$5$ (nếu không xuất hiện, tính bằng 0).
- **Latency (ms)**: Thời gian xử lý truy vấn tính bằng mili-giây, gồm **Trung bình (Mean)** và **Trung vị (Median)** sau bước khởi tạo kết nối.
- **Refusal Rate / False Refusal Rate**: Tỷ lệ từ chối đúng câu hỏi ngoài phạm vi và tỷ lệ từ chối nhầm câu hỏi hợp lệ.

---

## 4. Kết quả thực nghiệm truy vấn (Retrieval Benchmark - 200 câu, k=5)

### 4.1. So sánh tổng thể các phương thức truy vấn

| Phương thức truy vấn | Hit@1 | Hit@3 | Hit@5 | MRR | Độ trễ TB (ms) | Độ trễ Trung vị (ms) |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| **ChromaDB only** (Semantic + Metadata Filter) | **87.0%** | 98.0% | **99.5%** | 0.9260 | 120.24 ms | 117.23 ms |
| **Neo4j only** (Cypher Graph Search) | 36.5% | 47.5% | 47.5% | 0.4167 | **13.44 ms** | **2.76 ms** |
| **Hybrid Baseline** (Chưa áp dụng Reranking) | 74.0% | 97.0% | **99.5%** | 0.8404 | 122.66 ms | 119.50 ms |
| **Hybrid + Rule-based Reranking** *(Mặc định)* | **87.0%** | **98.5%** | **99.5%** | **0.9283** | 127.24 ms | 131.36 ms |

> **Phân bổ nguồn tài liệu trong Top-5 của Hybrid**:
> - Nguồn chỉ từ ChromaDB: **782 tài liệu (78.44%)**
> - Nguồn xác thực kép đồng thời từ cả ChromaDB & Neo4j (`both`): **215 tài liệu (21.56%)**

---

### 4.2. Phân tích chi tiết theo Loại vấn đề (By Issue Type)

| Loại vấn đề | Số câu | Phương thức | Hit@1 | Hit@3 | Hit@5 | MRR |
| :--- | :---: | :--- | :---: | :---: | :---: | :---: |
| **ERROR_CODE** (Câu hỏi có mã lỗi) | 98 | ChromaDB | **88.78%** | 98.98% | **100.0%** | 0.9391 |
| | | Neo4j | 71.43% | 91.84% | 91.84% | 0.8112 |
| | | Hybrid + Rerank | **88.78%** | **100.0%** | **100.0%** | **0.9439** |
| **SYMPTOM** (Câu hỏi theo triệu chứng) | 98 | ChromaDB | **84.69%** | **96.94%** | **98.98%** | **0.9099** |
| | | Neo4j | 3.06% | 5.10% | 5.10% | 0.0391 |
| | | Hybrid + Rerank | **84.69%** | **96.94%** | **98.98%** | **0.9099** |
| **ERROR_CODE_UNKNOWN** (Mã lỗi chưa rõ) | 4 | ChromaDB | **100.0%** | **100.0%** | **100.0%** | **1.0000** |
| | | Neo4j | 0.0% | 0.0% | 0.0% | 0.0000 |
| | | Hybrid + Rerank | **100.0%** | **100.0%** | **100.0%** | **1.0000** |

---

### 4.3. Phân tích chi tiết theo Hãng sản xuất (By Brand)

| Thương hiệu | Số câu | ChromaDB Hit@1 | Neo4j Hit@1 | Hybrid + Rerank Hit@1 | Hybrid + Rerank Hit@5 | Hybrid + Rerank MRR |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| **LG** | 55 | 96.36% | 27.27% | **96.36%** | **100.0%** | **0.9818** |
| **Panasonic** | 65 | 81.54% | 43.08% | **81.54%** | **100.0%** | **0.9077** |
| **Samsung** | 80 | 85.00% | 37.50% | **85.00%** | **98.75%** | **0.9083** |

---

### 4.4. Nhận xét kỹ thuật về tầng Hybrid Retrieval & Reranking

1. **Vai trò bổ trợ giữa ChromaDB và Neo4j**:
   - **ChromaDB** xử lý tốt các câu hỏi ngôn ngữ tự nhiên và mô tả triệu chứng (`SYMPTOM`), đạt **Hit@5 = 99.5%**.
   - **Neo4j** truy xuất cực nhanh (**~2.76 ms**) và chính xác theo quan hệ thực thể đối với nhóm câu hỏi chứa mã lỗi (`ERROR_CODE` đạt **Hit@5 = 91.84%**).
2. **Hiệu quả của Rule-based Reranking (`src/rag_chatbot/retrieval.py`)**:
   - Khi chỉ ưu tiên đơn thuần `retrieval_source == "both"` (Hybrid Baseline), một số câu hỏi triệu chứng bị kéo lệch thứ hạng xuống Rank 2–3 (Hit@1 = 74.0%).
   - Sau khi kết hợp hàm điểm xếp hạng tuyến tính theo độ gần ngữ nghĩa + điểm thưởng thực thể khớp chính xác (Hãng `+0.08`, Thiết bị `+0.08`, Mã lỗi `+0.20`, Nguồn kép `+0.02`), **Hit@1 tăng từ 74.0% lên 87.0% (+13.0%)** và **MRR tăng từ 0.8404 lên 0.9283**, trong khi chi phí tính toán chỉ mất **~0.03 ms**.
3. **Bản chất của 26 câu hỏi ở Rank 2 (Ngưỡng 87.0% Hit@1)**:
   - Trong tập dữ liệu gốc `dataset.xlsx` tồn tại các cặp bản ghi đồng nghĩa/trùng lặp (`Duplicate_Group`, ví dụ `Q0158` và `Q0308` cùng hướng dẫn xử lý điều hòa Panasonic lỗi `F16` với nội dung giống nhau).
   - Khi hệ thống xếp bản ghi cùng tri thức lên Rank 1 thay vì đúng mã `expected_question_id`, chỉ số Exact-ID Hit@1 ghi nhận là trượt Rank 1, nhưng **về mặt tri thức kỹ thuật người dùng vẫn nhận được đúng hướng dẫn xử lý sự cố ngay ở kết quả đầu tiên** (Hit@5 đạt **99.5%**, 199/200 câu).

---

## 5. Đánh giá Bộ lọc phạm vi (Scope Guard - `src/rag_chatbot/scope.py`)

Kiểm thử tự động trên tập 30 câu Out-of-Scope và 200 câu In-Scope:

| Tập kiểm thử | Quy mô | Kết quả đạt được | Ý nghĩa thực tế |
| :--- | :---: | :---: | :--- |
| **Out-of-Scope** (`out_of_scope_30.json`) | 30 câu | Từ chối **30 / 30 (100.0%)** | Chặn triệt để câu hỏi ngoài ngành, False Acceptance = **0.0%** |
| **In-Scope** (`evaluation_set_200.json`) | 200 câu | Chấp nhận **190 / 200 (95.0%)** | Giảm thiểu từ chối nhầm xuống mức thấp (**5.0%**) |

### Cải tiến xử lý ngôn ngữ tự nhiên trong `scope.py`:
- Bổ sung từ điển cụm triệu chứng tự nhiên có từ đệm thường gặp trong đời thực (*"không đủ mát"*, *"không được mát"*, *"làm lạnh kém"*, *"lạnh yếu"*, *"kêu to"*, *"nháy đèn"*...).
- Áp dụng kiểm tra ranh giới từ (`\b`) cho các từ đơn ngắn như `"hư"`, `"mã"` để tránh khớp nhầm chuỗi con trong các từ tiếng Việt phổ thông (ví dụ không bắt nhầm `"hư"` trong chữ *"phương pháp"*).

---

## 6. Đánh giá Chất lượng sinh của Local LLM (12 câu đại diện)

Kiểm thử quy trình RAG hoàn chỉnh (Hybrid Retrieval $\rightarrow$ Prompt $\rightarrow$ Ollama `qwen2.5:7b`) trên 12 câu hỏi đa dạng:

| ID | Câu hỏi | Hãng / Thiết bị | Mã lỗi | Trạng thái | Grounded | Không bịa mã | Nguồn trích dẫn | Độ trễ (s) |
|:---:|:---|:---|:---:|:---:|:---:|:---:|:---|:---:|
| `Q0001` | tủ lạnh LG Mã lỗi rS | LG / Tủ lạnh | rS | Success | **OK** | **OK** | Trang khắc phục sự cố LG | 8.67s |
| `Q0003` | tủ lạnh LG lỗi ER CL và ER CL | LG / Tủ lạnh | ER CL | Success | **OK** | **OK** | Trang khắc phục sự cố LG | 19.18s |
| `Q0157` | Điều hoà panasonic bị lỗi F11 | Panasonic / Điều hòa | F11 | Success | **OK** | **OK** | Trang tra mã lỗi máy lạnh Panasonic | 18.73s |
| `Q0158` | Điều hoà panasonic bị lỗi F16 | Panasonic / Điều hòa | F16 | Success | **OK** | **OK** | Trang tra mã lỗi máy lạnh Panasonic | 15.17s |
| `Q0358` | Máy điều hòa Samsung lỗi CF | Samsung / Điều hòa | CF | Success | **OK** | **OK** | Hướng dẫn mã lỗi điều hòa Samsung | 8.56s |
| `Q0360` | Máy điều hòa Samsung lỗi E1 | Samsung / Điều hòa | E1 | Success | **OK** | **OK** | Hướng dẫn mã lỗi điều hòa Samsung | 13.54s |
| `Q0417` | Máy sấy Samsung lỗi do | Samsung / Máy sấy | do | Success | **OK** | **OK** | Hướng dẫn mã lỗi máy sấy Samsung | 10.07s |
| `Q0691` | LG Máy giặt không vào nước? | LG / Máy giặt | - | Success | **OK** | **OK** | Trang khắc phục sự cố LG | 11.79s |
| `Q0692` | LG Máy sấy không sấy khô? | LG / Máy sấy | - | Success | **OK** | **OK** | Thư viện trợ giúp máy sấy LG | 6.93s |
| `Q0841` | Panasonic Máy giặt không vào nước? | Panasonic / Máy giặt | - | Success | **OK** | **OK** | Chăm sóc máy giặt Panasonic | 12.33s |
| `Q0842` | Panasonic Tủ lạnh không lạnh? | Panasonic / Tủ lạnh | - | Success | **OK** | **OK** | Kinh nghiệm tủ lạnh Panasonic | 10.70s |
| `Q0993` | Samsung Điều hòa không đủ mát? | Samsung / Điều hòa | - | Success | **OK** | **OK** | Trang thiết bị gia dụng Samsung | 8.24s |

---

## 7. Đánh giá Tầng Kiểm định Câu trả lời (Answer Validator - `src/rag_chatbot/answer_validator.py`)

### 7.1. Mục đích & Nguyên tắc thiết kế
Sau khi Ollama `qwen2.5:7b` sinh văn bản, câu trả lời được kiểm định qua module `answer_validator.py` trước khi trả về giao diện người dùng:
- **Rule-based tường minh**: Kiểm tra trực tiếp bằng Python thuần túy dựa trên tập luật nhất quán thực thể, không dùng LLM thứ hai để chấm điểm nhằm giữ tốc độ tức thì (**~0.37 ms**) và dễ kiểm soát.
- **Các tiêu chí kiểm tra**:
  1. **Brand Consistency**: Không tráo hãng (ví dụ hỏi `Samsung` không được trả lời sang `LG` hoặc `Panasonic`).
  2. **Device Consistency**: Không tráo loại thiết bị (ví dụ hỏi `Điều hòa` không trả lời sang `Tủ lạnh`).
  3. **Error Code Consistency**: Giữ đúng mã lỗi người dùng hỏi, không tự ý bịa mã lỗi lạ đối với câu hỏi triệu chứng; phân biệt số đo thời gian (*"60 giây"*) với mã lỗi kỹ thuật và hỗ trợ nhóm đa mã lỗi (`d80, d90, d95`).
  4. **Technical Groundedness**: Phát hiện và chặn trường hợp mô hình tự suy diễn thao tác can thiệp sâu (`bo mạch`, `máy nén/lốc`, `nạp gas`...) khi tài liệu gốc không đề cập.
  5. **Safe Fallback**: Nếu `status == "fail"`, hệ thống tự động trả về thông báo an toàn thay vì hiển thị nội dung chưa kiểm chứng.

### 7.2. Kết quả thực nghiệm trên 26 câu hỏi đại diện (`data/evaluation/answer_validation_results.json`)

| Chỉ số đo lường | Giá trị đạt được | Mục tiêu đề ra | Kết luận |
| :--- | :---: | :---: | :--- |
| **Số lượng câu đánh giá** | **26 câu** | 20 – 30 câu | Đạt chuẩn đại diện |
| **Validation Pass Rate** | **100.0%** (26/26) | $\ge 90\%$ | Đạt yêu cầu |
| **Fail / Hallucination Rate** | **0.0%** (0/26) | $\le 5\%$ | Không xuất hiện ảo giác |
| **Brand / Device / Error Code Consistency** | **100.0%** (26/26) | 100% | Nhất quán tuyệt đối |
| **Độ trễ trung bình của Answer Validator** | **0.37 ms** | $< 5\text{ ms}$ | Tức thì (~0.001% tổng thời gian) |

---

## 8. Tổng kết kiểm thử hệ thống

1. **Chất lượng truy vấn (Hybrid Retrieval)**: Đạt **Hit@1 = 87.0%**, **Hit@3 = 98.5%**, **Hit@5 = 99.5%**, **MRR = 0.9283** trên 200 câu hỏi độc lập.
2. **An toàn phạm vi & chống ảo giác**: Chặn **100%** câu hỏi ngoài phạm vi trên tập kiểm thử Out-of-Scope và đạt **100% Pass Rate** qua tầng kiểm định `Answer Validator`.
3. **Kiểm thử phần mềm tự động (`pytest`)**: Toàn bộ hệ thống gồm **14 module kiểm thử cốt lõi với 135 test cases** kiểm tra đầy đủ từ xử lý tiếng Việt, ChromaDB, Neo4j, Hybrid RAG, Answer Validator, xác thực Argon2id, mã hóa AES Fernet cho Brevo SMTP, Admin Dashboard đến FastAPI & Chainlit UI.

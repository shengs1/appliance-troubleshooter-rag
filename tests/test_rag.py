"""Kiem thu chuc nang RAG Generation voi Local LLM (Phase 6).

Cac test case bao gom:
1. Kiem thu ham xay dung ngu canh (build_context) tu danh sach tai lieu.
2. Kiem thu ham tao prompt (create_prompt) chua day du cau hoi, ngu canh va quy tac chong ao giac.
3. Kiem thu ham dieu phoi RAG (generate_rag_answer) voi cau hoi thuc te Q0358:
   - Truy van duoc dung Q0358
   - Ngu canh co day du thong tin Samsung, Dieu hoa, CF, ve sinh bo loc
   - Prompt chua day du ngu canh va cau hoi
4. Kiem thu xu ly ngoai le ket noi khi dich vu Local LLM offline (bao loi ro rang, khong gia mao ket qua).
5. Kiem thu luong sinh cau tra loi khi LLM phan hoi thanh cong.
"""

from unittest.mock import patch
import pytest

from rag_chatbot.rag import (
    build_context,
    call_local_llm,
    create_prompt,
    generate_rag_answer,
)


def test_build_context_from_retrieved_results():
    """Kiem tra ham build_context tao ra chuoi van ban ngu canh ro rang tu danh sach ban ghi."""
    sample_docs = [
        {
            "question_id": "Q0358",
            "question": "Máy điều hòa Samsung lỗi CF",
            "answer": "Nguyên nhân sự cố: Mã CF là nhắc vệ sinh bộ lọc. Cách khắc phục: Hãy vệ sinh hoặc thay bộ lọc rồi đặt lại nhắc lọc.",
            "brand": "Samsung",
            "device": "Điều hòa",
            "error_code": "CF",
            "source_url": "https://www.samsung.com/vn/support/",
            "retrieval_source": "both",
        }
    ]

    context = build_context(sample_docs)

    assert "TÀI LIỆU THAM KHẢO 1" in context
    assert "Hãng: Samsung" in context
    assert "Thiết bị: Điều hòa" in context
    assert "Mã lỗi: CF" in context
    assert "nhắc vệ sinh bộ lọc" in context
    assert "thay bộ lọc" in context
    assert "https://www.samsung.com/vn/support/" in context


def test_create_prompt_contains_question_and_context():
    """Kiem tra prompt sinh ra chua day du cau hoi nguoi dung, ngu canh va quy tac bat buoc."""
    question = "Máy điều hòa Samsung lỗi CF là gì?"
    context = "Hãng: Samsung | Thiết bị: Điều hòa | Mã lỗi: CF | Cách khắc phục: Vệ sinh bộ lọc"

    prompt = create_prompt(question, context)

    # Kiem tra noi dung prompt
    assert question in prompt
    assert context in prompt
    # Kiem tra cac chi dan chong ao giac (Grounding instructions)
    assert "NGỮ CẢNH KỸ THUẬT" in prompt
    assert "Tuyệt đối KHÔNG tự sáng tác" in prompt
    assert "cơ sở tri thức chưa có đủ thông tin" in prompt


def test_rag_pipeline_with_q0358_example():
    """Kiem tra toan bo luong RAG tich hop thuc te voi ban ghi Q0358.
    
    Xac thuc:
    - search_hybrid duoc thuc thi va tim thay Q0358
    - Context duoc xay dung chua dung tri thuc ve sinh bo loc
    - Prompt chua day du thong tin can thiet
    """
    question = "Máy điều hòa Samsung lỗi CF là gì?"
    result = generate_rag_answer(question, k=5)

    assert result["question"] == question

    # Kiem tra tai lieu truy van chua Q0358
    doc_ids = [d["question_id"] for d in result["retrieved_documents"]]
    assert "Q0358" in doc_ids, f"Q0358 phai xuat hien trong retrieved_documents: {doc_ids}"

    # Kiem tra ngu canh duoc tao ra
    context = result["context"]
    assert "Samsung" in context
    assert "Điều hòa" in context
    assert "CF" in context
    assert "vệ sinh bộ lọc" in context

    # Kiem tra prompt tong hop
    prompt = result["prompt"]
    assert question in prompt
    assert "CF" in prompt
    assert "Samsung" in prompt


def test_call_local_llm_handles_connection_error():
    """Kiem tra call_local_llm bao loi ro rang khi dich vu Local LLM khong kha dung."""
    # Goi toi cong khong ton tai de kiem tra viec bat loi ket noi
    with pytest.raises(ConnectionError) as exc_info:
        call_local_llm("test prompt", base_url="http://localhost:59999", timeout=1)

    assert "Không thể kết nối tới dịch vụ Local LLM" in str(exc_info.value)


def test_generate_rag_answer_with_mocked_llm():
    """Kiem tra generate_rag_answer tich hop voi cau tra loi mo phong tu LLM hop le."""
    mock_response = (
        "Theo tài liệu của Samsung, mã lỗi CF trên máy điều hòa là thông báo nhắc nhở người dùng "
        "cần vệ sinh hoặc thay thế bộ lọc không khí. Bạn nên vệ sinh bộ lọc rồi thiết lập lại nhắc nhở."
    )

    with patch("rag_chatbot.rag.call_local_llm", return_value=mock_response):
        res = generate_rag_answer("Máy điều hòa Samsung lỗi CF là gì?")
        assert res["llm_status"] == "success"
        assert "vệ sinh hoặc thay thế bộ lọc" in res["answer"]
        assert "Q0358" in [d["question_id"] for d in res["retrieved_documents"]]

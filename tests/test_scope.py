"""Kiem thu co che phat hien va tu choi cau hoi ngoai pham vi (Phase 10A).

Cac test case bao gom:
1. Danh sach retrieved_documents rong -> should_refuse = True.
2. Tai lieu co khoang cach xa (> threshold) -> should_refuse = True.
3. Tai lieu phu hop voi khoang cach thap va co bang chung loi -> should_refuse = False.
4. Cau hoi co ten hang nhung ngoai pham vi ('Samsung co san xuat o to khong?') -> bi tu choi.
5. Cau hoi co ten thiet bi va hang nhung khong phai troubleshooting ('Dieu hoa Samsung co tot khong?') -> bi tu choi.
6. Cau hoi co hang + thiet bi dien thoai ngoai pham vi ('Samsung ra mat dien thoai moi nao?') -> bi tu choi.
7. Cau hoi hoan toan ngoai pham vi ('Python la gi?') -> bi tu choi.
8. Kiem tra cau hoi ngoai pham vi KHONG goi local LLM (Qwen2.5:7b).
9. Kiem tra cau hoi in-scope GOI local LLM binh thuong.
10. Endpoint POST /chat tra ve HTTP 200 voi llm_status='refused_scope' va khong bi loi 500.
11. UI chat_fn hien thi thong bao tu choi gon gang va khong dinh kem nguon tham khao.
"""

from unittest.mock import patch
import pytest
from fastapi.testclient import TestClient

from rag_chatbot.main import app
from rag_chatbot.rag import generate_rag_answer
from rag_chatbot.scope import (
    REFUSAL_MESSAGE,
    has_troubleshooting_signal,
    should_refuse,
)
from rag_chatbot.ui import chat_fn


client = TestClient(app)


def test_should_refuse_when_documents_empty():
    """Kiem tra tu choi khi danh sach tai lieu rong."""
    assert should_refuse([]) is True
    assert should_refuse([], question="Samsung lỗi CF") is True


def test_should_refuse_when_distance_exceeds_threshold():
    """Kiem tra tu choi khi tai lieu co khoang cach lon hon nguong cho phep."""
    docs = [
        {
            "question_id": "Q9999",
            "question": "Không liên quan",
            "answer": "Không liên quan",
            "distance": 0.65,
            "error_code": "",
            "retrieval_source": "chroma",
        }
    ]
    # Nguong mac dinh la 0.40, khoang cach 0.65 phai bi tu choi
    assert should_refuse(docs, question="Python là gì?", threshold=0.40) is True


def test_should_not_refuse_valid_in_scope_document():
    """Kiem tra chap nhan khi tai lieu co khoang cach tot va cau hoi co bang chung su co."""
    docs = [
        {
            "question_id": "Q0358",
            "question": "Máy điều hòa Samsung lỗi CF",
            "answer": "Mã CF là nhắc vệ sinh bộ lọc.",
            "distance": 0.25,
            "error_code": "CF",
            "brand": "Samsung",
            "device": "Điều hòa",
            "retrieval_source": "both",
        }
    ]
    assert should_refuse(docs, question="Samsung lỗi CF là gì?", threshold=0.40) is False


def test_refuse_tricky_out_of_scope_questions():
    """Kiem tra cac truong hop bien: co hang hoac thiet bi nhung khong phai troubleshooting."""
    mock_doc = {
        "question_id": "Q0993",
        "question": "Samsung Điều hòa không đủ mát?",
        "answer": "Kiểm tra chế độ và bộ lọc.",
        "distance": 0.26,
        "error_code": "",
        "brand": "Samsung",
        "device": "Điều hòa",
        "retrieval_source": "chroma",
    }

    # 1. Co hang + thiet bi nhung hoi y kien/review ("co tot khong")
    assert should_refuse([mock_doc], question="Điều hòa Samsung có tốt không?") is True

    # 2. Co hang nhung hoi ve o to
    mock_doc_far = dict(mock_doc, distance=0.48)
    assert should_refuse([mock_doc_far], question="Samsung có sản xuất ô tô không?") is True

    # 3. Co hang nhung hoi ve dien thoai moi
    mock_doc_phone = dict(mock_doc, distance=0.55)
    assert should_refuse([mock_doc_phone], question="Samsung ra mắt điện thoại mới nào?") is True

    # 4. Hoan toan ngoai le
    mock_doc_python = dict(mock_doc, distance=0.63)
    assert should_refuse([mock_doc_python], question="Python là gì?") is True


def test_out_of_scope_does_not_call_local_llm():
    """Kiem tra quy trinh RAG: cau hoi ngoai pham vi TUYET DOI KHONG goi den Local LLM."""
    with patch("rag_chatbot.rag.call_local_llm") as mock_llm:
        result = generate_rag_answer("Python là gì?")

        # LLM khong duoc phep goi
        mock_llm.assert_not_called()
        assert result["llm_status"] == "refused_scope"
        assert result["answer"] == REFUSAL_MESSAGE
        assert result["prompt"] == ""
        assert result["context"] == ""


def test_in_scope_calls_local_llm():
    """Kiem tra quy trinh RAG: cau hoi in-scope van goi Local LLM binh thuong."""
    with patch("rag_chatbot.rag.call_local_llm", return_value="Hướng dẫn sửa chữa") as mock_llm:
        result = generate_rag_answer("Samsung lỗi CF là gì?")

        # LLM phai duoc goi
        mock_llm.assert_called_once()
        assert result["llm_status"] == "success"
        assert result["answer"] == "Hướng dẫn sửa chữa"


def test_api_chat_refusal_returns_200():
    """Kiem tra endpoint POST /chat xu ly tu choi tra ve HTTP 200 va dung format (khong loi 500)."""
    response = client.post("/chat", json={"question": "Bitcoin hôm nay giá bao nhiêu?"})

    assert response.status_code == 200
    data = response.json()
    assert data["llm_status"] == "refused_scope"
    assert REFUSAL_MESSAGE in data["answer"]
    assert data["sources"] == []


def test_ui_chat_fn_refusal_display():
    """Kiem tra ham chat_fn cua Gradio UI hien thi cau tra loi tu choi khong chua nguon."""
    history, empty_input = chat_fn("Messi đang thi đấu cho đội nào?", history=[])

    assert empty_input == ""
    assert len(history) == 2
    assert history[0]["role"] == "user"
    assert history[1]["role"] == "assistant"
    assert REFUSAL_MESSAGE in history[1]["content"]
    assert "**Nguồn tham khảo:**" not in history[1]["content"]

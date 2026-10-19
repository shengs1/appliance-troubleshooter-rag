"""Kiem thu chuc nang Neural Reranking voi BAAI/bge-reranker-v2-m3.

Bao gom:
1. Format candidate text: dam bao du cac truong Hang, Thiet bi, Ma loi, Cau hoi, Cau tra loi.
2. Danh sach ung vien rong: tra ve rong an toan.
3. Danh sach chi co 1 ung vien: xu ly an toan va gan reranker_score.
4. Mock cross-encoder: sap xep giam dan, bao toan metadata, cat dung top_k.
5. Tich hop thuc te: goi rerank_with_model tren 2 ung vien voi model thuc te de kiem tra tinh dung dan.
"""

from unittest.mock import MagicMock
import pytest
from rag_chatbot.reranker import (
    format_candidate_text,
    get_reranker,
    rerank_with_model,
)


def test_format_candidate_text():
    """Kiem tra dinh dang van ban dau vao cho Cross-Encoder."""
    candidate = {
        "brand": "Samsung",
        "device": "Điều hòa",
        "error_code": "CF",
        "question": "Máy điều hòa Samsung báo lỗi CF",
        "answer": "Vệ sinh lưới lọc bụi của dàn lạnh.",
    }
    text = format_candidate_text(candidate)
    assert "Hãng: Samsung" in text
    assert "Thiết bị: Điều hòa" in text
    assert "Mã lỗi: CF" in text
    assert "Câu hỏi: Máy điều hòa Samsung báo lỗi CF" in text
    assert "Câu trả lời: Vệ sinh lưới lọc bụi của dàn lạnh." in text


def test_rerank_empty_results():
    """Kiem tra danh sach ung vien rong tra ve rong."""
    assert rerank_with_model("Samsung điều hòa", []) == []
    assert rerank_with_model("", []) == []


def test_rerank_single_candidate():
    """Kiem tra 1 ung vien duoc giu nguyen va co reranker_score."""
    candidate = {
        "question_id": "Q001",
        "brand": "Samsung",
        "device": "Điều hòa",
        "question": "Điều hòa không mát",
        "answer": "Kiểm tra gas",
    }
    results = rerank_with_model("Điều hòa không mát", [candidate])
    assert len(results) == 1
    assert results[0]["question_id"] == "Q001"
    assert "reranker_score" in results[0]


def test_rerank_with_mock_model():
    """Kiem tra logic sap xep giam dan va bao toan metadata voi mock model."""
    mock_model = MagicMock()
    # Mock tra ve score: ung vien 1 score 0.35, ung vien 2 score 0.92
    mock_model.predict.return_value = [0.35, 0.92]

    candidates = [
        {
            "question_id": "Q001",
            "brand": "Samsung",
            "device": "Điều hòa",
            "question": "Điều hòa Samsung kêu to",
            "answer": "Kê lại chân đế",
            "source_url": "https://example.com/1",
            "retrieval_source": "chroma",
        },
        {
            "question_id": "Q002",
            "brand": "Samsung",
            "device": "Điều hòa",
            "question": "Điều hòa Samsung lỗi CF",
            "answer": "Vệ sinh lưới lọc",
            "source_url": "https://example.com/2",
            "retrieval_source": "both",
        },
    ]

    reranked = rerank_with_model(
        query="Samsung lỗi CF",
        results=candidates,
        top_k=2,
        model=mock_model,
    )

    # Q002 co score 0.92 phai len dau
    assert len(reranked) == 2
    assert reranked[0]["question_id"] == "Q002"
    assert reranked[0]["reranker_score"] == 0.92
    assert reranked[0]["source_url"] == "https://example.com/2"
    assert reranked[0]["retrieval_source"] == "both"

    # Q001 phai o vi tri thu 2
    assert reranked[1]["question_id"] == "Q001"
    assert reranked[1]["reranker_score"] == 0.35


def test_rerank_top_k_limit():
    """Kiem tra gioi han so luong tra ve boi top_k."""
    mock_model = MagicMock()
    mock_model.predict.return_value = [0.1, 0.8, 0.5, 0.9]

    candidates = [
        {"question_id": f"Q{i}", "question": f"Question {i}"}
        for i in range(1, 5)
    ]

    reranked = rerank_with_model(
        query="Test query",
        results=candidates,
        top_k=2,
        model=mock_model,
    )
    assert len(reranked) == 2
    assert reranked[0]["question_id"] == "Q4"  # score 0.9
    assert reranked[1]["question_id"] == "Q2"  # score 0.8


def test_real_model_integration():
    """Kiem tra tich hop voi mo hinh BAAI/bge-reranker-v2-m3 thuc te."""
    query = "Điều hòa Samsung không mát"
    matching_cand = {
        "question_id": "Q_MATCH",
        "brand": "Samsung",
        "device": "Điều hòa",
        "error_code": "",
        "question": "Điều hòa Samsung không lạnh cần xử lý sao?",
        "answer": "Kiểm tra chế độ Cool, vệ sinh lưới lọc và dàn nóng.",
    }
    irrelevant_cand = {
        "question_id": "Q_OTHER",
        "brand": "LG",
        "device": "Máy giặt",
        "error_code": "UE",
        "question": "Máy giặt LG rung lắc báo lỗi UE",
        "answer": "Kê lại chân máy giặt và phân bổ đều quần áo.",
    }

    reranked = rerank_with_model(query, [irrelevant_cand, matching_cand], top_k=2)

    assert len(reranked) == 2
    # Tai lieu Samsung Dieu hoa khong mat phai duoc model danh gia diem cao hon
    assert reranked[0]["question_id"] == "Q_MATCH"
    assert reranked[0]["reranker_score"] > reranked[1]["reranker_score"]

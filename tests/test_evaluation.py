"""Kiem thu module danh gia he thong RAG (Phase 8 - Evaluation).

Cac test case bao gom:
1. Tap du lieu danh gia load thanh cong tu JSON va dung 30 ban ghi.
2. Moi ban ghi co day du cac truong co ban (question_id, question, brand, device, issue_type).
3. Ban ghi Q0358 co mat trong tap danh gia.
4. Tinh toan Hit@1 va Hit@5 chinh xac voi cac truong hop bien.
5. evaluate_chroma tra ve dung cau truc voi du lieu mock.
6. evaluate_neo4j tra ve dung cau truc voi du lieu mock.
7. evaluate_hybrid tra ve dung cau truc va dem duoc both_source_count voi du lieu mock.
8. evaluate_rag tra ve dung thong ke thanh cong/that bai va do tre voi du lieu mock.
"""

from unittest.mock import patch
import pytest

from rag_chatbot.evaluation import (
    load_evaluation_set,
    calculate_hit_at_k,
    calculate_mrr,
    evaluate_chroma,
    evaluate_neo4j,
    evaluate_hybrid,
    evaluate_rag,
)


def test_load_evaluation_set_structure():
    """Kiem tra load_evaluation_set doc duoc 30 ban ghi voi day du truong thong tin."""
    eval_set = load_evaluation_set()
    assert len(eval_set) == 30

    required_fields = ["question_id", "question", "brand", "device", "issue_type"]
    for item in eval_set:
        for field in required_fields:
            assert field in item, f"Trường {field} bị thiếu trong {item}"
        assert item["question_id"].startswith("Q")


def test_q0358_exists_in_evaluation_set():
    """Kiem tra ban ghi mau Q0358 nam trong tap danh gia."""
    eval_set = load_evaluation_set()
    q0358 = next((item for item in eval_set if item["question_id"] == "Q0358"), None)
    assert q0358 is not None
    assert q0358["brand"] == "Samsung"
    assert q0358["error_code"] == "CF"


def test_calculate_hit_at_k():
    """Kiem tra logic tinh Hit@k."""
    docs = ["Q0001", "Q0002", "Q0003", "Q0004", "Q0005"]
    assert calculate_hit_at_k(docs, "Q0001", 1) is True
    assert calculate_hit_at_k(docs, "Q0002", 1) is False
    assert calculate_hit_at_k(docs, "Q0002", 5) is True
    assert calculate_hit_at_k(docs, "Q9999", 5) is False


def test_evaluate_retrievals_with_mocks():
    """Kiem tra cac ham danh gia retrieval voi mock data khong phu thuoc vao database live."""
    sample_eval = [
        {"question_id": "Q0001", "question": "Hỏi câu 1"},
        {"question_id": "Q0002", "question": "Hỏi câu 2"},
    ]

    mock_docs_q1 = [{"question_id": "Q0001", "retrieval_source": "both"}]
    mock_docs_q2 = [{"question_id": "Q9999", "retrieval_source": "chroma"}, {"question_id": "Q0002", "retrieval_source": "both"}]

    with patch("rag_chatbot.evaluation.search_similar_documents") as mock_chroma, \
         patch("rag_chatbot.evaluation.search_graph") as mock_neo4j, \
         patch("rag_chatbot.evaluation.search_hybrid") as mock_hybrid:

        mock_chroma.side_effect = [mock_docs_q1, mock_docs_q2]
        mock_neo4j.side_effect = [mock_docs_q1, mock_docs_q2]
        mock_hybrid.side_effect = [mock_docs_q1, mock_docs_q2]

        res_chroma = evaluate_chroma(sample_eval)
        assert res_chroma["total_queries"] == 2
        assert res_chroma["hit_1_count"] == 1
        assert res_chroma["hit_5_count"] == 2
        assert res_chroma["hit_1_rate"] == 50.0
        assert res_chroma["hit_5_rate"] == 100.0

        res_neo = evaluate_neo4j(sample_eval)
        assert res_neo["total_queries"] == 2
        assert res_neo["hit_1_count"] == 1
        assert res_neo["hit_5_count"] == 2

        res_hybrid = evaluate_hybrid(sample_eval)
        assert res_hybrid["total_queries"] == 2
        assert res_hybrid["hit_1_count"] == 1
        assert res_hybrid["hit_5_count"] == 2
        assert res_hybrid["both_source_count"] == 2


def test_evaluate_rag_with_mocks():
    """Kiem tra ham evaluate_rag tinh toan dung latency va success count ma khong can Ollama live."""
    sample_eval = [
        {"question_id": "Q0001", "question": "Hỏi câu 1"},
        {"question_id": "Q0002", "question": "Hỏi câu 2"},
    ]

    mock_rag_res1 = {
        "question": "Hỏi câu 1",
        "answer": "Trả lời câu 1",
        "llm_status": "success",
        "context": "Context 1",
        "retrieved_documents": [],
    }
    mock_rag_res2 = {
        "question": "Hỏi câu 2",
        "answer": "Trả lời câu 2",
        "llm_status": "unavailable",
        "context": "Context 2",
        "retrieved_documents": [],
    }

    with patch("rag_chatbot.evaluation.generate_rag_answer", side_effect=[mock_rag_res1, mock_rag_res2]):
        rag_metrics = evaluate_rag(sample_eval)
        assert rag_metrics["total_evaluated"] == 2
        assert rag_metrics["llm_success_count"] == 1
        assert rag_metrics["llm_unavailable_count"] == 1
        assert rag_metrics["avg_latency_seconds"] > 0
        assert len(rag_metrics["details"]) == 2


def test_calculate_mrr():
    """Kiem tra tinh toan Mean Reciprocal Rank (MRR)."""
    docs = ["Q0001", "Q0002", "Q0003", "Q0004", "Q0005"]
    assert calculate_mrr(docs, "Q0001", max_k=5) == 1.0
    assert calculate_mrr(docs, "Q0002", max_k=5) == 0.5
    assert calculate_mrr(docs, "Q0003", max_k=5) == pytest.approx(1.0 / 3.0)
    assert calculate_mrr(docs, "Q0005", max_k=5) == 0.2
    assert calculate_mrr(docs, "Q9999", max_k=5) == 0.0
    assert calculate_mrr([], "Q0001", max_k=5) == 0.0


def test_evaluation_set_200_validity():
    """Kiem tra tap du lieu danh gia 200 cau in-scope co day du 200 cau va hop le."""
    eval_200 = load_evaluation_set("data/evaluation/evaluation_set_200.json")
    assert len(eval_200) == 200

    required_fields = ["question_id", "question", "brand", "device", "issue_type"]
    brands = set()
    devices = set()
    issue_types = set()

    for item in eval_200:
        for field in required_fields:
            assert field in item, f"Trường {field} bị thiếu trong {item['question_id']}"
        brands.add(item["brand"])
        devices.add(item["device"])
        issue_types.add(item["issue_type"])

    # Kiem tra co du ca 3 brand va cac loai thiet bi / issue_type
    assert {"Samsung", "Panasonic", "LG"}.issubset(brands)
    assert len(devices) >= 5
    assert {"ERROR_CODE", "SYMPTOM"}.issubset(issue_types)

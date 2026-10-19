"""Unit tests cho module danh gia Knowledge-Aware Evaluation.

Kiem tra 10 truong hop bat buoc theo yeu cau:
1. Exact match
2. Duplicate group match
3. Twin knowledge match
4. Non-equivalent record
5. Expected rank 1
6. Expected rank 2 nhung knowledge rank 1
7. No match
8. Q0535 case
9. Empty Top-K
10. Khong lam thay doi retrieval results
"""

from rag_chatbot.knowledge_eval import (
    evaluate_query_dual_level,
    is_equivalent_knowledge,
    load_knowledge_equivalence_map,
)


def test_1_exact_match():
    """1. Exact match: retrieved_id == expected_id -> exact_rank=1, knowledge_rank=1."""
    equiv_map = {"Q0001": {"Q0001"}}
    retrieved = [{"question_id": "Q0001"}, {"question_id": "Q0002"}]
    res = evaluate_query_dual_level(retrieved, "Q0001", equiv_map)
    assert res["exact_rank"] == 1
    assert res["knowledge_rank"] == 1
    assert res["exact_hit_1"] is True
    assert res["knowledge_hit_1"] is True


def test_2_duplicate_group_match():
    """2. Duplicate group match: retrieved doc la ban ghi sinh doi trong cung Duplicate_Group."""
    equiv_map = {"Q0158": {"Q0158", "Q0308"}, "Q0308": {"Q0158", "Q0308"}}
    retrieved = [{"question_id": "Q0308"}, {"question_id": "Q0999"}]
    res = evaluate_query_dual_level(retrieved, "Q0158", equiv_map)
    assert res["exact_rank"] is None
    assert res["knowledge_rank"] == 1
    assert res["exact_hit_1"] is False
    assert res["knowledge_hit_1"] is True


def test_3_twin_knowledge_match():
    """3. Twin knowledge match: retrieved doc la twin cluster (cung error code hoac cau tra loi)."""
    equiv_map = {"Q0036": {"Q0036", "Q0103"}, "Q0103": {"Q0036", "Q0103"}}
    retrieved = [{"question_id": "Q0103"}]
    res = evaluate_query_dual_level(retrieved, "Q0036", equiv_map)
    assert res["exact_rank"] is None
    assert res["knowledge_rank"] == 1
    assert res["knowledge_hit_1"] is True


def test_4_non_equivalent_record():
    """4. Non-equivalent record: retrieved doc khong phai expected va khong thuoc cum tri thuc."""
    equiv_map = {"Q0001": {"Q0001"}}
    retrieved = [{"question_id": "Q0999"}, {"question_id": "Q0888"}]
    res = evaluate_query_dual_level(retrieved, "Q0001", equiv_map)
    assert res["exact_rank"] is None
    assert res["knowledge_rank"] is None
    assert res["exact_hit_1"] is False
    assert res["knowledge_hit_1"] is False


def test_5_expected_rank_1():
    """5. Expected rank 1: ca exact va knowledge deu dat rank 1."""
    equiv_map = {"Q0358": {"Q0358"}}
    retrieved = [{"question_id": "Q0358"}, {"question_id": "Q0359"}]
    res = evaluate_query_dual_level(retrieved, "Q0358", equiv_map)
    assert res["exact_rank"] == 1
    assert res["knowledge_rank"] == 1
    assert res["exact_mrr"] == 1.0
    assert res["knowledge_mrr"] == 1.0


def test_6_expected_rank_2_knowledge_rank_1():
    """6. Expected rank 2 nhung knowledge rank 1: Rank 1 la twin, Rank 2 la expected ID."""
    equiv_map = {"Q0002": {"Q0002", "Q0108"}, "Q0108": {"Q0002", "Q0108"}}
    retrieved = [
        {"question_id": "Q0108"},  # Rank 1: Twin
        {"question_id": "Q0002"},  # Rank 2: Expected
        {"question_id": "Q0041"},
    ]
    res = evaluate_query_dual_level(retrieved, "Q0002", equiv_map)
    assert res["exact_rank"] == 2
    assert res["knowledge_rank"] == 1
    assert res["exact_hit_1"] is False
    assert res["knowledge_hit_1"] is True
    assert res["exact_mrr"] == 0.5
    assert res["knowledge_mrr"] == 1.0


def test_7_no_match():
    """7. No match: khong co bat ky ket qua nao khop exact hoac knowledge trong top 5."""
    equiv_map = {"Q0500": {"Q0500"}}
    retrieved = [{"question_id": f"Q000{i}"} for i in range(1, 6)]
    res = evaluate_query_dual_level(retrieved, "Q0500", equiv_map)
    assert res["exact_rank"] is None
    assert res["knowledge_rank"] is None
    assert res["exact_hit_5"] is False
    assert res["knowledge_hit_5"] is False
    assert res["exact_mrr"] == 0.0
    assert res["knowledge_mrr"] == 0.0


def test_8_q0535_special_case():
    """8. Q0535 case: expected Q0535 khong nam trong top-5, nhung top-1 Q0690 la twin knowledge."""
    equiv_map = {"Q0535": {"Q0535", "Q0690"}, "Q0690": {"Q0535", "Q0690"}}
    retrieved = [
        {"question_id": "Q0690"},  # Top-1 twin
        {"question_id": "Q0597"},
        {"question_id": "Q0659"},
        {"question_id": "Q1006"},
        {"question_id": "Q0628"},
    ]
    res = evaluate_query_dual_level(retrieved, "Q0535", equiv_map)
    assert res["exact_rank"] is None
    assert res["knowledge_rank"] == 1
    assert res["exact_hit_1"] is False
    assert res["exact_hit_5"] is False
    assert res["knowledge_hit_1"] is True
    assert res["knowledge_hit_5"] is True
    assert res["exact_mrr"] == 0.0
    assert res["knowledge_mrr"] == 1.0


def test_9_empty_top_k():
    """9. Empty Top-K: xu ly an toan khi danh sach retrieved rong."""
    equiv_map = {"Q0001": {"Q0001"}}
    res = evaluate_query_dual_level([], "Q0001", equiv_map)
    assert res["exact_rank"] is None
    assert res["knowledge_rank"] is None
    assert res["exact_hit_1"] is False
    assert res["knowledge_hit_1"] is False
    assert res["exact_mrr"] == 0.0
    assert res["knowledge_mrr"] == 0.0
    assert res["match_details"] == []


def test_10_does_not_modify_retrieval_results():
    """10. Khong lam thay doi retrieval results: evaluation layer khong sua doi list hoac dict."""
    equiv_map = {"Q0001": {"Q0001", "Q0002"}}
    doc1 = {"question_id": "Q0002", "score": 0.95}
    doc2 = {"question_id": "Q0001", "score": 0.85}
    retrieved = [doc1, doc2]
    retrieved_copy = [dict(d) for d in retrieved]

    res = evaluate_query_dual_level(retrieved, "Q0001", equiv_map)

    assert len(retrieved) == 2
    assert retrieved == retrieved_copy
    assert retrieved[0]["question_id"] == "Q0002"
    assert retrieved[1]["question_id"] == "Q0001"

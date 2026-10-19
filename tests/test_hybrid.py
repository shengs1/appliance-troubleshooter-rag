"""Kiem thu chuc nang truy van ket hop Hybrid Retrieval (ChromaDB + Neo4j) - Phase 5.

Cac test case bao gom:
1. Kiem thu ham trich xuat thuc the co ban tu cau hoi (Hang, Thiet bi, Ma loi).
2. Kiem thu tim kiem rieng biet qua ChromaDB tim duoc Q0358.
3. Kiem thu tim kiem rieng biet qua Neo4j graph tim duoc Q0358.
4. Kiem thu ham truy van ket hop search_hybrid hoat dong tot va tim duoc Q0358.
5. Kiem thu ban ghi Q0358 duoc danh dau dung retrieval_source = 'both' khi ca 2 ben deu tim thay.
6. Kiem thu cau truc tra ve day du 8 truong thong tin theo yeu cau.
"""

import pytest

from rag_chatbot.retrieval import (
    extract_question_entities,
    search_graph,
    search_hybrid,
    search_similar_documents,
)


def test_extract_question_entities():
    """Kiem tra ham trich xuat thuc the nhan dien dung Hang, Thiet bi va Ma loi."""
    query = "Máy điều hòa Samsung lỗi CF là gì?"
    entities = extract_question_entities(query)

    assert entities["brand"] == "Samsung"
    assert entities["device"] == "Điều hòa"
    assert entities["error_code"] == "CF"


def test_chroma_retrieves_q0358():
    """Kiem tra tim kiem rieng biet tu ChromaDB co the tim thay Q0358."""
    query = "Máy điều hòa Samsung lỗi CF là gì?"
    chroma_results = search_similar_documents(query, k=5)

    assert len(chroma_results) > 0
    ids = [r["id"] for r in chroma_results]
    assert "Q0358" in ids, f"Q0358 khong xuat hien trong ket qua ChromaDB: {ids}"


def test_neo4j_retrieves_q0358():
    """Kiem tra tim kiem rieng biet tu Neo4j do thi co the tim thay Q0358."""
    query = "Máy điều hòa Samsung lỗi CF là gì?"
    neo4j_results = search_graph(query, k=5)

    assert len(neo4j_results) > 0
    ids = [r["question_id"] for r in neo4j_results]
    assert "Q0358" in ids, f"Q0358 khong xuat hien trong ket qua Neo4j: {ids}"


def test_hybrid_retrieval_finds_q0358_and_marks_both():
    """Kiem tra hybrid retrieval hop nhat dung va danh dau retrieval_source = 'both' cho Q0358."""
    query = "Máy điều hòa Samsung lỗi CF là gì?"
    hybrid_results = search_hybrid(query, k=5)

    assert len(hybrid_results) > 0

    # Tim ban ghi Q0358 trong ket qua
    q0358_items = [r for r in hybrid_results if r["question_id"] == "Q0358"]
    assert len(q0358_items) == 1, "Q0358 phai xuat hien dung 1 lan trong ket qua hop nhat"

    q0358 = q0358_items[0]
    # Kiem tra retrieval_source duoc danh dau la 'both'
    assert q0358["retrieval_source"] == "both"

    # Kiem tra Q0358 duoc uu tien dua len dau (top 1) vi co bang chung tu ca 2 nguon
    assert hybrid_results[0]["question_id"] == "Q0358"


def test_hybrid_result_structure():
    """Kiem tra cau truc ket qua hybrid chua day du cac truong theo yeu cau."""
    query = "Máy điều hòa Samsung lỗi CF là gì?"
    results = search_hybrid(query, k=5)

    expected_keys = [
        "question_id",
        "question",
        "answer",
        "brand",
        "device",
        "error_code",
        "source_url",
        "retrieval_source",
    ]

    for item in results:
        for key in expected_keys:
            assert key in item, f"Thieu key: {key} trong ban ghi hybrid"
        assert item["retrieval_source"] in ["chroma", "neo4j", "both"]


def test_device_name_normalization():
    """Kiem tra chuan hoa tat ca cac bien the ten goi thiet bi Dieu hoa ve 'Điều hòa'."""
    assert extract_question_entities("Máy lạnh Samsung không lạnh")["device"] == "Điều hòa"
    assert extract_question_entities("máy điều hòa Samsung không lạnh")["device"] == "Điều hòa"
    assert extract_question_entities("máy điều hoà Samsung không lạnh")["device"] == "Điều hòa"
    assert extract_question_entities("điều hòa Samsung không lạnh")["device"] == "Điều hòa"
    assert extract_question_entities("điều hoà Samsung không lạnh")["device"] == "Điều hòa"
    assert extract_question_entities("Tủ lạnh Samsung không lạnh")["device"] == "Tủ lạnh"


def test_case_a_may_lanh_samsung_khong_lanh():
    """Case A: 'Máy lạnh Samsung không lạnh' -> device = Điều hòa, không có source Tủ lạnh."""
    query = "Máy lạnh Samsung không lạnh"
    entities = extract_question_entities(query)
    assert entities["brand"] == "Samsung"
    assert entities["device"] == "Điều hòa"

    results = search_hybrid(query, k=5)
    assert len(results) > 0

    # Bao dam tat ca ban ghi deu thuoc ve Dieu hoa, tuyet doi khong co Tu lanh
    for r in results:
        assert r["device"] == "Điều hòa", f"Tim thay thiet bi sai: {r['device']}"
        assert "refrigerator" not in r["source_url"].lower(), "Nguon bi sai thanh nguon Tu lanh"


def test_case_b_dieu_hoa_samsung_khong_lanh():
    """Case B: 'Điều hòa Samsung không lạnh' -> device = Điều hòa."""
    query = "Điều hòa Samsung không lạnh"
    entities = extract_question_entities(query)
    assert entities["brand"] == "Samsung"
    assert entities["device"] == "Điều hòa"

    results = search_hybrid(query, k=5)
    assert len(results) > 0
    for r in results:
        assert r["device"] == "Điều hòa"


def test_case_c_tu_lanh_samsung_khong_lanh():
    """Case C: 'Tủ lạnh Samsung không lạnh' -> device = Tủ lạnh."""
    query = "Tủ lạnh Samsung không lạnh"
    entities = extract_question_entities(query)
    assert entities["brand"] == "Samsung"
    assert entities["device"] == "Tủ lạnh"

    results = search_hybrid(query, k=5)
    assert len(results) > 0
    for r in results:
        assert r["device"] == "Tủ lạnh"


def test_case_d_may_dieu_hoa_samsung_loi_cf():
    """Case D: 'Máy điều hòa Samsung lỗi CF' -> device = Điều hòa -> vẫn tìm đúng Q0358."""
    query = "Máy điều hòa Samsung lỗi CF"
    entities = extract_question_entities(query)
    assert entities["brand"] == "Samsung"
    assert entities["device"] == "Điều hòa"
    assert entities["error_code"] == "CF"

    results = search_hybrid(query, k=5)
    ids = [r["question_id"] for r in results]
    assert "Q0358" in ids, "Phai tim thay Q0358"
    assert results[0]["question_id"] == "Q0358"
    assert results[0]["device"] == "Điều hòa"


def test_case_e_samsung_loi_cf_la_gi():
    """Case E: 'Samsung lỗi CF là gì?' -> vẫn hoạt động như hiện tại, tìm đúng Q0358."""
    query = "Samsung lỗi CF là gì?"
    entities = extract_question_entities(query)
    assert entities["brand"] == "Samsung"
    assert entities["device"] is None
    assert entities["error_code"] == "CF"

    results = search_hybrid(query, k=5)
    ids = [r["question_id"] for r in results]
    assert "Q0358" in ids, "Phai tim thay Q0358"
    assert results[0]["question_id"] == "Q0358"

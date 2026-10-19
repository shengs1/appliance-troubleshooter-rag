"""Kiem thu chuc nang Post-Retrieval Reranking.

Cac test case bat buoc:
1. Exact error code: Samsung + Dieu hoa + CF -> document dung CF phai duoc uu tien.
2. Dung brand + device: Samsung + Dieu hoa -> khong duoc dua document tu lanh Samsung len truoc chi vi semantic similarity nho.
3. Symptom: Samsung + Dieu hoa + 'khong lanh' -> semantic similarity van giu vai tro chinh giua cac tai lieu cung brand va device.
4. Khong co error code: query khong co ma loi -> khong cong error_code bonus.
5. Sai brand: Samsung query khong duoc uu tien tai lieu LG chi vi cac tu giong nhau.
6. Sai device: Dieu hoa query khong duoc uu tien Tu lanh.
7. Khong co entity: query khong xac dinh brand/device/error code -> reranking giu nguyen thu tu semantic hien tai.
8. Empty results: danh sach ung vien rong -> tra ve rong an toan.
"""

import pytest
from rag_chatbot.retrieval import rerank_results


def test_1_exact_error_code_priority():
    """1. Exact error code: Samsung + Dieu hoa + CF -> document dung CF phai duoc uu tien cao nhat."""
    query = "Samsung điều hòa lỗi CF"
    entities = {"brand": "Samsung", "device": "Điều hòa", "error_code": "CF"}

    candidates = [
        {
            "question_id": "Q_GENERIC",
            "question": "Điều hòa Samsung nhấp nháy",
            "brand": "Samsung",
            "device": "Điều hòa",
            "error_code": "",
            "distance": 0.20,  # semantic_score = 0.80
            "retrieval_source": "chroma",
        },
        {
            "question_id": "Q_EXACT_CF",
            "question": "Máy điều hòa Samsung lỗi CF",
            "brand": "Samsung",
            "device": "Điều hòa",
            "error_code": "CF",
            "distance": 0.30,  # semantic_score = 0.70 + 0.20 (CF) = 0.90 + brand + device
            "retrieval_source": "chroma",
        },
        {
            "question_id": "Q_OTHER_CODE",
            "question": "Máy điều hòa Samsung lỗi E1",
            "brand": "Samsung",
            "device": "Điều hòa",
            "error_code": "E1",
            "distance": 0.25,  # semantic_score = 0.75
            "retrieval_source": "chroma",
        },
    ]

    reranked = rerank_results(query, candidates, entities=entities)
    assert reranked[0]["question_id"] == "Q_EXACT_CF"
    assert reranked[0]["error_code"] == "CF"


def test_2_correct_brand_and_device_priority():
    """2. Dung brand + device: Samsung + Dieu hoa -> khong duoc dua tu lanh Samsung len truoc."""
    query = "Điều hòa Samsung không lạnh"
    entities = {"brand": "Samsung", "device": "Điều hòa", "error_code": None}

    candidates = [
        {
            "question_id": "Q_FRIDGE",
            "question": "Tủ lạnh Samsung không lạnh",
            "brand": "Samsung",
            "device": "Tủ lạnh",
            "error_code": "",
            "distance": 0.15,  # semantic_score = 0.85 + 0.08 (brand) = 0.93
            "retrieval_source": "chroma",
        },
        {
            "question_id": "Q_AC",
            "question": "Điều hòa Samsung không lạnh",
            "brand": "Samsung",
            "device": "Điều hòa",
            "error_code": "",
            "distance": 0.20,  # semantic_score = 0.80 + 0.08 (brand) + 0.08 (device) = 0.96
            "retrieval_source": "chroma",
        },
    ]

    reranked = rerank_results(query, candidates, entities=entities)
    assert reranked[0]["question_id"] == "Q_AC"
    assert reranked[0]["device"] == "Điều hòa"


def test_3_symptom_semantic_similarity_rules():
    """3. Symptom: Samsung + Dieu hoa + 'khong lanh' -> giua cac tai lieu cung brand+device, semantic quyet dinh."""
    query = "Điều hòa Samsung không lạnh"
    entities = {"brand": "Samsung", "device": "Điều hòa", "error_code": None}

    candidates = [
        {
            "question_id": "Q_REMOTE",
            "question": "Điều hòa Samsung không nhận điều khiển",
            "brand": "Samsung",
            "device": "Điều hòa",
            "error_code": "",
            "distance": 0.40,  # semantic = 0.60 + 0.16 = 0.76
            "retrieval_source": "chroma",
        },
        {
            "question_id": "Q_COOLING",
            "question": "Điều hòa Samsung không đủ mát",
            "brand": "Samsung",
            "device": "Điều hòa",
            "error_code": "",
            "distance": 0.15,  # semantic = 0.85 + 0.16 = 1.01
            "retrieval_source": "chroma",
        },
    ]

    reranked = rerank_results(query, candidates, entities=entities)
    assert reranked[0]["question_id"] == "Q_COOLING"


def test_4_no_error_code_in_query_no_bonus():
    """4. Khong co error code: query khong co ma loi -> khong duoc cong error_code bonus."""
    query = "Máy giặt LG rung lắc mạnh"
    entities = {"brand": "LG", "device": "Máy giặt", "error_code": None}

    candidates = [
        {
            "question_id": "Q_UE",
            "question": "Máy giặt LG báo lỗi UE",
            "brand": "LG",
            "device": "Máy giặt",
            "error_code": "UE",
            "distance": 0.35,  # semantic = 0.65 + 0.16 (brand+device) = 0.81 (khong duoc cong UE)
            "retrieval_source": "chroma",
        },
        {
            "question_id": "Q_VIBRATE",
            "question": "Máy giặt LG bị rung lắc",
            "brand": "LG",
            "device": "Máy giặt",
            "error_code": "",
            "distance": 0.20,  # semantic = 0.80 + 0.16 (brand+device) = 0.96
            "retrieval_source": "chroma",
        },
    ]

    reranked = rerank_results(query, candidates, entities=entities)
    assert reranked[0]["question_id"] == "Q_VIBRATE"
    # Q_UE khong duoc vuot len vi query khong hoi ma UE
    assert reranked[1]["question_id"] == "Q_UE"


def test_5_wrong_brand_not_boosted():
    """5. Sai brand: Samsung query khong duoc uu tien tai lieu LG."""
    query = "Tủ lạnh Samsung không đông đá"
    entities = {"brand": "Samsung", "device": "Tủ lạnh", "error_code": None}

    candidates = [
        {
            "question_id": "Q_LG",
            "question": "Tủ lạnh LG không đông đá",
            "brand": "LG",
            "device": "Tủ lạnh",
            "error_code": "",
            "distance": 0.18,  # semantic = 0.82 + 0.08 (device) = 0.90
            "retrieval_source": "chroma",
        },
        {
            "question_id": "Q_SAMSUNG",
            "question": "Tủ lạnh Samsung không làm đá",
            "brand": "Samsung",
            "device": "Tủ lạnh",
            "error_code": "",
            "distance": 0.20,  # semantic = 0.80 + 0.08 (brand) + 0.08 (device) = 0.96
            "retrieval_source": "chroma",
        },
    ]

    reranked = rerank_results(query, candidates, entities=entities)
    assert reranked[0]["question_id"] == "Q_SAMSUNG"
    assert reranked[0]["brand"] == "Samsung"


def test_6_wrong_device_not_boosted():
    """6. Sai device: Dieu hoa query khong duoc uu tien Tu lanh."""
    query = "Điều hòa Panasonic kém lạnh"
    entities = {"brand": "Panasonic", "device": "Điều hòa", "error_code": None}

    candidates = [
        {
            "question_id": "Q_FRIDGE",
            "question": "Tủ lạnh Panasonic kém lạnh",
            "brand": "Panasonic",
            "device": "Tủ lạnh",
            "error_code": "",
            "distance": 0.18,  # semantic = 0.82 + 0.08 (brand) = 0.90
            "retrieval_source": "chroma",
        },
        {
            "question_id": "Q_AC",
            "question": "Điều hòa Panasonic làm lạnh kém",
            "brand": "Panasonic",
            "device": "Điều hòa",
            "error_code": "",
            "distance": 0.20,  # semantic = 0.80 + 0.08 (brand) + 0.08 (device) = 0.96
            "retrieval_source": "chroma",
        },
    ]

    reranked = rerank_results(query, candidates, entities=entities)
    assert reranked[0]["question_id"] == "Q_AC"
    assert reranked[0]["device"] == "Điều hòa"


def test_7_no_entity_preserves_semantic_order():
    """7. Khong co entity: query khong xac dinh brand/device/error code -> giu nguyen thu tu semantic."""
    query = "Thiết bị không chạy phải làm sao?"
    entities = {"brand": None, "device": None, "error_code": None}

    candidates = [
        {
            "question_id": "Q1",
            "question": "Tủ lạnh không chạy",
            "brand": "LG",
            "device": "Tủ lạnh",
            "error_code": "",
            "distance": 0.22,  # semantic = 0.78
            "retrieval_source": "chroma",
        },
        {
            "question_id": "Q2",
            "question": "Máy giặt không chạy",
            "brand": "Samsung",
            "device": "Máy giặt",
            "error_code": "",
            "distance": 0.15,  # semantic = 0.85
            "retrieval_source": "chroma",
        },
        {
            "question_id": "Q3",
            "question": "Điều hòa không chạy",
            "brand": "Panasonic",
            "device": "Điều hòa",
            "error_code": "",
            "distance": 0.30,  # semantic = 0.70
            "retrieval_source": "chroma",
        },
    ]

    reranked = rerank_results(query, candidates, entities=entities)
    # Q2 (0.15) > Q1 (0.22) > Q3 (0.30)
    assert reranked[0]["question_id"] == "Q2"
    assert reranked[1]["question_id"] == "Q1"
    assert reranked[2]["question_id"] == "Q3"


def test_8_empty_results_safe():
    """8. Empty results: tra ve danh sach rong an toan."""
    assert rerank_results("Samsung điều hòa", []) == []
    assert rerank_results("", []) == []
    assert rerank_results("Samsung điều hòa", [], mode="adaptive") == []


def test_9_adaptive_error_code_priority():
    """9. Adaptive mode: exact error code receives higher +0.25 bonus."""
    query = "Panasonic điều hòa lỗi F95"
    entities = {"brand": "Panasonic", "device": "Điều hòa", "error_code": "F95"}

    candidates = [
        {
            "question_id": "Q_OTHER_CODE",
            "question": "Điều hòa Panasonic lỗi F93",
            "brand": "Panasonic",
            "device": "Điều hòa",
            "error_code": "F93",
            "distance": 0.20,  # semantic = 0.80 + 0.16 = 0.96
            "retrieval_source": "chroma",
        },
        {
            "question_id": "Q_EXACT_F95",
            "question": "Điều hòa Panasonic lỗi F95",
            "brand": "Panasonic",
            "device": "Điều hòa",
            "error_code": "F95",
            "distance": 0.35,  # semantic = 0.65 + 0.16 + 0.25 = 1.06
            "retrieval_source": "chroma",
        },
    ]

    reranked = rerank_results(query, candidates, entities=entities, mode="adaptive")
    assert reranked[0]["question_id"] == "Q_EXACT_F95"
    assert reranked[0]["error_code"] == "F95"


def test_10_adaptive_symptom_semantic_dominance():
    """10. Adaptive mode: query symptom su dung bonus brand/device nhe (0.05) va both (0.01)."""
    query = "Tủ lạnh LG không làm đá"
    entities = {"brand": "LG", "device": "Tủ lạnh", "error_code": None}

    candidates = [
        {
            "question_id": "Q_WEAK_BOTH",
            "question": "Tủ lạnh LG kêu to",
            "brand": "LG",
            "device": "Tủ lạnh",
            "error_code": "",
            "distance": 0.35,  # semantic = 0.65 + 0.10 + 0.01 = 0.76
            "retrieval_source": "both",
        },
        {
            "question_id": "Q_STRONG_SEMANTIC",
            "question": "Tủ lạnh LG không rơi đá",
            "brand": "LG",
            "device": "Tủ lạnh",
            "error_code": "",
            "distance": 0.18,  # semantic = 0.82 + 0.10 = 0.92
            "retrieval_source": "chroma",
        },
    ]

    reranked = rerank_results(query, candidates, entities=entities, mode="adaptive")
    assert reranked[0]["question_id"] == "Q_STRONG_SEMANTIC"


def test_11_adaptive_preserves_metadata():
    """11. Adaptive mode khong lam mat bat ky truong metadata nao cua candidate."""
    query = "Điều hòa Samsung lỗi CF"
    entities = {"brand": "Samsung", "device": "Điều hòa", "error_code": "CF"}
    candidates = [
        {
            "question_id": "Q1",
            "question": "Câu hỏi test",
            "answer": "Câu trả lời test",
            "brand": "Samsung",
            "device": "Điều hòa",
            "error_code": "CF",
            "source_url": "https://example.com/cf",
            "retrieval_source": "both",
            "distance": 0.25,
        }
    ]

    reranked = rerank_results(query, candidates, entities=entities, mode="adaptive")
    assert len(reranked) == 1
    item = reranked[0]
    assert item["question_id"] == "Q1"
    assert item["question"] == "Câu hỏi test"
    assert item["answer"] == "Câu trả lời test"
    assert item["brand"] == "Samsung"
    assert item["device"] == "Điều hòa"
    assert item["error_code"] == "CF"
    assert item["source_url"] == "https://example.com/cf"
    assert item["retrieval_source"] == "both"
    assert "rerank_score" in item


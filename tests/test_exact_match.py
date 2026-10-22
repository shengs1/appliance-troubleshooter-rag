"""Unit tests cho chuc nang Exact Question Match va chuan hoa van ban tieng Viet.

Cac test case:
1. Chuan hoa Unicode NFC (composed vs decomposed).
2. Chuan hoa vi tri dau thanh tieng Viet (kieu moi vs kieu cu: oa/ao, uy/yu...).
3. Loai bo dau cau va gom khoang trang thua.
4. Kiem tra is_exact_question_match cho ket qua True (trung khop chinh xac sau chuan hoa).
5. Kiem tra is_exact_question_match cho ket qua False (khac nhau, trung mot phan, chuoi rong).
6. Kiem tra rerank_results cong diem exact_question_match_bonus (+0.02) dung cach.
7. Kiem tra rerank_results khong cong bonus khi cau hoi khong trung khop.
"""

import pytest
import unicodedata

from rag_chatbot.retrieval import (
    normalize_question_text,
    is_exact_question_match,
    rerank_results,
)


def test_normalize_question_text_unicode_nfc():
    """Kiem tra chuan hoa Unicode NFC giua to hop (NFD) va dung san (NFC)."""
    text_nfc = "Điều hòa Panasonic không lạnh"
    text_nfd = unicodedata.normalize("NFD", text_nfc)

    assert normalize_question_text(text_nfc) == normalize_question_text(text_nfd)


def test_normalize_question_text_tone_marks():
    """Kiem tra dong nhat vi tri dat dau thanh tieng Viet (oà vs òa, uỳ vs ùy)."""
    q_old_tone = "Điều hoà panasonic bị lỗi F16"
    q_new_tone = "Điều hòa panasonic bị lỗi F16"

    norm_old = normalize_question_text(q_old_tone)
    norm_new = normalize_question_text(q_new_tone)

    assert norm_old == norm_new
    assert "òa" in norm_new


def test_normalize_question_text_punctuation_and_whitespace():
    """Kiem tra loai bo dau cau (?, !, ., ,) va gom khoang trang thua."""
    raw = "   Máy   giặt,   không vắt được???   "
    expected = "máy giặt không vắt được"
    assert normalize_question_text(raw) == expected


def test_is_exact_question_match_true():
    """Kiem tra hai cau hoi trung khop chinh xac du khac viet hoa, dau cau hay vi tri dau thanh."""
    # Khac dau cau va viet hoa
    assert is_exact_question_match(
        "Máy giặt rung mạnh khi vắt xử lý thế nào?",
        "máy giặt rung mạnh khi vắt xử lý thế nào"
    ) is True

    # Khac kieu go dau tieng Viet (oà vs òa)
    assert is_exact_question_match(
        "Điều hoà panasonic bị lỗi F16",
        "Điều hòa panasonic bị lỗi F16"
    ) is True


def test_is_exact_question_match_false():
    """Kiem tra cac truong hop khong duoc coi la trung khop (khong fuzzy, khong trung mot phan)."""
    # Khac han noi dung
    assert is_exact_question_match(
        "Máy giặt kêu to",
        "Máy giặt không vắt"
    ) is False

    # Trung mot phan (substring) - khong duoc coi la exact match
    assert is_exact_question_match(
        "Máy giặt không vắt",
        "Máy giặt không vắt được thì nguyên nhân thường là gì?"
    ) is False

    # Chuoi rong hoac None
    assert is_exact_question_match("", "Máy giặt lỗi") is False
    assert is_exact_question_match("", "") is False


def test_rerank_results_applies_exact_question_bonus():
    """Kiem tra ung vien trung khop cau hoi duoc cong bonus (+0.02) va vuot len Top-1."""
    query = "Máy giặt không xả nước phải làm sao?"
    entities = {"brand": None, "device": "Máy giặt", "error_code": None}

    candidates = [
        {
            "question_id": "Q_SIMILAR",
            "question": "Máy giặt không xả nước thì sửa thế nào cho nhanh?",
            "brand": "",
            "device": "Máy giặt",
            "error_code": "",
            "distance": 0.20,  # semantic_score = 0.80 + 0.08 device = 0.88
            "retrieval_source": "chroma",
        },
        {
            "question_id": "Q_EXACT",
            "question": "Máy giặt không xả nước phải làm sao?",
            "brand": "",
            "device": "Máy giặt",
            "error_code": "",
            "distance": 0.21,  # semantic_score = 0.79 + 0.08 device + 0.02 exact = 0.89
            "retrieval_source": "chroma",
        },
    ]

    reranked = rerank_results(query, candidates, entities=entities, mode="fixed")

    # Q_EXACT phai vuot len Top-1 vi nhan bonus +0.02
    assert reranked[0]["question_id"] == "Q_EXACT"
    assert reranked[0]["rerank_score"] == 0.89
    assert reranked[1]["question_id"] == "Q_SIMILAR"
    assert reranked[1]["rerank_score"] == 0.88


def test_rerank_results_no_bonus_when_no_match():
    """Kiem tra neu khong co ung vien nao trung khop cau hoi thi khong duoc cong bonus."""
    query = "Máy giặt tự nhiên không chạy được"
    entities = {"brand": None, "device": "Máy giặt", "error_code": None}

    candidates = [
        {
            "question_id": "Q1",
            "question": "Máy giặt không vắt được",
            "brand": "",
            "device": "Máy giặt",
            "error_code": "",
            "distance": 0.20,  # semantic_score = 0.80 + 0.08 device = 0.88
            "retrieval_source": "chroma",
        },
        {
            "question_id": "Q2",
            "question": "Máy giặt không cấp nước",
            "brand": "",
            "device": "Máy giặt",
            "error_code": "",
            "distance": 0.25,  # semantic_score = 0.75 + 0.08 device = 0.83
            "retrieval_source": "chroma",
        },
    ]

    reranked = rerank_results(query, candidates, entities=entities, mode="fixed")
    assert reranked[0]["question_id"] == "Q1"
    assert reranked[0]["rerank_score"] == 0.88
    assert reranked[1]["question_id"] == "Q2"
    assert reranked[1]["rerank_score"] == 0.83

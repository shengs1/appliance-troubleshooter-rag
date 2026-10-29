"""Kiem thu chong phan hoi tieng Trung / CJK khong mong muon va quy trinh rewrite 1-lan.

Dam bao:
1. Phat hien chinh xac ky tu CJK / chu Han bat thuong.
2. Khong canh bao nham tren tieng Viet, ma loi ky thuat (F16, H97, CF, U04), URL hoac ten hang (Panasonic, Samsung).
3. Co che rewrite chi thu lai dung 1 lan duy nhat.
4. Neu van con CJK sau khi rewrite, tra ve fallback message an toan bang tieng Viet.
"""

from unittest.mock import patch
import pytest

from rag_chatbot.rag import (
    contains_unexpected_cjk,
    create_cjk_rewrite_prompt,
    generate_rag_answer,
)


def test_01_contains_unexpected_cjk_detection():
    """Kiem tra phat hien chu Han / CJK dung cho ca van ban thuan va van ban tron tieng Viet."""
    # Co chua ky tu chu Han
    assert contains_unexpected_cjk("Mã lỗi F16 là do cảm biến nhiệt độ 故障.") is True
    assert contains_unexpected_cjk("建议检查排水管.") is True
    assert contains_unexpected_cjk("Điều hòa bị hỏng quạt 检查.") is True

    # Khong chua chu Han (Tieng Viet thuan, ma loi, URL, ten hang)
    assert contains_unexpected_cjk("Mã lỗi F16 là lỗi cảm biến nhiệt độ dàn lạnh máy lạnh Panasonic.") is False
    assert contains_unexpected_cjk("Kiểm tra mã H97, U04, CF trên điều hòa Samsung và máy giặt LG.") is False
    assert contains_unexpected_cjk("Tham khảo tại https://www.panasonic.com/vn/support/doc1") is False
    assert contains_unexpected_cjk("") is False


def test_02_preserves_technical_codes_and_brand_names():
    """Dam bao khong nham lan ma loi, so, ten hang voi chu Han."""
    safe_texts = [
        "Mã lỗi F16: Kiểm tra cảm biến nhiệt độ ngoài trời Panasonic.",
        "Mã lỗi H97 máy giặt Panasonic: Hỏng mô tơ quạt lồng giặt.",
        "Lỗi U04 bếp từ: Nghẹt đường thoát khí làm mát.",
        "Mã CF máy điều hòa Samsung: Nhắc vệ sinh lưới lọc không khí.",
    ]
    for text in safe_texts:
        assert contains_unexpected_cjk(text) is False


def test_03_cjk_rewrite_prompt_creation():
    """Kiem tra prompt yeu cau viet lai giu nguyen ngu canh va cam chu Han."""
    prompt = create_cjk_rewrite_prompt(
        question="Điều hòa Panasonic lỗi F16 là gì?",
        context="F16 là lỗi cảm biến nhiệt độ ngoài trời.",
        initial_answer="F16 是室外机传感器故障。",
    )
    assert "HOÀN TOÀN bằng tiếng Việt" in prompt
    assert "KHÔNG chứa bất kỳ chữ Hán nào" in prompt
    assert "F16 是室外机传感器故障。" in prompt


def test_04_rag_answer_retries_once_when_cjk_detected():
    """Kiem tra RAG pipeline goi LLM lan 2 (retry 1 lan) khi phat hien CJK va thanh cong."""
    cjk_answer = "Mã lỗi F16 là 传感器故障 của điều hòa Panasonic."
    clean_answer = "Mã lỗi F16 là lỗi cảm biến nhiệt độ ngoài trời của điều hòa Panasonic."

    mock_docs = [{
        "brand": "Panasonic",
        "device": "điều hòa",
        "error_code": "F16",
        "question": "Điều hòa Panasonic lỗi F16",
        "answer": "F16 là lỗi cảm biến nhiệt độ ngoài trời.",
        "retrieval_source": "neo4j",
        "source_url": "https://panasonic.com/support",
    }]

    call_count = 0
    def mock_call_llm(prompt, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return cjk_answer
        return clean_answer

    with patch("rag_chatbot.rag.search_hybrid", return_value=mock_docs), \
         patch("rag_chatbot.rag.should_refuse", return_value=False), \
         patch("rag_chatbot.rag.call_local_llm", side_effect=mock_call_llm):

        res = generate_rag_answer("Điều hòa Panasonic lỗi F16")
        assert call_count == 2  # Goi lan dau + retry dung 1 lan
        assert "F16" in res["answer"]
        assert contains_unexpected_cjk(res["answer"]) is False
        assert "cảm biến nhiệt độ" in res["answer"]


def test_05_rag_answer_cjk_fallback_after_failed_retry():
    """Kiem tra neu sau 1 lan retry ma LLM van tra ve CJK thi he thong dung thong bao an toan tieng Viet."""
    stubborn_cjk = "仍然是故障。"
    mock_docs = [{
        "brand": "Panasonic",
        "device": "điều hòa",
        "error_code": "F16",
        "question": "Điều hòa Panasonic lỗi F16",
        "answer": "Lỗi cảm biến.",
        "retrieval_source": "neo4j",
    }]

    with patch("rag_chatbot.rag.search_hybrid", return_value=mock_docs), \
         patch("rag_chatbot.rag.should_refuse", return_value=False), \
         patch("rag_chatbot.rag.call_local_llm", return_value=stubborn_cjk):

        res = generate_rag_answer("Điều hòa Panasonic lỗi F16")
        # Answer cuoi cung phai khong con chua ky tu chu Han
        assert contains_unexpected_cjk(res["answer"]) is False
        assert "tiếng Việt" in res["answer"] or "tài liệu kỹ thuật" in res["answer"]


"""Unit tests for the Answer Validator module (Phase: Answer Validation).

Cac test cases bat buoc theo dac ta:
1. Correct grounded answer -> PASS
2. Hallucinated error code -> FAIL
3. Wrong brand -> FAIL
4. Wrong device -> FAIL
5. Wrong error code -> FAIL
6. Extra unsupported solution -> WARNING/FAIL
7. No hallucination, paraphrase -> PASS
8. Query without error code -> khong bat buoc error code -> PASS
9. Context insufficient -> WARNING/FAIL
10. Empty answer -> FAIL
11. Empty context -> FAIL
12. Source/document mismatch -> FAIL hoac WARNING
13. Samsung + Dieu hoa + CF -> giu dung brand/device/error code -> PASS
"""

from typing import Any
import pytest

from rag_chatbot.answer_validator import validate_answer


@pytest.fixture
def sample_cf_doc() -> list[dict[str, Any]]:
    return [
        {
            "question_id": "Q0358",
            "question": "Máy điều hòa Samsung lỗi CF là gì?",
            "answer": "Nguyên nhân sự cố: Mã CF là nhắc vệ sinh bộ lọc. Cách khắc phục: Hãy vệ sinh hoặc thay bộ lọc.",
            "brand": "Samsung",
            "device": "Điều hòa",
            "error_code": "CF",
            "source_url": "https://www.samsung.com/vn/support/doc1",
        }
    ]


def test_1_correct_grounded_answer(sample_cf_doc):
    """Test 1: Cau tra loi grounded, dung hang, thiet bi, ma loi va noi dung -> PASS."""
    question = "Máy điều hòa Samsung lỗi CF là gì?"
    answer = (
        "Mã lỗi CF trên máy điều hòa Samsung là tín hiệu nhắc nhở vệ sinh bộ lọc không khí. "
        "Bạn hãy tháo và vệ sinh hoặc thay thế bộ lọc."
    )
    res = validate_answer(question, answer, sample_cf_doc)

    assert res["status"] == "pass"
    assert res["grounded"] is True
    assert res["brand_consistent"] is True
    assert res["device_consistent"] is True
    assert res["error_code_consistent"] is True
    assert res["hallucination_detected"] is False
    assert res["source_consistent"] is True
    assert len(res["reasons"]) == 0


def test_2_hallucinated_error_code():
    """Test 2: Cau hoi symptom khong co ma loi, LLM tu bia ra ma loi la -> FAIL."""
    question = "Máy giặt LG không cấp nước phải làm sao?"
    docs = [
        {
            "question_id": "Q0100",
            "question": "Máy giặt LG không cấp nước",
            "answer": "Nguyên nhân: Vòi nước bị khóa hoặc lưới lọc cặn bị nghẹt. Khắc phục: Mở vòi và vệ sinh lưới lọc.",
            "brand": "LG",
            "device": "Máy giặt",
            "error_code": None,
        }
    ]
    # LLM tu sinh ma loi CL (khong co trong context)
    answer = "Máy giặt LG của bạn bị lỗi CL, hãy mở khóa trẻ em để máy hoạt động bình thường."
    res = validate_answer(question, answer, docs)

    assert res["status"] == "fail"
    assert res["hallucination_detected"] is True
    assert res["error_code_consistent"] is False
    assert any("CL" in r for r in res["reasons"])


def test_3_wrong_brand(sample_cf_doc):
    """Test 3: Cau hoi ve Samsung nhung LLM tra loi sang Panasonic -> FAIL."""
    question = "Máy điều hòa Samsung lỗi CF là gì?"
    answer = "Mã lỗi CF trên máy điều hòa Panasonic là cảnh báo vệ sinh lưới lọc bụi."
    res = validate_answer(question, answer, sample_cf_doc)

    assert res["status"] == "fail"
    assert res["brand_consistent"] is False
    assert res["hallucination_detected"] is True
    assert any("Panasonic" in r for r in res["reasons"])


def test_4_wrong_device(sample_cf_doc):
    """Test 4: Cau hoi ve Dieu hoa nhung LLM tra loi sang Tu lanh -> FAIL."""
    question = "Máy điều hòa Samsung lỗi CF là gì?"
    answer = "Mã lỗi CF trên tủ lạnh Samsung là nhắc vệ sinh bộ lọc."
    res = validate_answer(question, answer, sample_cf_doc)

    assert res["status"] == "fail"
    assert res["device_consistent"] is False
    assert res["hallucination_detected"] is True
    assert any("Tủ lạnh" in r for r in res["reasons"])


def test_5_wrong_error_code(sample_cf_doc):
    """Test 5: Cau hoi ma loi CF nhung LLM tra ve ma loi IE hoac F11 -> FAIL."""
    question = "Máy điều hòa Samsung lỗi CF là gì?"
    answer = "Mã lỗi IE trên máy điều hòa Samsung là lỗi cấp nước, cần kiểm tra van."
    res = validate_answer(question, answer, sample_cf_doc)

    assert res["status"] == "fail"
    assert res["error_code_consistent"] is False
    assert res["hallucination_detected"] is True
    assert any("IE" in r for r in res["reasons"])


def test_6_extra_unsupported_solution(sample_cf_doc):
    """Test 6: LLM them giai phap xam lan / linh kien la khong co trong context -> FAIL/WARNING."""
    question = "Máy điều hòa Samsung lỗi CF là gì?"
    answer = (
        "Mã lỗi CF là nhắc vệ sinh bộ lọc. Ngoài ra bạn cần thay bo mạch điều khiển mới "
        "và nạp gas cho máy."
    )
    res = validate_answer(question, answer, sample_cf_doc)

    assert res["status"] in ["fail", "warning"]
    assert res["grounded"] is False
    assert res["hallucination_detected"] is True


def test_7_no_hallucination_paraphrase(sample_cf_doc):
    """Test 7: Cau tra loi paraphrase tu nhien, khong co linh kien la -> PASS."""
    question = "Máy điều hòa Samsung lỗi CF là gì?"
    answer = (
        "Khi máy lạnh Samsung hiện mã CF, điều này thông báo bộ lọc gió đã bẩn "
        "và cần được làm sạch để máy làm mát tốt hơn."
    )
    res = validate_answer(question, answer, sample_cf_doc)

    assert res["status"] == "pass"
    assert res["grounded"] is True
    assert res["hallucination_detected"] is False


def test_8_query_without_error_code():
    """Test 8: Query symptom khong co ma loi -> khong bat buoc answer phai co ma loi."""
    question = "Máy giặt Samsung bị rung lắc mạnh khi vắt"
    docs = [
        {
            "question_id": "Q0500",
            "question": "Máy giặt Samsung rung lắc khi vắt",
            "answer": "Nguyên nhân: Chân máy kê không cân bằng hoặc quần áo dồn một phía. Khắc phục: Kê lại chân máy và dàn đều quần áo.",
            "brand": "Samsung",
            "device": "Máy giặt",
            "error_code": None,
        }
    ]
    answer = (
        "Máy giặt Samsung bị rung lắc khi vắt có thể do vị trí đặt máy không cân bằng "
        "hoặc lượng đồ giặt bị lệch về một bên. Bạn hãy kiểm tra kê lại chân máy và dàn đều quần áo."
    )
    res = validate_answer(question, answer, docs)

    assert res["status"] == "pass"
    assert res["error_code_consistent"] is True
    assert res["grounded"] is True


def test_9_context_insufficient():
    """Test 9: Tai lieu khong co noi dung huong dan xu ly -> FAIL/WARNING."""
    question = "Máy giặt Samsung lỗi XYZ123"
    docs = [
        {
            "question_id": "Q9999",
            "question": "",
            "answer": "",
            "brand": "Samsung",
            "device": "Máy giặt",
            "error_code": None,
        }
    ]
    answer = "Không có thông tin cụ thể."
    res = validate_answer(question, answer, docs)

    assert res["status"] in ["fail", "warning"]


def test_10_empty_answer(sample_cf_doc):
    """Test 10: Cau tra loi rong -> FAIL."""
    question = "Máy điều hòa Samsung lỗi CF là gì?"
    res = validate_answer(question, "", sample_cf_doc)

    assert res["status"] == "fail"
    assert res["grounded"] is False
    assert any("rỗng" in r.lower() for r in res["reasons"])


def test_11_empty_context():
    """Test 11: Danh sach tai lieu retrieved rong -> FAIL."""
    question = "Máy điều hòa Samsung lỗi CF là gì?"
    res = validate_answer(question, "Mã CF là nhắc vệ sinh bộ lọc.", [])

    assert res["status"] == "fail"
    assert res["grounded"] is False
    assert res["source_consistent"] is False


def test_12_source_document_mismatch():
    """Test 12: Tai lieu retrieved bi mismatch hang/thiet bi -> FAIL hoac WARNING."""
    question = "Máy điều hòa Samsung lỗi CF là gì?"
    mismatched_docs = [
        {
            "question_id": "Q0200",
            "question": "Tủ lạnh Panasonic kêu to",
            "answer": "Nguyên nhân: Lắp đặt kênh chân. Khắc phục: Kê lại tủ.",
            "brand": "Panasonic",
            "device": "Tủ lạnh",
            "error_code": None,
        }
    ]
    answer = "Mã lỗi CF là nhắc vệ sinh bộ lọc."
    res = validate_answer(question, answer, mismatched_docs)

    assert res["source_consistent"] is False
    assert res["status"] in ["fail", "warning"]


def test_13_samsung_dieuhoa_cf_retention(sample_cf_doc):
    """Test 13: Samsung + Dieu hoa + CF phai giu dung ca 3 thuc the -> PASS."""
    question = "Máy điều hòa Samsung lỗi CF là gì?"
    answer = (
        "Mã lỗi CF trên máy điều hòa Samsung xuất hiện nhằm nhắc nhở bạn "
        "cần vệ sinh tấm lưới lọc bụi. Sau khi vệ sinh sạch sẽ, bạn lắp lại bộ lọc vào máy."
    )
    res = validate_answer(question, answer, sample_cf_doc)

    assert res["status"] == "pass"
    assert res["brand_consistent"] is True
    assert res["device_consistent"] is True
    assert res["error_code_consistent"] is True
    assert res["source_consistent"] is True
    assert res["grounded"] is True
    assert res["hallucination_detected"] is False

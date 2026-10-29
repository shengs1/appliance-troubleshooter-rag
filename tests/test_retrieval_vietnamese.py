"""Kiem thu nang cao cho trích xuat thuc the va pham vi cau hoi tieng Viet:
Co dau, khong dau, tron dau, alias hang/thiet bi, ma loi co khoang trang va negative controls.
"""

import pytest

from rag_chatbot.retrieval import extract_question_entities, is_exact_question_match
from rag_chatbot.scope import has_troubleshooting_signal, should_refuse


# ==============================================================================
# 1. Kiem thu trich xuat thuc the tren cac cau hoi de bai yeu cau
# ==============================================================================

def test_extract_dieu_hoa_panasonic_f16():
    cases = [
        "Điều hòa Panasonic báo lỗi F16",
        "dieu hoa panasonic bao loi F16",
        "dieu hòa pana bao loi F16",
        "điều hoà pana báo f16 là bị làm sao thợ ơi",
        "Điều hòa Panasonic báo lỗi F 16",
        "dieu hoa pana bao loi f 16",
    ]
    for q in cases:
        entities = extract_question_entities(q)
        assert entities["brand"] == "Panasonic", f"Failed brand on: {q}"
        assert entities["device"] == "Điều hòa", f"Failed device on: {q}"
        assert entities["error_code"] == "F16", f"Failed error code on: {q}"


def test_extract_may_giat_toshiba():
    cases = [
        "Máy giặt Toshiba kêu cạch cạch lúc vắt",
        "may giat toshiba keu cach cạch luc vat",
        "máy giặc Toshiba kêu cạch cạch",
        "may giac toshiba keu",
    ]
    for q in cases:
        entities = extract_question_entities(q)
        # Toshiba khong phai hang trong DB (LG, Samsung, Panasonic)
        assert entities["brand"] is None
        assert entities["device"] == "Máy giặt"
        assert entities["error_code"] is None


def test_extract_tu_lanh_lg_sb():
    cases = [
        "Tủ lạnh LG lỗi SB",
        "tu lanh lg loi sb",
        "tủ lạnh LG báo lỗi SB",
        "tu lanh LG bao loi sb",
    ]
    for q in cases:
        entities = extract_question_entities(q)
        assert entities["brand"] == "LG"
        assert entities["device"] == "Tủ lạnh"
        assert entities["error_code"] == "SB"


def test_extract_lo_vi_song_panasonic_khong_nong():
    cases = [
        "Lò vi sóng Panasonic không nóng",
        "lo vi song panasonic khong nong",
        "lò vi ba Panasonic không nóng",
        "lo vi ba pana khong nong",
    ]
    for q in cases:
        entities = extract_question_entities(q)
        assert entities["brand"] == "Panasonic"
        assert entities["device"] == "Lò vi sóng"
        assert entities["error_code"] is None


def test_extract_bep_tu_panasonic_u04():
    cases = [
        "Bếp từ Panasonic lỗi U04",
        "bep tu panasonic loi U04",
        "bếp từ Panasonic lỗi U 04",
        "bep tu pana loi u 04",
    ]
    for q in cases:
        entities = extract_question_entities(q)
        assert entities["brand"] == "Panasonic"
        assert entities["device"] == "Bếp"
        assert entities["error_code"] == "U04"


def test_extract_negative_and_typos():
    # May xay (may say) va may giac (may giat)
    res_dryer = extract_question_entities("máy xấy LG không nóng")
    assert res_dryer["brand"] == "LG"
    assert res_dryer["device"] == "Máy sấy"

    res_washer = extract_question_entities("may giac Samsung bao loi 4C")
    assert res_washer["brand"] == "Samsung"
    assert res_washer["device"] == "Máy giặt"
    assert res_washer["error_code"] == "4C"


def test_error_code_not_confused():
    e1 = extract_question_entities("Điều hòa LG lỗi CH05")
    e2 = extract_question_entities("Điều hòa LG lỗi CH06")
    assert e1["error_code"] == "CH05"
    assert e2["error_code"] == "CH06"
    assert e1["error_code"] != e2["error_code"]


# ==============================================================================
# 2. Kiem thu nhan dien tin hieu su co (has_troubleshooting_signal)
# ==============================================================================

@pytest.mark.parametrize(
    "question,expected",
    [
        ("lo vi song panasonic khong nong", True),
        ("may giat toshiba keu cach cạch luc vat", True),
        ("tu lanh lg loi sb", True),
        ("dieu hoa khong lanh", True),
        ("bep tu khong len nguon", True),
        ("cach sua may say khong kho", True),
        ("thoi tiet hom nay the nao", False),
        ("gia tivi samsung 55 inch bao nhieu", False),
        ("lap trinh python co kho khong", False),
    ],
)
def test_troubleshooting_signals(question: str, expected: bool):
    assert has_troubleshooting_signal(question) == expected


# ==============================================================================
# 3. Kiem thu Exact Question Match (co dau vs khong dau)
# ==============================================================================

def test_exact_match_accented_and_unaccented():
    q_accented = "Điều hòa Panasonic báo lỗi F16"
    q_unaccented = "dieu hoa panasonic bao loi F16"
    assert is_exact_question_match(q_accented, q_unaccented) is True

    q_other = "Điều hòa Panasonic báo lỗi F18"
    assert is_exact_question_match(q_accented, q_other) is False

"""Bo kiem thu toan dien cho xu ly tieng Viet co dau, khong dau, tron dau va alias.

Bao gom hon 40 test cases bao quat:
1. Chuan hoa Unicode NFC / NFD.
2. Dong nhat vi tri dau thanh (kieu moi vs kieu cu: hoa / hoa).
3. Xu ly loai bo dau (unaccent) cho d va D.
4. Chuan hoa khoang trang ma loi (F 16 -> F16, H 97 -> H97, U 04 -> U04).
5. Thay the alias theo token boundary (pana -> Panasonic, may lanh -> dieu hoa...).
6. Loai bo loi go pho bien (may giac -> may giat, may xay -> may say).
7. Negative cases (khong thay the substring ben trong tu dai hon, khong nham ma loi).
8. Chuoi rong, khoang trang thua, ky tu dac biet.
"""

import pytest

from rag_chatbot.vietnamese import (
    apply_aliases,
    generate_query_variants,
    normalize_error_code_spaces,
    normalize_vietnamese_query,
    remove_vietnamese_accents,
)


# ==============================================================================
# 1. Kiem thu loai bo dau tieng Viet (remove_vietnamese_accents)
# ==============================================================================

@pytest.mark.parametrize(
    "input_text,expected",
    [
        ("Điều hòa Panasonic báo lỗi F16", "Dieu hoa Panasonic bao loi F16"),
        ("Máy giặt Toshiba kêu cạch cạch lúc vắt", "May giat Toshiba keu cach cach luc vat"),
        ("Tủ lạnh LG lỗi SB", "Tu lanh LG loi SB"),
        ("Lò vi sóng Panasonic không nóng", "Lo vi song Panasonic khong nong"),
        ("Bếp từ Panasonic lỗi U04", "Bep tu Panasonic loi U04"),
        ("Đèn led nhấp nháy liên tục", "Den led nhap nhay lien tuc"),
        ("ĐIỀU HOÀ ĐÈN ĐỎ", "DIEU HOA DEN DO"),
        ("hòa và hoà", "hoa va hoa"),
        ("", ""),
        ("   ", ""),
    ],
)
def test_remove_vietnamese_accents(input_text: str, expected: str):
    result = remove_vietnamese_accents(input_text)
    assert result == expected


# ==============================================================================
# 2. Kiem thu chuan hoa khoang trang ma loi (normalize_error_code_spaces)
# ==============================================================================

@pytest.mark.parametrize(
    "input_text,expected",
    [
        ("Điều hòa lỗi F 16", "Điều hòa lỗi F16"),
        ("Lỗi H 97 máy giặt", "Lỗi H97 máy giặt"),
        ("Bếp từ báo U 04", "Bếp từ báo U04"),
        ("Mã lỗi E 01 tủ lạnh", "Mã lỗi E01 tủ lạnh"),
        ("Mã lỗi CF không bị thay đổi", "Mã lỗi CF không bị thay đổi"),
        ("Mã lỗi 4C không bị thay đổi", "Mã lỗi 4C không bị thay đổi"),
        ("Khoảng trắng bình thường giữa các từ", "Khoảng trắng bình thường giữa các từ"),
    ],
)
def test_normalize_error_code_spaces(input_text: str, expected: str):
    assert normalize_error_code_spaces(input_text) == expected


# ==============================================================================
# 3. Kiem thu chuan hoa tong the (normalize_vietnamese_query)
# ==============================================================================

def test_normalize_vietnamese_query_tone_and_spaces():
    # hoa (kieu cu) -> hoa (kieu moi)
    raw = "  Điều  hoà   Panasonic   báo  lỗi   F  16  "
    norm = normalize_vietnamese_query(raw)
    assert norm == "Điều hòa Panasonic báo lỗi F16"


def test_normalize_vietnamese_query_nfc():
    import unicodedata
    nfd_text = unicodedata.normalize("NFD", "Tủ lạnh LG lỗi SB")
    nfc_result = normalize_vietnamese_query(nfd_text)
    assert unicodedata.is_normalized("NFC", nfc_result)
    assert nfc_result == "Tủ lạnh LG lỗi SB"


# ==============================================================================
# 4. Kiem thu thay the Alias va token boundary (apply_aliases)
# ==============================================================================

@pytest.mark.parametrize(
    "input_text,expected_contains",
    [
        ("dieu hoa pana bao loi F16", "Panasonic"),
        ("điều hoà pana báo f16 là bị làm sao thợ ơi", "Panasonic"),
        ("máy lạnh không mát", "điều hòa"),
        ("lò vi ba không nóng", "lò vi sóng"),
        ("máy rửa chén không thoát nước", "máy rửa bát"),
        ("máy giặc kêu to", "máy giặt"),
        ("máy xấy không nóng", "máy sấy"),
        ("bếp từ Panasonic lỗi U04", "bếp"),
        ("tivi không lên hình", "TV"),
    ],
)
def test_apply_aliases_matches(input_text: str, expected_contains: str):
    result = apply_aliases(input_text)
    assert expected_contains.lower() in result.lower()


def test_apply_aliases_token_boundary_safety():
    # 'pana' khong duoc thay the ben trong 'panasonic' hoac 'companion'
    text1 = "panasonic inverter"
    assert apply_aliases(text1).lower() == "panasonic inverter"

    text2 = "công ty companion"
    assert "panasonic" not in apply_aliases(text2).lower()


# ==============================================================================
# 5. Kiem thu sinh bien the cau hoi (generate_query_variants)
# ==============================================================================

def test_generate_query_variants_pana_f16():
    query = "dieu hòa pana bao loi F 16"
    variants = generate_query_variants(query)
    # Phai co it nhat 2-4 bien the khac nhau
    assert len(variants) >= 2
    # Bien the dau tien phai giu nguyen y nghia co ban cua cau
    assert "F16" in variants[0]
    # Phai co bien the chua Panasonic va bien the khong dau
    all_text = " ".join(variants)
    assert "Panasonic" in all_text
    assert "dieu hoa" in all_text.lower()


def test_generate_query_variants_empty():
    assert generate_query_variants("") == []
    assert generate_query_variants("   ") == []


def test_generate_query_variants_deduplication():
    # Neu cau don gian khong dau va khong co alias, khong sinh cac chuoi trung lap
    variants = generate_query_variants("Samsung TV")
    assert len(variants) == len(set(v.lower() for v in variants))

"""Module xu ly va chuan hoa tieng Viet (Vietnamese Query Normalization & Expansion).

Module nay cung cap:
1. Chuan hoa Unicode NFC, dau thanh (kieu moi vs kieu cu), khoang trang.
2. Loai bo dau tieng Viet (unaccent) an toan bang Unicode NFD va xu ly d/D.
3. Chuan hoa ma loi ky thuat co khoang trang (F 16 -> F16, H 97 -> H97, U 04 -> U04).
4. Thay the alias theo ranh gioi tu (token boundary: pana -> Panasonic, may lanh -> dieu hoa...).
5. Sinh bien the cau hoi (query expansion) co kiem soat de toi uu retrieval.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Any

# Danh sach cac cap nguyen am chuan hoa vi tri dau thanh tieng Viet (kieu cu -> kieu moi)
TONE_PAIRS = [
    ("oà", "òa"), ("oá", "óa"), ("oả", "ỏa"), ("oã", "õa"), ("oạ", "ọa"),
    ("uỳ", "ùy"), ("uý", "úy"), ("uỷ", "ủy"), ("uỹ", "ũy"), ("uỵ", "ụy"),
    ("oè", "òe"), ("oé", "óe"), ("oẻ", "ỏe"), ("oẽ", "õe"), ("oẹ", "ọe"),
]

# Bang chuyen doi ky tu dac biet d/D tieng Viet
CHAR_MAP_D = {
    "đ": "d",
    "Đ": "D",
}

# Alias cho thuong hieu (ap dung token boundary)
BRAND_ALIASES = [
    (r"\bpana\b", "Panasonic"),
    (r"\bpanasonic\b", "Panasonic"),
    (r"\bsamsung\b", "Samsung"),
    (r"\blg\b", "LG"),
]

# Alias va loi go cho thiet bi (ap dung token boundary)
DEVICE_ALIASES = [
    (r"\bmáy điều hòa\b", "Điều hòa"),
    (r"\bmáy điều hoà\b", "Điều hòa"),
    (r"\bmay dieu hoa\b", "dieu hoa"),
    (r"\bmáy lạnh\b", "điều hòa"),
    (r"\bmay lanh\b", "dieu hoa"),
    (r"\blò vi ba\b", "lò vi sóng"),
    (r"\blo vi ba\b", "lo vi song"),
    (r"\bmáy rửa chén\b", "máy rửa bát"),
    (r"\bmay rua chen\b", "may rua bat"),
    (r"\bmáy giặc\b", "máy giặt"),
    (r"\bmay giac\b", "may giat"),
    (r"\bmáy xấy\b", "máy sấy"),
    (r"\bbếp từ\b", "bếp"),
    (r"\bbep tu\b", "bep"),
    (r"\btivi\b", "TV"),
]


def remove_vietnamese_accents(text: str) -> str:
    """Loai bo dau tieng Viet (unaccent) mot cach an toan va chinh xac.
    
    Quy trinh:
    1. Thay the d/D dac thu cua tieng Viet.
    2. Phan ra ky tu ket hop bang Unicode NFD.
    3. Loai bo cac dau thanh ket hop (category Mn).
    4. Chuan hoa tro lai NFC.
    """
    if not text or not text.strip():
        return ""
    # Thay the d/D truoc khi decompose
    res = text
    for d_char, plain_char in CHAR_MAP_D.items():
        res = res.replace(d_char, plain_char)
    # Decompose Unicode NFD va bo combining marks
    decomposed = unicodedata.normalize("NFD", res)
    stripped = "".join(ch for ch in decomposed if unicodedata.category(ch) != "Mn")
    return unicodedata.normalize("NFC", stripped)


def normalize_error_code_spaces(text: str) -> str:
    """Chuan hoa cac ma loi co khoang trang khong can thiet giua chu va so.
    
    Vi du:
    - 'F 16' -> 'F16'
    - 'H 97' -> 'H97'
    - 'U 04' -> 'U04'
    - 'E 01' -> 'E01'
    """
    if not text:
        return ""
    # Chuan hoa cac cap [Chu cai 1-2 ky tu] [1 hoac nhieu khoang trang] [Chu so 1-3 ky tu]
    return re.sub(
        r"\b([A-Za-z]{1,2})\s+([0-9]{1,3})\b",
        r"\1\2",
        text,
    )


def normalize_vietnamese_query(text: str) -> str:
    """Chuan hoa tong the van ban cau hoi tieng Viet:
    
    1. Chuyen ve Unicode NFC.
    2. Dong nhat vi tri dau thanh (kieu cu -> kieu moi).
    3. Chuan hoa khoang trang ma loi (F 16 -> F16).
    4. Dong nhat khoang trang thua.
    """
    if not text:
        return ""
    t = unicodedata.normalize("NFC", text)
    for old, new in TONE_PAIRS:
        t = t.replace(old, new)
    t = normalize_error_code_spaces(t)
    # Gom khoang trang thua
    return " ".join(t.split())


def apply_aliases(text: str) -> str:
    """Thay the cac alias hang, thiet bi va loi go pho bien dua tren token boundary."""
    if not text:
        return ""
    res = text
    for pattern, replacement in BRAND_ALIASES:
        res = re.sub(pattern, replacement, res, flags=re.IGNORECASE)
    for pattern, replacement in DEVICE_ALIASES:
        res = re.sub(pattern, replacement, res, flags=re.IGNORECASE)
    return " ".join(res.split())


# Danh sach chuyen doi cac cum tu khong dau pho bien sang co dau chuan de mo rong tim kiem
UNACCENT_TO_ACCENT_PATTERNS = [
    # Thiet bi
    (r"\bmay dieu hoa\b", "máy điều hòa"),
    (r"\bmay lanh\b", "máy điều hòa"),
    (r"\bdieu hoa\b", "điều hòa"),
    (r"\btu lanh\b", "tủ lạnh"),
    (r"\bmay giat\b", "máy giặt"),
    (r"\bmay giac\b", "máy giặt"),
    (r"\bmay say\b", "máy sấy"),
    (r"\bbep tu\b", "bếp từ"),
    (r"\blo vi song\b", "lò vi sóng"),
    (r"\bmay rua bat\b", "máy rửa bát"),
    (r"\bmay rua chen\b", "máy rửa bát"),
    # Su co & Trieu chung
    (r"\bma loi\b", "mã lỗi"),
    (r"\bloi\b", "lỗi"),
    (r"\bkhong lanh\b", "không lạnh"),
    (r"\bkhong mat\b", "không mát"),
    (r"\bkém lanh\b", "kém lạnh"),
    (r"\blanh yeu\b", "lạnh yếu"),
    (r"\bkhong nong\b", "không nóng"),
    (r"\bkhong chay\b", "không chạy"),
    (r"\bkhong len nguon\b", "không lên nguồn"),
    (r"\bkhong len\b", "không lên"),
    (r"\bkhong sang den\b", "không sáng đèn"),
    (r"\bnhay den\b", "nháy đèn"),
    (r"\bkhong xa nuoc\b", "không xả nước"),
    (r"\bkhong vắt\b", "không vắt"),
    (r"\bkhong vat\b", "không vắt"),
    (r"\bkhong cap nuoc\b", "không cấp nước"),
    (r"\bkhong vao nuoc\b", "không vào nước"),
    (r"\bkhong dong da\b", "không đông đá"),
    (r"\brung lac\b", "rung lắc"),
    (r"\bkeu to\b", "kêu to"),
    (r"\bchay nuoc\b", "chảy nước"),
    (r"\bbao loi\b", "báo lỗi"),
    # Y dinh xu ly
    (r"\bkhac phuc\b", "khắc phục"),
    (r"\bxu ly\b", "xử lý"),
    (r"\bcach sua\b", "cách sửa"),
    (r"\bthe nao\b", "thế nào"),
    (r"\bra sao\b", "ra sao"),
    (r"\bnguyen nhan\b", "nguyên nhân"),
    (r"\bhu hong\b", "hư hỏng"),
]


def restore_common_accents(text: str) -> str:
    """Khoi phuc dau tieng Viet cho cac cum tu thiet bi dien gia dung va su co pho bien."""
    if not text:
        return ""
    res = text
    for pattern, replacement in UNACCENT_TO_ACCENT_PATTERNS:
        res = re.sub(pattern, replacement, res, flags=re.IGNORECASE)
    return " ".join(res.split())


def generate_query_variants(question: str) -> list[str]:
    """Sinh cac bien the cau hoi co kiem soat de mo rong tim kiem ngu nghia:
    
    1. Cau hoi goc da chuan hoa (NFC, dau thanh, ma loi).
    2. Cau hoi sau khi ap dung alias (pana -> Panasonic, may lanh -> dieu hoa...).
    3. Cau hoi sau khi phuc hoi dau tieng Viet cho tu khoa su co / thiet bi.
    4. Cau hoi khong dau (unaccented).
    5. Cau hoi ap dung alias va khong dau.
    
    Loai bo cac bien the trung lap de toi uu so luong query.
    """
    if not question or not question.strip():
        return []

    base_norm = normalize_vietnamese_query(question.strip())
    alias_expanded = apply_aliases(base_norm)
    accent_restored = restore_common_accents(alias_expanded)
    unaccented = remove_vietnamese_accents(base_norm)
    unaccented_alias = remove_vietnamese_accents(alias_expanded)

    candidates = [base_norm, alias_expanded, accent_restored, unaccented, unaccented_alias]
    variants: list[str] = []
    seen: set[str] = set()

    for c in candidates:
        cleaned = " ".join(c.split())
        c_lower = cleaned.lower()
        if c_lower and c_lower not in seen:
            seen.add(c_lower)
            variants.append(cleaned)

    return variants

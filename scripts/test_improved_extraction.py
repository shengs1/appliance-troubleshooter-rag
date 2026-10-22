import json
import re
import sys
import unicodedata
from pathlib import Path
import pandas as pd

sys.stdout.reconfigure(encoding='utf-8')

# 1. Load known error codes from dataset
def get_known_error_codes() -> set[str]:
    df = pd.read_excel('data/raw/dataset.xlsx', sheet_name='DATA_CLEAN_TECH')
    codes = set()
    for c in df['Mã_lỗi'].dropna():
        for sub in str(c).split(','):
            cleaned = sub.strip().upper()
            if cleaned and cleaned != 'NAN':
                codes.add(cleaned)
    return codes

KNOWN_ERROR_CODES = get_known_error_codes()

# Common words to definitely avoid matching as error code after báo/hiện/chữ
COMMON_FALSE_POSITIVES = {
    "CÁO", "TẠI", "LÊN", "RA", "ĐƯỢC", "NHIỀU", "RÕ", "LỚN", "NHỎ", "THƯỜNG",
    "NHẠT", "TO", "ĐỎ", "VÀNG", "XANH", "CHỚP", "SÁNG", "TẮT", "MỜ", "ĐẦY",
    "HẾT", "NGAY", "LUÔN", "LIỀN", "TRƯỚC", "SAU", "GÌ", "NÀO", "SAO", "MẤY",
    "CHẬM", "NHANH", "NÓNG", "LẠNH", "MÙI", "KÊU", "RUNG", "RỈ", "CHẢY", "ĐÁ",
    "NƯỚC", "ĐIỆN", "NGUỒN", "CỬA", "VAN", "BƠM", "QUẠT", "BO", "MẠCH", "LẮP"
}

# Unit words following numbers
NUMERIC_UNITS = {"LẦN", "TIẾNG", "PHÚT", "GIÂY", "NGÀY", "ĐỘ", "%", "C", "H", "S"}

def extract_question_entities_improved(text: str) -> dict[str, str | None]:
    """Cải tiến nhận diện thực thể: Hãng (kèm alias), Thiết bị (kèm từ đồng nghĩa), Mã lỗi tự nhiên."""
    if not text:
        return {"brand": None, "device": None, "error_code": None}

    text_lower = text.lower()
    text_norm = unicodedata.normalize('NFC', text_lower)

    # 1. Hãng (Brand) - Hỗ trợ alias 'pana' có ranh giới từ
    brand: str | None = None
    if re.search(r'\b(panasonic|pana)\b', text_norm):
        brand = "Panasonic"
    elif re.search(r'\bsamsung\b', text_norm):
        brand = "Samsung"
    elif re.search(r'\blg\b', text_norm):
        brand = "LG"

    # 2. Thiết bị (Device) - Bổ sung các từ đồng nghĩa, lỗi gõ, biến thể địa phương
    device: str | None = None
    device_keywords = [
        # Điều hòa / Máy lạnh / Máy làm lạnh
        (r'\b(máy\s+điều\s+h[oò][aà]|máy\s+lạnh|điều\s+h[oò][aà]|máy\s+làm\s+lạnh)\b', "Điều hòa"),
        # Máy lọc không khí
        (r'\b(máy\s+lọc\s+không\s+khí)\b', "Máy lọc không khí"),
        # Máy rửa bát / Máy rửa chén
        (r'\b(máy\s+rửa\s+bát|máy\s+rửa\s+chén(\s+bát)?)\b', "Máy rửa bát"),
        # Lò vi sóng / Lò vi ba
        (r'\b(lò\s+vi\s+sóng|lò\s+vi\s+ba)\b', "Lò vi sóng"),
        # Lò nướng
        (r'\b(lò\s+nướng)\b', "Lò nướng"),
        # Máy giặt / Máy giặc
        (r'\b(máy\s+giặt|máy\s+giặc)\b', "Máy giặt"),
        # Máy sấy / Máy xấy
        (r'\b(máy\s+sấy|máy\s+xấy)\b', "Máy sấy"),
        # Tủ lạnh
        (r'\b(tủ\s+lạnh)\b', "Tủ lạnh"),
        # Bếp điện từ / Bếp từ / Bếp
        (r'\b(bếp\s+(điện\s+)?từ|bếp)\b', "Bếp"),
        # Tivi / TV
        (r'\b(tivi|tv)\b', "TV"),
    ]
    for pattern, target_dev in device_keywords:
        if re.search(pattern, text_norm):
            device = target_dev
            break

    # 3. Mã lỗi (Error Code)
    error_code: str | None = None

    # Quy tắc 1: Cấu trúc trực tiếp kinh điển (sau "mã lỗi", "mã", "lỗi")
    # Cho phép khoảng trắng giữa chữ và số như 'H 97' -> 'H97', 'U 11' -> 'U11', 'E1 01'
    match_classic = re.search(r'(?:mã\s+lỗi|mã|lỗi)\s+([A-Za-z0-9]+(?:\s+[A-Za-z0-9]+)?)', text, re.IGNORECASE)
    if match_classic:
        raw_code = match_classic.group(1).strip().upper()
        # Chuẩn hóa nếu có khoảng trắng giữa 1 chữ cái và số (ví dụ 'H 97' -> 'H97', 'U 11' -> 'U11')
        compact_code = re.sub(r'^([A-Z])\s+(\d+)$', r'\1\2', raw_code)
        
        # Kiểm tra token có hợp lệ không
        first_token = compact_code.split()[0]
        if first_token not in COMMON_FALSE_POSITIVES:
            # Nếu là mã 2 cụm như 'E1 01'
            if compact_code in KNOWN_ERROR_CODES:
                error_code = compact_code
            elif first_token in KNOWN_ERROR_CODES:
                error_code = first_token
            else:
                error_code = compact_code

    # Quy tắc 2: Cấu trúc tự nhiên (sau "báo", "hiện", "chữ", "nhấp nháy")
    if not error_code:
        match_natural = re.search(
            r'(?:báo|hiện|nhấp\s+nháy|chớp|sáng)\s+(?:mã\s+lỗi|mã|lỗi|chữ|đèn)?\s*([A-Za-z0-9]+(?:\s+[A-Za-z0-9]+)?)',
            text,
            re.IGNORECASE
        )
        if match_natural:
            raw_token = match_natural.group(1).strip().upper()
            compact_token = re.sub(r'^([A-Z])\s+(\d+)$', r'\1\2', raw_token)
            first_tok = compact_token.split()[0]

            # Kiểm tra xem token tiếp theo có phải là đơn vị số lượng không (ví dụ "báo 2 lần" -> từ sau là "lần")
            after_match = text[match_natural.end():].strip().upper().split()
            next_word = after_match[0] if after_match else ""

            if first_tok not in COMMON_FALSE_POSITIVES and next_word not in NUMERIC_UNITS:
                # Nếu là mã ghép như 'E1 01'
                if compact_token in KNOWN_ERROR_CODES:
                    error_code = compact_token
                elif first_tok in KNOWN_ERROR_CODES:
                    error_code = first_tok
                # Hoặc token mang hình thái mã lỗi rõ rệt (có cả chữ và số, ví dụ F16, 4C, 22E)
                elif re.match(r'^[A-Z]+\d+[A-Z]*$|^\d+[A-Z]+[0-9]*$', first_tok):
                    error_code = first_tok
                # Hoặc mã 2 chữ cái viết hoa ngắn thuộc bảng mã (như IE, OE, CL, SB, UB, CF, DC)
                elif first_tok in {"IE", "OE", "CL", "SB", "UB", "CF", "DC", "TC", "UE", "DE", "LE", "PE"}:
                    error_code = first_tok

    return {
        "brand": brand,
        "device": device,
        "error_code": error_code,
    }

def main():
    print("=== KIỂM TRA HÀM BÓC TÁCH THỰC THỂ CẢI TIẾN TRÊN 60 CÂU ĐỘC LẬP ===")
    with open("data/evaluation/independent_eval_60.json", "r", encoding="utf-8") as f:
        queries = json.load(f)

    from rag_chatbot.retrieval import extract_question_entities as old_extract

    diff_count = 0
    for q in queries:
        query_text = q['query']
        old_ent = old_extract(query_text)
        new_ent = extract_question_entities_improved(query_text)

        if old_ent != new_ent:
            diff_count += 1
            print(f"\n[ID: {q['id']}] '{query_text}'")
            print(f"  CŨ  : {old_ent}")
            print(f"  MỚI : {new_ent}")
            print(f"  KỲ VỌNG: Brand={q['brand'] or 'None'}, Device={q['device'] or 'None'}, Code={q['error_code'] or 'None'}")

    print(f"\nTổng số câu có cải thiện nhận diện: {diff_count} / {len(queries)} câu")

if __name__ == '__main__':
    main()

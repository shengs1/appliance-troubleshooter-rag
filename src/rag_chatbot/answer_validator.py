"""Module Answer Validation - Kiem tra va xac thuc cau tra loi cua Local LLM.

Nhiem vu:
1. Kiem tra tinh groundedness (cau tra loi co bam sat tai lieu retrieved khong).
2. Kiem tra tinh nhat quan ve Hang (Brand consistency).
3. Kiem tra tinh nhat quan ve Thiet bi (Device consistency).
4. Kiem tra tinh nhat quan ve Ma loi (Error code consistency).
5. Phat hien ao giac (Hallucination detection): ma loi la, hang la, thiet bi la, linh kien / nguyen nhan khong co trong context.
6. Kiem tra tinh nhat quan ve Nguon (Source consistency): tai lieu retrieved co phu hop thuc the yeu cau khong.
7. Xu ly khi context khong du hoac cau tra loi rong.

Tuan thu quy tac:
- Rule-based / deterministic hoan toan.
- Khong dung LLM judge / model judge / agent / framework phuc tap.
- De hieu, de giai thich trong do an tot nghiep.
"""

from __future__ import annotations
import re
from typing import Any

from rag_chatbot.retrieval import extract_question_entities


# Thong bao an toan chuan khi cau tra loi khong dat kiem dinh
SAFE_FALLBACK_MESSAGE = "Không thể xác nhận câu trả lời hoàn toàn từ cơ sở dữ liệu hiện có."
INSUFFICIENT_CONTEXT_MESSAGE = "Thông tin trong cơ sở dữ liệu hiện chưa đủ để xác định chính xác nguyên nhân và cách khắc phục."

# Danh sach cac hang dien tu pho bien
KNOWN_BRANDS = [
    "Samsung", "LG", "Panasonic", "Sony", "Daikin",
    "Toshiba", "Electrolux", "Aqua", "Casper", "Sharp",
    "Hitachi", "TCL", "Xiaomi",
]

# Tu dien anh xa tu khoa thiet bi ve ten chuan hoa
DEVICE_KEYWORDS_MAP = [
    ("máy điều hòa", "Điều hòa"),
    ("máy điều hoà", "Điều hòa"),
    ("máy lạnh", "Điều hòa"),
    ("điều hòa", "Điều hòa"),
    ("điều hoà", "Điều hòa"),
    ("máy lọc không khí", "Máy lọc không khí"),
    ("máy rửa bát", "Máy rửa bát"),
    ("máy rửa chén", "Máy rửa bát"),
    ("lò vi sóng", "Lò vi sóng"),
    ("lò nướng", "Lò nướng"),
    ("máy giặt", "Máy giặt"),
    ("máy sấy", "Máy sấy"),
    ("tủ lạnh", "Tủ lạnh"),
    ("bếp từ", "Bếp"),
    ("bếp", "Bếp"),
    ("tivi", "TV"),
    ("tv", "TV"),
]

# Danh sach thanh phan ky thuat quan trong de phat hien ao giac
CRITICAL_TECHNICAL_COMPONENTS = [
    "bo mạch điều khiển", "bo mạch inverter", "bo mạch", "mainboard", "bo nguồn",
    "máy nén", "block máy nén", "lốc máy nén", "lốc nén",
    "cảm biến nhiệt độ", "cảm biến độ ẩm", "cảm biến áp suất", "cảm biến mực nước",
    "van tiết lưu", "van cấp nước", "van xả", "van điện từ",
    "mô tơ", "motor", "động cơ", "chổi than",
    "môi chất lạnh", "xì gas", "rò rỉ gas", "nạp gas", "bơm gas", "hết gas", "gas",
    "dây curoa", "dây curoa đứt",
    "tụ điện", "tụ quạt", "tụ khởi động", "cháy tụ",
    "thanh nhiệt", "sợi đốt", "thanh sấy",
    "bơm xả", "bơm thoát nước", "bơm cấp",
    "phao áp lực", "phao cấp nước", "công tắc cửa",
    "quạt dàn nóng", "quạt dàn lạnh",
]

# Cac hanh vi sua chua xam lan bat thuong can canh bao neu khong co trong context
UNSUPPORTED_ACTIONS = [
    "thay bo mạch", "thay bo", "thay máy nén", "thay lốc", "nạp gas", "bơm gas",
    "thay linh kiện", "thay mô tơ", "thay động cơ", "thay phao", "thay cảm biến",
    "hàn ống đồng", "sửa bo", "thay tụ",
]

# Ky tu dau tieng Viet de loai bo tu tieng Viet bi cat nham thanh ma loi
VIETNAMESE_DIACRITICS = "àáảãạăằắẳẵặâầấẩẫậèéẻẽẹêềếểễệìíỉĩịòóỏõọôồốổỗộơờớởỡợùúủũụưừứửữựỳýỷỹỵđ"

# Tap hop tu dung de loc token khong phai ma loi
NON_ERROR_CODE_WORDS = {
    "TV", "AI", "LG", "AC", "DC", "BO", "NH", "MÁY", "LỖI", "NẶNG", "NHẸ",
    "KHI", "CHO", "VÀ", "CỦA", "LÀ", "CÓ", "ĐỂ", "BỊ", "DO", "NÀY",
    "GÌ", "SAO", "TẠI", "VÌ", "ĐƯỢC", "KHÔNG", "ĐIỆN", "NƯỚC", "GAS",
    "ON", "OFF", "AUTO", "SET", "MODE", "ECO", "OK", "KO", "CAN", "NEN",
}


def is_valid_error_code_token(token: str) -> bool:
    """Kiem tra xem mot token co phai la dinh dang ma loi hop le khong."""
    cleaned = token.strip()
    if not cleaned or len(cleaned) > 10:
        return False
    # Neu chua dau tieng Viet -> la tu tu nhien, khong phai ma loi
    if any(c in VIETNAMESE_DIACRITICS for c in cleaned.lower()):
        return False
    # Neu chua chu thuong ma khong co chu so -> la tu tu nhien
    if any(c.islower() for c in cleaned) and not any(c.isdigit() for c in cleaned):
        return False
    upper = cleaned.upper()
    if upper in NON_ERROR_CODE_WORDS:
        return False
    # Phai la alphanumeric, co the chua dau gach noi
    if not re.match(r'^[A-Z0-9\-]+$', upper):
        return False
    # Neu chua chu so (vi du F11, H97, 4E, E3, D1): hop le
    if any(c.isdigit() for c in upper):
        return True
    # Neu toan chu cai, phai tu 2 den 4 ky tu viet hoa (vi du CF, IE, OE, CL, RS)
    if 2 <= len(upper) <= 4:
        return True
    return False


def extract_error_codes_from_text(text: str) -> set[str]:
    """Trich xuat cac ma loi xuat hien trong van ban mot cach chac chan."""
    if not text:
        return set()

    found: set[str] = set()

    # Mau 1: Di sau cac cum tu chi dinh ma loi ro rang
    pattern = r'(?:mã\s+lỗi|mã|lỗi|báo\s+lỗi|báo\s+mã|hiển\s+thị\s+mã|hiển\s+thị\s+lỗi)\s+([^\s,.:;!?()\[\]{}]+)'
    for match in re.finditer(pattern, text, re.IGNORECASE):
        candidate = match.group(1)
        if is_valid_error_code_token(candidate):
            found.add(candidate.upper())

    # Mau 2: Cac token chu hoa dang ma loi co chu so (nhu F11, H97, 4E, E3)
    for token in re.findall(r'\b[A-Za-z0-9\-]{2,6}\b', text):
        candidate = token.upper()
        # Neu token chi chua chu so (vi du 60 giay, 30 phut): bo qua
        if candidate.isdigit():
            continue
        if any(c.isdigit() for c in candidate) and is_valid_error_code_token(candidate):
            found.add(candidate)

    return found


def extract_brands_from_text(text: str) -> set[str]:
    """Trich xuat cac hang xuat hien trong van ban."""
    if not text:
        return set()
    found: set[str] = set()
    text_lower = text.lower()
    for brand in KNOWN_BRANDS:
        if re.search(r'\b' + re.escape(brand.lower()) + r'\b', text_lower):
            found.add(brand)
    return found


def extract_devices_from_text(text: str) -> set[str]:
    """Trich xuat cac loai thiet bi xuat hien trong van ban theo ten chuan hoa."""
    if not text:
        return set()
    found: set[str] = set()
    text_lower = text.lower()
    for keyword, canonical_device in DEVICE_KEYWORDS_MAP:
        if keyword in text_lower:
            found.add(canonical_device)
    return found


def build_full_context_text(retrieved_documents: list[dict[str, Any]]) -> str:
    """Tong hop toan bo noi dung van ban tu cac tai lieu retrieved."""
    parts: list[str] = []
    for doc in retrieved_documents:
        parts.append(str(doc.get("question", "")))
        parts.append(str(doc.get("answer", "")))
        parts.append(str(doc.get("brand", "")))
        parts.append(str(doc.get("device", "")))
        if doc.get("error_code"):
            parts.append(str(doc.get("error_code")))
    return " ".join(parts)


def validate_answer(
    question: str,
    answer: str,
    retrieved_documents: list[dict[str, Any]],
    entities: dict[str, str | None] | None = None,
) -> dict[str, Any]:
    """Ham xac thuc kiem dinh cau tra loi cua Local LLM.
    
    Kiem tra 6 tieu chi co ban:
    1. Groundedness (co bam sat context khong, khong bia dat giai phap/linh kien la)
    2. Brand consistency (khong doi hang hoac chen hang la)
    3. Device consistency (khong doi thiet bi hoac chen thiet bi la)
    4. Error code consistency (giu dung ma loi, khong bia ma loi moi)
    5. Hallucination detection (phat hien ao giac ve thuc the va linh kien)
    6. Source consistency (tai lieu retrieved co dung hang/thiet bi yeu cau khong)

    Args:
        question: Cau hoi cua nguoi dung.
        answer: Cau tra loi sinh ra boi LLM.
        retrieved_documents: Danh sach tai lieu lay tu hybrid retrieval.
        entities: Dict thuc the trich xuat tu cau hoi (tuy chon).

    Returns:
        Dict ket qua danh gia:
        {
            "status": "pass" | "warning" | "fail",
            "grounded": bool,
            "brand_consistent": bool,
            "device_consistent": bool,
            "error_code_consistent": bool,
            "hallucination_detected": bool,
            "source_consistent": bool,
            "reasons": list[str]
        }
    """
    reasons: list[str] = []
    warning_reasons: list[str] = []

    # 1. Kiem tra truong hop rong (Edge cases)
    if not answer or not answer.strip():
        return {
            "status": "fail",
            "grounded": False,
            "brand_consistent": False,
            "device_consistent": False,
            "error_code_consistent": False,
            "hallucination_detected": False,
            "source_consistent": False,
            "reasons": ["Câu trả lời rỗng."],
        }

    if not retrieved_documents:
        return {
            "status": "fail",
            "grounded": False,
            "brand_consistent": False,
            "device_consistent": False,
            "error_code_consistent": False,
            "hallucination_detected": False,
            "source_consistent": False,
            "reasons": ["Không tìm thấy tài liệu kỹ thuật nào trong cơ sở tri thức (retrieved documents rỗng)."],
        }

    # Kiem tra xem retrieved_documents co chua noi dung huong dan nao khong
    guidance_content = " ".join(
        [
            str(d.get("answer", "")).strip() + " " + str(d.get("question", "")).strip()
            for d in retrieved_documents
        ]
    ).strip()
    if not guidance_content:
        return {
            "status": "fail",
            "grounded": False,
            "brand_consistent": True,
            "device_consistent": True,
            "error_code_consistent": True,
            "hallucination_detected": False,
            "source_consistent": True,
            "reasons": ["Tài liệu tham khảo không chứa thông tin xử lý sự cố (ngữ cảnh không đủ)."],
        }

    context_text = build_full_context_text(retrieved_documents).strip()

    # 2. Trich xuat thuc the tu cau hoi va tai lieu
    if entities is None:
        entities = extract_question_entities(question)

    query_brand = entities.get("brand")
    query_device = entities.get("device")
    query_error_code = (entities.get("error_code") or "").strip().upper()
    query_error_codes: set[str] = set()
    if query_error_code:
        for p in re.split(r'[,/;\s]+', query_error_code):
            if p and is_valid_error_code_token(p):
                query_error_codes.add(p)

    # Tap hop thuc the tu context
    context_brands = {str(d.get("brand")) for d in retrieved_documents if d.get("brand")}
    context_devices = {str(d.get("device")) for d in retrieved_documents if d.get("device")}
    context_error_codes: set[str] = set()
    for d in retrieved_documents:
        raw_ec = str(d.get("error_code") or "").strip().upper()
        if raw_ec and raw_ec != "NONE":
            for p in re.split(r'[,/;\s]+', raw_ec):
                if p and is_valid_error_code_token(p):
                    context_error_codes.add(p)

    # Tap hop thuc the trong cau tra loi
    answer_brands = extract_brands_from_text(answer)
    answer_devices = extract_devices_from_text(answer)
    answer_error_codes = extract_error_codes_from_text(answer)

    # 3. Kiem tra Source Consistency
    source_consistent = True
    top_doc = retrieved_documents[0]
    top_brand = top_doc.get("brand")
    top_device = top_doc.get("device")

    if query_brand and top_brand and top_brand.lower() != query_brand.lower():
        source_consistent = False
        reasons.append(
            f"Tài liệu tham khảo ({top_brand}) không khớp với hãng yêu cầu ({query_brand})."
        )

    if query_device and top_device and top_device.lower() != query_device.lower():
        source_consistent = False
        reasons.append(
            f"Tài liệu tham khảo ({top_device}) không khớp với thiết bị yêu cầu ({query_device})."
        )

    # 4. Kiem tra Brand Consistency
    brand_consistent = True
    hallucination_detected = False

    if query_brand:
        # Neu query co brand: answer khong duoc co brand khac tru khi brand do co trong context
        for ab in answer_brands:
            if ab.lower() != query_brand.lower() and ab not in context_brands:
                brand_consistent = False
                hallucination_detected = True
                reasons.append(
                    f"Câu trả lời đề cập hãng '{ab}' khác với hãng '{query_brand}' trong câu hỏi và không có trong tài liệu."
                )
    else:
        # Neu query khong co brand: answer khong duoc tu y bia ra brand khong co trong context
        for ab in answer_brands:
            if ab not in context_brands:
                brand_consistent = False
                hallucination_detected = True
                reasons.append(
                    f"Câu trả lời tự ý đề cập hãng '{ab}' không có trong tài liệu tham khảo."
                )

    # 5. Kiem tra Device Consistency
    device_consistent = True
    if query_device:
        # Neu query co device: answer khong duoc co device khac tru khi co trong context
        for ad in answer_devices:
            if ad.lower() != query_device.lower() and ad not in context_devices:
                device_consistent = False
                hallucination_detected = True
                reasons.append(
                    f"Câu trả lời đề cập thiết bị '{ad}' khác với thiết bị '{query_device}' trong câu hỏi."
                )
    else:
        # Neu query khong co device: answer khong duoc bia device ngoai context
        for ad in answer_devices:
            if ad not in context_devices:
                device_consistent = False
                hallucination_detected = True
                reasons.append(
                    f"Câu trả lời đề cập thiết bị '{ad}' không có trong tài liệu tham khảo."
                )

    # 6. Kiem tra Error Code Consistency & Hallucinated Error Code
    error_code_consistent = True
    if query_error_codes:
        # Query co ma loi:
        # Neu answer nhac toi ma loi khac ma ma loi do khong thuoc query_error_codes va khong co trong context
        for aec in answer_error_codes:
            if aec not in query_error_codes and aec not in context_error_codes:
                error_code_consistent = False
                hallucination_detected = True
                reasons.append(
                    f"Câu trả lời nhắc mã lỗi '{aec}' khác với mã lỗi '{query_error_code}' trong câu hỏi."
                )
    else:
        # Query khong co ma loi (Symptom): khong bat buoc answer phai co ma loi.
        # Nhung neu answer tu nhien dua ra ma loi khong he co trong context -> Hallucination!
        for aec in answer_error_codes:
            if aec not in context_error_codes:
                error_code_consistent = False
                hallucination_detected = True
                reasons.append(
                    f"Câu trả lời tự tạo mã lỗi '{aec}' không có trong tài liệu tham khảo."
                )

    # 7. Kiem tra Groundedness & Phat hien thanh phan ky thuat ao giac (Technical Hallucination)
    grounded = True
    answer_lower = answer.lower()
    context_lower = context_text.lower()

    # Kiem tra cac linh kien ky thuat quan trong xuat hien trong answer
    for comp in CRITICAL_TECHNICAL_COMPONENTS:
        if comp in answer_lower:
            # Neu linh kien xuat hien trong answer ma khong he xuat hien trong context
            if comp not in context_lower:
                grounded = False
                hallucination_detected = True
                reasons.append(
                    f"Phát hiện thành phần kỹ thuật '{comp}' trong câu trả lời nhưng không có trong tài liệu tham khảo."
                )

    # Kiem tra cac hanh vi sua chua xam lan khong duoc context ho tro
    for act in UNSUPPORTED_ACTIONS:
        if act in answer_lower:
            if act not in context_lower:
                grounded = False
                reasons.append(
                    f"Phát hiện thao tác sửa chữa '{act}' trong câu trả lời không có căn cứ từ tài liệu tham khảo."
                )

    # 8. Tong hop trang thai Status (pass / warning / fail)
    if (
        not brand_consistent
        or not device_consistent
        or not error_code_consistent
        or not source_consistent
        or hallucination_detected
        or not grounded
        or len(reasons) > 0
    ):
        status = "fail"
    elif warning_reasons:
        status = "warning"
        reasons.extend(warning_reasons)
    else:
        status = "pass"

    return {
        "status": status,
        "grounded": grounded,
        "brand_consistent": brand_consistent,
        "device_consistent": device_consistent,
        "error_code_consistent": error_code_consistent,
        "hallucination_detected": hallucination_detected,
        "source_consistent": source_consistent,
        "reasons": reasons,
    }

"""Module kiểm tra phạm vi câu hỏi (Scope Checking) và từ chối câu hỏi ngoài lề.

Mục tiêu:
1. Phát hiện các câu hỏi ngoài phạm vi hỗ trợ (thời tiết, tài chính, lập trình, ý kiến chủ quan...).
2. Đánh giá độ tin cậy dựa trên khoảng cách vector ngữ nghĩa và bằng chứng mã lỗi/triệu chứng kỹ thuật.
3. Cung cấp thông báo từ chối an toàn, lịch sự và đúng trọng tâm.
"""

from __future__ import annotations
import re
from typing import Any

from rag_chatbot.config import get_settings
from rag_chatbot.vietnamese import normalize_error_code_spaces, remove_vietnamese_accents


REFUSAL_MESSAGE = (
    "Xin lỗi, câu hỏi này nằm ngoài phạm vi kiến thức của chatbot. "
    "Tôi chỉ hỗ trợ tra cứu và khắc phục sự cố thiết bị điện tử gia dụng có trong cơ sở dữ liệu."
)

# Các từ khóa đơn ngắn cần khớp ranh giới từ để tránh khớp nhầm (ví dụ: 'hư' trong 'phương pháp')
STANDALONE_KEYWORDS = ["hư", "mã lỗi"]

# Danh sách từ khóa và cụm từ về sự cố, triệu chứng và xử lý kỹ thuật thiết bị điện gia dụng
TROUBLESHOOTING_KEYWORDS = [
    # 1. Mã lỗi và sự cố chung
    "lỗi", "mã lỗi", "sự cố", "hỏng", "hư hỏng", "bị hư", "báo lỗi", "cảnh báo",
    
    # 2. Triệu chứng bất thường về âm thanh, rung, mùi, nhiệt độ, nước
    "kêu", "rung", "tiếng ồn", "chảy nước", "bị chảy", "mùi", "chớp", "nhấp nháy", "tự tắt", "tự dừng",
    "tự nhiên dừng", "quá nhiệt", "rò rỉ", "tràn nước", "bị tràn", "nước tràn", "tràn bọt", "chập", "đọng nước", "đọng sương",
    "đóng tuyết", "bị nhăn", "nhiều bọt",

    # 3. Biến thể làm mát / làm lạnh (theo yêu cầu)
    "không lạnh", "không đủ lạnh", "không được lạnh", "kém lạnh", "lạnh yếu", "ít lạnh", "lâu lạnh", "chậm lạnh", "không làm lạnh", "làm lạnh kém",
    "không mát", "không đủ mát", "không được mát", "kém mát", "mát yếu", "ít mát", "chậm mát", "lâu mát", "không làm mát",

    # 4. Biến thể làm nóng / làm đá / nhiệt độ
    "không nóng", "không đủ nóng", "kém nóng", "nóng yếu", "không làm nóng", "nóng không đều", "nóng hai bên",
    "không làm đá", "không đông đá", "không đông",

    # 5. Biến thể sấy / giặt / nước / cửa / gió / điện
    "không khô", "không đủ khô", "không sấy", "không sấy khô", "sấy không khô", "sấy kém", "sấy lâu",
    "không sạch", "giặt không sạch", "giặt lâu",
    "không thoát nước", "không cấp nước", "không vào nước", "không xả", "không vắt",
    "không bật được", "không bật", "không lên", "không chạy", "không hoạt động", "không quay",
    "không khóa cửa", "khó đóng", "khó mở", "không đóng", "không mở",
    "thổi gió yếu", "gió yếu", "không kết nối", "mất điện", "tốn điện",

    # 6. Ý định sửa chữa, khắc phục, tìm nguyên nhân
    "khắc phục", "xử lý", "sửa", "nguyên nhân", "vệ sinh", "kiểm tra",
    "bảo trì", "reset", "đặt lại", "thay thế",
]


def has_troubleshooting_signal(text: str) -> bool:
    """Kiem tra xem van ban co chua tu khoa ve su co, ma loi hoac huong dan khac phuc hay khong.
    
    Ho tro ca tieng Viet co dau va khong dau.
    """
    if not text:
        return False
    text_lower = text.lower()
    text_unaccent = remove_vietnamese_accents(text_lower)

    # 1. Kiem tra tu khoa don ngan can ranh gioi tu (co dau va khong dau)
    for word in STANDALONE_KEYWORDS:
        if re.search(r"\b" + re.escape(word) + r"\b", text_lower):
            return True
        unaccent_word = remove_vietnamese_accents(word)
        if re.search(r"\b" + re.escape(unaccent_word) + r"\b", text_unaccent):
            return True

    # 2. Kiem tra cac tu khoa ve su co / trieu chung voi ranh gioi tu (co dau va khong dau)
    for keyword in TROUBLESHOOTING_KEYWORDS:
        pattern = r"\b" + re.escape(keyword) + r"\b"
        if re.search(pattern, text_lower):
            return True
        unaccent_kw = remove_vietnamese_accents(keyword)
        if unaccent_kw == "mat dien":
            unaccent_pattern = r"(?<!\bra\s)\bmat dien\b"
        else:
            unaccent_pattern = r"\b" + re.escape(unaccent_kw) + r"\b"
        if re.search(unaccent_pattern, text_unaccent):
            return True

    return False


def should_refuse(
    retrieved_documents: list[dict[str, Any]],
    question: str | None = None,
    threshold: float | None = None,
) -> bool:
    """Kiem tra xem cau hoi co nen bi tu choi hay khong.
    
    Thu tu danh gia:
    1. Danh sach tai lieu rong -> Tu choi (True).
    2. Khoang cach vector ChromaDB cua tai lieu tot nhat vuot nguong -> Tu choi (True).
    3. Thieu bang chung ky thuat (khong co ma loi, khong co trieu chung su co) -> Tu choi (True).
    4. Du bang chung va khoang cach phu hop -> Chap nhan (False).
    
    Args:
        retrieved_documents: Danh sach tai lieu tra ve tu Hybrid Retrieval.
        question: Cau hoi cua nguoi dung (tuy chon).
        threshold: Nguong khoang cach vector toi da (mac dinh lay tu Settings).
        
    Returns:
        True neu can tu choi, False neu chap nhan tra loi.
    """
    # 1. Neu khong co tai lieu nao duoc tim thay -> Tu choi
    if not retrieved_documents:
        return True

    settings = get_settings()
    top_doc = retrieved_documents[0]
    distance = top_doc.get("distance")

    # 2. Kiem tra bang chung ky thuat / su co
    has_evidence = False
    
    # 2a. Neu co ma loi khop giua cau hoi va tai lieu hang dau
    if question:
        q_norm = normalize_error_code_spaces(question)
        for doc in retrieved_documents[:3]:
            doc_error_code = str(doc.get("error_code", "")).strip().lower()
            if doc_error_code and (
                doc_error_code in question.lower()
                or doc_error_code in q_norm.lower()
            ):
                has_evidence = True
                break
        
    # 2b. Neu chua co evidence ma loi, kiem tra tin hieu ve trieu chung/khac phuc su co trong cau hoi
    if not has_evidence and question and has_troubleshooting_signal(question):
        has_evidence = True
        
    # 2c. Truong hop khong truyen question (goi don le voi retrieved_documents)
    if not has_evidence and question is None:
        doc_error_code = str(top_doc.get("error_code", "")).strip()
        has_evidence = bool(doc_error_code or top_doc.get("answer"))

    # Neu hoan toan khong co bang chung ky thuat/su co -> Tu choi ngay lap tuc
    if not has_evidence:
        return True

    # 3. Kiem tra khoang cach vector ChromaDB
    # Neu threshold duoc truyen cu the tu caller (vi du: unit test), ton trong threshold do.
    # Khi su dung mac dinh: cau hoi co tin hieu su co ro rang cho phep khoang cach ngu nghia
    # len toi 0.70 de tranh tu choi nham cau hoi trieu chung tu nhien va cau hoi khong dau.
    if threshold is not None:
        effective_threshold = threshold
    elif has_evidence:
        effective_threshold = max(settings.scope_distance_threshold, 0.70)
    else:
        effective_threshold = settings.scope_distance_threshold

    if distance is not None and distance > effective_threshold:
        return True

    # 4. Khi da du bang chung va khoang cach phu hop -> Chap nhan
    return False

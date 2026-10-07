"""Module kiem tra pham vi cau hoi (Scope Checking) va tu choi cau hoi ngoai le.

Nhiem vu trong Phase 10A:
1. Phat hien cac cau hoi ngoai pham vi ho tro cua chatbot:
   - Chatbot chi ho tro: ma loi, nguyen nhan su co, huong dan khac phuc cho thiet bi dien gia dung.
   - Tu choi cac cau hoi ngoai le (tien so, thoi tiet, the thao, lap trinh, hoi y kien, gia ca...).
2. Quyết dinh pham vi dua tren cac tieu chi theo thu tu uu tien:
   - Khoang cach ngu nghia ChromaDB (distance) cua ket qua tot nhat.
   - Bang chung ve loi ky thuat / trieu chung su co / ma loi trong cau hoi va tai lieu.
   - retrieval_source ('both') chi dong vai tro tin hieu tang do tin cay, khong tu dong chap nhan.
3. Cung cap thong bao tu choi tu nhien va lich su.
"""

from __future__ import annotations
from typing import Any

from rag_chatbot.config import get_settings


REFUSAL_MESSAGE = (
    "Xin lỗi, câu hỏi này nằm ngoài phạm vi kiến thức của chatbot. "
    "Tôi chỉ hỗ trợ tra cứu và khắc phục sự cố thiết bị điện tử gia dụng có trong cơ sở dữ liệu."
)

# Danh sach tu khoa ve su co, trieu chung va xu ly ky thuat thiet bi dien gia dung
TROUBLESHOOTING_KEYWORDS = [
    # Ma loi va su co chung
    "lỗi", "mã", "mã lỗi", "sự cố", "hỏng", "hư", "báo lỗi", "cảnh báo",
    # Trieu chung bat thuong
    "kêu", "rung", "chảy", "mùi", "chớp", "nhấp nháy", "tự tắt", "tự dừng",
    "quá nhiệt", "rò rỉ", "tràn", "chập",
    # Trieu chung phu dinh (khong hoat dong binh thuong)
    "không lạnh", "không mát", "không đông", "không vào", "không vắt",
    "không xả", "không chạy", "không hoạt động", "không lên", "không quay",
    "không sạch", "không đóng", "không mở", "không nóng", "không khô", "không sấy",
    # Y dinh sua chua, khac phuc, tim nguyen nhan
    "khắc phục", "xử lý", "sửa", "nguyên nhân", "vệ sinh", "kiểm tra",
    "bảo trì", "reset", "đặt lại", "thay thế",
]


def has_troubleshooting_signal(text: str) -> bool:
    """Kiem tra xem van ban co chua tu khoa ve su co, ma loi hoac huong dan khac phuc hay khong."""
    if not text:
        return False
    text_lower = text.lower()
    return any(keyword in text_lower for keyword in TROUBLESHOOTING_KEYWORDS)


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
    active_threshold = threshold if threshold is not None else settings.scope_distance_threshold

    top_doc = retrieved_documents[0]
    distance = top_doc.get("distance")

    # 2. Khoang cach vector ChromaDB vuot nguong -> Tu choi
    # (Khoang cach lon nghia la do tuong dong ngu nghia kem, cau hoi xa la)
    if distance is not None and distance > active_threshold:
        return True

    # 3. Kiem tra bang chung ky thuat / su co
    has_evidence = False
    
    # 3a. Neu co ma loi khop giua cau hoi va tai lieu
    doc_error_code = str(top_doc.get("error_code", "")).strip()
    if doc_error_code and question and doc_error_code.lower() in question.lower():
        has_evidence = True
        
    # 3b. Neu cau hoi chua tin hieu ve trieu chung/khac phuc su co
    elif question and has_troubleshooting_signal(question):
        has_evidence = True
        
    # 3c. Truong hop khong truyen question (goi don le voi retrieved_documents)
    elif question is None:
        # Kiem tra xem tai lieu co chua thong tin ky thuat ro rang khong
        has_evidence = bool(doc_error_code or top_doc.get("answer"))

    if not has_evidence:
        return True

    # 4. Khi da du bang chung va khoang cach tot -> Chap nhan
    return False

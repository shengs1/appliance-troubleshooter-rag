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
import re
from typing import Any

from rag_chatbot.config import get_settings


REFUSAL_MESSAGE = (
    "Xin lỗi, câu hỏi này nằm ngoài phạm vi kiến thức của chatbot. "
    "Tôi chỉ hỗ trợ tra cứu và khắc phục sự cố thiết bị điện tử gia dụng có trong cơ sở dữ liệu."
)

# Các từ khóa đơn ngắn cần khớp ranh giới từ để tránh khớp nhầm (ví dụ: 'hư' trong 'phương pháp')
STANDALONE_KEYWORDS = ["hư", "mã"]

# Danh sách từ khóa và cụm từ về sự cố, triệu chứng và xử lý kỹ thuật thiết bị điện gia dụng
TROUBLESHOOTING_KEYWORDS = [
    # 1. Mã lỗi và sự cố chung
    "lỗi", "mã lỗi", "sự cố", "hỏng", "hư hỏng", "bị hư", "báo lỗi", "cảnh báo",
    
    # 2. Triệu chứng bất thường về âm thanh, rung, mùi, nhiệt độ, nước
    "kêu", "rung", "tiếng ồn", "chảy", "mùi", "chớp", "nhấp nháy", "tự tắt", "tự dừng",
    "tự nhiên dừng", "quá nhiệt", "rò rỉ", "tràn", "chập", "đọng nước", "đọng sương",
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
    """Kiem tra xem van ban co chua tu khoa ve su co, ma loi hoac huong dan khac phuc hay khong."""
    if not text:
        return False
    text_lower = text.lower()
    for word in STANDALONE_KEYWORDS:
        if re.search(r"\b" + re.escape(word) + r"\b", text_lower):
            return True
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

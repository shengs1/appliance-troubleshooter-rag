"""Module truy van du lieu (Retrieval Module).

Nhiem vu trong Phase 3:
- Cung cap ham tim kiem ngu nghia (Semantic Search) dua tren cau hoi cua nguoi dung.
- Tra ve top-k tai lieu tuong dong nhat kem theo metadata va khoang cach (similarity information).

(Cac chuc nang Hybrid Retrieval ket hop Neo4j se duoc phat trien trong Phase 4)
"""

from typing import Any
from rag_chatbot.chroma_db import query_similar_documents


def search_similar_documents(
    question: str,
    k: int = 5,
    collection: Any = None,
    where: dict | None = None,
) -> list[dict]:
    """Truy van top-k tai lieu tuong dong ngu nghia tu ChromaDB cho cau hoi nguoi dung.
    
    Args:
        question: Cau hoi cua nguoi dung (vi du: 'Máy điều hòa Samsung lỗi CF là gì?').
        k: So luong ket qua can tra ve (mac dinh k = 5).
        collection: Collection doi tuong tuy chon (dung khi kiem thu).
        where: Bo loc metadata tuy chon (vi du: {'brand': 'Samsung'}).
        
    Returns:
        Danh sach cac dict chua thong tin tai lieu tuong dong:
        - 'id': Ma dinh danh cau hoi (vi du: 'Q0358')
        - 'document': Noi dung van ban cua tai lieu (page_content)
        - 'metadata': Thong tin thuoc tinh kem theo (hang, thiet bi, ma loi, nguon...)
        - 'distance': Khoang cach vector (cang nho cang tuong dong)
    """
    if not question or not question.strip():
        return []

    return query_similar_documents(
        query_text=question.strip(),
        n_results=k,
        collection=collection,
        where=where,
    )


def retrieve_hybrid_context(query: str):
    """Ham thuc hien truy van ket hop Vector va Graph cho cau hoi (Phase 4)."""
    raise NotImplementedError("Hybrid Retrieval (ChromaDB + Neo4j) se duoc trien khai trong Phase 4.")

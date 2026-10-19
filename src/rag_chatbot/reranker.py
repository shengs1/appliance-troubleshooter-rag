"""Neural Reranker su dung Cross-Encoder model BAAI/bge-reranker-v2-m3.

Module nay cung cap kha nang xep hang lai ket qua tim kiem (Post-Retrieval Reranking)
bang mo hinh hoc sau (Neural Cross-Encoder) cho he thong Hybrid RAG.

Dac diem:
- Su dung model BAAI/bge-reranker-v2-m3 tu sentence-transformers.
- Model duoc khoi tao singleton (load 1 lan duy nhat va tai su dung).
- Tinh toan diem tuong dong ngu nghia sau giua query va candidate text.
- Khong xoa hoac lam mat bat ky truong metadata goc nao cua ung vien.
"""

from typing import Any
from sentence_transformers import CrossEncoder

# Singleton instance de tranh load model nhieu lan
_RERANKER_MODEL: CrossEncoder | None = None
_DEFAULT_MODEL_NAME = "BAAI/bge-reranker-v2-m3"


def get_reranker(model_name: str = _DEFAULT_MODEL_NAME) -> CrossEncoder:
    """Lay hoac khoi tao doi tuong CrossEncoder model (Singleton).
    
    Args:
        model_name: Ten mo hinh CrossEncoder (mac dinh la BAAI/bge-reranker-v2-m3).
        
    Returns:
        Doi tuong CrossEncoder da duoc khoi tao.
    """
    global _RERANKER_MODEL
    if _RERANKER_MODEL is None:
        _RERANKER_MODEL = CrossEncoder(model_name)
    return _RERANKER_MODEL


def format_candidate_text(item: dict[str, Any]) -> str:
    """Dinh dang thong tin ung vien thanh van ban dau vao cho Cross-Encoder.
    
    Cau truc dinh dang:
    Hãng: {brand}
    Thiết bị: {device}
    Mã lỗi: {error_code}
    Câu hỏi: {question}
    Câu trả lời: {answer}
    """
    brand = item.get("brand", "") or ""
    device = item.get("device", "") or ""
    error_code = item.get("error_code", "") or ""
    question = item.get("question", "") or ""
    answer = item.get("answer", "") or ""

    return (
        f"Hãng: {brand}\n"
        f"Thiết bị: {device}\n"
        f"Mã lỗi: {error_code}\n"
        f"Câu hỏi: {question}\n"
        f"Câu trả lời: {answer}"
    )


def rerank_with_model(
    query: str,
    results: list[dict[str, Any]],
    top_k: int = 5,
    model: Any = None,
) -> list[dict[str, Any]]:
    """Xep hang lai danh sach ket qua tim kiem bang neural Cross-Encoder model.
    
    Quy trinh:
    1. Kiem tra danh sach results rong hoac chi co 1 phan tu.
    2. Format tung candidate thanh van ban dau vao chuan hoa.
    3. Du doan similarity score giua [query, candidate_text].
    4. Gan score vao truong 'reranker_score' = round(float(score), 4).
    5. Sap xep giam dan theo 'reranker_score' va tra ve top_k phan tu.
    
    Bao dam:
    - Khong thay doi hoac xoa bo bat ky truong metadata goc nao.
    - Bao toan thu tu on dinh khi diem bang nhau.
    """
    if not results:
        return []

    if len(results) == 1:
        item_copy = dict(results[0])
        if "reranker_score" not in item_copy:
            # Neu co model san thi predict, neu khong thi gan 1.0 de khong bat buoc load model
            if model is not None:
                pair = [[query, format_candidate_text(item_copy)]]
                score = model.predict(pair)
                if hasattr(score, "__iter__"):
                    item_copy["reranker_score"] = round(float(score[0]), 4)
                else:
                    item_copy["reranker_score"] = round(float(score), 4)
            else:
                item_copy["reranker_score"] = 1.0
        return [item_copy]

    reranker = model if model is not None else get_reranker()

    pairs = [[query, format_candidate_text(item)] for item in results]
    raw_scores = reranker.predict(pairs)

    scored_items: list[tuple[float, dict[str, Any]]] = []
    for score_val, item in zip(raw_scores, results):
        item_copy = dict(item)
        score_float = float(score_val)
        item_copy["reranker_score"] = round(score_float, 4)
        scored_items.append((score_float, item_copy))

    # Sap xep giam dan theo diem score
    scored_items.sort(key=lambda x: x[0], reverse=True)

    return [item for _, item in scored_items][:top_k]

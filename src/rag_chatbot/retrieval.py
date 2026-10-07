"""Module truy van du lieu ket hop Hybrid Retrieval (ChromaDB + Neo4j).

Nhiem vu trong Phase 5:
1. Trich xuat thuc the co ban tu cau hoi cua nguoi dung (Hang, Thiet bi, Ma loi).
2. Thuc hien tim kiem ngu nghia (Semantic Search) bang ChromaDB.
3. Thuc hien tim kiem quan he do thi (Graph Search) bang Neo4j.
4. Hop nhat (Combine) ket qua tu ca hai nguon mot cach don gian va ro rang:
   - Neu ban ghi duoc tim thay boi ca ChromaDB va Neo4j -> retrieval_source = 'both'.
   - Neu chi tim thay boi mot nguon -> retrieval_source = 'chroma' hoac 'neo4j'.
   - Uu tien dua cac ban ghi tim thay tu ca hai nguon ('both') len dau danh sach.
"""

from __future__ import annotations
import re
from typing import Any

from rag_chatbot.chroma_db import query_similar_documents
from rag_chatbot.neo4j_db import run_query


def extract_question_entities(text: str) -> dict[str, str | None]:
    """Trich xuat cac thuc the co ban tu cau hoi nguoi dung: Hang, Thiet bi, Ma loi.
    
    Phuong phap:
    - Su dung tu khoa cho Hang (Samsung, LG, Panasonic).
    - Su dung tu dien anh xa tu khoa cho Loai thiet bi (Dieu hoa, Tu lanh, May giat...).
    - Su dung bieu thuc chinh quy (regex) de bat ma loi sau tu 'loi' hoac 'ma loi'.
    """
    if not text:
        return {"brand": None, "device": None, "error_code": None}

    text_lower = text.lower()

    # 1. Nhan dien Hang (Brand)
    brand: str | None = None
    for b in ["Samsung", "LG", "Panasonic"]:
        if b.lower() in text_lower:
            brand = b
            break

    # 2. Nhan dien Loai thiet bi (Device)
    device: str | None = None
    device_keywords = {
        "máy điều hòa": "Điều hòa",
        "điều hòa": "Điều hòa",
        "máy lạnh": "Điều hòa",
        "tủ lạnh": "Tủ lạnh",
        "máy giặt": "Máy giặt",
        "máy sấy": "Máy sấy",
        "lò nướng": "Lò nướng",
        "lò vi sóng": "Lò vi sóng",
        "máy rửa bát": "Máy rửa bát",
        "máy lọc không khí": "Máy lọc không khí",
        "bếp từ": "Bếp",
        "bếp": "Bếp",
        "tivi": "TV",
        "tv": "TV",
    }
    for kw, target_dev in device_keywords.items():
        if kw in text_lower:
            device = target_dev
            break

    # 3. Nhan dien Ma loi (Error Code)
    error_code: str | None = None
    # Tim ma loi dung sau tu 'ma loi', 'ma' hoac 'loi' (vi du: 'loi CF', 'ma loi RS')
    match = re.search(r'(?:mã\s+lỗi|mã|lỗi)\s+([A-Za-z0-9\-]+)', text, re.IGNORECASE)
    if match:
        error_code = match.group(1).upper()

    return {
        "brand": brand,
        "device": device,
        "error_code": error_code,
    }


def search_similar_documents(
    question: str,
    k: int = 5,
    collection: Any = None,
    where: dict | None = None,
) -> list[dict]:
    """Truy van top-k tai lieu tuong dong ngu nghia tu ChromaDB.
    
    Args:
        question: Cau hoi cua nguoi dung.
        k: So luong ket qua can tra ve (mac dinh k = 5).
        collection: Collection doi tuong tuy chon.
        where: Bo loc metadata tuy chon.
        
    Returns:
        Danh sach cac dict chua thong tin tai lieu tuong dong tu ChromaDB.
    """
    if not question or not question.strip():
        return []

    return query_similar_documents(
        query_text=question.strip(),
        n_results=k,
        collection=collection,
        where=where,
    )


def search_graph(
    question: str,
    k: int = 5,
    driver: Any = None,
) -> list[dict]:
    """Truy van cac ban ghi Question va Answer lien quan tu do thi Neo4j.
    
    Quy trinh:
    1. Trich xuat cac thuc the (Hang, Thiet bi, Ma loi) tu cau hoi.
    2. Neu co ma loi: Tim theo ErrorCode -> Issue -> Question -> Answer.
    3. Neu khong co ma loi nhung co Hang/Thiet bi: Tim theo Brand/Device -> Issue -> Question.
    """
    if not question or not question.strip():
        return []

    entities = extract_question_entities(question)
    brand = entities["brand"]
    device = entities["device"]
    error_code = entities["error_code"]

    # Neu khong trich xuat duoc bat ky thuc the nao, tra ve rong de de cho vector search xu ly
    if not brand and not device and not error_code:
        return []

    if error_code:
        # Truong hop 1: Co ma loi -> tim cac cau hoi gan voi ma loi va ket hop loc theo Hang/Thiet bi
        cypher = """
        MATCH (e:ErrorCode)
        WHERE toUpper(e.code) = toUpper($error_code)
        MATCH (i:Issue)-[:HAS_ERROR_CODE]->(e)
        MATCH (q:Question)-[:ABOUT]->(i)
        MATCH (b:Brand {brand_id: q.brand_id})
        MATCH (d:Device {device_id: q.device_id})
        WHERE ($brand IS NULL OR toLower(b.name) = toLower($brand))
          AND ($device IS NULL OR toLower(d.name) = toLower($device))
        OPTIONAL MATCH (q)-[:ANSWERED_BY]->(a:Answer)
        OPTIONAL MATCH (q)-[:SOURCED_FROM]->(s:Source)
        RETURN 
            q.question_id AS question_id,
            q.question AS question,
            coalesce(a.answer, '') AS answer,
            b.name AS brand,
            d.name AS device,
            e.code AS error_code,
            coalesce(s.url, '') AS source_url
        LIMIT $limit
        """
    else:
        # Truong hop 2: Khong co ma loi cu the -> tim cac cau hoi theo Hang va Thiet bi
        cypher = """
        MATCH (q:Question)-[:ABOUT]->(i:Issue)
        MATCH (b:Brand {brand_id: q.brand_id})
        MATCH (d:Device {device_id: q.device_id})
        WHERE ($brand IS NULL OR toLower(b.name) = toLower($brand))
          AND ($device IS NULL OR toLower(d.name) = toLower($device))
        OPTIONAL MATCH (i)-[:HAS_ERROR_CODE]->(e:ErrorCode)
        OPTIONAL MATCH (q)-[:ANSWERED_BY]->(a:Answer)
        OPTIONAL MATCH (q)-[:SOURCED_FROM]->(s:Source)
        RETURN 
            q.question_id AS question_id,
            q.question AS question,
            coalesce(a.answer, '') AS answer,
            b.name AS brand,
            d.name AS device,
            coalesce(e.code, '') AS error_code,
            coalesce(s.url, '') AS source_url
        LIMIT $limit
        """

    params = {
        "error_code": error_code,
        "brand": brand,
        "device": device,
        "limit": k,
    }

    raw_results = run_query(cypher, parameters=params, driver=driver)
    
    # Chuan hoa format tra ve
    results: list[dict] = []
    for r in raw_results:
        results.append({
            "question_id": r.get("question_id", ""),
            "question": r.get("question", ""),
            "answer": r.get("answer", ""),
            "brand": r.get("brand", ""),
            "device": r.get("device", ""),
            "error_code": r.get("error_code", ""),
            "source_url": r.get("source_url", ""),
            "retrieval_source": "neo4j",
            "distance": None,
        })
    return results


def search_hybrid(
    question: str,
    k: int = 5,
    chroma_collection: Any = None,
    neo4j_driver: Any = None,
) -> list[dict]:
    """Truy van ket hop Hybrid Retrieval: ChromaDB (ngu nghia) + Neo4j (quan he).
    
    Quy trinh:
    1. Tim kiem semantic bang ChromaDB (top k).
    2. Tim kiem graph bang Neo4j (top k).
    3. Hop nhat ket qua:
       - Ban ghi xuat hien o ca 2 ben -> retrieval_source = 'both'.
       - Ban ghi chi xuat hien o 1 ben -> retrieval_source = 'chroma' hoac 'neo4j'.
    4. Sap xep: Uu tien cac ban ghi co bang chung tu ca 2 nguon ('both') len dau.
    5. Tra ve toi da k ban ghi phu hop nhat.
    
    Args:
        question: Cau hoi cua nguoi dung.
        k: So luong ban ghi can tra ve (mac dinh k = 5).
        chroma_collection: Chroma collection tuy chon (phuc vu test).
        neo4j_driver: Neo4j driver tuy chon (phuc vu test).
        
    Returns:
        Danh sach dict gom: question_id, question, answer, brand, device, error_code, source_url, retrieval_source.
    """
    if not question or not question.strip():
        return []

    # 1. Tim kiem tuong dong ngu nghia tu ChromaDB
    chroma_raw = search_similar_documents(question, k=k, collection=chroma_collection)
    chroma_items: list[dict] = []
    for r in chroma_raw:
        meta = r.get("metadata", {})
        doc_text = r.get("document", "")

        # Trích xuất câu hỏi và câu trả lời từ document text
        q_text = ""
        ans_text = ""
        for line in doc_text.splitlines():
            if line.startswith("Câu hỏi: "):
                q_text = line[len("Câu hỏi: "):].strip()
            elif line.startswith("Câu trả lời: "):
                ans_text = line[len("Câu trả lời: "):].strip()

        chroma_items.append({
            "question_id": str(meta.get("question_id", r.get("id", ""))),
            "question": q_text or str(meta.get("question_id", "")),
            "answer": ans_text,
            "brand": str(meta.get("brand", "")),
            "device": str(meta.get("device", "")),
            "error_code": str(meta.get("error_code", "")),
            "source_url": str(meta.get("source_url", "")),
            "retrieval_source": "chroma",
            "distance": r.get("distance"),
        })

    # 2. Tim kiem cau truc quan he tu Neo4j
    neo4j_items = search_graph(question, k=k, driver=neo4j_driver)

    # 3. Hop nhat ket qua (Combine)
    combined: dict[str, dict] = {}

    for item in chroma_items:
        qid = item["question_id"]
        combined[qid] = item

    for item in neo4j_items:
        qid = item["question_id"]
        if qid in combined:
            # Da co tu ChromaDB -> danh dau 'both'
            combined[qid]["retrieval_source"] = "both"
            # Bo sung cau tra loi neu ChromaDB bi thieu
            if not combined[qid]["answer"] and item.get("answer"):
                combined[qid]["answer"] = item["answer"]
        else:
            combined[qid] = item

    # 4. Sap xep: Uu tien ban ghi tim thay tu ca 2 nguon ('both') len dau
    sorted_results = sorted(
        combined.values(),
        key=lambda x: (0 if x["retrieval_source"] == "both" else 1)
    )

    return sorted_results[:k]


def retrieve_hybrid_context(query: str, k: int = 5) -> list[dict]:
    """Ham thuc hien truy van ket hop Vector va Graph cho cau hoi (alias cho search_hybrid)."""
    return search_hybrid(question=query, k=k)


if __name__ == "__main__":
    sample_query = "Máy điều hòa Samsung lỗi CF là gì?"
    print(f"=== TEST HYBRID RETRIEVAL: {sample_query} ===")
    results = search_hybrid(sample_query, k=5)
    for idx, res in enumerate(results, 1):
        print(f"\n[{idx}] Question ID: {res['question_id']} (Source: {res['retrieval_source']})")
        print(f"    Hãng: {res['brand']} | Thiết bị: {res['device']} | Mã lỗi: {res['error_code']}")
        print(f"    Câu hỏi: {res['question']}")
        print(f"    Câu trả lời: {res['answer'][:120]}...")
        print(f"    Nguồn: {res['source_url']}")

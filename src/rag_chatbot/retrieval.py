"""Module truy vấn dữ liệu kết hợp Hybrid Retrieval (ChromaDB + Neo4j).

Chức năng chính:
1. Trích xuất thực thể từ câu hỏi (Hãng, Thiết bị, Mã lỗi).
2. Tìm kiếm ngữ nghĩa vector qua ChromaDB và đồ thị tri thức quan hệ qua Neo4j.
3. Hợp nhất và xếp hạng lại tài liệu kỹ thuật (Reranking).
"""

from __future__ import annotations
import logging
import re
from typing import Any
import unicodedata

logger = logging.getLogger(__name__)

from rag_chatbot.chroma_db import query_similar_documents
from rag_chatbot.config import get_settings
from rag_chatbot.neo4j_db import run_query
from rag_chatbot.vietnamese import (
    apply_aliases,
    generate_query_variants,
    normalize_error_code_spaces,
    normalize_vietnamese_query,
    remove_vietnamese_accents,
)


# Danh sach cac cap nguyen am chuan hoa vi tri dau thanh tieng Viet (kieu moi vs kieu cu)
TONE_PAIRS = [
    ("oà", "òa"), ("oá", "óa"), ("oả", "ỏa"), ("oã", "õa"), ("oạ", "ọa"),
    ("uỳ", "ùy"), ("uý", "úy"), ("uỷ", "ủy"), ("uỹ", "ũy"), ("uỵ", "ụy"),
    ("oè", "òe"), ("oé", "óe"), ("oẻ", "ỏe"), ("oẽ", "õe"), ("oẹ", "ọe"),
]


def normalize_question_text(text: str) -> str:
    """Chuan hoa Unicode NFC, khoang trang va dau cau cho cau hoi.
    
    Quy trinh:
    1. Chuyen ve chu thuong va chuan hoa Unicode NFC.
    2. Dong nhat vi tri dau thanh tieng Viet (kieu cu -> kieu moi).
    3. Loai bo ky tu dac biet, dau cau (chi giu chu cai, chu so, khoang trang, gach ngang).
    4. Gom cac khoang trang thua thanh mot khoang trang duy nhat.
    """
    if not text:
        return ""
    t = unicodedata.normalize("NFC", text.lower())
    for old, new in TONE_PAIRS:
        t = t.replace(old, new)
    t = re.sub(r"[^\w\s\-]", " ", t)
    return " ".join(t.split())


def is_exact_question_match(q1: str, q2: str) -> bool:
    """Kiem tra hai cau hoi co trung khop hoan toan sau khi chuan hoa hay khong.
    
    Kiem tra ca truong hop co dau va khong dau de ho tro cau hoi tieng Viet khong dau.
    """
    n1 = normalize_question_text(q1)
    n2 = normalize_question_text(q2)
    if n1 and n2 and n1 == n2:
        return True
    u1 = remove_vietnamese_accents(n1)
    u2 = remove_vietnamese_accents(n2)
    return bool(u1 and u2 and u1 == u2)


def extract_question_entities(text: str) -> dict[str, str | None]:
    """Trich xuat cac thuc the co ban tu cau hoi nguoi dung: Hang, Thiet bi, Ma loi.
    
    Ho tro day du:
    - Tieng Viet co dau, khong dau va tron dau.
    - Alias thuong hieu (pana -> Panasonic).
    - Cac bien the ma loi co khoang trang (F 16 -> F16, H 97 -> H97).
    - Dong nhat danh xung thiet bi (may lanh -> Dieu hoa, may giac -> May giat...).
    """
    if not text:
        return {"brand": None, "device": None, "error_code": None}

    # Chuan hoa khoang trang ma loi va dua ve chu thuong
    normalized_text = normalize_error_code_spaces(text)
    text_lower = normalized_text.lower()
    text_unaccent = remove_vietnamese_accents(text_lower)

    # 1. Nhan dien Hang (Brand)
    brand: str | None = None
    if re.search(r"\bpana\b", text_lower) or "panasonic" in text_lower or "panasonic" in text_unaccent:
        brand = "Panasonic"
    elif "samsung" in text_lower or "samsung" in text_unaccent:
        brand = "Samsung"
    elif re.search(r"\blg\b", text_lower) or re.search(r"\blg\b", text_unaccent):
        brand = "LG"

    # 2. Nhan dien Loai thiet bi (Device) voi chuan hoa danh xung (ca co dau va khong dau)
    device: str | None = None
    device_keywords = [
        # Dieu hoa / May lanh (chuan hoa tat ca cac cach goi ve 'Dieu hoa')
        ("máy điều hòa", "Điều hòa"),
        ("máy điều hoà", "Điều hòa"),
        ("máy lạnh", "Điều hòa"),
        ("điều hòa", "Điều hòa"),
        ("điều hoà", "Điều hòa"),
        ("may dieu hoa", "Điều hòa"),
        ("may lanh", "Điều hòa"),
        ("dieu hoa", "Điều hòa"),
        # Cac loai thiet bi khac trong co so du lieu
        ("máy lọc không khí", "Máy lọc không khí"),
        ("may loc khong khi", "Máy lọc không khí"),
        ("máy rửa bát", "Máy rửa bát"),
        ("máy rửa chén", "Máy rửa bát"),
        ("may rua bat", "Máy rửa bát"),
        ("may rua chen", "Máy rửa bát"),
        ("lò vi sóng", "Lò vi sóng"),
        ("lò vi ba", "Lò vi sóng"),
        ("lo vi song", "Lò vi sóng"),
        ("lo vi ba", "Lò vi sóng"),
        ("lò nướng", "Lò nướng"),
        ("lo nuong", "Lò nướng"),
        ("máy giặt", "Máy giặt"),
        ("máy giặc", "Máy giặt"),
        ("may giat", "Máy giặt"),
        ("may giac", "Máy giặt"),
        ("máy sấy", "Máy sấy"),
        ("máy xấy", "Máy sấy"),
        ("may say", "Máy sấy"),
        ("may xay", "Máy sấy"),
        ("tủ lạnh", "Tủ lạnh"),
        ("tu lanh", "Tủ lạnh"),
        ("bếp từ", "Bếp"),
        ("bep tu", "Bếp"),
        ("bếp", "Bếp"),
        ("bep", "Bếp"),
        ("tivi", "TV"),
        ("tv", "TV"),
    ]
    for kw, target_dev in device_keywords:
        if kw in text_lower or kw in text_unaccent:
            device = target_dev
            break

    # 3. Nhan dien Ma loi (Error Code)
    error_code: str | None = None
    # Tim ma loi sau cac tu khoa: 'ma loi', 'ma', 'loi' (ca co dau va khong dau)
    match = re.search(r'(?:mã\s+lỗi|mã|lỗi|ma\s+loi|ma|loi)\s+([A-Za-z0-9\-]+(?:\s+[0-9]+)?)', normalized_text, re.IGNORECASE)
    if not match:
        # Tim ma loi dang 'bao f16', 'báo F16', 'bao CF'
        match = re.search(r'(?:báo|bao)\s+([A-Za-z][0-9]{1,3})\b', normalized_text, re.IGNORECASE)

    # Danh sach tu dung sau "loi" la thiet bi hoac tu tieng Viet thong dung, khong phai ma loi
    non_error_words = {
        "MAY", "TU", "DIEU", "HOA", "BEP", "LO", "TI", "TIVI", "TV", "QUAT",
        "KHONG", "BI", "CUA", "TAI", "GI", "SAO", "NAO", "THE", "LAM", "VI",
        "XAY", "GIAC", "NUOC", "DONG", "MO", "BAT", "TAT", "KHI", "CHO", "LA"
    }

    if match:
        raw_code = match.group(1).strip()
        clean_code = normalize_error_code_spaces(raw_code).upper()
        # Ma loi hop le: co chua so (vi du: F16, U04, 4C) hoac la ma viet tat ky thuat ngan (vi du: CF, CL)
        # va khong phai tu thiet bi / tu tieng Viet thong thuong
        clean_unaccent = remove_vietnamese_accents(clean_code).upper()
        if clean_unaccent not in non_error_words:
            # Neu co chua so hoac la ma ngan 2-4 ky tu khong phai tu thong thuong
            if re.search(r'\d', clean_code) or (len(clean_code) <= 4 and clean_unaccent not in non_error_words):
                error_code = clean_code

    return {
        "brand": brand,
        "device": device,
        "error_code": error_code,
    }


def build_chroma_where_filter(
    brand: str | None = None,
    device: str | None = None,
) -> dict | None:
    """Xay dung bo loc metadata (where) cho ChromaDB theo Hang va Loai thiet bi.
    
    Quy tac:
    - Neu co ca Hang va Thiet bi: ket hop bang $and de loc chinh xac ca hai.
    - Neu chi co Hang: loc theo Hang.
    - Neu chi co Thiet bi: loc theo Thiet bi.
    - Neu khong co: tra ve None (khong loc).
    """
    conditions: list[dict[str, str]] = []
    if brand:
        conditions.append({"brand": brand})
    if device:
        conditions.append({"device": device})

    if not conditions:
        return None
    if len(conditions) == 1:
        return conditions[0]
    return {"$and": conditions}


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

    try:
        raw_results = run_query(cypher, parameters=params, driver=driver)
    except Exception as exc:
        logger.warning("Truy van do thi Neo4j khong thanh cong hoac server chua san sang: %s", exc)
        raw_results = []
    
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


def rerank_results(
    query: str,
    results: list[dict[str, Any]],
    entities: dict[str, Any] | None = None,
    mode: str = "fixed",
) -> list[dict[str, Any]]:
    """Xep hang lai cac tai lieu ung vien (Post-Retrieval Reranking) bang rule-based scoring.
    
    Quy tac tinh diem:
    1. semantic_score:
       - Neu tai lieu co ChromaDB distance: max(0.0, 1.0 - distance).
       - Neu chi den tu Neo4j khong co distance: semantic_score = 0.0.
    2. Cac trong so bonus duoc ap dung theo mode:
       - mode="fixed":
         + brand_bonus = +0.08
         + device_bonus = +0.08
         + exact_error_code_bonus = +0.20 (chi cong khi query thuc su co error_code)
         + both_bonus = +0.02
         + exact_question_bonus = +0.02 (cong khi cau hoi khop chinh xac sau chuan hoa)
       - mode="adaptive" (thich ung theo loai truy van):
         + ERROR_CODE query: exact error code duoc uu tien cao nhat (+0.25), brand/device (+0.08), both (+0.02)
         + SYMPTOM query: semantic score chiem uu the tuyet doi, brand/device (+0.05), error_code bonus = 0.0, both (+0.01)
         + NO_ENTITY query: giu nguyen thu tu semantic, bonus thuc the = 0.0, both (+0.005)
         + exact_question_bonus = +0.02 (cong khi cau hoi khop chinh xac sau chuan hoa)
    
    Bao dam:
    - Khong xoa candidate, khong lam mat bat ky field metadata nao.
    - Sap xep giam dan theo final_score.
    """
    if not results:
        return []

    if entities is None:
        entities = extract_question_entities(query)

    settings = get_settings()
    target_brand = entities.get("brand")
    target_device = entities.get("device")
    target_error_code = entities.get("error_code")
    exact_question_bonus_val = settings.rerank_exact_question_bonus

    if mode == "adaptive":
        if target_error_code:
            # Truy van co ma loi
            brand_bonus_val = 0.08
            device_bonus_val = 0.08
            error_code_bonus_val = 0.25
            both_bonus_val = 0.02
        elif target_brand or target_device:
            # Truy van trieu chung thuan
            brand_bonus_val = 0.05
            device_bonus_val = 0.05
            error_code_bonus_val = 0.0
            both_bonus_val = 0.01
        else:
            # Truy van khong co thuc the
            brand_bonus_val = 0.0
            device_bonus_val = 0.0
            error_code_bonus_val = 0.0
            both_bonus_val = 0.005
    else:
        # mode == "fixed"
        brand_bonus_val = settings.rerank_brand_bonus
        device_bonus_val = settings.rerank_device_bonus
        error_code_bonus_val = settings.rerank_exact_error_code_bonus
        both_bonus_val = settings.rerank_both_bonus

    scored_items: list[tuple[float, dict[str, Any]]] = []

    for item in results:
        # 1. Semantic score
        dist = item.get("distance")
        if dist is not None:
            semantic_score = max(0.0, 1.0 - float(dist))
        else:
            semantic_score = 0.0

        score = semantic_score

        # 2. Brand bonus
        item_brand = item.get("brand", "")
        if target_brand and item_brand and target_brand.lower() == item_brand.lower():
            score += brand_bonus_val

        # 3. Device bonus
        item_device = item.get("device", "")
        if target_device and item_device and target_device.lower() == item_device.lower():
            score += device_bonus_val

        # 4. Error Code bonus (chi cong khi query thuc su co error_code)
        item_code = item.get("error_code", "")
        if target_error_code and item_code and target_error_code.lower() == item_code.lower():
            score += error_code_bonus_val

        # 5. Both source bonus (tin hieu phu nho)
        if item.get("retrieval_source") == "both":
            score += both_bonus_val

        # 6. Exact question match bonus (chi cong khi cau hoi khop chinh xac sau chuan hoa)
        item_q = item.get("question", "")
        if exact_question_bonus_val > 0.0 and is_exact_question_match(query, item_q):
            score += exact_question_bonus_val

        item_copy = dict(item)
        item_copy["rerank_score"] = round(score, 4)
        scored_items.append((score, item_copy))

    # Stable sort giam dan theo final score
    scored_items.sort(key=lambda x: x[0], reverse=True)
    return [item for _, item in scored_items]


def search_hybrid(
    question: str,
    k: int = 5,
    chroma_collection: Any = None,
    neo4j_driver: Any = None,
    where: dict | None = None,
    use_reranking: bool = True,
    rerank_mode: str = "fixed",
) -> list[dict]:
    """Truy van ket hop Hybrid Retrieval: ChromaDB (ngu nghia) + Neo4j (quan he).
    
    Quy trinh:
    1. Trich xuat thuc the (Hang, Thiet bi, Ma loi) tu cau hoi nguoi dung.
    2. Su dung metadata filter (where) dua tren Hang va Thiet bi de ChromaDB
       khong tra ve tai lieu sai loai thiet bi (vi du: cau hoi Dieu hoa khong lay Tu lanh).
    3. Tim kiem semantic bang ChromaDB (top k).
    4. Tim kiem graph bang Neo4j (top k) theo dung Hang va Thiet bi.
    5. Hop nhat ket qua:
       - Ban ghi xuat hien o ca 2 ben -> retrieval_source = 'both'.
       - Ban ghi chi xuat hien o 1 ben -> retrieval_source = 'chroma' hoac 'neo4j'.
    6. Loc bao dam toan bo ket qua phu hop voi Hang va Thiet bi neu cau hoi xac dinh duoc.
    7. Sap xep:
       - Neu use_reranking=True: Ap dung Post-Retrieval Reranking voi rule-based scoring.
       - Neu use_reranking=False (Baseline): Uu tien ban ghi tim thay tu ca 2 nguon ('both') len dau.
    
    Args:
        question: Cau hoi cua nguoi dung.
        k: So luong ban ghi can tra ve (mac dinh k = 5).
        chroma_collection: Chroma collection tuy chon (phuc vu test).
        neo4j_driver: Neo4j driver tuy chon (phuc vu test).
        where: Bo loc metadata tuy chon (neu None se tu dong tao tu entities).
        use_reranking: Cho phep bat/tat Post-retrieval Reranking de so sanh A/B.
        
    Returns:
        Danh sach dict gom: question_id, question, answer, brand, device, error_code, source_url, retrieval_source.
    """
    if not question or not question.strip():
        return []

    # Trich xuat thuc the
    entities = extract_question_entities(question)
    brand = entities["brand"]
    device = entities["device"]

    fetch_k = max(10, k * 2) if (use_reranking and rerank_mode == "neural") else k

    # 1. Tim kiem tuong dong ngu nghia tu ChromaDB (ap dung metadata filtering neu co thuc the)
    active_where = where if where is not None else build_chroma_where_filter(brand=brand, device=device)

    # Sinh bien the cau hoi (query expansion) co kiem soat de ho tro tieng Viet khong dau / tron dau / alias
    query_variants = generate_query_variants(question)
    if not query_variants:
        query_variants = [question]

    chroma_by_id: dict[str, dict] = {}
    for q_var in query_variants:
        chroma_raw = search_similar_documents(
            q_var,
            k=fetch_k,
            collection=chroma_collection,
            where=active_where,
        )
        for r in chroma_raw:
            meta = r.get("metadata", {})
            doc_text = r.get("document", "")

            # Trich xuat cau hoi va cau tra loi tu document text
            q_text = ""
            ans_text = ""
            for line in doc_text.splitlines():
                if line.startswith("Câu hỏi: "):
                    q_text = line[len("Câu hỏi: "):].strip()
                elif line.startswith("Câu trả lời: "):
                    ans_text = line[len("Câu trả lời: "):].strip()

            qid = str(meta.get("question_id", r.get("id", "")))
            dist = r.get("distance")

            # Hop nhat: giu ban ghi co khoang cach vector nho nhat, tranh trung lap
            if qid not in chroma_by_id or (
                dist is not None and (chroma_by_id[qid].get("distance") is None or dist < chroma_by_id[qid]["distance"])
            ):
                chroma_by_id[qid] = {
                    "question_id": qid,
                    "question": q_text or str(meta.get("question_id", "")),
                    "answer": ans_text,
                    "brand": str(meta.get("brand", "")),
                    "device": str(meta.get("device", "")),
                    "error_code": str(meta.get("error_code", "")),
                    "source_url": str(meta.get("source_url", "")),
                    "retrieval_source": "chroma",
                    "distance": dist,
                }

    chroma_items: list[dict] = list(chroma_by_id.values())

    # 2. Tim kiem cau truc quan he tu Neo4j
    neo4j_items = search_graph(question, k=fetch_k, driver=neo4j_driver)

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

    # 4. Loc bao dam toan bo ket qua phu hop voi Hang va Thiet bi neu cau hoi xac dinh duoc
    filtered_results: list[dict] = []
    for item in combined.values():
        item_brand = item.get("brand", "")
        item_device = item.get("device", "")
        if brand and item_brand and item_brand.lower() != brand.lower():
            continue
        if device and item_device and item_device.lower() != device.lower():
            continue
        filtered_results.append(item)

    # 5. Sap xep: Reranking hoac Baseline
    if use_reranking:
        if rerank_mode == "neural":
            from rag_chatbot.reranker import rerank_with_model
            sorted_results = rerank_with_model(
                question, filtered_results, top_k=k
            )
        else:
            sorted_results = rerank_results(
                question, filtered_results, entities=entities, mode=rerank_mode
            )
    else:
        sorted_results = sorted(
            filtered_results,
            key=lambda x: (0 if x["retrieval_source"] == "both" else 1)
        )

    return sorted_results[:k]


def extract_matching_sources(
    retrieved_docs: list[dict[str, Any]],
    question: str,
) -> list[str]:
    """Trich xuat URL nguon tham khao phu hop voi Hang va Thiet bi cua cau hoi.
    
    Quy tac:
    - Chi lay tai lieu co source_url hop le.
    - Neu cau hoi xac dinh duoc Hang, tai lieu phai thuoc dung Hang do.
    - Neu cau hoi xac dinh duoc Thiet bi, tai lieu phai thuoc dung Thiet bi do.
    - Tuyet doi khong hien thi nguon cua thiet bi khac (vi du: hoi Dieu hoa khong hien thi link Tu lanh).
    """
    if not retrieved_docs:
        return []

    entities = extract_question_entities(question)
    target_brand = entities.get("brand")
    target_device = entities.get("device")

    valid_sources: list[str] = []
    seen_urls: set[str] = set()

    for doc in retrieved_docs:
        url = (doc.get("source_url") or "").strip()
        if not url or url in seen_urls:
            continue

        doc_brand = (doc.get("brand") or "").strip()
        doc_device = (doc.get("device") or "").strip()

        # Kiem tra Hang neu cau hoi co Hang va doc co brand
        if target_brand and doc_brand and doc_brand.lower() != target_brand.lower():
            continue

        # Kiem tra Thiet bi neu cau hoi co Thiet bi va doc co device
        if target_device and doc_device and doc_device.lower() != target_device.lower():
            continue

        valid_sources.append(url)
        seen_urls.add(url)
        # Lay 1 nguon phu hop nhat (top-1)
        break

    return valid_sources


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

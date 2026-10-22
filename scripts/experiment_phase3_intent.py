import json
import re
import sys
import time
import unicodedata
from pathlib import Path
import pandas as pd

sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, ".")

from rag_chatbot.evaluation import load_evaluation_set, calculate_hit_at_k, calculate_mrr
from rag_chatbot.chroma_db import get_or_create_collection
from rag_chatbot.neo4j_db import get_neo4j_driver
from rag_chatbot.retrieval import (
    search_similar_documents,
    search_graph,
    build_chroma_where_filter,
    extract_question_entities,
    is_exact_question_match,
)

# Từ khóa nhận diện ý định đơn giản, dễ giải thích
DIAGNOSIS_KEYWORDS = [
    "nguyên nhân", "tại sao", "vì sao", "ý nghĩa", "nghĩa là gì", "là gì", "là lỗi gì", "do đâu"
]
REPAIR_KEYWORDS = [
    "cách sửa", "khắc phục", "sửa thế nào", "làm sao", "phải làm sao", "xử lý thế nào", "kiểm tra gì", "cần làm gì", "sửa như thế nào", "thay thế", "vệ sinh thế nào"
]

def classify_query_intent(query: str) -> str:
    """Phân loại ý định câu hỏi: DIAGNOSIS, REPAIR, hoặc GENERAL/AMBIGUOUS."""
    q_low = query.lower()
    # Kiểm tra REPAIR trước (vì 'phải làm sao', 'cách sửa' là các cụm xử lý trực diện)
    has_repair = any(kw in q_low for kw in REPAIR_KEYWORDS)
    has_diag = any(kw in q_low for kw in DIAGNOSIS_KEYWORDS)

    if has_repair and not has_diag:
        return "REPAIR"
    if has_diag and not has_repair:
        return "DIAGNOSIS"
    return "GENERAL/AMBIGUOUS"

def classify_candidate_content(doc: dict, df_by_id: dict) -> str:
    """Xác định nội dung candidate thiên về DIAGNOSIS hay REPAIR dựa trên trường dữ liệu có sẵn."""
    qid = doc.get("question_id")
    row = df_by_id.get(qid)
    
    ans_text = doc.get("answer", "")
    q_text = doc.get("question", "")

    # 1. Nếu có trường Nguyên_nhân và Cách_khắc_phục rõ ràng trong dataset
    if row is not None:
        cause = str(row.get("Nguyên_nhân", ""))
        fix = str(row.get("Cách_khắc_phục", ""))
        if fix != "nan" and fix.strip() and (cause == "nan" or not cause.strip()):
            return "REPAIR"
        if cause != "nan" and cause.strip() and (fix == "nan" or not fix.strip()):
            return "DIAGNOSIS"

    # 2. Phân tích nội dung text câu trả lời (Action-oriented vs Descriptive)
    # Từ khóa hướng dẫn hành động kỹ thuật
    action_words = ["kiểm tra", "thay mới", "thay thế", "vệ sinh", "nhấn và giữ", "gọi thợ", "liên hệ", "lau sạch", "tắt nguồn", "khởi động lại", "cắm lại"]
    diag_words = ["nguyên nhân do", "là hiện tượng", "bảo vệ dòng", "quá tải", "hỏng bo mạch", "cảm biến bị", "nhiệt độ quá cao"]

    ans_low = ans_text.lower()
    has_action = any(w in ans_low for w in action_words)
    has_diag = any(w in ans_low for w in diag_words)

    if has_action and not has_diag:
        return "REPAIR"
    if has_diag and not has_action:
        return "DIAGNOSIS"
    return "GENERAL/AMBIGUOUS"

def rerank_with_intent(query: str, candidates: list[dict], exact_bonus: float, intent_bonus: float, df_by_id: dict) -> list[dict]:
    if not candidates:
        return []

    entities = extract_question_entities(query)
    target_brand = entities.get("brand")
    target_device = entities.get("device")
    target_error_code = entities.get("error_code")
    query_intent = classify_query_intent(query)

    b_bonus = 0.08
    d_bonus = 0.08
    e_bonus = 0.20
    both_bonus = 0.02

    scored = []
    for item in candidates:
        dist = item.get("distance")
        semantic_score = max(0.0, 1.0 - float(dist)) if dist is not None else 0.0
        score = semantic_score

        item_brand = item.get("brand", "")
        item_device = item.get("device", "")
        item_code = item.get("error_code", "")
        item_q = item.get("question", "")

        if target_brand and item_brand and target_brand.lower() == item_brand.lower():
            score += b_bonus
        if target_device and item_device and target_device.lower() == item_device.lower():
            score += d_bonus
        if target_error_code and item_code and target_error_code.lower() == item_code.lower():
            score += e_bonus
        if item.get("retrieval_source") == "both":
            score += both_bonus
        if exact_bonus > 0.0 and is_exact_question_match(query, item_q):
            score += exact_bonus

        # Intent bonus: chỉ cộng khi query intent rõ ràng VÀ candidate content khớp ý định
        if intent_bonus > 0.0 and query_intent in ("DIAGNOSIS", "REPAIR"):
            cand_content_type = classify_candidate_content(item, df_by_id)
            if query_intent == cand_content_type:
                score += intent_bonus

        item_copy = dict(item)
        item_copy["rerank_score"] = round(score, 4)
        scored.append((score, item_copy))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [x[1] for x in scored]

def evaluate_intent_on_set(dataset, pool_k: int, exact_bonus: float, intent_bonus: float, chroma_col, neo_driver, df_by_id: dict):
    from scripts.benchmark_phase2_configurations import retrieve_candidate_pool
    hit1, hit3, hit5 = 0, 0, 0
    total_mrr = 0.0
    latencies = []
    n = len(dataset)

    for item in dataset:
        q = item.get("question") or item.get("query")
        exp = item.get("expected_primary_id") or item.get("question_id")
        cand, base_lat = retrieve_candidate_pool(q, pool_k, chroma_col, neo_driver)

        t0 = time.perf_counter()
        ranked = rerank_with_intent(q, cand, exact_bonus, intent_bonus, df_by_id)[:5]
        lat = base_lat + (time.perf_counter() - t0) * 1000.0
        latencies.append(lat)

        ids = [d["question_id"] for d in ranked]
        h1 = calculate_hit_at_k(ids, exp, 1)
        h3 = calculate_hit_at_k(ids, exp, 3)
        h5 = calculate_hit_at_k(ids, exp, 5)
        rr = calculate_mrr(ids, exp, 5)

        if h1: hit1 += 1
        if h3: hit3 += 1
        if h5: hit5 += 1
        total_mrr += rr

    return {
        "hit@1": round(hit1 / n * 100.0, 2),
        "hit@3": round(hit3 / n * 100.0, 2),
        "hit@5": round(hit5 / n * 100.0, 2),
        "mrr": round(total_mrr / n, 4),
        "avg_latency_ms": round(sum(latencies) / n, 2),
    }

def main():
    chroma_col = get_or_create_collection()
    neo_driver = get_neo4j_driver()
    df = pd.read_excel('data/raw/dataset.xlsx', sheet_name='DATA_CLEAN_TECH')
    df_by_id = {str(row['ID']).strip(): row for _, row in df.iterrows()}

    print("=== 1. THỬ NGHIỆM INTENT RERANKING TRÊN DEVELOPMENT SET (100 câu) ===")
    dev_100 = load_evaluation_set("data/evaluation/reranking_dev_100.json")

    # Kiểm tra phân bố intent trên dev
    intent_counts = {}
    for item in dev_100:
        intent = classify_query_intent(item["question"])
        intent_counts[intent] = intent_counts.get(intent, 0) + 1
    print(f"Phân bố ý định trên Dev 100: {intent_counts}")

    for ib in [0.0, 0.01, 0.02, 0.03]:
        res = evaluate_intent_on_set(dev_100, pool_k=10, exact_bonus=0.02, intent_bonus=ib, chroma_col=chroma_col, neo_driver=neo_driver, df_by_id=df_by_id)
        print(f"  Dev (Pool=10, Exact=0.02, Intent={ib:<4}): Hit@1 = {res['hit@1']}% | Hit@3 = {res['hit@3']}% | MRR = {res['mrr']} | Latency = {res['avg_latency_ms']} ms")

    print("\n=== 2. KIỂM TRA PHÂN BỐ Ý ĐỊNH TRÊN EVALUATION SET (200 câu) & INDEPENDENT (60 câu) ===")
    eval_200 = load_evaluation_set("data/evaluation/evaluation_set_200.json")
    indep_60 = load_evaluation_set("data/evaluation/independent_eval_60.json")

    intent_eval200 = {}
    for item in eval_200:
        it = classify_query_intent(item["question"])
        intent_eval200[it] = intent_eval200.get(it, 0) + 1
    print(f"Phân bố ý định trên Eval 200: {intent_eval200}")

    intent_indep60 = {}
    for item in indep_60:
        it = classify_query_intent(item["query"])
        intent_indep60[it] = intent_indep60.get(it, 0) + 1
    print(f"Phân bố ý định trên Indep 60: {intent_indep60}")

    # Chạy trên Indep 60 để kiểm tra tác động
    print("\n=== 3. KẾT QUẢ TRÊN BỘ KIỂM THỬ ĐỘC LẬP (independent_eval_60.json) ===")
    from scripts.benchmark_phase2_configurations import retrieve_candidate_pool
    for ib in [0.0, 0.01, 0.02]:
        strict_h1 = 0
        cluster_h1 = 0
        h3, h5 = 0, 0
        total_mrr = 0.0
        n_ind = len(indep_60)

        for item in indep_60:
            q = item["query"]
            primary_id = item["expected_primary_id"]
            all_valid_ids = set(item.get("equivalent_ids", [])).union({primary_id})
            cand, _ = retrieve_candidate_pool(q, pool_size=10, chroma_col=chroma_col, neo_driver=neo_driver)
            ranked = rerank_with_intent(q, cand, exact_bonus=0.02, intent_bonus=ib, df_by_id=df_by_id)[:5]
            ids = [d["question_id"] for d in ranked]
            top1 = ids[0] if ids else ""

            if top1 == primary_id: strict_h1 += 1
            if top1 in all_valid_ids: cluster_h1 += 1
            if any(rid in all_valid_ids for rid in ids[:3]): h3 += 1
            if any(rid in all_valid_ids for rid in ids[:5]): h5 += 1
            rr = 0.0
            for r_idx, rid in enumerate(ids[:5], 1):
                if rid in all_valid_ids:
                    rr = 1.0 / r_idx
                    break
            total_mrr += rr

        print(f"  Indep (Pool=10, Intent={ib:<4}): Strict Hit@1 = {strict_h1/n_ind*100:.1f}% ({strict_h1}/{n_ind}) | Cluster Hit@1 = {cluster_h1/n_ind*100:.1f}% ({cluster_h1}/{n_ind}) | Hit@3 = {h3/n_ind*100:.1f}% | MRR = {total_mrr/n_ind:.4f}")

if __name__ == "__main__":
    main()

import json
import sys
import time
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
    rerank_results,
    is_exact_question_match,
)

def retrieve_candidate_pool(query: str, pool_size: int, chroma_col, neo_driver) -> tuple[list[dict], float]:
    """Truy van pool ung vien tu ChromaDB va Neo4j voi so luong pool_size (5 hoac 10)."""
    t0 = time.perf_counter()
    entities = extract_question_entities(query)
    brand = entities["brand"]
    device = entities["device"]

    active_where = build_chroma_where_filter(brand=brand, device=device)
    chroma_raw = search_similar_documents(
        query,
        k=pool_size,
        collection=chroma_col,
        where=active_where,
    )
    chroma_items: list[dict] = []
    for r in chroma_raw:
        meta = r.get("metadata", {})
        doc_text = r.get("document", "")
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
            "metadata": meta,
        })

    neo4j_items = search_graph(query, k=pool_size, driver=neo_driver)

    combined: dict[str, dict] = {}
    for item in chroma_items:
        combined[item["question_id"]] = item

    for item in neo4j_items:
        qid = item["question_id"]
        if qid in combined:
            combined[qid]["retrieval_source"] = "both"
            if not combined[qid]["answer"] and item.get("answer"):
                combined[qid]["answer"] = item["answer"]
        else:
            combined[qid] = item

    filtered: list[dict] = []
    for item in combined.values():
        item_brand = item.get("brand", "")
        item_device = item.get("device", "")
        if brand and item_brand and item_brand.lower() != brand.lower():
            continue
        if device and item_device and item_device.lower() != device.lower():
            continue
        filtered.append(item)

    lat = (time.perf_counter() - t0) * 1000.0
    return filtered, lat

def rerank_custom(query: str, candidates: list[dict], exact_bonus: float) -> tuple[list[dict], float]:
    """Rerank candidates voi exact_question_bonus tuỳ chon (0.00 hoac 0.02)."""
    t0 = time.perf_counter()
    if not candidates:
        return [], 0.0

    entities = extract_question_entities(query)
    target_brand = entities.get("brand")
    target_device = entities.get("device")
    target_error_code = entities.get("error_code")

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

        applied = {"semantic": round(semantic_score, 4)}

        if target_brand and item_brand and target_brand.lower() == item_brand.lower():
            score += b_bonus
            applied["brand"] = b_bonus
        if target_device and item_device and target_device.lower() == item_device.lower():
            score += d_bonus
            applied["device"] = d_bonus
        if target_error_code and item_code and target_error_code.lower() == item_code.lower():
            score += e_bonus
            applied["error_code"] = e_bonus
        if item.get("retrieval_source") == "both":
            score += both_bonus
            applied["both"] = both_bonus

        is_exact = is_exact_question_match(query, item_q)
        if exact_bonus > 0.0 and is_exact:
            score += exact_bonus
            applied["exact_question"] = exact_bonus

        item_copy = dict(item)
        item_copy["rerank_score"] = round(score, 4)
        item_copy["applied_bonuses"] = applied
        scored.append((score, item_copy))

    scored.sort(key=lambda x: x[0], reverse=True)
    lat = (time.perf_counter() - t0) * 1000.0
    return [x[1] for x in scored], lat

def main():
    eval_200 = load_evaluation_set("data/evaluation/evaluation_set_200.json")
    chroma_col = get_or_create_collection()
    neo_driver = get_neo4j_driver()

    df = pd.read_excel('data/raw/dataset.xlsx', sheet_name='DATA_CLEAN_TECH')
    df_by_id = {str(row['ID']).strip(): row for _, row in df.iterrows()}

    print(f"Loaded {len(eval_200)} queries from evaluation_set_200.json\n")

    # 1. Thu thap candidate pool cho ca pool_k=5 va pool_k=10
    print("Pre-fetching candidate pools for pool_k=5 and pool_k=10...")
    pools_5 = []
    pools_10 = []

    for item in eval_200:
        q = item["question"]
        cand5, lat5 = retrieve_candidate_pool(q, 5, chroma_col, neo_driver)
        cand10, lat10 = retrieve_candidate_pool(q, 10, chroma_col, neo_driver)
        pools_5.append({"item": item, "candidates": cand5, "retrieval_lat": lat5})
        pools_10.append({"item": item, "candidates": cand10, "retrieval_lat": lat10})

    configs = [
        {"name": "A (Pool=5, Bonus=0.00)", "pool_k": 5, "bonus": 0.00, "pools": pools_5},
        {"name": "B (Pool=5, Bonus=0.02 - Prod)", "pool_k": 5, "bonus": 0.02, "pools": pools_5},
        {"name": "C (Pool=10, Bonus=0.00)", "pool_k": 10, "bonus": 0.00, "pools": pools_10},
        {"name": "D (Pool=10, Bonus=0.02)", "pool_k": 10, "bonus": 0.02, "pools": pools_10},
    ]

    all_results = {}
    n = len(eval_200)

    for cfg in configs:
        name = cfg["name"]
        bonus = cfg["bonus"]
        pools = cfg["pools"]

        h1, h3, h5 = 0, 0, 0
        total_mrr = 0.0
        candidate_recalls = 0
        latencies = []
        failures = []
        details = []

        for p in pools:
            item = p["item"]
            q = item["question"]
            exp = item["question_id"]
            cand = p["candidates"]
            base_lat = p["retrieval_lat"]

            # Kiem tra candidate recall (truoc reranking)
            cand_ids = [d["question_id"] for d in cand]
            in_candidate_pool = exp in cand_ids
            if in_candidate_pool:
                candidate_recalls += 1

            # Rerank va lay top 5 cuoi cung
            ranked, rerank_lat = rerank_custom(q, cand, exact_bonus=bonus)
            final_top5 = ranked[:5]
            top_ids = [d["question_id"] for d in final_top5]
            top1_id = top_ids[0] if top_ids else ""

            total_lat = base_lat + rerank_lat
            latencies.append(total_lat)

            is_h1 = (top1_id == exp)
            is_h3 = exp in top_ids[:3]
            is_h5 = exp in top_ids[:5]
            rr = calculate_mrr(top_ids, exp, 5)

            if is_h1: h1 += 1
            if is_h3: h3 += 1
            if is_h5: h5 += 1
            total_mrr += rr

            if not is_h1:
                # Phan biet ro Candidate Retrieval Error vs Reranker Error
                error_type = "CANDIDATE_RECALL_ERROR" if not in_candidate_pool else "RERANKER_RANKING_ERROR"
                exp_rank = top_ids.index(exp) + 1 if exp in top_ids else (cand_ids.index(exp) + 1 if in_candidate_pool else ">pool")
                failures.append({
                    "question_id": exp,
                    "query": q,
                    "top1_id": top1_id,
                    "in_candidate_pool": in_candidate_pool,
                    "error_type": error_type,
                    "expected_rank_final": exp_rank,
                    "candidate_pool_size": len(cand),
                })

            details.append({
                "question_id": exp,
                "top1_id": top1_id,
                "in_candidate_pool": in_candidate_pool,
                "is_h1": is_h1,
                "top_ids": top_ids,
            })

        all_results[name] = {
            "name": name,
            "pool_k": cfg["pool_k"],
            "bonus": bonus,
            "hit@1": round(h1 / n * 100.0, 2),
            "hit@1_count": h1,
            "hit@3": round(h3 / n * 100.0, 2),
            "hit@3_count": h3,
            "hit@5": round(h5 / n * 100.0, 2),
            "hit@5_count": h5,
            "mrr": round(total_mrr / n, 4),
            "candidate_recall": round(candidate_recalls / n * 100.0, 2),
            "candidate_recall_count": candidate_recalls,
            "avg_latency_ms": round(sum(latencies) / n, 2),
            "failures_count": len(failures),
            "failures": failures,
            "details": details,
        }

    # In bang ket qua so sanh
    print("="*95)
    print("GIAI ĐOẠN 2 — KẾT QUẢ SO SÁNH 4 CẤU HÌNH TRÊN EVALUATION SET (200 CÂU)")
    print("="*95)
    print(f"{'Cấu hình':<30} | {'Candidate Recall':<18} | {'Hit@1':<12} | {'Hit@3':<10} | {'Hit@5':<10} | {'MRR':<8} | {'Latency'}")
    print("-" * 95)
    for name, r in all_results.items():
        print(f"{name:<30} | {r['candidate_recall']:>5.1f}% ({r['candidate_recall_count']:>3}/200) | {r['hit@1']:>5.1f}% ({r['hit@1_count']:>3}) | {r['hit@3']:>5.1f}% | {r['hit@5']:>5.1f}% | {r['mrr']:>6.4f} | {r['avg_latency_ms']:>6.2f} ms")
    print("="*95)

    # Phan tich rieng Q0535 tren ca 4 cau hinh
    print("\n=== PHÂN TÍCH RIÊNG TRƯỜNG HỢP Q0535 ('Máy giặt không xả nước phải làm sao?') ===")
    for name, r in all_results.items():
        q0535_res = next((d for d in r["details"] if d["question_id"] == "Q0535"), None)
        f_info = next((f for f in r["failures"] if f["question_id"] == "Q0535"), None)
        if q0535_res:
            in_pool = q0535_res["in_candidate_pool"]
            top1 = q0535_res["top1_id"]
            status = "HIT@1 SUCCESS" if q0535_res["is_h1"] else f"FAIL (Top1={top1}, Type={f_info['error_type'] if f_info else 'N/A'})"
            print(f"  [{name}]: In Candidate Pool? {in_pool} -> {status} (Top-5: {q0535_res['top_ids']})")

    # Phan tich cac loi cua cau hinh D
    print(f"\n=== DANH SÁCH TOÀN BỘ {all_results['D (Pool=10, Bonus=0.02)']['failures_count']} LỖI TOP-1 CỦA CẤU HÌNH D (Pool=10, Bonus=0.02) ===")
    for idx, f in enumerate(all_results['D (Pool=10, Bonus=0.02)']['failures'], 1):
        print(f"  #{idx:<2} Exp: {f['question_id']} | Top1: {f['top1_id']} | In Pool? {f['in_candidate_pool']} | Type: {f['error_type']} | Query: '{f['query']}'")

    out_file = "data/evaluation/phase2_configurations_results.json"
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(all_results, f, ensure_ascii=False, indent=2)
    print(f"\nSaved phase 2 results to {out_file}")

if __name__ == "__main__":
    main()

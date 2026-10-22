import json
import re
import sys
import time
import unicodedata
from difflib import SequenceMatcher
from pathlib import Path

sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, ".")

from rag_chatbot.chroma_db import get_or_create_collection
from rag_chatbot.neo4j_db import get_neo4j_driver
from rag_chatbot.retrieval import search_hybrid, extract_question_entities
from scripts.ablation_dev_weights import normalize_vietnamese_text, calculate_q2q_sim, rerank_with_q2q

def main():
    test_path = Path("data/evaluation/independent_eval_60.json")
    with open(test_path, "r", encoding="utf-8") as f:
        test_queries = json.load(f)

    chroma_col = get_or_create_collection()
    neo_driver = get_neo4j_driver()

    print(f"=== TẢI CANDIDATE POOLS CHO BỘ KIỂM THỬ ĐỘC LẬP ({len(test_queries)} câu) ===")
    pools = []
    t0 = time.perf_counter()
    for item in test_queries:
        q = item["query"]
        ent = extract_question_entities(q)
        t_start = time.perf_counter()
        raw_res = search_hybrid(
            q, k=10, chroma_collection=chroma_col, neo4j_driver=neo_driver, use_reranking=False
        )
        lat = (time.perf_counter() - t_start) * 1000.0
        pools.append({
            "item": item,
            "entities": ent,
            "raw_candidates": raw_res,
            "retrieval_lat_ms": lat
        })
    print(f"Tải xong candidate pools trong {time.perf_counter() - t0:.2f}s (TB {sum(p['retrieval_lat_ms'] for p in pools)/len(pools):.2f} ms/câu)")

    weights = [0.0, 0.02, 0.04, 0.06]
    all_eval_results = []

    print("\n=== KẾT QUẢ TRÊN BỘ KIỂM THỬ ĐỘC LẬP (60 CÂU) ===")
    print(f"{'Cấu hình':<22} | {'Strict Hit@1':<12} | {'Cluster Hit@1':<13} | {'Hit@3':<8} | {'Hit@5':<8} | {'MRR':<8} | {'Độ trễ'}")
    print("-" * 90)

    for w in weights:
        strict_h1 = 0
        cluster_h1 = 0
        h3 = 0
        h5 = 0
        total_mrr = 0.0
        latencies = []
        n = len(pools)

        category_stats = {}

        for p in pools:
            item = p["item"]
            q = item["query"]
            primary_id = item["expected_primary_id"]
            equiv_ids = set(item.get("equivalent_ids", []))
            all_valid_ids = equiv_ids.union({primary_id})
            cat = item.get("category", "OTHER")

            ent = p["entities"]
            cand = p["raw_candidates"]
            base_lat = p["retrieval_lat_ms"]

            t_rerank = time.perf_counter()
            ranked = rerank_with_q2q(q, cand, ent, w_q2q=w)[:5]
            rerank_lat = (time.perf_counter() - t_rerank) * 1000.0
            latencies.append(base_lat + rerank_lat)

            retrieved_ids = [d["question_id"] for d in ranked]
            top1_id = retrieved_ids[0] if retrieved_ids else ""

            # 1. Strict exact Hit@1
            is_strict_h1 = (top1_id == primary_id)
            if is_strict_h1:
                strict_h1 += 1

            # 2. Cluster / Knowledge-aware Hit@1 (chấp nhận cả primary và equivalent)
            is_cluster_h1 = (top1_id in all_valid_ids)
            if is_cluster_h1:
                cluster_h1 += 1

            # 3. Hit@3, Hit@5, MRR (dựa trên cluster tri thức tương đương)
            is_h3 = any(rid in all_valid_ids for rid in retrieved_ids[:3])
            is_h5 = any(rid in all_valid_ids for rid in retrieved_ids[:5])
            if is_h3: h3 += 1
            if is_h5: h5 += 1

            # Reciprocal rank
            rr = 0.0
            for rank_idx, rid in enumerate(retrieved_ids[:5], 1):
                if rid in all_valid_ids:
                    rr = 1.0 / rank_idx
                    break
            total_mrr += rr

            # Categorical breakdown
            if cat not in category_stats:
                category_stats[cat] = {"total": 0, "cluster_h1": 0, "strict_h1": 0}
            category_stats[cat]["total"] += 1
            if is_strict_h1: category_stats[cat]["strict_h1"] += 1
            if is_cluster_h1: category_stats[cat]["cluster_h1"] += 1

        label = f"Baseline (w=0.00)" if w == 0.0 else f"Q2Q w={w:.2f}"
        s_rate = strict_h1 / n * 100.0
        c_rate = cluster_h1 / n * 100.0
        h3_rate = h3 / n * 100.0
        h5_rate = h5 / n * 100.0
        mrr_val = total_mrr / n
        avg_lat = sum(latencies) / n

        print(f"{label:<22} | {s_rate:<5.1f}% ({strict_h1:>2}/{n}) | {c_rate:<5.1f}% ({cluster_h1:>2}/{n}) | {h3_rate:<5.1f}% | {h5_rate:<5.1f}% | {mrr_val:<6.4f} | {avg_lat:.2f} ms")

        all_eval_results.append({
            "weight": w,
            "label": label,
            "strict_hit1": round(s_rate, 2),
            "cluster_hit1": round(c_rate, 2),
            "hit3": round(h3_rate, 2),
            "hit5": round(h5_rate, 2),
            "mrr": round(mrr_val, 4),
            "avg_latency_ms": round(avg_lat, 2),
            "by_category": {
                c: {
                    "total": data["total"],
                    "strict_hit1_rate": round(data["strict_h1"] / data["total"] * 100.0, 1),
                    "cluster_hit1_rate": round(data["cluster_h1"] / data["total"] * 100.0, 1)
                }
                for c, data in category_stats.items()
            }
        })

    with open("data/evaluation/independent_eval_results.json", "w", encoding="utf-8") as f:
        json.dump(all_eval_results, f, ensure_ascii=False, indent=2)
    print("\nSaved detailed independent results to data/evaluation/independent_eval_results.json")

if __name__ == '__main__':
    main()

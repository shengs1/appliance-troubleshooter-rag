import json
import re
import sys
import time
import unicodedata
from pathlib import Path

sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, ".")

from rag_chatbot.chroma_db import get_or_create_collection
from rag_chatbot.neo4j_db import get_neo4j_driver
from rag_chatbot.retrieval import search_hybrid, extract_question_entities
from scripts.test_exact_question_bonus import (
    normalize_question_text,
    is_exact_question_match,
    rerank_with_exact_bonus,
)

def main():
    test_path = Path("data/evaluation/independent_eval_60.json")
    if not test_path.exists():
        print(f"Error: {test_path} does not exist!")
        return

    with open(test_path, "r", encoding="utf-8") as f:
        test_queries = json.load(f)

    chroma_col = get_or_create_collection()
    neo_driver = get_neo4j_driver()

    print(f"Loaded {len(test_queries)} queries from independent_eval_60.json")

    # 1. Warm-up and retrieve candidate pool
    print("Retrieving candidates for all 60 queries...")
    pools = []
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

    weights = [0.0, 0.02]
    config_results = {}
    ranked_by_config = {}

    for bw in weights:
        exact_h1 = 0
        cluster_h1 = 0
        h3 = 0
        h5 = 0
        total_mrr_cluster = 0.0
        total_mrr_exact = 0.0
        latencies = []
        n = len(pools)
        category_stats = {}
        all_ranked = []

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

            t0 = time.perf_counter()
            ranked = rerank_with_exact_bonus(q, cand, ent, exact_match_bonus=bw)[:5]
            rerank_lat = (time.perf_counter() - t0) * 1000.0
            latencies.append(base_lat + rerank_lat)

            retrieved_ids = [d["question_id"] for d in ranked]
            top1_id = retrieved_ids[0] if retrieved_ids else ""

            is_exact_h1 = (top1_id == primary_id)
            is_cluster_h1 = (top1_id in all_valid_ids)
            is_h3 = any(rid in all_valid_ids for rid in retrieved_ids[:3])
            is_h5 = any(rid in all_valid_ids for rid in retrieved_ids[:5])

            if is_exact_h1: exact_h1 += 1
            if is_cluster_h1: cluster_h1 += 1
            if is_h3: h3 += 1
            if is_h5: h5 += 1

            # MRR Cluster
            rr_cluster = 0.0
            for r_idx, rid in enumerate(retrieved_ids[:5], 1):
                if rid in all_valid_ids:
                    rr_cluster = 1.0 / r_idx
                    break
            total_mrr_cluster += rr_cluster

            # MRR Exact
            rr_exact = 0.0
            for r_idx, rid in enumerate(retrieved_ids[:5], 1):
                if rid == primary_id:
                    rr_exact = 1.0 / r_idx
                    break
            total_mrr_exact += rr_exact

            # By category
            if cat not in category_stats:
                category_stats[cat] = {"total": 0, "exact_h1": 0, "cluster_h1": 0}
            category_stats[cat]["total"] += 1
            if is_exact_h1: category_stats[cat]["exact_h1"] += 1
            if is_cluster_h1: category_stats[cat]["cluster_h1"] += 1

            # Check if any candidate got exact match bonus
            exact_matches_in_cand = [
                d["question_id"] for d in ranked
                if is_exact_question_match(q, d.get("question", ""))
            ]

            all_ranked.append({
                "id": item["id"],
                "query": q,
                "category": cat,
                "expected_primary_id": primary_id,
                "equivalent_ids": list(equiv_ids),
                "top1_id": top1_id,
                "retrieved_ids": retrieved_ids,
                "is_exact_h1": is_exact_h1,
                "is_cluster_h1": is_cluster_h1,
                "exact_matches_in_cand": exact_matches_in_cand,
                "ranked_candidates": ranked,
            })

        label = "Baseline (bonus=0.0)" if bw == 0.0 else "Bonus = 0.02"
        config_results[bw] = {
            "label": label,
            "exact_hit1": round(exact_h1 / n * 100.0, 2),
            "exact_hit1_count": exact_h1,
            "cluster_hit1": round(cluster_h1 / n * 100.0, 2),
            "cluster_hit1_count": cluster_h1,
            "hit3": round(h3 / n * 100.0, 2),
            "hit3_count": h3,
            "hit5": round(h5 / n * 100.0, 2),
            "hit5_count": h5,
            "mrr_cluster": round(total_mrr_cluster / n, 4),
            "mrr_exact": round(total_mrr_exact / n, 4),
            "avg_latency_ms": round(sum(latencies) / n, 2),
            "by_category": {
                c: {
                    "total": d["total"],
                    "exact_h1_rate": round(d["exact_h1"] / d["total"] * 100.0, 1),
                    "cluster_h1_rate": round(d["cluster_h1"] / d["total"] * 100.0, 1)
                }
                for c, d in category_stats.items()
            }
        }
        ranked_by_config[bw] = all_ranked

    print("\n" + "="*80)
    print("BENCHMARK COMPARISON ON INDEPENDENT EVAL SET (60 CÂU)")
    print("="*80)
    print(f"{'Metric':<25} | {'Baseline (bonus=0.0)':<22} | {'Bonus = 0.02':<22} | {'Độ lệch (Delta)'}")
    print("-" * 80)
    b0 = config_results[0.0]
    b2 = config_results[0.02]

    metrics = [
        ("Exact-ID Hit@1", f"{b0['exact_hit1']}% ({b0['exact_hit1_count']}/60)", f"{b2['exact_hit1']}% ({b2['exact_hit1_count']}/60)", f"{b2['exact_hit1'] - b0['exact_hit1']:+.2f}%"),
        ("Cluster Hit@1", f"{b0['cluster_hit1']}% ({b0['cluster_hit1_count']}/60)", f"{b2['cluster_hit1']}% ({b2['cluster_hit1_count']}/60)", f"{b2['cluster_hit1'] - b0['cluster_hit1']:+.2f}%"),
        ("Hit@3", f"{b0['hit3']}% ({b0['hit3_count']}/60)", f"{b2['hit3']}% ({b2['hit3_count']}/60)", f"{b2['hit3'] - b0['hit3']:+.2f}%"),
        ("Hit@5", f"{b0['hit5']}% ({b0['hit5_count']}/60)", f"{b2['hit5']}% ({b2['hit5_count']}/60)", f"{b2['hit5'] - b0['hit5']:+.2f}%"),
        ("MRR (Cluster-aware)", f"{b0['mrr_cluster']:.4f}", f"{b2['mrr_cluster']:.4f}", f"{b2['mrr_cluster'] - b0['mrr_cluster']:+.4f}"),
        ("MRR (Exact-ID)", f"{b0['mrr_exact']:.4f}", f"{b2['mrr_exact']:.4f}", f"{b2['mrr_exact'] - b0['mrr_exact']:+.4f}"),
        ("Avg Latency", f"{b0['avg_latency_ms']:.2f} ms", f"{b2['avg_latency_ms']:.2f} ms", f"{b2['avg_latency_ms'] - b0['avg_latency_ms']:+.2f} ms"),
    ]
    for name, v0, v2, diff in metrics:
        print(f"{name:<25} | {v0:<22} | {v2:<22} | {diff}")

    print("\n" + "="*80)
    print("KIỂM TRA CÁC CÂU CÓ THAY ĐỔI (DIFF CHECK)")
    print("="*80)

    changed_top1 = []
    changed_ranks = []
    bonus_triggered_queries = []

    for r0, r2 in zip(ranked_by_config[0.0], ranked_by_config[0.02]):
        q_id = r0["id"]
        query = r0["query"]
        if r0["top1_id"] != r2["top1_id"]:
            changed_top1.append({
                "id": q_id,
                "query": query,
                "base_top1": r0["top1_id"],
                "bonus_top1": r2["top1_id"],
                "base_cluster_h1": r0["is_cluster_h1"],
                "bonus_cluster_h1": r2["is_cluster_h1"],
            })
        if r0["retrieved_ids"] != r2["retrieved_ids"]:
            changed_ranks.append({
                "id": q_id,
                "query": query,
                "base_ids": r0["retrieved_ids"],
                "bonus_ids": r2["retrieved_ids"],
            })
        if r2["exact_matches_in_cand"]:
            bonus_triggered_queries.append({
                "id": q_id,
                "query": query,
                "matches": r2["exact_matches_in_cand"]
            })

    print(f"Số câu thay đổi Top-1 ID:        {len(changed_top1)}")
    print(f"Số câu thay đổi thứ tự Top-5:    {len(changed_ranks)}")
    print(f"Số câu kích hoạt exact match:    {len(bonus_triggered_queries)}")

    if changed_top1:
        print("\nChi tiết các câu thay đổi Top-1:")
        for ch in changed_top1:
            print(f"  - [{ch['id']}] '{ch['query']}'")
            print(f"    Baseline: Top1={ch['base_top1']} (ClusterHit1={ch['base_cluster_h1']})")
            print(f"    Bonus 0.02: Top1={ch['bonus_top1']} (ClusterHit1={ch['bonus_cluster_h1']})")
    else:
        print("-> KHÔNG có bất kỳ câu nào bị thay đổi Top-1!")

    if changed_ranks:
        print("\nChi tiết các câu thay đổi thứ tự Top-5:")
        for ch in changed_ranks:
            print(f"  - [{ch['id']}] '{ch['query']}': {ch['base_ids']} -> {ch['bonus_ids']}")
    else:
        print("-> KHÔNG có bất kỳ câu nào bị thay đổi thứ tự xếp hạng trong Top-5!")

    # Breakdown by category
    print("\n" + "="*80)
    print("PHÂN TÍCH THEO DANH MỤC CÂU HỎI (CATEGORY BREAKDOWN)")
    print("="*80)
    for cat in b0["by_category"]:
        c0 = b0["by_category"][cat]
        c2 = b2["by_category"][cat]
        print(f"[{cat}] (Total: {c0['total']} câu):")
        print(f"  Cluster Hit@1: Baseline = {c0['cluster_h1_rate']}% | Bonus 0.02 = {c2['cluster_h1_rate']}%")
        print(f"  Exact Hit@1:   Baseline = {c0['exact_h1_rate']}% | Bonus 0.02 = {c2['exact_h1_rate']}%")

    out_file = "data/evaluation/independent_exact_bonus_results.json"
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump({
            "metrics": config_results,
            "changed_top1": changed_top1,
            "changed_ranks": changed_ranks,
            "bonus_triggered_queries": bonus_triggered_queries,
            "details": ranked_by_config[0.02]
        }, f, ensure_ascii=False, indent=2)
    print(f"\nSaved benchmark results to {out_file}")

if __name__ == "__main__":
    main()

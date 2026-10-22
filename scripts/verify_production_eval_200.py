import json
import sys
import time
from pathlib import Path

sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, ".")

from rag_chatbot.evaluation import load_evaluation_set, calculate_hit_at_k, calculate_mrr
from rag_chatbot.chroma_db import get_or_create_collection
from rag_chatbot.neo4j_db import get_neo4j_driver
from rag_chatbot.retrieval import search_hybrid

def main():
    eval_set_path = "data/evaluation/evaluation_set_200.json"
    eval_200 = load_evaluation_set(eval_set_path)
    chroma_col = get_or_create_collection()
    neo_driver = get_neo4j_driver()

    print(f"Running production search_hybrid on {len(eval_200)} queries...")

    # Warm-up
    _ = search_hybrid("Khởi động warm-up", k=5, chroma_collection=chroma_col, neo4j_driver=neo_driver)

    hit1, hit3, hit5 = 0, 0, 0
    total_mrr = 0.0
    latencies = []
    failures = []
    details = []

    for idx, item in enumerate(eval_200, 1):
        q = item["question"]
        exp = item["question_id"]

        t0 = time.perf_counter()
        results = search_hybrid(
            q,
            k=5,
            chroma_collection=chroma_col,
            neo4j_driver=neo_driver,
            use_reranking=True,
            rerank_mode="fixed"
        )
        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        latencies.append(elapsed_ms)

        retrieved_ids = [d["question_id"] for d in results]
        top1_id = retrieved_ids[0] if retrieved_ids else ""

        h1 = calculate_hit_at_k(retrieved_ids, exp, 1)
        h3 = calculate_hit_at_k(retrieved_ids, exp, 3)
        h5 = calculate_hit_at_k(retrieved_ids, exp, 5)
        rr = calculate_mrr(retrieved_ids, exp, 5)

        if h1: hit1 += 1
        if h3: hit3 += 1
        if h5: hit5 += 1
        total_mrr += rr

        if not h1:
            rank = retrieved_ids.index(exp) + 1 if exp in retrieved_ids else ">5"
            failures.append({
                "index": idx,
                "expected_id": exp,
                "predicted_top1_id": top1_id,
                "expected_rank": rank,
                "query": q,
                "retrieved_ids": retrieved_ids
            })

        details.append({
            "question_id": exp,
            "query": q,
            "top1_id": top1_id,
            "retrieved_ids": retrieved_ids,
            "hit1": h1,
            "hit3": h3,
            "hit5": h5,
            "mrr": rr,
            "latency_ms": round(elapsed_ms, 2)
        })

    n = len(eval_200)
    hit1_rate = round(hit1 / n * 100.0, 2)
    hit3_rate = round(hit3 / n * 100.0, 2)
    hit5_rate = round(hit5 / n * 100.0, 2)
    mrr_val = round(total_mrr / n, 4)
    avg_lat = round(sum(latencies) / n, 2)

    print("\n" + "="*80)
    print("PRODUCTION VERIFICATION RESULTS ON EVALUATION SET (200 CÂU)")
    print("="*80)
    print(f"Hit@1:          {hit1_rate}% ({hit1}/{n})")
    print(f"Hit@3:          {hit3_rate}% ({hit3}/{n})")
    print(f"Hit@5:          {hit5_rate}% ({hit5}/{n})")
    print(f"MRR:            {mrr_val}")
    print(f"Avg Latency:    {avg_lat} ms")
    print(f"Total Failures: {len(failures)}")
    print("="*80)

    print("\nDanh sách các ca thất bại Hit@1:")
    for f in failures:
        print(f"  - #{f['index']} Expected: {f['expected_id']} | Top-1: {f['predicted_top1_id']} | Rank: {f['expected_rank']} | Query: '{f['query']}'")

    out_path = "data/evaluation/post_integration_eval_200.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump({
            "metrics": {
                "hit1_rate": hit1_rate,
                "hit1_count": hit1,
                "hit3_rate": hit3_rate,
                "hit3_count": hit3,
                "hit5_rate": hit5_rate,
                "hit5_count": hit5,
                "mrr": mrr_val,
                "avg_latency_ms": avg_lat,
                "total_queries": n,
                "failures_count": len(failures)
            },
            "failures": failures,
            "details": details
        }, f, ensure_ascii=False, indent=2)
    print(f"\nSaved post-integration evaluation to {out_path}")

if __name__ == "__main__":
    main()

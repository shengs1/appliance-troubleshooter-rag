import json
import sys
import time
from pathlib import Path

sys.stdout.reconfigure(encoding='utf-8')

from rag_chatbot.chroma_db import get_or_create_collection
from rag_chatbot.neo4j_db import get_neo4j_driver
from rag_chatbot.retrieval import search_hybrid
from rag_chatbot.evaluation import calculate_hit_at_k, calculate_mrr

def main():
    with open('data/evaluation/evaluation_set_200.json', 'r', encoding='utf-8') as f:
        eval_200 = json.load(f)

    chroma_col = get_or_create_collection()
    neo_driver = get_neo4j_driver()

    print(f"Loaded {len(eval_200)} queries from evaluation_set_200.json")

    # Warm-up
    _ = search_hybrid("Khoi dong warm up", k=5, chroma_collection=chroma_col, neo4j_driver=neo_driver)

    modes = ["baseline_no_rerank", "fixed_rerank"]
    results = {}

    for mode in modes:
        use_rerank = (mode == "fixed_rerank")
        hit1, hit3, hit5 = 0, 0, 0
        total_mrr = 0.0
        latencies = []

        failures = []

        t_start = time.perf_counter()
        for idx, item in enumerate(eval_200):
            q = item['question']
            expected_id = item['question_id']

            t0 = time.perf_counter()
            docs = search_hybrid(
                q,
                k=5,
                chroma_collection=chroma_col,
                neo4j_driver=neo_driver,
                use_reranking=use_rerank,
                rerank_mode="fixed"
            )
            elapsed_ms = (time.perf_counter() - t0) * 1000.0
            latencies.append(elapsed_ms)

            retrieved_ids = [d['question_id'] for d in docs]
            h1 = calculate_hit_at_k(retrieved_ids, expected_id, 1)
            h3 = calculate_hit_at_k(retrieved_ids, expected_id, 3)
            h5 = calculate_hit_at_k(retrieved_ids, expected_id, 5)
            rr = calculate_mrr(retrieved_ids, expected_id, max_k=5)

            if h1: hit1 += 1
            if h3: hit3 += 1
            if h5: hit5 += 1
            total_mrr += rr

            if not h1:
                rank = None
                for r, rid in enumerate(retrieved_ids, 1):
                    if rid == expected_id:
                        rank = r
                        break
                failures.append({
                    "index": len(failures) + 1,
                    "question_id": expected_id,
                    "question": q,
                    "brand": item.get("brand"),
                    "device": item.get("device"),
                    "issue_type": item.get("issue_type"),
                    "error_code": item.get("error_code"),
                    "expected_rank": rank,
                    "top_docs": docs[:5]
                })

        total_time = time.perf_counter() - t_start
        n = len(eval_200)
        results[mode] = {
            "hit@1": round(hit1 / n * 100.0, 2),
            "hit@3": round(hit3 / n * 100.0, 2),
            "hit@5": round(hit5 / n * 100.0, 2),
            "mrr": round(total_mrr / n, 4),
            "avg_latency_ms": round(sum(latencies) / n, 2),
            "failures_count": len(failures),
            "failures": failures
        }
        print(f"[{mode:<20}] Hit@1: {results[mode]['hit@1']}% ({hit1}/{n}) | Hit@3: {results[mode]['hit@3']}% | Hit@5: {results[mode]['hit@5']}% | MRR: {results[mode]['mrr']} | Avg Latency: {results[mode]['avg_latency_ms']} ms | Failures: {len(failures)}")

    # Save detailed failure report for fixed_rerank
    with open('data/evaluation/current_run_failures_26.json', 'w', encoding='utf-8') as f:
        json.dump(results['fixed_rerank']['failures'], f, ensure_ascii=False, indent=2)
    print("Saved failures to data/evaluation/current_run_failures_26.json")

if __name__ == '__main__':
    main()

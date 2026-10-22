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

def test_fetch_k_impact(dev_path, indep_path):
    chroma_col = get_or_create_collection()
    neo_driver = get_neo4j_driver()

    dev_100 = load_evaluation_set(dev_path)
    indep_60 = load_evaluation_set(indep_path)

    print("=== TESTING IMPACT OF FETCH_K ON DEV 100 ===")
    for fk in [5, 10]:
        h1, h3, h5 = 0, 0, 0
        total_mrr = 0.0
        n = len(dev_100)
        for item in dev_100:
            q = item["question"]
            exp = item["question_id"]
            # To test fetch_k: we can temporarily test search_hybrid with k=5 vs k=10
            # Let's see: if candidate pool has 5 vs 10
            from scripts.benchmark_phase2_configurations import retrieve_candidate_pool, rerank_custom
            cand, _ = retrieve_candidate_pool(q, fk, chroma_col, neo_driver)
            ranked, _ = rerank_custom(q, cand, exact_bonus=0.02)
            top5 = [d["question_id"] for d in ranked[:5]]
            if calculate_hit_at_k(top5, exp, 1): h1 += 1
            if calculate_hit_at_k(top5, exp, 3): h3 += 1
            if calculate_hit_at_k(top5, exp, 5): h5 += 1
            total_mrr += calculate_mrr(top5, exp, 5)
        print(f"  Dev 100 (Candidate Pool = {fk:>2}): Hit@1 = {h1/n*100:.1f}% ({h1}/{n}) | Hit@3 = {h3/n*100:.1f}% | Hit@5 = {h5/n*100:.1f}% | MRR = {total_mrr/n:.4f}")

    print("\n=== TESTING IMPACT OF FETCH_K ON INDEPENDENT 60 ===")
    for fk in [5, 10]:
        strict_h1 = 0
        cluster_h1 = 0
        h3, h5 = 0, 0
        total_mrr = 0.0
        n_ind = len(indep_60)
        for item in indep_60:
            q = item["query"]
            primary_id = item["expected_primary_id"]
            valid_ids = set(item.get("equivalent_ids", [])).union({primary_id})
            from scripts.benchmark_phase2_configurations import retrieve_candidate_pool, rerank_custom
            cand, _ = retrieve_candidate_pool(q, fk, chroma_col, neo_driver)
            ranked, _ = rerank_custom(q, cand, exact_bonus=0.02)
            top5 = [d["question_id"] for d in ranked[:5]]
            if top5[0] == primary_id: strict_h1 += 1
            if top5[0] in valid_ids: cluster_h1 += 1
            if any(rid in valid_ids for rid in top5[:3]): h3 += 1
            if any(rid in valid_ids for rid in top5[:5]): h5 += 1
            rr = 0.0
            for r_idx, rid in enumerate(top5[:5], 1):
                if rid in valid_ids:
                    rr = 1.0 / r_idx
                    break
            total_mrr += rr
        print(f"  Indep 60 (Candidate Pool = {fk:>2}): Strict Hit@1 = {strict_h1/n_ind*100:.1f}% ({strict_h1}/{n_ind}) | Cluster Hit@1 = {cluster_h1/n_ind*100:.1f}% ({cluster_h1}/{n_ind}) | Hit@3 = {h3/n_ind*100:.1f}% | Hit@5 = {h5/n_ind*100:.1f}% | MRR = {total_mrr/n_ind:.4f}")

if __name__ == "__main__":
    test_fetch_k_impact("data/evaluation/reranking_dev_100.json", "data/evaluation/independent_eval_60.json")

import json
import sys
import time
from pathlib import Path

sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, ".")

from rag_chatbot.evaluation import load_evaluation_set, calculate_hit_at_k, calculate_mrr
from rag_chatbot.chroma_db import get_or_create_collection
from rag_chatbot.neo4j_db import get_neo4j_driver
from rag_chatbot.retrieval import search_hybrid, extract_question_entities
from scripts.experiment_lexical_dev import rerank_experiment

def main():
    eval_200 = load_evaluation_set("data/evaluation/evaluation_set_200.json")
    col = get_or_create_collection()
    driver = get_neo4j_driver()

    print(f"=== TESTING CANDIDATE STRATEGY (exp_B, w_q2q=0.04) ON EVAL 200 SET ({len(eval_200)} queries) ===")

    hit1_base, hit1_new = 0, 0
    hit3_base, hit3_new = 0, 0
    hit5_base, hit5_new = 0, 0
    mrr_base, mrr_new = 0.0, 0.0

    rescued = []
    regressed = []
    still_failed = []

    for item in eval_200:
        q = item["question"]
        exp = item["question_id"]
        ent = extract_question_entities(q)

        # Baseline search_hybrid (k=10 candidate pool)
        raw_res = search_hybrid(q, k=10, chroma_collection=col, neo4j_driver=driver, use_reranking=False)

        res_base = rerank_experiment(q, raw_res, ent, method="baseline")[:5]
        res_new = rerank_experiment(q, raw_res, ent, method="exp_B", weights={"w_q2q": 0.04})[:5]

        base_ids = [d["question_id"] for d in res_base]
        new_ids = [d["question_id"] for d in res_new]

        b_h1 = calculate_hit_at_k(base_ids, exp, 1)
        n_h1 = calculate_hit_at_k(new_ids, exp, 1)

        if b_h1: hit1_base += 1
        if calculate_hit_at_k(base_ids, exp, 3): hit3_base += 1
        if calculate_hit_at_k(base_ids, exp, 5): hit5_base += 1
        mrr_base += calculate_mrr(base_ids, exp, 5)

        if n_h1: hit1_new += 1
        if calculate_hit_at_k(new_ids, exp, 3): hit3_new += 1
        if calculate_hit_at_k(new_ids, exp, 5): hit5_new += 1
        mrr_new += calculate_mrr(new_ids, exp, 5)

        if not b_h1 and n_h1:
            rescued.append({"id": exp, "q": q, "base_top1": base_ids[0], "new_top1": new_ids[0]})
        elif b_h1 and not n_h1:
            regressed.append({"id": exp, "q": q, "base_top1": base_ids[0], "new_top1": new_ids[0]})
        elif not b_h1 and not n_h1:
            still_failed.append({"id": exp, "q": q, "top1": new_ids[0]})

    n = len(eval_200)
    print(f"\n[BASELINE (Fixed Rule-based)] Hit@1: {hit1_base/n*100.0:.2f}% | Hit@3: {hit3_base/n*100.0:.2f}% | Hit@5: {hit5_base/n*100.0:.2f}% | MRR: {mrr_base/n:.4f}")
    print(f"[EXP_B (Q2Q Matching 0.04)  ] Hit@1: {hit1_new/n*100.0:.2f}% | Hit@3: {hit3_new/n*100.0:.2f}% | Hit@5: {hit5_new/n*100.0:.2f}% | MRR: {mrr_new/n:.4f}")
    print(f"\nRescued queries ({len(rescued)}):")
    for r in rescued:
        print(f"  [+] {r['id']} | '{r['q']}' | Old Top1: {r['base_top1']} -> New Top1: {r['new_top1']}")

    print(f"\nRegressed queries ({len(regressed)}):")
    for r in regressed:
        print(f"  [-] {r['id']} | '{r['q']}'")

    print(f"\nStill failed queries ({len(still_failed)}):")
    for r in still_failed:
        print(f"  [x] {r['id']} | '{r['q']}' | Top1: {r['top1']}")

if __name__ == '__main__':
    main()

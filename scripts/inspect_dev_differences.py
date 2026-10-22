import json
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding='utf-8')

sys.path.insert(0, ".")
from rag_chatbot.evaluation import load_evaluation_set, calculate_hit_at_k
from scripts.experiment_lexical_dev import calculate_q2q_similarity, rerank_experiment

def main():
    dev_set = load_evaluation_set("data/evaluation/reranking_dev_100.json")
    from rag_chatbot.chroma_db import get_or_create_collection
    from rag_chatbot.neo4j_db import get_neo4j_driver
    from rag_chatbot.retrieval import search_hybrid, extract_question_entities

    col = get_or_create_collection()
    driver = get_neo4j_driver()

    rescued = []
    regressed = []
    still_failed = []

    for item in dev_set:
        q = item["question"]
        exp = item["question_id"]
        ent = extract_question_entities(q)
        raw_res = search_hybrid(q, k=10, chroma_collection=col, neo4j_driver=driver, use_reranking=False)

        res_base = rerank_experiment(q, raw_res, ent, method="baseline")[:5]
        res_b = rerank_experiment(q, raw_res, ent, method="exp_B", weights={"w_q2q": 0.04})[:5]

        base_ids = [d["question_id"] for d in res_base]
        b_ids = [d["question_id"] for d in res_b]

        base_hit1 = calculate_hit_at_k(base_ids, exp, 1)
        b_hit1 = calculate_hit_at_k(b_ids, exp, 1)

        if not base_hit1 and b_hit1:
            rescued.append({
                "id": exp,
                "query": q,
                "base_top1": base_ids[0],
                "new_top1": b_ids[0],
            })
        elif base_hit1 and not b_hit1:
            regressed.append({
                "id": exp,
                "query": q,
                "base_top1": base_ids[0],
                "new_top1": b_ids[0],
            })
        elif not base_hit1 and not b_hit1:
            still_failed.append({
                "id": exp,
                "query": q,
                "base_top1": base_ids[0],
                "new_top1": b_ids[0],
                "base_rank": base_ids.index(exp) + 1 if exp in base_ids else None,
                "new_rank": b_ids.index(exp) + 1 if exp in b_ids else None,
            })

    print(f"Rescued ({len(rescued)}):")
    for r in rescued:
        print(f"  [+] {r['id']} | Query: '{r['query']}' | Old Top1: {r['base_top1']} -> New Top1: {r['new_top1']}")

    print(f"\nRegressed ({len(regressed)}):")
    for r in regressed:
        print(f"  [-] {r['id']} | Query: '{r['query']}' | Old Top1: {r['base_top1']} -> New Top1: {r['new_top1']}")

    print(f"\nStill Failed ({len(still_failed)}):")
    for r in still_failed:
        print(f"  [x] {r['id']} | Query: '{r['query']}' | Top1: {r['new_top1']} | Rank: {r['new_rank']}")

if __name__ == '__main__':
    main()

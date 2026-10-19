import json
import sys
from pathlib import Path
sys.stdout.reconfigure(encoding='utf-8')

from rag_chatbot.retrieval import search_hybrid, extract_question_entities
from rag_chatbot.chroma_db import get_or_create_collection
from rag_chatbot.neo4j_db import get_neo4j_driver
from rag_chatbot.evaluation import load_evaluation_set, calculate_hit_at_k, calculate_mrr

def adaptive_rerank_test(query, results, entities, strategy="strategy_1"):
    if not results:
        return []

    target_brand = entities.get("brand")
    target_device = entities.get("device")
    target_error_code = entities.get("error_code")

    # Determine query type
    if target_error_code:
        q_type = "ERROR_CODE"
    elif target_brand or target_device:
        q_type = "SYMPTOM"
    else:
        q_type = "NO_ENTITY"

    # Define weight profiles
    if strategy == "fixed":
        # Current fixed configuration
        b_bonus_val = 0.08
        d_bonus_val = 0.08
        e_bonus_val = 0.20
        both_bonus_val = 0.02
    elif strategy == "strategy_1":
        # Pure adaptive by query type
        if q_type == "ERROR_CODE":
            b_bonus_val = 0.06
            d_bonus_val = 0.06
            e_bonus_val = 0.25
            both_bonus_val = 0.02
        elif q_type == "SYMPTOM":
            b_bonus_val = 0.05
            d_bonus_val = 0.05
            e_bonus_val = 0.0
            both_bonus_val = 0.01
        else: # NO_ENTITY
            b_bonus_val = 0.0
            d_bonus_val = 0.0
            e_bonus_val = 0.0
            both_bonus_val = 0.005
    elif strategy == "strategy_2":
        # Strategy 2: Higher error code priority + question text token overlap
        if q_type == "ERROR_CODE":
            b_bonus_val = 0.08
            d_bonus_val = 0.08
            e_bonus_val = 0.30
            both_bonus_val = 0.02
        elif q_type == "SYMPTOM":
            b_bonus_val = 0.06
            d_bonus_val = 0.06
            e_bonus_val = 0.0
            both_bonus_val = 0.01
        else:
            b_bonus_val = 0.0
            d_bonus_val = 0.0
            e_bonus_val = 0.0
            both_bonus_val = 0.0
    elif strategy == "strategy_3":
        # Strategy 3: Error code high bonus + normalized semantic scaling
        if q_type == "ERROR_CODE":
            b_bonus_val = 0.05
            d_bonus_val = 0.05
            e_bonus_val = 0.25
            both_bonus_val = 0.01
        elif q_type == "SYMPTOM":
            b_bonus_val = 0.04
            d_bonus_val = 0.04
            e_bonus_val = 0.0
            both_bonus_val = 0.005
        else:
            b_bonus_val = 0.0
            d_bonus_val = 0.0
            e_bonus_val = 0.0
            both_bonus_val = 0.0

    scored = []
    for item in results:
        dist = item.get("distance")
        semantic_score = max(0.0, 1.0 - float(dist)) if dist is not None else 0.0
        score = semantic_score

        item_brand = item.get("brand", "")
        item_device = item.get("device", "")
        item_code = item.get("error_code", "")

        if target_brand and item_brand and target_brand.lower() == item_brand.lower():
            score += b_bonus_val
        if target_device and item_device and target_device.lower() == item_device.lower():
            score += d_bonus_val
        if target_error_code and item_code and target_error_code.lower() == item_code.lower():
            score += e_bonus_val
        if item.get("retrieval_source") == "both":
            score += both_bonus_val

        item_copy = dict(item)
        item_copy["score"] = score
        scored.append((score, item_copy))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [x[1] for x in scored]

def evaluate_dev(dev_set, chroma_col, neo_driver, strat):
    hit1, hit3, hit5, total_mrr = 0, 0, 0, 0.0
    n = len(dev_set)

    for item in dev_set:
        q = item["question"]
        exp = item["question_id"]
        ent = extract_question_entities(q)

        # Baseline search_hybrid (no rerank)
        raw_res = search_hybrid(q, k=10, chroma_collection=chroma_col, neo4j_driver=neo_driver, use_reranking=False)
        
        if strat == "baseline":
            final_res = raw_res[:5]
        else:
            final_res = adaptive_rerank_test(q, raw_res, ent, strategy=strat)[:5]

        ids = [d["question_id"] for d in final_res]
        if calculate_hit_at_k(ids, exp, 1): hit1 += 1
        if calculate_hit_at_k(ids, exp, 3): hit3 += 1
        if calculate_hit_at_k(ids, exp, 5): hit5 += 1
        total_mrr += calculate_mrr(ids, exp, 5)

    return {
        "hit@1": round(hit1 / n * 100.0, 2),
        "hit@3": round(hit3 / n * 100.0, 2),
        "hit@5": round(hit5 / n * 100.0, 2),
        "mrr": round(total_mrr / n, 4),
    }

def main():
    dev_set = load_evaluation_set("data/evaluation/reranking_dev_100.json")
    chroma_col = get_or_create_collection()
    neo_driver = get_neo4j_driver()

    print(f"Loaded DEV SET with {len(dev_set)} queries.")
    print("Testing candidate strategies on DEV SET...")

    strategies = ["baseline", "fixed", "strategy_1", "strategy_2", "strategy_3"]
    for s in strategies:
        res = evaluate_dev(dev_set, chroma_col, neo_driver, s)
        print(f"[{s:<12}] Hit@1: {res['hit@1']:<6}% | Hit@3: {res['hit@3']:<6}% | Hit@5: {res['hit@5']:<6}% | MRR: {res['mrr']}")

if __name__ == "__main__":
    main()

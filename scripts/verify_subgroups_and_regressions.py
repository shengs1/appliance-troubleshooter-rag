import json
from pathlib import Path
from rag_chatbot.retrieval import search_hybrid, extract_question_entities
from rag_chatbot.chroma_db import get_or_create_collection
from rag_chatbot.neo4j_db import get_neo4j_driver
from rag_chatbot.evaluation import load_evaluation_set, calculate_hit_at_k, calculate_mrr

def get_rank(retrieved_ids, target_id, max_k=5):
    for r, did in enumerate(retrieved_ids[:max_k], 1):
        if did == target_id:
            return r
    return None

def main():
    eval_set = load_evaluation_set("data/evaluation/evaluation_set_200.json")
    chroma_col = get_or_create_collection()
    neo_driver = get_neo4j_driver()

    records = []

    for item in eval_set:
        q = item["question"]
        exp = item["question_id"]
        issue_type = item.get("issue_type", "UNKNOWN")
        entities = extract_question_entities(q)
        query_has_code = bool(entities.get("error_code"))

        # Baseline
        base_res = search_hybrid(q, k=5, chroma_collection=chroma_col, neo4j_driver=neo_driver, use_reranking=False)
        base_ids = [d["question_id"] for d in base_res]
        base_rank = get_rank(base_ids, exp, 5)

        # Reranking
        rerank_res = search_hybrid(q, k=5, chroma_collection=chroma_col, neo4j_driver=neo_driver, use_reranking=True)
        rerank_ids = [d["question_id"] for d in rerank_res]
        rerank_rank = get_rank(rerank_ids, exp, 5)

        records.append({
            "question_id": exp,
            "question": q,
            "brand": item.get("brand"),
            "device": item.get("device"),
            "issue_type": issue_type,
            "query_has_code": query_has_code,
            "extracted_code": entities.get("error_code"),
            "base_ids": base_ids,
            "rerank_ids": rerank_ids,
            "base_rank": base_rank,
            "rerank_rank": rerank_rank,
            "base_hit1": base_rank == 1,
            "base_hit3": base_rank is not None and base_rank <= 3,
            "base_hit5": base_rank is not None and base_rank <= 5,
            "base_mrr": 1.0 / base_rank if base_rank else 0.0,
            "rerank_hit1": rerank_rank == 1,
            "rerank_hit3": rerank_rank is not None and rerank_rank <= 3,
            "rerank_hit5": rerank_rank is not None and rerank_rank <= 5,
            "rerank_mrr": 1.0 / rerank_rank if rerank_rank else 0.0,
        })

    # 1. Subgroup metrics
    subgroups = sorted(list(set(r["issue_type"] for r in records)))
    subgroup_summary = {}

    for st in subgroups:
        subset = [r for r in records if r["issue_type"] == st]
        n = len(subset)
        if n == 0:
            continue
        subgroup_summary[st] = {
            "count": n,
            "baseline": {
                "hit@1": round(sum(1 for r in subset if r["base_hit1"]) / n * 100.0, 2),
                "hit@3": round(sum(1 for r in subset if r["base_hit3"]) / n * 100.0, 2),
                "hit@5": round(sum(1 for r in subset if r["base_hit5"]) / n * 100.0, 2),
                "mrr": round(sum(r["base_mrr"] for r in subset) / n, 4),
            },
            "reranking": {
                "hit@1": round(sum(1 for r in subset if r["rerank_hit1"]) / n * 100.0, 2),
                "hit@3": round(sum(1 for r in subset if r["rerank_hit3"]) / n * 100.0, 2),
                "hit@5": round(sum(1 for r in subset if r["rerank_hit5"]) / n * 100.0, 2),
                "mrr": round(sum(r["rerank_mrr"] for r in subset) / n, 4),
            },
        }

    # 2. Check exact error code queries
    # Queries that actually have an error_code extracted
    error_code_queries = [r for r in records if r["query_has_code"]]
    improved_code = 0
    unchanged_code = 0
    degraded_code = 0
    code_diff_details = []

    for r in error_code_queries:
        b_r = r["base_rank"]
        r_r = r["rerank_rank"]
        # Convert None (missed in top 5) to 999 for comparison
        b_val = b_r if b_r is not None else 999
        r_val = r_r if r_r is not None else 999

        if r_val < b_val:
            improved_code += 1
            code_diff_details.append({
                "type": "IMPROVED",
                "qid": r["question_id"],
                "q": r["question"],
                "code": r["extracted_code"],
                "base_rank": b_r,
                "rerank_rank": r_r,
            })
        elif r_val == b_val:
            unchanged_code += 1
        else:
            degraded_code += 1
            code_diff_details.append({
                "type": "DEGRADED",
                "qid": r["question_id"],
                "q": r["question"],
                "code": r["extracted_code"],
                "base_rank": b_r,
                "rerank_rank": r_r,
            })

    # 3. Check SYMPTOM queries
    symptom_queries = [r for r in records if r["issue_type"] == "SYMPTOM"]
    improved_sym = 0
    unchanged_sym = 0
    degraded_sym = 0
    sym_regressions = []

    for r in symptom_queries:
        b_r = r["base_rank"]
        r_r = r["rerank_rank"]
        b_val = b_r if b_r is not None else 999
        r_val = r_r if r_r is not None else 999

        if r_val < b_val:
            improved_sym += 1
        elif r_val == b_val:
            unchanged_sym += 1
        else:
            degraded_sym += 1
            sym_regressions.append({
                "qid": r["question_id"],
                "q": r["question"],
                "base_rank": b_r,
                "rerank_rank": r_r,
            })

    output = {
        "subgroups": subgroup_summary,
        "error_code_analysis": {
            "total_queries_with_code": len(error_code_queries),
            "improved_count": improved_code,
            "unchanged_count": unchanged_code,
            "degraded_count": degraded_code,
            "details": code_diff_details,
        },
        "symptom_analysis": {
            "total_symptom_queries": len(symptom_queries),
            "improved_count": improved_sym,
            "unchanged_count": unchanged_sym,
            "degraded_count": degraded_sym,
            "regressions": sym_regressions,
        },
    }

    out_path = Path("data/evaluation/subgroup_analysis.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print("Subgroup Analysis complete. Saved to", out_path)

if __name__ == "__main__":
    main()

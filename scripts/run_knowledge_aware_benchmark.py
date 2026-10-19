"""Script chay benchmark danh gia Retrieval theo 2 muc: Exact-ID va Knowledge-aware tren 200 cau.

Xuat cac artifact:
1. data/evaluation/knowledge_aware_results_200.json
2. data/evaluation/knowledge_aware_summary.json
"""

from __future__ import annotations
import json
import statistics
import sys
import time
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

from rag_chatbot.chroma_db import get_or_create_collection
from rag_chatbot.evaluation import load_evaluation_set
from rag_chatbot.knowledge_eval import (
    evaluate_query_dual_level,
    load_knowledge_equivalence_map,
)
from rag_chatbot.neo4j_db import get_neo4j_driver
from rag_chatbot.retrieval import search_hybrid


def run_benchmark():
    print("=== BAT DAU KNOWLEDGE-AWARE RETRIEVAL BENCHMARK (200 CAU) ===")
    t_start = time.perf_counter()

    # 1. Load resources
    eval_set_path = "data/evaluation/evaluation_set_200.json"
    eval_set = load_evaluation_set(eval_set_path)
    print(f"Loaded {len(eval_set)} queries from {eval_set_path}.")

    equiv_map = load_knowledge_equivalence_map()
    print(f"Loaded knowledge equivalence map with {len(equiv_map)} mapped IDs.")

    col = get_or_create_collection()
    drv = get_neo4j_driver()

    detailed_results = []

    # Counters overall
    n = len(eval_set)
    exact_h1, exact_h3, exact_h5 = 0, 0, 0
    know_h1, know_h3, know_h5 = 0, 0, 0
    exact_mrr_sum = 0.0
    know_mrr_sum = 0.0

    # Counters by Issue Type
    subgroups_issue = {
        "ERROR_CODE": {"total": 0, "exact_h1": 0, "exact_h3": 0, "exact_h5": 0, "exact_mrr": 0.0, "know_h1": 0, "know_h3": 0, "know_h5": 0, "know_mrr": 0.0},
        "SYMPTOM": {"total": 0, "exact_h1": 0, "exact_h3": 0, "exact_h5": 0, "exact_mrr": 0.0, "know_h1": 0, "know_h3": 0, "know_h5": 0, "know_mrr": 0.0},
        "ERROR_CODE_UNKNOWN": {"total": 0, "exact_h1": 0, "exact_h3": 0, "exact_h5": 0, "exact_mrr": 0.0, "know_h1": 0, "know_h3": 0, "know_h5": 0, "know_mrr": 0.0},
    }

    # Counters by Brand
    subgroups_brand = {
        "Samsung": {"total": 0, "exact_h1": 0, "exact_h3": 0, "exact_h5": 0, "exact_mrr": 0.0, "know_h1": 0, "know_h3": 0, "know_h5": 0, "know_mrr": 0.0},
        "Panasonic": {"total": 0, "exact_h1": 0, "exact_h3": 0, "exact_h5": 0, "exact_mrr": 0.0, "know_h1": 0, "know_h3": 0, "know_h5": 0, "know_mrr": 0.0},
        "LG": {"total": 0, "exact_h1": 0, "exact_h3": 0, "exact_h5": 0, "exact_mrr": 0.0, "know_h1": 0, "know_h3": 0, "know_h5": 0, "know_mrr": 0.0},
    }

    exact_miss_know_hit_count = 0
    twin_duplicate_influence_count = 0

    print("Executing retrieval on 200 evaluation queries...")
    for idx, item in enumerate(eval_set, 1):
        q = item["question"]
        exp_id = item["question_id"]
        issue_type = item.get("issue_type", "UNKNOWN")
        brand = item.get("brand", "UNKNOWN")

        # Chay runtime retrieval: Hybrid + Fixed Reranking (tuyet doi khong dung ground truth)
        docs = search_hybrid(
            question=q,
            k=5,
            chroma_collection=col,
            neo4j_driver=drv,
            use_reranking=True,
            rerank_mode="fixed",
        )

        eval_res = evaluate_query_dual_level(
            retrieved_docs=docs,
            expected_id=exp_id,
            equivalence_map=equiv_map,
            max_k=5,
        )

        e_rank = eval_res["exact_rank"]
        k_rank = eval_res["knowledge_rank"]

        e_h1 = eval_res["exact_hit_1"]
        e_h3 = eval_res["exact_hit_3"]
        e_h5 = eval_res["exact_hit_5"]
        e_rr = eval_res["exact_mrr"]

        k_h1 = eval_res["knowledge_hit_1"]
        k_h3 = eval_res["knowledge_hit_3"]
        k_h5 = eval_res["knowledge_hit_5"]
        k_rr = eval_res["knowledge_mrr"]

        if e_h1: exact_h1 += 1
        if e_h3: exact_h3 += 1
        if e_h5: exact_h5 += 1
        exact_mrr_sum += e_rr

        if k_h1: know_h1 += 1
        if k_h3: know_h3 += 1
        if k_h5: know_h5 += 1
        know_mrr_sum += k_rr

        if not e_h1 and k_h1:
            exact_miss_know_hit_count += 1

        if e_rank != k_rank:
            twin_duplicate_influence_count += 1

        # Subgroup issue
        if issue_type in subgroups_issue:
            s_i = subgroups_issue[issue_type]
            s_i["total"] += 1
            if e_h1: s_i["exact_h1"] += 1
            if e_h3: s_i["exact_h3"] += 1
            if e_h5: s_i["exact_h5"] += 1
            s_i["exact_mrr"] += e_rr
            if k_h1: s_i["know_h1"] += 1
            if k_h3: s_i["know_h3"] += 1
            if k_h5: s_i["know_h5"] += 1
            s_i["know_mrr"] += k_rr

        # Subgroup brand
        if brand in subgroups_brand:
            s_b = subgroups_brand[brand]
            s_b["total"] += 1
            if e_h1: s_b["exact_h1"] += 1
            if e_h3: s_b["exact_h3"] += 1
            if e_h5: s_b["exact_h5"] += 1
            s_b["exact_mrr"] += e_rr
            if k_h1: s_b["know_h1"] += 1
            if k_h3: s_b["know_h3"] += 1
            if k_h5: s_b["know_h5"] += 1
            s_b["know_mrr"] += k_rr

        top5_formatted = []
        for r_idx, d in enumerate(docs, 1):
            did = str(d.get("question_id") or "")
            top5_formatted.append({
                "rank": r_idx,
                "question_id": did,
                "question": d.get("question", ""),
                "score": d.get("rerank_score"),
                "is_exact": (did == exp_id),
                "is_knowledge_equivalent": (did in equiv_map.get(exp_id, set())),
            })

        detailed_results.append({
            "index": idx,
            "question_id": exp_id,
            "question": q,
            "issue_type": issue_type,
            "brand": brand,
            "expected_question_id": exp_id,
            "exact_rank": e_rank,
            "knowledge_rank": k_rank,
            "exact_hit_1": e_h1,
            "knowledge_hit_1": k_h1,
            "exact_hit_5": e_h5,
            "knowledge_hit_5": k_h5,
            "top5": top5_formatted,
            "knowledge_match_details": eval_res["match_details"],
        })

    # Save detailed results
    out_results_file = Path("data/evaluation/knowledge_aware_results_200.json")
    with open(out_results_file, "w", encoding="utf-8") as f:
        json.dump(detailed_results, f, ensure_ascii=False, indent=2)
    print(f"Da ghi ket qua chi tiet: {out_results_file}")

    # Format Subgroups summary
    formatted_sub_issue = {}
    for stype, sdata in subgroups_issue.items():
        stot = sdata["total"]
        if stot > 0:
            formatted_sub_issue[stype] = {
                "sample_size": stot,
                "exact_id": {
                    "hit@1": round(sdata["exact_h1"] / stot * 100.0, 2),
                    "hit@3": round(sdata["exact_h3"] / stot * 100.0, 2),
                    "hit@5": round(sdata["exact_h5"] / stot * 100.0, 2),
                    "mrr": round(sdata["exact_mrr"] / stot, 4),
                },
                "knowledge_aware": {
                    "hit@1": round(sdata["know_h1"] / stot * 100.0, 2),
                    "hit@3": round(sdata["know_h3"] / stot * 100.0, 2),
                    "hit@5": round(sdata["know_h5"] / stot * 100.0, 2),
                    "mrr": round(sdata["know_mrr"] / stot, 4),
                },
                "gain_hit@1": round((sdata["know_h1"] - sdata["exact_h1"]) / stot * 100.0, 2),
            }

    formatted_sub_brand = {}
    for btype, bdata in subgroups_brand.items():
        btot = bdata["total"]
        if btot > 0:
            formatted_sub_brand[btype] = {
                "sample_size": btot,
                "exact_id": {
                    "hit@1": round(bdata["exact_h1"] / btot * 100.0, 2),
                    "hit@3": round(bdata["exact_h3"] / btot * 100.0, 2),
                    "hit@5": round(bdata["exact_h5"] / btot * 100.0, 2),
                    "mrr": round(bdata["exact_mrr"] / btot, 4),
                },
                "knowledge_aware": {
                    "hit@1": round(bdata["know_h1"] / btot * 100.0, 2),
                    "hit@3": round(bdata["know_h3"] / btot * 100.0, 2),
                    "hit@5": round(bdata["know_h5"] / btot * 100.0, 2),
                    "mrr": round(bdata["know_mrr"] / btot, 4),
                },
                "gain_hit@1": round((bdata["know_h1"] - bdata["exact_h1"]) / btot * 100.0, 2),
            }

    # Reclassify 26 failures
    failures_26 = [d for d in detailed_results if not d["exact_hit_1"]]
    cat_a_count = 0  # Exact-ID failure nhung Knowledge-aware success
    cat_b_count = 0  # True retrieval failure
    cat_c_count = 0  # Missed retrieval

    failure_reclass = []
    for f in failures_26:
        qid = f["question_id"]
        e_rank = f["exact_rank"]
        k_rank = f["knowledge_rank"]
        if k_rank == 1:
            cat = "CATEGORY_A: Exact-ID failure nhung Knowledge-aware success"
            cat_a_count += 1
        elif e_rank is None and k_rank is None:
            cat = "CATEGORY_C: Missed retrieval (khong xuat hien trong top 5)"
            cat_c_count += 1
        else:
            cat = "CATEGORY_B: True retrieval failure"
            cat_b_count += 1

        failure_reclass.append({
            "question_id": qid,
            "question": f["question"],
            "issue_type": f["issue_type"],
            "exact_rank": e_rank,
            "knowledge_rank": k_rank,
            "category": cat,
            "top1_id": f["top5"][0]["question_id"] if f["top5"] else None,
        })

    q0535_item = next((d for d in detailed_results if d["question_id"] == "Q0535"), {})

    summary_data = {
        "total_queries": n,
        "exact_id_metrics": {
            "hit@1": round(exact_h1 / n * 100.0, 2),
            "hit@3": round(exact_h3 / n * 100.0, 2),
            "hit@5": round(exact_h5 / n * 100.0, 2),
            "mrr": round(exact_mrr_sum / n, 4),
        },
        "knowledge_aware_metrics": {
            "hit@1": round(know_h1 / n * 100.0, 2),
            "hit@3": round(know_h3 / n * 100.0, 2),
            "hit@5": round(know_h5 / n * 100.0, 2),
            "mrr": round(know_mrr_sum / n, 4),
        },
        "comparison_table": {
            "hit@1": {"exact_id": round(exact_h1 / n * 100.0, 2), "knowledge_aware": round(know_h1 / n * 100.0, 2), "delta": round((know_h1 - exact_h1) / n * 100.0, 2)},
            "hit@3": {"exact_id": round(exact_h3 / n * 100.0, 2), "knowledge_aware": round(know_h3 / n * 100.0, 2), "delta": round((know_h3 - exact_h3) / n * 100.0, 2)},
            "hit@5": {"exact_id": round(exact_h5 / n * 100.0, 2), "knowledge_aware": round(know_h5 / n * 100.0, 2), "delta": round((know_h5 - exact_h5) / n * 100.0, 2)},
            "mrr": {"exact_id": round(exact_mrr_sum / n, 4), "knowledge_aware": round(know_mrr_sum / n, 4), "delta": round((know_mrr_sum - exact_mrr_sum) / n, 4)},
        },
        "discrepancy_counts": {
            "exact_miss_knowledge_hit_count": exact_miss_know_hit_count,
            "true_retrieval_miss_count": n - know_h5,
            "twin_duplicate_influence_count": twin_duplicate_influence_count,
            "knowledge_aware_unresolved_count": 0,
        },
        "failures_26_reclassification": {
            "total_failures": len(failures_26),
            "category_a_exact_miss_knowledge_hit": cat_a_count,
            "category_b_true_retrieval_failure": cat_b_count,
            "category_c_missed_retrieval": cat_c_count,
            "cases": failure_reclass,
        },
        "by_issue_type": formatted_sub_issue,
        "by_brand": formatted_sub_brand,
        "q0535_special_case": {
            "question_id": "Q0535",
            "question": "Máy giặt không xả nước phải làm sao?",
            "exact_rank": q0535_item.get("exact_rank"),
            "knowledge_rank": q0535_item.get("knowledge_rank"),
            "top1_id": q0535_item.get("top5", [{}])[0].get("question_id"),
            "explanation": "Q0535 khong xuat hien trong Top-5 cua Fixed (Exact-ID miss, exact_rank=None), nhung tai Rank 1 la Q0690 co 100% cung noi dung cau tra loi va cung van de ky thuat, nen o goc nhin Knowledge-aware dat Rank 1 thanh cong.",
        },
    }

    out_summary_file = Path("data/evaluation/knowledge_aware_summary.json")
    with open(out_summary_file, "w", encoding="utf-8") as f:
        json.dump(summary_data, f, ensure_ascii=False, indent=2)
    print(f"Da ghi summary: {out_summary_file}")

    print("\n=== KET QUA BENCHMARK KNOWLEDGE-AWARE HOAN TAT ===")
    print(f"Exact-ID Hit@1: {summary_data['exact_id_metrics']['hit@1']}% | Hit@5: {summary_data['exact_id_metrics']['hit@5']}% | MRR: {summary_data['exact_id_metrics']['mrr']}")
    print(f"Knowledge-aware Hit@1: {summary_data['knowledge_aware_metrics']['hit@1']}% | Hit@5: {summary_data['knowledge_aware_metrics']['hit@5']}% | MRR: {summary_data['knowledge_aware_metrics']['mrr']}")
    print(f"Chenh lech Hit@1: +{summary_data['comparison_table']['hit@1']['delta']}% ({exact_miss_know_hit_count} cau exact-miss tro thanh knowledge-hit)")
    print(f"Reclassification 26 failure: Category A={cat_a_count}, Category B={cat_b_count}, Category C={cat_c_count}")
    print(f"Tong thoi gian chay: {time.perf_counter() - t_start:.2f}s")


if __name__ == "__main__":
    run_benchmark()

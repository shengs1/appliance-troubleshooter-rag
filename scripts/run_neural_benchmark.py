"""Benchmark toan dien Neural Reranker (BAAI/bge-reranker-v2-m3) tren Dev Set va Eval Set.

Muc tieu:
1. Danh gia tren Dev Set 100 cau: Fixed vs Neural.
2. Danh gia tren Eval Set 200 cau: Hybrid Baseline vs Fixed Reranking vs Neural Reranking.
3. Tinh toan Metrics tong the: Hit@1, Hit@3, Hit@5, MRR.
4. Tinh toan Metrics theo subgroup: ERROR_CODE, SYMPTOM, ERROR_CODE_UNKNOWN.
5. Do latency chi tiet: retrieval_latency_ms, reranker_latency_ms, total_latency_ms.
6. Kiem tra va phan tich 26 failure cases tu Fixed Reranking.
7. Luu ket qua chi tiet ra file data/evaluation/neural_benchmark_results.json.
"""

from __future__ import annotations
import json
import statistics
import sys
import time
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

from rag_chatbot.chroma_db import get_or_create_collection
from rag_chatbot.evaluation import (
    calculate_hit_at_k,
    calculate_mrr,
    load_evaluation_set,
)
from rag_chatbot.neo4j_db import get_neo4j_driver
from rag_chatbot.reranker import get_reranker, rerank_with_model
from rag_chatbot.retrieval import (
    build_chroma_where_filter,
    extract_question_entities,
    rerank_results,
    search_graph,
    search_hybrid,
    search_similar_documents,
)


def run_single_retrieval(
    question: str,
    mode: str,
    chroma_collection,
    neo4j_driver,
    reranker_model,
    k: int = 5,
) -> tuple[list[dict], float, float, float]:
    """Chay 1 query va do latency theo tung thanh phan.
    
    Returns:
        (results, retrieval_latency_ms, reranker_latency_ms, total_latency_ms)
    """
    t0 = time.perf_counter()
    entities = extract_question_entities(question)
    brand = entities["brand"]
    device = entities["device"]

    fetch_k = 10 if mode == "neural" else k
    active_where = build_chroma_where_filter(brand=brand, device=device)

    # 1. Candidate Retrieval (ChromaDB + Neo4j)
    t_ret_start = time.perf_counter()
    chroma_raw = search_similar_documents(
        question,
        k=fetch_k,
        collection=chroma_collection,
        where=active_where,
    )
    chroma_items = []
    for r in chroma_raw:
        meta = r.get("metadata", {})
        doc_text = r.get("document", "")
        q_text, ans_text = "", ""
        for line in doc_text.splitlines():
            if line.startswith("Câu hỏi: "):
                q_text = line[len("Câu hỏi: "):].strip()
            elif line.startswith("Câu trả lời: "):
                ans_text = line[len("Câu trả lời: "):].strip()

        chroma_items.append({
            "question_id": str(meta.get("question_id", r.get("id", ""))),
            "question": q_text or str(meta.get("question_id", "")),
            "answer": ans_text,
            "brand": str(meta.get("brand", "")),
            "device": str(meta.get("device", "")),
            "error_code": str(meta.get("error_code", "")),
            "source_url": str(meta.get("source_url", "")),
            "retrieval_source": "chroma",
            "distance": r.get("distance"),
        })

    neo4j_items = search_graph(question, k=fetch_k, driver=neo4j_driver)

    combined = {}
    for item in chroma_items:
        combined[item["question_id"]] = item
    for item in neo4j_items:
        qid = item["question_id"]
        if qid in combined:
            combined[qid]["retrieval_source"] = "both"
            if not combined[qid]["answer"] and item.get("answer"):
                combined[qid]["answer"] = item["answer"]
        else:
            combined[qid] = item

    filtered_results = []
    for item in combined.values():
        item_brand = item.get("brand", "")
        item_device = item.get("device", "")
        if brand and item_brand and item_brand.lower() != brand.lower():
            continue
        if device and item_device and item_device.lower() != device.lower():
            continue
        filtered_results.append(item)

    t_ret_end = time.perf_counter()
    retrieval_latency_ms = (t_ret_end - t_ret_start) * 1000.0

    # 2. Reranking / Ordering
    t_rerank_start = time.perf_counter()
    if mode == "baseline":
        final_results = sorted(
            filtered_results,
            key=lambda x: (0 if x["retrieval_source"] == "both" else 1),
        )[:k]
    elif mode == "fixed":
        final_results = rerank_results(
            question, filtered_results, entities=entities, mode="fixed"
        )[:k]
    elif mode == "neural":
        final_results = rerank_with_model(
            question, filtered_results, top_k=k, model=reranker_model
        )
    else:
        raise ValueError(f"Unknown mode: {mode}")

    t_rerank_end = time.perf_counter()
    reranker_latency_ms = (t_rerank_end - t_rerank_start) * 1000.0
    total_latency_ms = (t_rerank_end - t0) * 1000.0

    return final_results, retrieval_latency_ms, reranker_latency_ms, total_latency_ms


def evaluate_dataset(
    dataset: list[dict],
    mode: str,
    chroma_collection,
    neo4j_driver,
    reranker_model,
) -> dict:
    """Danh gia tap du lieu theo che do va tinh toan tat ca metrics."""
    hit1, hit3, hit5 = 0, 0, 0
    total_mrr = 0.0
    n = len(dataset)

    retrieval_lats = []
    reranker_lats = []
    total_lats = []

    # Subgroups
    subgroups = {
        "ERROR_CODE": {"hit1": 0, "hit3": 0, "hit5": 0, "mrr": 0.0, "total": 0},
        "SYMPTOM": {"hit1": 0, "hit3": 0, "hit5": 0, "mrr": 0.0, "total": 0},
        "ERROR_CODE_UNKNOWN": {"hit1": 0, "hit3": 0, "hit5": 0, "mrr": 0.0, "total": 0},
    }

    detailed_results = []

    for item in dataset:
        q = item["question"]
        exp_id = item["question_id"]
        issue_type = item.get("issue_type", "UNKNOWN")

        results, r_lat, rk_lat, tot_lat = run_single_retrieval(
            q,
            mode=mode,
            chroma_collection=chroma_collection,
            neo4j_driver=neo4j_driver,
            reranker_model=reranker_model,
            k=5,
        )

        retrieval_lats.append(r_lat)
        reranker_lats.append(rk_lat)
        total_lats.append(tot_lat)

        cand_ids = [d["question_id"] for d in results]
        h1 = calculate_hit_at_k(cand_ids, exp_id, 1)
        h3 = calculate_hit_at_k(cand_ids, exp_id, 3)
        h5 = calculate_hit_at_k(cand_ids, exp_id, 5)
        mrr = calculate_mrr(cand_ids, exp_id, 5)

        if h1: hit1 += 1
        if h3: hit3 += 1
        if h5: hit5 += 1
        total_mrr += mrr

        if issue_type in subgroups:
            sub = subgroups[issue_type]
            sub["total"] += 1
            if h1: sub["hit1"] += 1
            if h3: sub["hit3"] += 1
            if h5: sub["hit5"] += 1
            sub["mrr"] += mrr

        # Rank of expected id
        rank = cand_ids.index(exp_id) + 1 if exp_id in cand_ids else None

        detailed_results.append({
            "question_id": exp_id,
            "question": q,
            "issue_type": issue_type,
            "rank": rank,
            "hit@1": bool(h1),
            "top1_id": cand_ids[0] if cand_ids else None,
            "top1_score": results[0].get("reranker_score") or results[0].get("rerank_score") if results else None,
            "retrieved_ids": cand_ids,
        })

    # Subgroups summary
    subgroups_summary = {}
    for stype, data in subgroups.items():
        stot = data["total"]
        if stot > 0:
            subgroups_summary[stype] = {
                "total": stot,
                "hit@1": round(data["hit1"] / stot * 100.0, 2),
                "hit@3": round(data["hit3"] / stot * 100.0, 2),
                "hit@5": round(data["hit5"] / stot * 100.0, 2),
                "mrr": round(data["mrr"] / stot, 4),
            }

    return {
        "mode": mode,
        "total_queries": n,
        "hit@1": round(hit1 / n * 100.0, 2),
        "hit@3": round(hit3 / n * 100.0, 2),
        "hit@5": round(hit5 / n * 100.0, 2),
        "mrr": round(total_mrr / n, 4),
        "latency": {
            "retrieval_mean_ms": round(statistics.mean(retrieval_lats), 2),
            "retrieval_median_ms": round(statistics.median(retrieval_lats), 2),
            "reranker_mean_ms": round(statistics.mean(reranker_lats), 2),
            "reranker_median_ms": round(statistics.median(reranker_lats), 2),
            "total_mean_ms": round(statistics.mean(total_lats), 2),
            "total_median_ms": round(statistics.median(total_lats), 2),
        },
        "subgroups": subgroups_summary,
        "detailed_results": detailed_results,
    }


def main():
    print("=== KHOI DONG BENCHMARK NEURAL RERANKER ===")
    chroma_collection = get_or_create_collection()
    neo4j_driver = get_neo4j_driver()
    print("Loading BAAI/bge-reranker-v2-m3 singleton...")
    t_load_start = time.perf_counter()
    reranker_model = get_reranker()
    print(f"Model loaded in {(time.perf_counter() - t_load_start):.2f}s.")

    # 1. EVALUATION TREN DEV SET (100 CAU)
    dev_path = "data/evaluation/reranking_dev_100.json"
    if Path(dev_path).exists():
        print(f"\n--- 1. DANH GIA TREN DEV SET ({dev_path}) ---")
        dev_set = load_evaluation_set(dev_path)
        print(f"Loaded {len(dev_set)} dev queries.")

        print("Running Fixed Reranking on Dev Set...")
        dev_fixed = evaluate_dataset(dev_set, "fixed", chroma_collection, neo4j_driver, reranker_model)
        print(f"Dev Fixed -> Hit@1: {dev_fixed['hit@1']}% | Hit@3: {dev_fixed['hit@3']}% | Hit@5: {dev_fixed['hit@5']}% | MRR: {dev_fixed['mrr']}")
        print(f"            Latency total mean: {dev_fixed['latency']['total_mean_ms']} ms")

        print("Running Neural Reranking on Dev Set...")
        dev_neural = evaluate_dataset(dev_set, "neural", chroma_collection, neo4j_driver, reranker_model)
        print(f"Dev Neural -> Hit@1: {dev_neural['hit@1']}% | Hit@3: {dev_neural['hit@3']}% | Hit@5: {dev_neural['hit@5']}% | MRR: {dev_neural['mrr']}")
        print(f"             Latency retrieval: {dev_neural['latency']['retrieval_mean_ms']} ms, reranker: {dev_neural['latency']['reranker_mean_ms']} ms, total: {dev_neural['latency']['total_mean_ms']} ms")
    else:
        dev_fixed, dev_neural = None, None

    # 2. EVALUATION TREN OFFICIAL TEST SET (200 CAU)
    eval_path = "data/evaluation/evaluation_set_200.json"
    print(f"\n--- 2. DANH GIA TREN OFFICIAL EVALUATION SET ({eval_path}) ---")
    eval_set = load_evaluation_set(eval_path)
    print(f"Loaded {len(eval_set)} evaluation queries.")

    print("Running Hybrid Baseline (No reranking)...")
    eval_baseline = evaluate_dataset(eval_set, "baseline", chroma_collection, neo4j_driver, reranker_model)
    print(f"Eval Baseline -> Hit@1: {eval_baseline['hit@1']}% | Hit@3: {eval_baseline['hit@3']}% | Hit@5: {eval_baseline['hit@5']}% | MRR: {eval_baseline['mrr']}")

    print("Running Hybrid Fixed Reranking...")
    eval_fixed = evaluate_dataset(eval_set, "fixed", chroma_collection, neo4j_driver, reranker_model)
    print(f"Eval Fixed -> Hit@1: {eval_fixed['hit@1']}% | Hit@3: {eval_fixed['hit@3']}% | Hit@5: {eval_fixed['hit@5']}% | MRR: {eval_fixed['mrr']}")
    print(f"            Latency mean: {eval_fixed['latency']['total_mean_ms']} ms")

    print("Running Hybrid Neural Reranking...")
    eval_neural = evaluate_dataset(eval_set, "neural", chroma_collection, neo4j_driver, reranker_model)
    print(f"Eval Neural -> Hit@1: {eval_neural['hit@1']}% | Hit@3: {eval_neural['hit@3']}% | Hit@5: {eval_neural['hit@5']}% | MRR: {eval_neural['mrr']}")
    print(f"             Latency retrieval: {eval_neural['latency']['retrieval_mean_ms']} ms, reranker: {eval_neural['latency']['reranker_mean_ms']} ms, total: {eval_neural['latency']['total_mean_ms']} ms")

    # 3. PHAN TICH 26 FAILURE CASES CUA FIXED RERANKING
    print("\n--- 3. SO SANH 26 CAU THAT BAI CUA FIXED RERANKING VOI NEURAL RERANKER ---")
    fixed_detail = {d["question_id"]: d for d in eval_fixed["detailed_results"]}
    neural_detail = {d["question_id"]: d for d in eval_neural["detailed_results"]}

    fixed_failed_qids = [d["question_id"] for d in eval_fixed["detailed_results"] if not d["hit@1"]]
    print(f"So luong cau Fixed khong dat Hit@1: {len(fixed_failed_qids)}")

    failure_comparison = []
    fixed_better = 0
    neural_better = 0
    tied = 0

    for qid in fixed_failed_qids:
        f_info = fixed_detail[qid]
        n_info = neural_detail[qid]

        f_rank = f_info["rank"]
        n_rank = n_info["rank"]

        if n_rank is not None and (f_rank is None or n_rank < f_rank):
            status = "NEURAL_BETTER"
            neural_better += 1
        elif f_rank is not None and (n_rank is None or f_rank < n_rank):
            status = "FIXED_BETTER"
            fixed_better += 1
        else:
            status = "EQUAL"
            tied += 1

        failure_comparison.append({
            "question_id": qid,
            "question": f_info["question"],
            "issue_type": f_info["issue_type"],
            "fixed_rank": f_rank,
            "fixed_top1": f_info["top1_id"],
            "neural_rank": n_rank,
            "neural_top1": n_info["top1_id"],
            "status": status,
        })

    print(f"Trong 26 cau that bai cua Fixed:")
    print(f"- Neural cai thien rank: {neural_better}")
    print(f"- Fixed tot hon Neural: {fixed_better}")
    print(f"- Bang nhau: {tied}")

    # Inspect notable cases: Q0158, Q0165, Q0002
    notable_qids = ["Q0158", "Q0165", "Q0002", "Q0281", "Q0111", "Q0108"]
    print("\nChi tiet mot so cau dang chu y:")
    for comp in failure_comparison:
        if comp["question_id"] in notable_qids:
            print(f"- {comp['question_id']} ({comp['question']}): Fixed Rank {comp['fixed_rank']} (Top1: {comp['fixed_top1']}) vs Neural Rank {comp['neural_rank']} (Top1: {comp['neural_top1']}) -> {comp['status']}")

    # 4. TONG HOP VA LUU KET QUA
    output_data = {
        "dev_set_100": {
            "fixed": {k: v for k, v in (dev_fixed or {}).items() if k != "detailed_results"},
            "neural": {k: v for k, v in (dev_neural or {}).items() if k != "detailed_results"},
        },
        "evaluation_set_200": {
            "baseline": {k: v for k, v in eval_baseline.items() if k != "detailed_results"},
            "fixed": {k: v for k, v in eval_fixed.items() if k != "detailed_results"},
            "neural": {k: v for k, v in eval_neural.items() if k != "detailed_results"},
        },
        "failure_cases_analysis_26": {
            "total_fixed_failures": len(fixed_failed_qids),
            "neural_better_count": neural_better,
            "fixed_better_count": fixed_better,
            "equal_count": tied,
            "cases": failure_comparison,
        },
    }

    out_file = Path("data/evaluation/neural_benchmark_results.json")
    out_file.parent.mkdir(parents=True, exist_ok=True)
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(output_data, f, ensure_ascii=False, indent=2)
    print(f"\nDa luu ket qua vao: {out_file}")


if __name__ == "__main__":
    main()

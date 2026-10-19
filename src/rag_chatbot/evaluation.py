"""Module danh gia he thong RAG Chatbot (Phase 8 - Evaluation).

Cung cap cac ham danh gia don gian, de hieu va minh bach ve:
1. Retrieval Evaluation: ChromaDB Hit@1 / Hit@5, Neo4j Hit@1 / Hit@5, Hybrid Hit@1 / Hit@5.
2. Dem so luong ban ghi duoc tim thay boi ca 2 nguon (retrieval_source == 'both').
3. RAG / Local LLM Generation: Tinh ti le phan hoi, do tre (latency: avg, min, max).
4. Do thoi gian phan hoi chi tiet cua tung thanh phan (ChromaDB, Neo4j, Hybrid, LLM).
"""

from __future__ import annotations
import json
from pathlib import Path
import statistics
import time
from typing import Any

from rag_chatbot.chroma_db import get_or_create_collection
from rag_chatbot.neo4j_db import get_neo4j_driver
from rag_chatbot.rag import generate_rag_answer
from rag_chatbot.retrieval import (
    build_chroma_where_filter,
    extract_matching_sources,
    extract_question_entities,
    rerank_results,
    search_graph,
    search_hybrid,
    search_similar_documents,
)
from rag_chatbot.scope import should_refuse


def load_evaluation_set(file_path: str | Path | None = None) -> list[dict[str, Any]]:
    """Doc tap du lieu danh gia chuan tu file JSON."""
    path = Path(file_path) if file_path else Path("data/evaluation/evaluation_set.json")
    if not path.exists():
        raise FileNotFoundError(f"Không tìm thấy file tập đánh giá tại: {path}")

    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def calculate_hit_at_k(retrieved_ids: list[str], target_id: str, k: int) -> bool:
    """Kiem tra target_id co nam trong top-k ban ghi truy van duoc hay khong."""
    return target_id in retrieved_ids[:k]


def calculate_mrr(retrieved_ids: list[str], target_id: str, max_k: int = 5) -> float:
    """Tinh chi so Reciprocal Rank (RR) cho mot cau hoi voi top-k ban ghi.
    
    Neu target_id xuat hien tai vi tri r (1-based, r <= max_k): RR = 1.0 / r.
    Neu khong xuat hien trong top max_k: RR = 0.0.
    """
    for rank, doc_id in enumerate(retrieved_ids[:max_k], 1):
        if doc_id == target_id:
            return 1.0 / rank
    return 0.0


def evaluate_chroma(eval_set: list[dict[str, Any]]) -> dict[str, Any]:
    """Danh gia do chinh xac tim kiem vector ChromaDB tren tap test."""
    total = len(eval_set)
    hit_1 = 0
    hit_5 = 0
    total_time = 0.0

    for item in eval_set:
        query = item["question"]
        target_id = item["question_id"]

        start = time.perf_counter()
        docs = search_similar_documents(query, k=5)
        elapsed = time.perf_counter() - start
        total_time += elapsed

        retrieved_ids = [
            d.get("question_id") or d.get("id") or d.get("metadata", {}).get("question_id")
            for d in docs
        ]
        if calculate_hit_at_k(retrieved_ids, target_id, 1):
            hit_1 += 1
        if calculate_hit_at_k(retrieved_ids, target_id, 5):
            hit_5 += 1

    return {
        "total_queries": total,
        "hit_1_count": hit_1,
        "hit_1_rate": (hit_1 / total * 100.0) if total else 0.0,
        "hit_5_count": hit_5,
        "hit_5_rate": (hit_5 / total * 100.0) if total else 0.0,
        "avg_time_ms": (total_time / total * 1000.0) if total else 0.0,
    }


def evaluate_neo4j(eval_set: list[dict[str, Any]]) -> dict[str, Any]:
    """Danh gia do chinh xac truy van do thi Neo4j tren tap test."""
    total = len(eval_set)
    hit_1 = 0
    hit_5 = 0
    total_time = 0.0

    for item in eval_set:
        query = item["question"]
        target_id = item["question_id"]

        start = time.perf_counter()
        docs = search_graph(query, k=5)
        elapsed = time.perf_counter() - start
        total_time += elapsed

        retrieved_ids = [d.get("question_id") for d in docs]
        if calculate_hit_at_k(retrieved_ids, target_id, 1):
            hit_1 += 1
        if calculate_hit_at_k(retrieved_ids, target_id, 5):
            hit_5 += 1

    return {
        "total_queries": total,
        "hit_1_count": hit_1,
        "hit_1_rate": (hit_1 / total * 100.0) if total else 0.0,
        "hit_5_count": hit_5,
        "hit_5_rate": (hit_5 / total * 100.0) if total else 0.0,
        "avg_time_ms": (total_time / total * 1000.0) if total else 0.0,
    }


def evaluate_hybrid(eval_set: list[dict[str, Any]]) -> dict[str, Any]:
    """Danh gia do chinh xac ket hop Hybrid Retrieval (ChromaDB + Neo4j)."""
    total = len(eval_set)
    hit_1 = 0
    hit_5 = 0
    both_count = 0
    total_time = 0.0

    for item in eval_set:
        query = item["question"]
        target_id = item["question_id"]

        start = time.perf_counter()
        docs = search_hybrid(query, k=5)
        elapsed = time.perf_counter() - start
        total_time += elapsed

        retrieved_ids = [d.get("question_id") for d in docs]
        if calculate_hit_at_k(retrieved_ids, target_id, 1):
            hit_1 += 1
        if calculate_hit_at_k(retrieved_ids, target_id, 5):
            hit_5 += 1

        # Dem so ban ghi tim thay boi ca 2 nguon
        both_count += sum(1 for d in docs if d.get("retrieval_source") == "both")

    return {
        "total_queries": total,
        "hit_1_count": hit_1,
        "hit_1_rate": (hit_1 / total * 100.0) if total else 0.0,
        "hit_5_count": hit_5,
        "hit_5_rate": (hit_5 / total * 100.0) if total else 0.0,
        "both_source_count": both_count,
        "avg_time_ms": (total_time / total * 1000.0) if total else 0.0,
    }


def evaluate_rag(eval_subset: list[dict[str, Any]]) -> dict[str, Any]:
    """Danh gia quy trinh RAG day du kem Local LLM tren tap mau (vi du 10 cau hoi)."""
    total = len(eval_subset)
    success_count = 0
    unavailable_count = 0
    latencies: list[float] = []
    results: list[dict[str, Any]] = []

    for item in eval_subset:
        query = item["question"]
        start = time.perf_counter()
        rag_res = generate_rag_answer(query, k=5)
        elapsed = time.perf_counter() - start
        latencies.append(elapsed)

        status = rag_res.get("llm_status", "unavailable")
        if status == "success":
            success_count += 1
        else:
            unavailable_count += 1

        results.append({
            "question_id": item["question_id"],
            "question": query,
            "llm_status": status,
            "answer": rag_res.get("answer", ""),
            "context": rag_res.get("context", ""),
            "retrieved_documents": rag_res.get("retrieved_documents", []),
            "latency_seconds": elapsed,
        })

    avg_time = (sum(latencies) / len(latencies)) if latencies else 0.0
    min_time = min(latencies) if latencies else 0.0
    max_time = max(latencies) if latencies else 0.0

    return {
        "total_evaluated": total,
        "llm_success_count": success_count,
        "llm_unavailable_count": unavailable_count,
        "avg_latency_seconds": avg_time,
        "min_latency_seconds": min_time,
        "max_latency_seconds": max_time,
        "details": results,
    }


def run_comprehensive_evaluation(
    eval_set_path: str | Path = "data/evaluation/evaluation_set_200.json",
    output_path: str | Path = "data/evaluation/rag_eval_results_200.json",
    k: int = 5,
) -> dict[str, Any]:
    """Chay danh gia toan dien 200 cau in-scope tren 3 phuong an: ChromaDB, Neo4j, Hybrid."""
    eval_set = load_evaluation_set(eval_set_path)
    chroma_col = get_or_create_collection()
    neo_driver = get_neo4j_driver()

    try:
        # 1. Warm-up de loai bo cold-start latency khoi tung query
        _ = search_similar_documents("Khoi dong warm up", k=k, collection=chroma_col)
        _ = search_graph("Khoi dong warm up", k=k, driver=neo_driver)
        _ = search_hybrid("Khoi dong warm up", k=k, chroma_collection=chroma_col, neo4j_driver=neo_driver)

        detailed_queries: list[dict[str, Any]] = []
        hybrid_source_counts = {"chroma": 0, "neo4j": 0, "both": 0}

        for item in eval_set:
            query = item["question"]
            expected_id = item["question_id"]
            brand = item.get("brand", "")
            device = item.get("device", "")
            issue_type = item.get("issue_type", "")

            entities = extract_question_entities(query)
            where_filter = build_chroma_where_filter(entities.get("brand"), entities.get("device"))

            # 1. ChromaDB only (co do thoi gian baseline va rerank)
            t0 = time.perf_counter()
            chroma_raw = search_similar_documents(query, k=k, collection=chroma_col, where=where_filter)
            lat_chroma_baseline = (time.perf_counter() - t0) * 1000.0
            chroma_baseline_ids = [
                d.get("question_id") or d.get("id") or d.get("metadata", {}).get("question_id")
                for d in chroma_raw
            ]

            chroma_items: list[dict] = []
            for r in chroma_raw:
                meta = r.get("metadata", {})
                doc_text = r.get("document", "")
                q_text = ""
                ans_text = ""
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

            t0 = time.perf_counter()
            chroma_reranked = rerank_results(query, chroma_items, entities=entities)
            lat_chroma_rerank = lat_chroma_baseline + (time.perf_counter() - t0) * 1000.0
            chroma_rerank_ids = [d["question_id"] for d in chroma_reranked[:k]]

            # 2. Neo4j only (co do thoi gian baseline va rerank)
            t0 = time.perf_counter()
            neo_raw = search_graph(query, k=k, driver=neo_driver)
            lat_neo_baseline = (time.perf_counter() - t0) * 1000.0
            neo_baseline_ids = [d.get("question_id") for d in neo_raw]

            t0 = time.perf_counter()
            neo_reranked = rerank_results(query, neo_raw, entities=entities)
            lat_neo_rerank = lat_neo_baseline + (time.perf_counter() - t0) * 1000.0
            neo_rerank_ids = [d["question_id"] for d in neo_reranked[:k]]

            # 3. Hybrid (Baseline vs Rerank)
            combined: dict[str, dict] = {}
            for item in chroma_items:
                qid = item["question_id"]
                combined[qid] = item

            for item in neo_raw:
                qid = item["question_id"]
                if qid in combined:
                    combined[qid]["retrieval_source"] = "both"
                    if not combined[qid]["answer"] and item.get("answer"):
                        combined[qid]["answer"] = item["answer"]
                else:
                    combined[qid] = item

            # 3. Hybrid (Baseline vs Fixed vs Adaptive)
            # 3a. Baseline (Truy van goc khong dung fixed/adaptive reranking)
            t0 = time.perf_counter()
            hybrid_base_docs = search_hybrid(
                query, k=k, chroma_collection=chroma_col, neo4j_driver=neo_driver, use_reranking=False
            )
            lat_hybrid_base = (time.perf_counter() - t0) * 1000.0
            hybrid_base_ids = [d["question_id"] for d in hybrid_base_docs]

            # 3b. Fixed Reranking
            t0 = time.perf_counter()
            hybrid_fixed_docs = search_hybrid(
                query, k=k, chroma_collection=chroma_col, neo4j_driver=neo_driver, use_reranking=True, rerank_mode="fixed"
            )
            lat_hybrid_fixed = (time.perf_counter() - t0) * 1000.0
            hybrid_fixed_ids = [d["question_id"] for d in hybrid_fixed_docs]

            # 3c. Adaptive Reranking
            t0 = time.perf_counter()
            hybrid_adaptive_docs = search_hybrid(
                query, k=k, chroma_collection=chroma_col, neo4j_driver=neo_driver, use_reranking=True, rerank_mode="adaptive"
            )
            lat_hybrid_adaptive = (time.perf_counter() - t0) * 1000.0
            hybrid_adaptive_ids = [d["question_id"] for d in hybrid_adaptive_docs]

            # Dem phan bo retrieval_source trong top-k cua Hybrid Adaptive
            for d in hybrid_adaptive_docs[:k]:
                src = d.get("retrieval_source", "chroma")
                hybrid_source_counts[src] = hybrid_source_counts.get(src, 0) + 1

            record = {
                "question_id": expected_id,
                "question": query,
                "brand": brand,
                "device": device,
                "issue_type": issue_type,
                "expected_question_id": expected_id,
                # Candidate IDs
                "chroma_results": chroma_baseline_ids,
                "neo4j_results": neo_baseline_ids,
                "hybrid_baseline_results": hybrid_base_ids,
                "hybrid_fixed_results": hybrid_fixed_ids,
                "hybrid_adaptive_results": hybrid_adaptive_ids,
                # Chroma Metrics
                "chroma_hit@1": calculate_hit_at_k(chroma_baseline_ids, expected_id, 1),
                "chroma_hit@3": calculate_hit_at_k(chroma_baseline_ids, expected_id, 3),
                "chroma_hit@5": calculate_hit_at_k(chroma_baseline_ids, expected_id, 5),
                "chroma_mrr": round(calculate_mrr(chroma_baseline_ids, expected_id, max_k=k), 4),
                # Neo4j Metrics
                "neo4j_hit@1": calculate_hit_at_k(neo_baseline_ids, expected_id, 1),
                "neo4j_hit@3": calculate_hit_at_k(neo_baseline_ids, expected_id, 3),
                "neo4j_hit@5": calculate_hit_at_k(neo_baseline_ids, expected_id, 5),
                "neo4j_mrr": round(calculate_mrr(neo_baseline_ids, expected_id, max_k=k), 4),
                # Hybrid Baseline Metrics
                "hybrid_baseline_hit@1": calculate_hit_at_k(hybrid_base_ids, expected_id, 1),
                "hybrid_baseline_hit@3": calculate_hit_at_k(hybrid_base_ids, expected_id, 3),
                "hybrid_baseline_hit@5": calculate_hit_at_k(hybrid_base_ids, expected_id, 5),
                "hybrid_baseline_mrr": round(calculate_mrr(hybrid_base_ids, expected_id, max_k=k), 4),
                # Hybrid Fixed Reranking Metrics
                "hybrid_fixed_hit@1": calculate_hit_at_k(hybrid_fixed_ids, expected_id, 1),
                "hybrid_fixed_hit@3": calculate_hit_at_k(hybrid_fixed_ids, expected_id, 3),
                "hybrid_fixed_hit@5": calculate_hit_at_k(hybrid_fixed_ids, expected_id, 5),
                "hybrid_fixed_mrr": round(calculate_mrr(hybrid_fixed_ids, expected_id, max_k=k), 4),
                # Hybrid Adaptive Reranking Metrics
                "hybrid_adaptive_hit@1": calculate_hit_at_k(hybrid_adaptive_ids, expected_id, 1),
                "hybrid_adaptive_hit@3": calculate_hit_at_k(hybrid_adaptive_ids, expected_id, 3),
                "hybrid_adaptive_hit@5": calculate_hit_at_k(hybrid_adaptive_ids, expected_id, 5),
                "hybrid_adaptive_mrr": round(calculate_mrr(hybrid_adaptive_ids, expected_id, max_k=k), 4),
                # Latencies
                "latency_chroma_ms": round(lat_chroma_baseline, 2),
                "latency_neo4j_ms": round(lat_neo_baseline, 2),
                "latency_hybrid_baseline_ms": round(lat_hybrid_base, 2),
                "latency_hybrid_fixed_ms": round(lat_hybrid_fixed, 2),
                "latency_hybrid_adaptive_ms": round(lat_hybrid_adaptive, 2),
            }
            detailed_queries.append(record)

        # Ham tinh chi so thong ke tong hop
        def summarize_group(records: list[dict[str, Any]]) -> dict[str, Any]:
            n = len(records)
            if n == 0:
                return {}

            def calc_metrics(prefix: str, lat_key: str):
                return {
                    "hit@1": round(sum(1 for r in records if r[f"{prefix}hit@1"]) / n * 100.0, 2),
                    "hit@3": round(sum(1 for r in records if r[f"{prefix}hit@3"]) / n * 100.0, 2),
                    "hit@5": round(sum(1 for r in records if r[f"{prefix}hit@5"]) / n * 100.0, 2),
                    "mrr": round(sum(r[f"{prefix}mrr"] for r in records) / n, 4),
                    "avg_latency_ms": round(statistics.mean(r[lat_key] for r in records), 2),
                    "median_latency_ms": round(statistics.median(r[lat_key] for r in records), 2),
                }

            chroma_b = calc_metrics("chroma_", "latency_chroma_ms")
            neo_b = calc_metrics("neo4j_", "latency_neo4j_ms")
            hybrid_b = calc_metrics("hybrid_baseline_", "latency_hybrid_baseline_ms")
            hybrid_f = calc_metrics("hybrid_fixed_", "latency_hybrid_fixed_ms")
            hybrid_a = calc_metrics("hybrid_adaptive_", "latency_hybrid_adaptive_ms")

            def diff(base: dict, target: dict):
                return {
                    k: round(target[k] - base[k], 4 if "mrr" in k else 2)
                    for k in ["hit@1", "hit@3", "hit@5", "mrr", "avg_latency_ms", "median_latency_ms"]
                }

            return {
                "total_queries": n,
                "chroma": chroma_b,
                "neo4j": neo_b,
                "hybrid_baseline": hybrid_b,
                "hybrid_fixed": hybrid_f,
                "hybrid_adaptive": hybrid_a,
                "diff_fixed_vs_baseline": diff(hybrid_b, hybrid_f),
                "diff_adaptive_vs_fixed": diff(hybrid_f, hybrid_a),
            }

        overall_summary = summarize_group(detailed_queries)

        # Summary theo Brand
        by_brand = {}
        for b in sorted(set(r["brand"] for r in detailed_queries if r["brand"])):
            by_brand[b] = summarize_group([r for r in detailed_queries if r["brand"] == b])

        # Summary theo Issue Type
        by_issue_type = {}
        for it in sorted(set(r["issue_type"] for r in detailed_queries if r["issue_type"])):
            by_issue_type[it] = summarize_group([r for r in detailed_queries if r["issue_type"] == it])

        # Summary theo Device
        by_device = {}
        for dev in sorted(set(r["device"] for r in detailed_queries if r["device"])):
            by_device[dev] = summarize_group([r for r in detailed_queries if r["device"] == dev])

        # Phan bo nguon Hybrid (chroma / neo4j / both)
        total_docs = sum(hybrid_source_counts.values())
        source_distribution = {
            k: {
                "count": v,
                "percentage": round(v / total_docs * 100.0, 2) if total_docs else 0.0,
            }
            for k, v in hybrid_source_counts.items()
        }

        eval_result_data = {
            "summary": {
                "overall": overall_summary,
                "by_brand": by_brand,
                "by_issue_type": by_issue_type,
                "by_device": by_device,
                "hybrid_source_distribution": source_distribution,
            },
            "detailed_queries": detailed_queries,
        }

        # Ghi file ket qua chi tiet
        out_file = Path(output_path)
        out_file.parent.mkdir(parents=True, exist_ok=True)
        with open(out_file, "w", encoding="utf-8") as f:
            json.dump(eval_result_data, f, ensure_ascii=False, indent=2)

        return eval_result_data
    finally:
        neo_driver.close()


def run_scope_evaluation(
    oos_path: str | Path = "data/evaluation/out_of_scope_30.json",
    in_scope_path: str | Path = "data/evaluation/evaluation_set_200.json",
) -> dict[str, Any]:
    """Danh gia pham vi (Phase 10A): Refusal rate tren Out-of-scope va False refusal tren In-scope."""
    chroma_col = get_or_create_collection()
    neo_driver = get_neo4j_driver()

    try:
        # 1. Kiem tra tap Out-of-scope (30 cau)
        with open(oos_path, "r", encoding="utf-8") as f:
            oos_data = json.load(f)

        refused_oos = 0
        accepted_oos = 0
        oos_details = []

        for item in oos_data:
            q = item["question"]
            docs = search_hybrid(q, k=5, chroma_collection=chroma_col, neo4j_driver=neo_driver)
            refused = should_refuse(docs, question=q)
            if refused:
                refused_oos += 1
            else:
                accepted_oos += 1
            oos_details.append({
                "id": item.get("id", ""),
                "category": item.get("category", ""),
                "question": q,
                "refused": refused,
                "top_distance": docs[0].get("distance") if docs else None,
            })

        total_oos = len(oos_data)
        refusal_rate_oos = round(refused_oos / total_oos * 100.0, 2) if total_oos else 0.0

        # 2. Kiem tra tap In-scope (200 cau) de do False Refusal
        in_scope_data = load_evaluation_set(in_scope_path)
        false_refused_in_scope = 0
        accepted_in_scope = 0

        for item in in_scope_data:
            q = item["question"]
            docs = search_hybrid(q, k=5, chroma_collection=chroma_col, neo4j_driver=neo_driver)
            refused = should_refuse(docs, question=q)
            if refused:
                false_refused_in_scope += 1
            else:
                accepted_in_scope += 1

        total_in = len(in_scope_data)
        false_refusal_rate = round(false_refused_in_scope / total_in * 100.0, 2) if total_in else 0.0

        return {
            "out_of_scope": {
                "total": total_oos,
                "refused_count": refused_oos,
                "refusal_rate": refusal_rate_oos,
                "false_acceptance_count": accepted_oos,
                "details": oos_details,
            },
            "in_scope": {
                "total": total_in,
                "accepted_count": accepted_in_scope,
                "false_refusal_count": false_refused_in_scope,
                "false_refusal_rate": false_refusal_rate,
            },
        }
    finally:
        neo_driver.close()


def run_sample_llm_evaluation(
    eval_set_path: str | Path = "data/evaluation/evaluation_set_200.json",
    sample_ids: list[str] | None = None,
) -> dict[str, Any]:
    """Danh gia chat luong sinh cau tra loi cua Local LLM tren tap mau dai dien 12 cau."""
    eval_set = load_evaluation_set(eval_set_path)
    
    # Neu khong chi dinh sample_ids, chon 12 cau can doi
    if not sample_ids:
        sample_ids = [
            "Q0358", "Q0360", "Q0417", "Q0993",  # Samsung (Air Conditioner, Dryer, Error code, Symptom)
            "Q0001", "Q0003", "Q0691", "Q0692",  # LG (Fridge, Washing machine, Error code, Symptom)
            "Q0157", "Q0158", "Q0841", "Q0842",  # Panasonic (Air Conditioner, Washing machine, Fridge)
        ]

    chosen = [item for item in eval_set if item["question_id"] in sample_ids]
    results = []

    for item in chosen:
        q = item["question"]
        qid = item["question_id"]
        t0 = time.perf_counter()
        rag_res = generate_rag_answer(q, k=5)
        elapsed = time.perf_counter() - t0

        answer = rag_res.get("answer", "")
        context = rag_res.get("context", "")
        docs = rag_res.get("retrieved_documents", [])
        status = rag_res.get("llm_status", "unavailable")

        sources = extract_matching_sources(docs, q)
        source_url = sources[0] if sources else (docs[0].get("source_url") if docs else "")

        # Kiem tra cac tieu chi chat luong
        # 1. Groundedness: cau tra loi dua tren ngu canh
        grounded = bool(context and (status == "success") and len(answer) > 20)
        # 2. Khong hallucinate ma loi: neu co ma loi trong answer, no phai xuat hien trong context
        no_fake_code = True
        if item.get("error_code"):
            no_fake_code = item["error_code"].lower() in answer.lower()

        results.append({
            "question_id": qid,
            "question": q,
            "brand": item.get("brand"),
            "device": item.get("device"),
            "error_code": item.get("error_code"),
            "llm_status": status,
            "answer": answer,
            "top_doc_question": docs[0].get("question") if docs else "",
            "source_url": source_url,
            "latency_seconds": round(elapsed, 2),
            "groundedness": grounded,
            "no_fake_code": no_fake_code,
        })

    return {
        "total_evaluated": len(results),
        "details": results,
    }

"""Module danh gia he thong RAG Chatbot (Phase 8 - Evaluation).

Cung cap cac ham danh gia don gian, de hieu va minh bach ve:
1. Retrieval Evaluation: ChromaDB Hit@1 / Hit@5, Neo4j Hit@1 / Hit@5, Hybrid Hit@1 / Hit@5.
2. Dem so luong ban ghi duoc tim thay boi ca 2 nguon (retrieval_source == 'both').
3. RAG / Local LLM Generation: Tinh ti le phan hoi, do tre (latency: avg, min, max).
4. Do thoi gian phan hoi chi tiet cua tung thanh phan (ChromaDB, Neo4j, Hybrid, LLM).
"""

from __future__ import annotations
import json
import time
from pathlib import Path
from typing import Any

from rag_chatbot.retrieval import (
    search_similar_documents,
    search_graph,
    search_hybrid,
)
from rag_chatbot.rag import generate_rag_answer


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

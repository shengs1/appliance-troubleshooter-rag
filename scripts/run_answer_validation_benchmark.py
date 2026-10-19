"""Script chay thuc nghiem danh gia Answer Validation voi Ollama Qwen2.5:7b tren 25 cau mau.

Tuan thu Phase Answer Validation:
1. Chay hybrid retrieval hien tai (FROZEN)
2. Xay dung context
3. Goi Ollama qwen2.5:7b sinh cau tra loi
4. Validate answer bang deterministic rule-based validator
5. Do latency: retrieval, LLM, validation, total
6. Tinh toan metrics va xuat JSON
"""

import json
import time
import sys
from pathlib import Path

if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

from rag_chatbot.answer_validator import validate_answer
from rag_chatbot.rag import (
    build_context,
    call_local_llm,
    create_prompt,
    strip_sources_from_answer,
)
from rag_chatbot.retrieval import extract_question_entities, search_hybrid


def run_benchmark():
    input_file = Path("data/evaluation/answer_validation_set.json")
    output_file = Path("data/evaluation/answer_validation_results.json")

    with open(input_file, "r", encoding="utf-8") as f:
        queries = json.load(f)

    print(f"=== BẮT ĐẦU BENCHMARK ANSWER VALIDATION TRÊN {len(queries)} CÂU ===")

    results = []
    
    for idx, item in enumerate(queries, 1):
        qid = item["question_id"]
        q_text = item["question"]
        print(f"[{idx}/{len(queries)}] Processing {qid}: {q_text[:40]}...")

        # 1. Retrieval Latency
        t0 = time.perf_counter()
        retrieved_docs = search_hybrid(q_text, k=5)
        retrieval_latency = (time.perf_counter() - t0) * 1000

        # 2. Context & Prompt
        context = build_context(retrieved_docs)
        prompt = create_prompt(q_text, context)

        # 3. LLM Generation Latency
        t1 = time.perf_counter()
        try:
            raw_answer = call_local_llm(prompt, model="qwen2.5:7b")
            clean_answer = strip_sources_from_answer(raw_answer)
            llm_status = "success"
        except Exception as e:
            raw_answer = ""
            clean_answer = f"[Lỗi LLM]: {e}"
            llm_status = "error"
        llm_latency = (time.perf_counter() - t1) * 1000

        # 4. Validation Latency
        t2 = time.perf_counter()
        entities = extract_question_entities(q_text)
        val_res = validate_answer(
            question=q_text,
            answer=clean_answer,
            retrieved_documents=retrieved_docs,
            entities=entities,
        )
        val_latency = (time.perf_counter() - t2) * 1000

        total_latency = retrieval_latency + llm_latency + val_latency

        record = {
            "question_id": qid,
            "question": q_text,
            "expected_brand": item.get("expected_brand"),
            "expected_device": item.get("expected_device"),
            "expected_error_code": item.get("expected_error_code"),
            "issue_type": item.get("issue_type"),
            "answer": clean_answer,
            "llm_status": llm_status,
            "validation_status": val_res["status"],
            "grounded": val_res["grounded"],
            "brand_consistent": val_res["brand_consistent"],
            "device_consistent": val_res["device_consistent"],
            "error_code_consistent": val_res["error_code_consistent"],
            "hallucination_detected": val_res["hallucination_detected"],
            "source_consistent": val_res["source_consistent"],
            "validation_reasons": val_res["reasons"],
            "retrieval_latency_ms": round(retrieval_latency, 2),
            "llm_latency_ms": round(llm_latency, 2),
            "validation_latency_ms": round(val_latency, 2),
            "total_latency_ms": round(total_latency, 2),
        }
        results.append(record)

    # 5. Tinh tong hop metrics
    n = len(results)
    pass_count = sum(1 for r in results if r["validation_status"] == "pass")
    warning_count = sum(1 for r in results if r["validation_status"] == "warning")
    fail_count = sum(1 for r in results if r["validation_status"] == "fail")

    grounded_count = sum(1 for r in results if r["grounded"])
    brand_cons_count = sum(1 for r in results if r["brand_consistent"])
    device_cons_count = sum(1 for r in results if r["device_consistent"])
    error_code_cons_count = sum(1 for r in results if r["error_code_consistent"])
    hallucination_count = sum(1 for r in results if r["hallucination_detected"])
    source_cons_count = sum(1 for r in results if r["source_consistent"])

    mean_retrieval_lat = sum(r["retrieval_latency_ms"] for r in results) / n
    mean_llm_lat = sum(r["llm_latency_ms"] for r in results) / n
    mean_val_lat = sum(r["validation_latency_ms"] for r in results) / n
    mean_total_lat = sum(r["total_latency_ms"] for r in results) / n

    summary = {
        "total_queries": n,
        "pass_count": pass_count,
        "pass_rate": round(pass_count / n * 100, 2),
        "warning_count": warning_count,
        "warning_rate": round(warning_count / n * 100, 2),
        "fail_count": fail_count,
        "fail_rate": round(fail_count / n * 100, 2),
        "grounded_count": grounded_count,
        "grounded_rate": round(grounded_count / n * 100, 2),
        "brand_consistent_count": brand_cons_count,
        "brand_consistency_rate": round(brand_cons_count / n * 100, 2),
        "device_consistent_count": device_cons_count,
        "device_consistency_rate": round(device_cons_count / n * 100, 2),
        "error_code_consistent_count": error_code_cons_count,
        "error_code_consistency_rate": round(error_code_cons_count / n * 100, 2),
        "hallucination_count": hallucination_count,
        "hallucination_rate": round(hallucination_count / n * 100, 2),
        "source_consistent_count": source_cons_count,
        "source_consistency_rate": round(source_cons_count / n * 100, 2),
        "mean_retrieval_latency_ms": round(mean_retrieval_lat, 2),
        "mean_llm_latency_ms": round(mean_llm_lat, 2),
        "mean_validation_latency_ms": round(mean_val_lat, 2),
        "mean_total_latency_ms": round(mean_total_lat, 2),
    }

    output_payload = {
        "summary": summary,
        "results": results,
    }

    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(output_payload, f, ensure_ascii=False, indent=2)

    print("\n=== HOÀN THÀNH BENCHMARK ===")
    print(f"Tổng số câu: {n}")
    print(f"Pass Rate: {summary['pass_rate']}% ({pass_count}/{n})")
    print(f"Warning Rate: {summary['warning_rate']}% ({warning_count}/{n})")
    print(f"Fail Rate: {summary['fail_rate']}% ({fail_count}/{n})")
    print(f"Groundedness Rate: {summary['grounded_rate']}%")
    print(f"Brand Consistency Rate: {summary['brand_consistency_rate']}%")
    print(f"Device Consistency Rate: {summary['device_consistency_rate']}%")
    print(f"Error Code Consistency Rate: {summary['error_code_consistency_rate']}%")
    print(f"Hallucination Rate: {summary['hallucination_rate']}%")
    print(f"Source Consistency Rate: {summary['source_consistency_rate']}%")
    print(f"Mean Retrieval Latency: {summary['mean_retrieval_latency_ms']} ms")
    print(f"Mean LLM Latency: {summary['mean_llm_latency_ms']} ms")
    print(f"Mean Validation Latency: {summary['mean_validation_latency_ms']} ms")
    print(f"Mean Total Latency: {summary['mean_total_latency_ms']} ms")


if __name__ == "__main__":
    run_benchmark()

"""Script thuc thi danh gia toan dien Phase 10B.

Bao gom:
1. 200 cau In-scope: So sanh ChromaDB, Neo4j, Hybrid (Hit@1, Hit@3, Hit@5, MRR, Latency).
2. 30 cau Out-of-scope + 200 cau In-scope: Do ti le Refusal va False Refusal.
3. 12 cau Dai dien LLM: Do do tin cay (groundedness), hallucination va do tre local LLM.
"""

import json
from pathlib import Path
import sys

# Dam bao in tieng Viet tren Windows khong bi loi cp1252
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from rag_chatbot.evaluation import (
    run_comprehensive_evaluation,
    run_scope_evaluation,
    run_sample_llm_evaluation,
)


def main():
    print("=" * 70)
    print("PHASE 10B - COMPREHENSIVE RAG BENCHMARK EXECUTION")
    print("=" * 70)

    # 1. 200 cau in-scope
    print("\n[1/3] Dang danh gia 200 cau in-scope tren ChromaDB, Neo4j va Hybrid...")
    eval_res = run_comprehensive_evaluation(
        eval_set_path="data/evaluation/evaluation_set_200.json",
        output_path="data/evaluation/rag_eval_results_200.json",
        k=5,
    )

    # In bang ket qua tong hop: Baseline vs Fixed vs Adaptive
    overall = eval_res["summary"]["overall"]
    print("\n" + "=" * 85)
    print("BANG SO SANH RETRIEVAL: BASELINE VS FIXED RERANKING VS ADAPTIVE RERANKING")
    print("=" * 85)
    header = f"{'Metric':<20} | {'Baseline':<12} | {'Fixed':<12} | {'Adaptive':<12} | {'Δ Adapt vs Fixed':<18}"
    print(header)
    print("-" * 85)

    base = overall["hybrid_baseline"]
    fixed = overall["hybrid_fixed"]
    adapt = overall["hybrid_adaptive"]
    diff = overall["diff_adaptive_vs_fixed"]

    metrics = [
        ("Hit@1", f"{base['hit@1']}%", f"{fixed['hit@1']}%", f"{adapt['hit@1']}%", f"{'+' if diff['hit@1'] > 0 else ''}{diff['hit@1']}%"),
        ("Hit@3", f"{base['hit@3']}%", f"{fixed['hit@3']}%", f"{adapt['hit@3']}%", f"{'+' if diff['hit@3'] > 0 else ''}{diff['hit@3']}%"),
        ("Hit@5", f"{base['hit@5']}%", f"{fixed['hit@5']}%", f"{adapt['hit@5']}%", f"{'+' if diff['hit@5'] > 0 else ''}{diff['hit@5']}%"),
        ("MRR", f"{base['mrr']}", f"{fixed['mrr']}", f"{adapt['mrr']}", f"{'+' if diff['mrr'] > 0 else ''}{diff['mrr']}"),
        ("Mean Latency", f"{base['avg_latency_ms']} ms", f"{fixed['avg_latency_ms']} ms", f"{adapt['avg_latency_ms']} ms", f"{'+' if diff['avg_latency_ms'] > 0 else ''}{diff['avg_latency_ms']} ms"),
        ("Median Latency", f"{base['median_latency_ms']} ms", f"{fixed['median_latency_ms']} ms", f"{adapt['median_latency_ms']} ms", f"{'+' if diff['median_latency_ms'] > 0 else ''}{diff['median_latency_ms']} ms"),
    ]

    for label, b_str, f_str, a_str, d_str in metrics:
        print(f"{label:<20} | {b_str:<12} | {f_str:<12} | {a_str:<12} | {d_str:<18}")

    print("\n--- SUBGROUP COMPARISON (BY ISSUE TYPE) ---")
    for it, sub in eval_res["summary"]["by_issue_type"].items():
        sb_b = sub["hybrid_baseline"]
        sb_f = sub["hybrid_fixed"]
        sb_a = sub["hybrid_adaptive"]
        print(f"[{it:<18}] Baseline: Hit@1={sb_b['hit@1']}%, MRR={sb_b['mrr']} | Fixed: Hit@1={sb_f['hit@1']}%, MRR={sb_f['mrr']} | Adapt: Hit@1={sb_a['hit@1']}%, MRR={sb_a['mrr']}")

    print("\n--- SUBGROUP COMPARISON (BY BRAND) ---")
    for b_name, sub in eval_res["summary"]["by_brand"].items():
        sb_b = sub["hybrid_baseline"]
        sb_f = sub["hybrid_fixed"]
        sb_a = sub["hybrid_adaptive"]
        print(f"[{b_name:<12}] Baseline: Hit@1={sb_b['hit@1']}%, MRR={sb_b['mrr']} | Fixed: Hit@1={sb_f['hit@1']}%, MRR={sb_f['mrr']} | Adapt: Hit@1={sb_a['hit@1']}%, MRR={sb_a['mrr']}")

    print("\n--- PHAN BO NGUON DOCS CUA HYBRID ADAPTIVE ---")
    for src, info in eval_res["summary"]["hybrid_source_distribution"].items():
        print(f"  {src}: {info['count']} ({info['percentage']}%)")

    # 2. Scope evaluation
    print("\n[2/3] Dang danh gia Scope Refusal (30 OOS + 200 In-scope)...")
    scope_res = run_scope_evaluation(
        oos_path="data/evaluation/out_of_scope_30.json",
        in_scope_path="data/evaluation/evaluation_set_200.json",
    )
    oos = scope_res["out_of_scope"]
    ins = scope_res["in_scope"]
    print(f"  Out-of-scope Refusal Rate: {oos['refused_count']}/{oos['total']} ({oos['refusal_rate']}%)")
    print(f"  In-scope False Refusal Rate: {ins['false_refusal_count']}/{ins['total']} ({ins['false_refusal_rate']}%)")

    # 3. Sample LLM evaluation
    print("\n[3/3] Dang danh gia Local LLM tren 12 cau dai dien...")
    llm_res = run_sample_llm_evaluation(
        eval_set_path="data/evaluation/evaluation_set_200.json",
    )
    print(f"  Tong so cau danh gia LLM: {llm_res['total_evaluated']}")
    for d in llm_res["details"]:
        status = d["llm_status"]
        grounded = "OK" if d["groundedness"] else "FAIL"
        fake_code = "OK" if d["no_fake_code"] else "FAIL"
        print(f"  [{d['question_id']}] {d['question'][:30]}... -> Status: {status}, Grounded: {grounded}, NoFakeCode: {fake_code}, Latency: {d['latency_seconds']}s")

    # Luu ket qua tong hop day du
    combined_file = Path("data/evaluation/rag_eval_results_200.json")
    with open(combined_file, "r", encoding="utf-8") as f:
        full_data = json.load(f)

    full_data["summary"]["scope_evaluation"] = {
        "out_of_scope_total": oos["total"],
        "out_of_scope_refused": oos["refused_count"],
        "out_of_scope_refusal_rate": oos["refusal_rate"],
        "in_scope_total": ins["total"],
        "in_scope_false_refused": ins["false_refusal_count"],
        "in_scope_false_refusal_rate": ins["false_refusal_rate"],
    }
    full_data["scope_details"] = scope_res["out_of_scope"]["details"]
    full_data["sample_llm_evaluation"] = llm_res

    with open(combined_file, "w", encoding="utf-8") as f:
        json.dump(full_data, f, ensure_ascii=False, indent=2)

    print(f"\nDa luu toan bo ket qua vao: {combined_file.resolve()}")


if __name__ == "__main__":
    main()

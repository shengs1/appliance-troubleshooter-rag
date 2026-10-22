import json
import re
import sys
import time
import unicodedata
from pathlib import Path
import pandas as pd

sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, ".")

from rag_chatbot.evaluation import load_evaluation_set, calculate_hit_at_k, calculate_mrr
from rag_chatbot.chroma_db import get_or_create_collection
from rag_chatbot.neo4j_db import get_neo4j_driver
from rag_chatbot.retrieval import search_hybrid, extract_question_entities

TONE_PAIRS = [
    ("oà", "òa"), ("oá", "óa"), ("oả", "ỏa"), ("oã", "õa"), ("oạ", "ọa"),
    ("uỳ", "ùy"), ("uý", "úy"), ("uỷ", "ủy"), ("uỹ", "ũy"), ("uỵ", "ụy"),
    ("oè", "òe"), ("oé", "óe"), ("oẻ", "ỏe"), ("oẽ", "õe"), ("oẹ", "ọe"),
]

def normalize_question_text(text: str) -> str:
    if not text:
        return ""
    t = unicodedata.normalize('NFC', text.lower())
    for old, new in TONE_PAIRS:
        t = t.replace(old, new)
    t = re.sub(r'[^\w\s\-]', ' ', t)
    return " ".join(t.split())

def is_exact_question_match(q1: str, q2: str) -> bool:
    n1 = normalize_question_text(q1)
    n2 = normalize_question_text(q2)
    return bool(n1 and n2 and n1 == n2)

def rerank_with_exact_bonus(
    query: str,
    candidates: list[dict],
    entities: dict,
    exact_match_bonus: float = 0.0,
) -> list[dict]:
    if not candidates:
        return []

    target_brand = entities.get("brand")
    target_device = entities.get("device")
    target_error_code = entities.get("error_code")

    b_bonus = 0.08
    d_bonus = 0.08
    e_bonus = 0.20
    both_bonus = 0.02

    scored = []
    for item in candidates:
        dist = item.get("distance")
        semantic_score = max(0.0, 1.0 - float(dist)) if dist is not None else 0.0
        score = semantic_score

        item_brand = item.get("brand", "")
        item_device = item.get("device", "")
        item_code = item.get("error_code", "")
        item_q = item.get("question", "")

        applied_bonuses = {"semantic": round(semantic_score, 4)}

        # 1. Brand bonus
        if target_brand and item_brand and target_brand.lower() == item_brand.lower():
            score += b_bonus
            applied_bonuses["brand"] = b_bonus
        # 2. Device bonus
        if target_device and item_device and target_device.lower() == item_device.lower():
            score += d_bonus
            applied_bonuses["device"] = d_bonus
        # 3. Error code bonus
        if target_error_code and item_code:
            codes = [c.strip().lower() for c in item_code.split(',')]
            if target_error_code.lower() in codes:
                score += e_bonus
                applied_bonuses["error_code"] = e_bonus
        # 4. Both source bonus
        if item.get("retrieval_source") == "both":
            score += both_bonus
            applied_bonuses["both"] = both_bonus

        # 5. Exact question match bonus
        is_exact = is_exact_question_match(query, item_q)
        if exact_match_bonus > 0.0 and is_exact:
            score += exact_match_bonus
            applied_bonuses["exact_question"] = exact_match_bonus

        item_copy = dict(item)
        item_copy["score"] = round(score, 4)
        item_copy["applied_bonuses"] = applied_bonuses
        item_copy["is_exact_match"] = is_exact
        scored.append((score, item_copy))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [x[1] for x in scored]

def main():
    print("Loading data...")
    eval_200 = load_evaluation_set("data/evaluation/evaluation_set_200.json")
    chroma_col = get_or_create_collection()
    neo_driver = get_neo4j_driver()

    df = pd.read_excel('data/raw/dataset.xlsx', sheet_name='DATA_CLEAN_TECH')
    df_by_id = {str(row['ID']).strip(): row for _, row in df.iterrows()}

    print(f"Total evaluation questions: {len(eval_200)}")

    # 1. Retrieval pool
    pools = []
    for item in eval_200:
        q = item.get("question") or item.get("query")
        ent = extract_question_entities(q)
        t0 = time.perf_counter()
        raw = search_hybrid(q, k=10, chroma_collection=chroma_col, neo4j_driver=neo_driver, use_reranking=False)
        lat = (time.perf_counter() - t0) * 1000.0
        pools.append({"item": item, "entities": ent, "raw": raw, "base_lat": lat})

    # 2. Run Baseline (bonus=0.0) and Bonus=0.02
    results_by_weight = {}
    ranked_by_weight = {}

    for bw in [0.0, 0.02]:
        hit1, hit3, hit5 = 0, 0, 0
        total_mrr = 0.0
        latencies = []
        all_ranked = []

        for p in pools:
            q = p["item"]["question"]
            exp = p["item"]["question_id"]
            ent = p["entities"]
            cand = p["raw"]
            base_lat = p["base_lat"]

            t0 = time.perf_counter()
            ranked = rerank_with_exact_bonus(q, cand, ent, exact_match_bonus=bw)[:5]
            lat = base_lat + (time.perf_counter() - t0) * 1000.0
            latencies.append(lat)

            ids = [d["question_id"] for d in ranked]
            h1 = calculate_hit_at_k(ids, exp, 1)
            h3 = calculate_hit_at_k(ids, exp, 3)
            h5 = calculate_hit_at_k(ids, exp, 5)
            rr = calculate_mrr(ids, exp, 5)

            if h1: hit1 += 1
            if h3: hit3 += 1
            if h5: hit5 += 1
            total_mrr += rr

            all_ranked.append({
                "question_id": exp,
                "question": q,
                "brand": p["item"].get("brand", ""),
                "device": p["item"].get("device", ""),
                "top_ids": ids,
                "top1_id": ids[0] if ids else "",
                "hit1": h1,
                "hit3": h3,
                "hit5": h5,
                "mrr": rr,
                "ranked_candidates": ranked,
            })

        n = len(eval_200)
        results_by_weight[bw] = {
            "hit@1": round(hit1 / n * 100.0, 2),
            "hit@1_count": hit1,
            "hit@3": round(hit3 / n * 100.0, 2),
            "hit@3_count": hit3,
            "hit@5": round(hit5 / n * 100.0, 2),
            "hit@5_count": hit5,
            "mrr": round(total_mrr / n, 4),
            "avg_latency_ms": round(sum(latencies) / n, 2),
            "errors_count": n - hit1,
        }
        ranked_by_weight[bw] = all_ranked

    print("\n=== METRIC COMPARISON ===")
    print(f"Baseline (bonus=0.0): Hit@1={results_by_weight[0.0]['hit@1']}% ({results_by_weight[0.0]['hit@1_count']}/200), Hit@3={results_by_weight[0.0]['hit@3']}%, Hit@5={results_by_weight[0.0]['hit@5']}%, MRR={results_by_weight[0.0]['mrr']}, Latency={results_by_weight[0.0]['avg_latency_ms']} ms")
    print(f"Bonus = 0.02:         Hit@1={results_by_weight[0.02]['hit@1']}% ({results_by_weight[0.02]['hit@1_count']}/200), Hit@3={results_by_weight[0.02]['hit@3']}%, Hit@5={results_by_weight[0.02]['hit@5']}%, MRR={results_by_weight[0.02]['mrr']}, Latency={results_by_weight[0.02]['avg_latency_ms']} ms")

    # 3. Find all failures where Expected ID != Predicted Top-1 ID under bonus=0.02
    failures_002 = []
    base_ranked_map = {r["question_id"]: r for r in ranked_by_weight[0.0]}

    for r in ranked_by_weight[0.02]:
        exp = r["question_id"]
        top1 = r["top1_id"]
        if exp != top1:
            base_r = base_ranked_map[exp]
            exp_row = df_by_id.get(exp)
            top1_row = df_by_id.get(top1)

            exp_q_clean = str(exp_row.get('Câu_hỏi_đã_làm_sạch', '')) if exp_row is not None else ""
            top1_q_clean = str(top1_row.get('Câu_hỏi_đã_làm_sạch', '')) if top1_row is not None else ""
            exp_cause = str(exp_row.get('Nguyên_nhân', '')) if exp_row is not None else ""
            top1_cause = str(top1_row.get('Nguyên_nhân', '')) if top1_row is not None else ""
            exp_fix = str(exp_row.get('Cách_khắc_phục', '')) if exp_row is not None else ""
            top1_fix = str(top1_row.get('Cách_khắc_phục', '')) if top1_row is not None else ""
            exp_dg = str(exp_row.get('Duplicate_Group', '')) if exp_row is not None and pd.notna(exp_row.get('Duplicate_Group')) else ""
            top1_dg = str(top1_row.get('Duplicate_Group', '')) if top1_row is not None and pd.notna(top1_row.get('Duplicate_Group')) else ""
            exp_issue = str(exp_row.get('Issue_ID', '')) if exp_row is not None and pd.notna(exp_row.get('Issue_ID')) else ""
            top1_issue = str(top1_row.get('Issue_ID', '')) if top1_row is not None and pd.notna(top1_row.get('Issue_ID')) else ""
            exp_code = str(exp_row.get('Mã_lỗi', '')) if exp_row is not None and pd.notna(exp_row.get('Mã_lỗi')) else ""
            top1_code = str(top1_row.get('Mã_lỗi', '')) if top1_row is not None and pd.notna(top1_row.get('Mã_lỗi')) else ""

            exp_cand = next((c for c in r["ranked_candidates"] if c["question_id"] == exp), None)
            top1_cand = r["ranked_candidates"][0] if r["ranked_candidates"] else None

            # Rank of expected in top candidates
            try:
                exp_rank = r["top_ids"].index(exp) + 1
            except ValueError:
                exp_rank = ">5"

            failures_002.append({
                "expected_id": exp,
                "predicted_top1_id": top1,
                "query": r["question"],
                "expected_rank": exp_rank,
                "base_top1_id": base_r["top1_id"],
                "exp_data": {
                    "question_clean": exp_q_clean,
                    "cause": exp_cause,
                    "fix": exp_fix,
                    "duplicate_group": exp_dg,
                    "issue_id": exp_issue,
                    "error_code": exp_code,
                    "score": exp_cand.get("score") if exp_cand else None,
                    "distance": exp_cand.get("distance") if exp_cand else None,
                    "bonuses": exp_cand.get("applied_bonuses") if exp_cand else None,
                    "is_exact_match": exp_cand.get("is_exact_match") if exp_cand else False,
                },
                "top1_data": {
                    "question_clean": top1_q_clean,
                    "cause": top1_cause,
                    "fix": top1_fix,
                    "duplicate_group": top1_dg,
                    "issue_id": top1_issue,
                    "error_code": top1_code,
                    "score": top1_cand.get("score") if top1_cand else None,
                    "distance": top1_cand.get("distance") if top1_cand else None,
                    "bonuses": top1_cand.get("applied_bonuses") if top1_cand else None,
                    "is_exact_match": top1_cand.get("is_exact_match") if top1_cand else False,
                }
            })

    print(f"\nTotal failures under bonus=0.02: {len(failures_002)}")
    output_path = "data/evaluation/bonus_002_failures_analysis.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump({
            "metrics": results_by_weight,
            "total_failures": len(failures_002),
            "failures": failures_002
        }, f, ensure_ascii=False, indent=2)
    print(f"Saved failure analysis to {output_path}")

    # Also list rescued cases
    rescued = []
    for r in ranked_by_weight[0.02]:
        exp = r["question_id"]
        top1_new = r["top1_id"]
        top1_old = base_ranked_map[exp]["top1_id"]
        if top1_old != exp and top1_new == exp:
            rescued.append({"id": exp, "query": r["question"], "old_top1": top1_old, "new_top1": top1_new})

    print(f"\nRescued cases ({len(rescued)}):")
    for rc in rescued:
        print(f"  + {rc['id']}: '{rc['query']}' (was {rc['old_top1']})")

if __name__ == "__main__":
    main()

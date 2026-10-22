import json
import re
import sys
import time
import unicodedata
from pathlib import Path

sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, ".")

from rag_chatbot.evaluation import load_evaluation_set, calculate_hit_at_k, calculate_mrr
from rag_chatbot.chroma_db import get_or_create_collection
from rag_chatbot.neo4j_db import get_neo4j_driver
from rag_chatbot.retrieval import search_hybrid, extract_question_entities

# Standard tone normalization
TONE_PAIRS = [
    ("oà", "òa"), ("oá", "óa"), ("oả", "ỏa"), ("oã", "õa"), ("oạ", "ọa"),
    ("uỳ", "ùy"), ("uý", "úy"), ("uỷ", "ủy"), ("uỹ", "ũy"), ("uỵ", "ụy"),
    ("oè", "òe"), ("oé", "óe"), ("oẻ", "ỏe"), ("oẽ", "õe"), ("oẹ", "ọe"),
]

def normalize_question_text(text: str) -> str:
    """Chuẩn hóa Unicode NFC, khoảng trắng và dấu câu cho câu hỏi."""
    if not text:
        return ""
    # 1. Unicode NFC
    t = unicodedata.normalize('NFC', text.lower())
    # 2. Tone mark standardization
    for old, new in TONE_PAIRS:
        t = t.replace(old, new)
    # 3. Strip punctuation
    t = re.sub(r'[^\w\s\-]', ' ', t)
    # 4. Collapse whitespace
    return " ".join(t.split())

def is_exact_question_match(q1: str, q2: str) -> bool:
    """Kiểm tra hai câu hỏi có trùng khớp hoàn toàn sau chuẩn hóa hay không."""
    n1 = normalize_question_text(q1)
    n2 = normalize_question_text(q2)
    return bool(n1 and n2 and n1 == n2)

def rerank_with_exact_bonus(
    query: str,
    candidates: list[dict],
    entities: dict,
    exact_match_bonus: float = 0.0,
) -> list[dict]:
    """Rerank with brand, device, error_code, both + exact_question_match_bonus."""
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

        # 1. Brand bonus
        if target_brand and item_brand and target_brand.lower() == item_brand.lower():
            score += b_bonus
        # 2. Device bonus
        if target_device and item_device and target_device.lower() == item_device.lower():
            score += d_bonus
        # 3. Error code bonus (hỗ trợ cả mã gộp dấu phẩy)
        if target_error_code and item_code:
            codes = [c.strip().lower() for c in item_code.split(',')]
            if target_error_code.lower() in codes:
                score += e_bonus
        # 4. Both source bonus
        if item.get("retrieval_source") == "both":
            score += both_bonus

        # 5. Exact question match bonus (THAY ĐỔI DUY NHẤT)
        if exact_match_bonus > 0.0 and is_exact_question_match(query, item_q):
            score += exact_match_bonus

        item_copy = dict(item)
        item_copy["score"] = round(score, 4)
        scored.append((score, item_copy))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [x[1] for x in scored]

def evaluate_on_set(dataset, chroma_col, neo_driver, bonus_weights):
    results = []
    pools = []
    n = len(dataset)

    # Cache raw retrieval
    for item in dataset:
        q = item.get("question") or item.get("query")
        ent = extract_question_entities(q)
        t0 = time.perf_counter()
        raw = search_hybrid(q, k=10, chroma_collection=chroma_col, neo4j_driver=neo_driver, use_reranking=False)
        lat = (time.perf_counter() - t0) * 1000.0
        pools.append({"item": item, "entities": ent, "raw": raw, "base_lat": lat})

    baseline_top1_map = {}

    for bw in bonus_weights:
        hit1, hit3, hit5 = 0, 0, 0
        total_mrr = 0.0
        latencies = []
        rescued = []
        regressed = []

        for p in pools:
            q = p["item"].get("question") or p["item"].get("query")
            exp = p["item"].get("expected_primary_id") or p["item"].get("question_id")
            ent = p["entities"]
            cand = p["raw"]
            base_lat = p["base_lat"]

            t0 = time.perf_counter()
            ranked = rerank_with_exact_bonus(q, cand, ent, exact_match_bonus=bw)[:5]
            lat = base_lat + (time.perf_counter() - t0) * 1000.0
            latencies.append(lat)

            ids = [d["question_id"] for d in ranked]
            top1 = ids[0] if ids else ""

            if bw == 0.0:
                baseline_top1_map[exp] = top1

            h1 = calculate_hit_at_k(ids, exp, 1)
            h3 = calculate_hit_at_k(ids, exp, 3)
            h5 = calculate_hit_at_k(ids, exp, 5)
            rr = calculate_mrr(ids, exp, 5)

            if h1: hit1 += 1
            if h3: hit3 += 1
            if h5: hit5 += 1
            total_mrr += rr

            if bw > 0.0:
                base_top1 = baseline_top1_map.get(exp)
                if base_top1 != exp and top1 == exp:
                    rescued.append({"id": exp, "q": q, "old": base_top1, "new": top1})
                elif base_top1 == exp and top1 != exp:
                    regressed.append({"id": exp, "q": q, "old": base_top1, "new": top1})

        res = {
            "bonus_weight": bw,
            "hit@1": round(hit1 / n * 100.0, 2),
            "hit@3": round(hit3 / n * 100.0, 2),
            "hit@5": round(hit5 / n * 100.0, 2),
            "mrr": round(total_mrr / n, 4),
            "avg_latency_ms": round(sum(latencies) / n, 2),
            "rescued_count": len(rescued),
            "regressed_count": len(regressed),
            "rescued": rescued,
            "regressed": regressed,
        }
        results.append(res)
        label = "Baseline (bonus=0.0)" if bw == 0.0 else f"Exact Bonus={bw:.2f}"
        print(f"[{label:<22}] Hit@1: {res['hit@1']:>5.1f}% | Hit@3: {res['hit@3']:>5.1f}% | Hit@5: {res['hit@5']:>5.1f}% | MRR: {res['mrr']:>6.4f} | Lat: {res['avg_latency_ms']:>6.2f} ms | +{len(rescued)} / -{len(regressed)}")

    return results

def main():
    chroma_col = get_or_create_collection()
    neo_driver = get_neo4j_driver()

    weights = [0.0, 0.01, 0.02, 0.03, 0.04, 0.05, 0.06]

    print("\n=======================================================")
    print("1. THỬ NGHIỆM TRỌNG SỐ TRÊN DEVELOPMENT SET (100 câu)")
    print("=======================================================")
    dev_100 = load_evaluation_set("data/evaluation/reranking_dev_100.json")
    dev_res = evaluate_on_set(dev_100, chroma_col, neo_driver, weights)

    # Tìm trọng số tốt nhất trên dev
    best_dev = max(dev_res, key=lambda x: (x["hit@1"], x["mrr"], -x["regressed_count"]))
    best_weight = best_dev["bonus_weight"]
    print(f"\n-> Trọng số tối ưu trên Development Set: {best_weight} (Hit@1 = {best_dev['hit@1']}%, MRR = {best_dev['mrr']})")

    print("\n=======================================================")
    print(f"2. CHẠY TRÊN EVALUATION SET (200 câu) VỚI TRỌNG SỐ {best_weight}")
    print("=======================================================")
    eval_200 = load_evaluation_set("data/evaluation/evaluation_set_200.json")
    eval_res = evaluate_on_set(eval_200, chroma_col, neo_driver, [0.0, best_weight])

    payload = {
        "dev_ablation": dev_res,
        "best_weight": best_weight,
        "eval_200": eval_res
    }
    with open("data/evaluation/exact_match_experiment_results.json", "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    print("\nSaved experiment results to data/evaluation/exact_match_experiment_results.json")

if __name__ == '__main__':
    main()

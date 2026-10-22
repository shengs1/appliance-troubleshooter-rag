import json
import re
import sys
import time
import unicodedata
from difflib import SequenceMatcher
from pathlib import Path

sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, ".")

from rag_chatbot.evaluation import load_evaluation_set, calculate_hit_at_k, calculate_mrr
from rag_chatbot.chroma_db import get_or_create_collection
from rag_chatbot.neo4j_db import get_neo4j_driver
from rag_chatbot.retrieval import search_hybrid, extract_question_entities

# Mapping tone variants (e.g. hoà -> hòa)
TONE_PAIRS = [
    ("oà", "òa"), ("oá", "óa"), ("oả", "ỏa"), ("oã", "õa"), ("oạ", "ọa"),
    ("uỳ", "ùy"), ("uý", "úy"), ("uỷ", "ủy"), ("uỹ", "ũy"), ("uỵ", "ụy"),
    ("oè", "òe"), ("oé", "óe"), ("oẻ", "ỏe"), ("oẽ", "õe"), ("oẹ", "ọe"),
]

def normalize_vietnamese_text(text: str) -> str:
    """Normalize Vietnamese text: NFC, standard tone placement, lower, strip punctuation."""
    if not text:
        return ""
    # 1. Unicode NFC
    t = unicodedata.normalize('NFC', text.lower())
    # 2. Tone standard
    for old, new in TONE_PAIRS:
        t = t.replace(old, new)
    # 3. Strip punctuation
    t = re.sub(r'[^\w\s\-]', ' ', t)
    # 4. Collapse whitespace
    return " ".join(t.split())

def calculate_q2q_sim(q1: str, q2: str) -> float:
    """Calculate SequenceMatcher similarity between normalized queries."""
    s1 = normalize_vietnamese_text(q1)
    s2 = normalize_vietnamese_text(q2)
    if not s1 or not s2:
        return 0.0
    if s1 == s2:
        return 1.0
    return SequenceMatcher(None, s1, s2).ratio()

def rerank_with_q2q(
    query: str,
    candidates: list[dict],
    entities: dict,
    w_q2q: float = 0.0,
) -> list[dict]:
    """Apply baseline fixed rule-based reranking + Q2Q Sequence Matching."""
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

        if target_brand and item_brand and target_brand.lower() == item_brand.lower():
            score += b_bonus
        if target_device and item_device and target_device.lower() == item_device.lower():
            score += d_bonus
        if target_error_code and item_code and target_error_code.lower() == item_code.lower():
            score += e_bonus
        if item.get("retrieval_source") == "both":
            score += both_bonus

        # Q2Q bonus
        if w_q2q > 0.0:
            sim = calculate_q2q_sim(query, item_q)
            score += w_q2q * sim

        item_copy = dict(item)
        item_copy["score"] = round(score, 4)
        scored.append((score, item_copy))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [x[1] for x in scored]

def main():
    dev_set = load_evaluation_set("data/evaluation/reranking_dev_100.json")
    chroma_col = get_or_create_collection()
    neo_driver = get_neo4j_driver()

    print(f"=== TẢI CANDIDATE POOL CHO TẬP DEV ({len(dev_set)} câu) ===")
    dev_pools = []
    t_start = time.perf_counter()
    for item in dev_set:
        q = item["question"]
        ent = extract_question_entities(q)
        t0 = time.perf_counter()
        raw_res = search_hybrid(
            q, k=10, chroma_collection=chroma_col, neo4j_driver=neo_driver, use_reranking=False
        )
        lat = (time.perf_counter() - t0) * 1000.0
        dev_pools.append({
            "item": item,
            "entities": ent,
            "raw_candidates": raw_res,
            "retrieval_lat_ms": lat
        })
    print(f"Hoàn thành trong {time.perf_counter() - t_start:.2f}s (TB {sum(p['retrieval_lat_ms'] for p in dev_pools)/len(dev_pools):.2f} ms/query)")

    weights = [0.0, 0.02, 0.03, 0.04, 0.05, 0.06, 0.08]
    summary_results = []
    baseline_ids_map = {}

    for w in weights:
        hit1, hit3, hit5 = 0, 0, 0
        total_mrr = 0.0
        latencies = []

        # Granular subsets
        err_hit1, err_n = 0, 0
        sym_hit1, sym_n = 0, 0

        rescued = []
        regressed = []

        for p in dev_pools:
            q = p["item"]["question"]
            exp = p["item"]["question_id"]
            it = p["item"].get("issue_type", "")
            ent = p["entities"]
            cand = p["raw_candidates"]
            base_lat = p["retrieval_lat_ms"]

            t0 = time.perf_counter()
            ranked = rerank_with_q2q(q, cand, ent, w_q2q=w)[:5]
            rerank_lat = (time.perf_counter() - t0) * 1000.0
            latencies.append(base_lat + rerank_lat)

            ids = [d["question_id"] for d in ranked]

            if w == 0.0:
                baseline_ids_map[exp] = ids[0]

            h1 = calculate_hit_at_k(ids, exp, 1)
            h3 = calculate_hit_at_k(ids, exp, 3)
            h5 = calculate_hit_at_k(ids, exp, 5)
            rr = calculate_mrr(ids, exp, 5)

            if h1: hit1 += 1
            if h3: hit3 += 1
            if h5: hit5 += 1
            total_mrr += rr

            if it == "ERROR_CODE":
                err_n += 1
                if h1: err_hit1 += 1
            elif it == "SYMPTOM":
                sym_n += 1
                if h1: sym_hit1 += 1

            if w > 0.0:
                base_top1 = baseline_ids_map.get(exp)
                if base_top1 != exp and ids[0] == exp:
                    rescued.append({"id": exp, "q": q, "old": base_top1, "new": ids[0]})
                elif base_top1 == exp and ids[0] != exp:
                    regressed.append({"id": exp, "q": q, "old": base_top1, "new": ids[0]})

        n = len(dev_pools)
        res = {
            "w_q2q": w,
            "hit@1": round(hit1 / n * 100.0, 2),
            "hit@3": round(hit3 / n * 100.0, 2),
            "hit@5": round(hit5 / n * 100.0, 2),
            "mrr": round(total_mrr / n, 4),
            "err_hit@1": round(err_hit1 / err_n * 100.0, 2) if err_n else 0.0,
            "sym_hit@1": round(sym_hit1 / sym_n * 100.0, 2) if sym_n else 0.0,
            "avg_latency_ms": round(sum(latencies) / n, 2),
            "rescued_count": len(rescued),
            "regressed_count": len(regressed),
            "rescued_items": rescued,
            "regressed_items": regressed,
        }
        summary_results.append(res)
        w_label = f"Baseline (w=0.00)" if w == 0.0 else f"w_q2q = {w:.2f}"
        print(f"[{w_label:<18}] Hit@1: {res['hit@1']:<5}% (Err: {res['err_hit@1']}%, Sym: {res['sym_hit@1']}%) | Hit@3: {res['hit@3']}% | Hit@5: {res['hit@5']}% | MRR: {res['mrr']} | Lat: {res['avg_latency_ms']} ms | +{len(rescued)} / -{len(regressed)}")

    with open("data/evaluation/dev_ablation_weights.json", "w", encoding="utf-8") as f:
        json.dump(summary_results, f, ensure_ascii=False, indent=2)
    print("Saved to data/evaluation/dev_ablation_weights.json")

if __name__ == '__main__':
    main()

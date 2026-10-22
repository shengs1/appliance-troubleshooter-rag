import json
import re
import sys
import time
from difflib import SequenceMatcher
from pathlib import Path

sys.stdout.reconfigure(encoding='utf-8')

from rag_chatbot.chroma_db import get_or_create_collection
from rag_chatbot.neo4j_db import get_neo4j_driver
from rag_chatbot.retrieval import search_hybrid, extract_question_entities
from rag_chatbot.evaluation import load_evaluation_set, calculate_hit_at_k, calculate_mrr

# Vietnamese stop words (excluding any potential error codes or devices)
STOP_WORDS = {
    "là", "gì", "sao", "phải", "làm", "thì", "có", "không", "như", "thế", "nào",
    "được", "bị", "và", "của", "ở", "trên", "trong", "cho", "với", "về", "khi",
    "hay", "hoặc", "này", "đó", "những", "các", "một", "tôi", "bạn", "người",
    "nào", "đâu", "nào", "ra", "lại", "đi", "đến"
}

def tokenize_vietnamese(text: str) -> list[str]:
    """Tokenize Vietnamese text while preserving error codes and alphanumeric tokens."""
    if not text:
        return []
    # Replace punctuation with spaces except hyphens within codes
    cleaned = re.sub(r'[^\w\s\-]', ' ', text.lower())
    tokens = cleaned.split()
    return tokens

def get_lexical_tokens(text: str) -> set[str]:
    """Get informative tokens excluding stopwords, keeping technical terms."""
    tokens = tokenize_vietnamese(text)
    meaningful = {t for t in tokens if t not in STOP_WORDS and len(t) > 1}
    return meaningful

def calculate_lexical_overlap(query: str, candidate_text: str) -> float:
    """Calculate token overlap ratio (Recall of query tokens in candidate)."""
    q_tokens = get_lexical_tokens(query)
    if not q_tokens:
        return 0.0
    cand_tokens = set(tokenize_vietnamese(candidate_text))
    overlap = q_tokens.intersection(cand_tokens)
    return len(overlap) / len(q_tokens)

def calculate_q2q_similarity(query: str, candidate_question: str) -> float:
    """Calculate sequence similarity ratio between query and candidate question."""
    q_norm = " ".join(tokenize_vietnamese(query))
    c_norm = " ".join(tokenize_vietnamese(candidate_question))
    if not q_norm or not c_norm:
        return 0.0
    if q_norm == c_norm:
        return 1.0
    return SequenceMatcher(None, q_norm, c_norm).ratio()

def rerank_experiment(
    query: str,
    results: list[dict],
    entities: dict,
    method: str = "baseline",
    weights: dict = None,
) -> list[dict]:
    """Rerank candidates based on specified experimental method."""
    if not results:
        return []

    target_brand = entities.get("brand")
    target_device = entities.get("device")
    target_error_code = entities.get("error_code")

    # Baseline weights
    b_bonus = 0.08
    d_bonus = 0.08
    e_bonus = 0.20
    both_bonus = 0.02

    scored = []
    for item in results:
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

        # Experimental signals
        if method == "baseline":
            pass
        elif method == "exp_A":
            # Lexical overlap with candidate question
            w_overlap = weights.get("w_overlap", 0.04) if weights else 0.04
            overlap_ratio = calculate_lexical_overlap(query, item_q)
            score += w_overlap * overlap_ratio
        elif method == "exp_B":
            # Question-to-question similarity
            w_q2q = weights.get("w_q2q", 0.03) if weights else 0.03
            q2q_sim = calculate_q2q_similarity(query, item_q)
            score += w_q2q * q2q_sim
        elif method == "exp_C":
            # Combined lexical overlap + exact match / sequence similarity
            w_overlap = weights.get("w_overlap", 0.03) if weights else 0.03
            w_q2q = weights.get("w_q2q", 0.02) if weights else 0.02
            overlap_ratio = calculate_lexical_overlap(query, item_q)
            q2q_sim = calculate_q2q_similarity(query, item_q)
            score += w_overlap * overlap_ratio + w_q2q * q2q_sim

        item_copy = dict(item)
        item_copy["rerank_score"] = round(score, 4)
        scored.append((score, item_copy))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [x[1] for x in scored]

def evaluate_method_on_dev(dev_set, chroma_col, neo_driver, method_name, weights=None):
    hit1, hit3, hit5 = 0, 0, 0
    total_mrr = 0.0
    latencies = []
    n = len(dev_set)

    for item in dev_set:
        q = item["question"]
        exp = item["question_id"]
        ent = extract_question_entities(q)

        t0 = time.perf_counter()
        # Retrieve candidate pool (k=10 to allow reranker to reorder)
        raw_res = search_hybrid(
            q, k=10, chroma_collection=chroma_col, neo4j_driver=neo_driver, use_reranking=False
        )

        final_res = rerank_experiment(q, raw_res, ent, method=method_name, weights=weights)[:5]
        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        latencies.append(elapsed_ms)

        ids = [d["question_id"] for d in final_res]
        if calculate_hit_at_k(ids, exp, 1): hit1 += 1
        if calculate_hit_at_k(ids, exp, 3): hit3 += 1
        if calculate_hit_at_k(ids, exp, 5): hit5 += 1
        total_mrr += calculate_mrr(ids, exp, 5)

    return {
        "method": method_name,
        "hit@1": round(hit1 / n * 100.0, 2),
        "hit@3": round(hit3 / n * 100.0, 2),
        "hit@5": round(hit5 / n * 100.0, 2),
        "mrr": round(total_mrr / n, 4),
        "avg_latency_ms": round(sum(latencies) / n, 2),
    }

def main():
    dev_set = load_evaluation_set("data/evaluation/reranking_dev_100.json")
    chroma_col = get_or_create_collection()
    neo_driver = get_neo4j_driver()

    print(f"=== RETRIEVING CANDIDATE POOLS FOR DEV SET ({len(dev_set)} queries) ===")
    
    # Retrieve raw candidate pool once per query
    dev_pools = []
    t_retrieval_start = time.perf_counter()
    for item in dev_set:
        q = item["question"]
        exp = item["question_id"]
        ent = extract_question_entities(q)
        t0 = time.perf_counter()
        raw_res = search_hybrid(
            q, k=10, chroma_collection=chroma_col, neo4j_driver=neo_driver, use_reranking=False
        )
        lat_retrieval = (time.perf_counter() - t0) * 1000.0
        dev_pools.append({
            "item": item,
            "entities": ent,
            "raw_candidates": raw_res,
            "retrieval_lat_ms": lat_retrieval
        })
    total_retrieval_time = time.perf_counter() - t_retrieval_start
    print(f"Candidate pools retrieved in {total_retrieval_time:.2f}s (Avg {sum(p['retrieval_lat_ms'] for p in dev_pools)/len(dev_pools):.2f} ms/query)")

    experiments = [
        ("baseline", None),
        ("exp_A (w_overlap=0.02)", "exp_A", {"w_overlap": 0.02}),
        ("exp_A (w_overlap=0.04)", "exp_A", {"w_overlap": 0.04}),
        ("exp_A (w_overlap=0.06)", "exp_A", {"w_overlap": 0.06}),
        ("exp_B (w_q2q=0.02)", "exp_B", {"w_q2q": 0.02}),
        ("exp_B (w_q2q=0.04)", "exp_B", {"w_q2q": 0.04}),
        ("exp_C (overlap=0.03, q2q=0.02)", "exp_C", {"w_overlap": 0.03, "w_q2q": 0.02}),
        ("exp_C (overlap=0.02, q2q=0.03)", "exp_C", {"w_overlap": 0.02, "w_q2q": 0.03}),
    ]

    all_results = []
    n = len(dev_pools)

    for entry in experiments:
        if len(entry) == 2:
            name, method, w = entry[0], entry[0], None
        else:
            name, method, w = entry[0], entry[1], entry[2]

        hit1, hit3, hit5 = 0, 0, 0
        total_mrr = 0.0
        latencies = []

        for p in dev_pools:
            q = p["item"]["question"]
            exp = p["item"]["question_id"]
            ent = p["entities"]
            candidates = p["raw_candidates"]
            base_lat = p["retrieval_lat_ms"]

            t0 = time.perf_counter()
            final_res = rerank_experiment(q, candidates, ent, method=method, weights=w)[:5]
            rerank_lat = (time.perf_counter() - t0) * 1000.0
            total_lat = base_lat + rerank_lat
            latencies.append(total_lat)

            ids = [d["question_id"] for d in final_res]
            if calculate_hit_at_k(ids, exp, 1): hit1 += 1
            if calculate_hit_at_k(ids, exp, 3): hit3 += 1
            if calculate_hit_at_k(ids, exp, 5): hit5 += 1
            total_mrr += calculate_mrr(ids, exp, 5)

        res = {
            "config_name": name,
            "method": method,
            "weights": w,
            "hit@1": round(hit1 / n * 100.0, 2),
            "hit@3": round(hit3 / n * 100.0, 2),
            "hit@5": round(hit5 / n * 100.0, 2),
            "mrr": round(total_mrr / n, 4),
            "avg_latency_ms": round(sum(latencies) / n, 2),
        }
        all_results.append(res)
        print(f"[{name:<35}] Hit@1: {res['hit@1']:<5}% | Hit@3: {res['hit@3']:<5}% | Hit@5: {res['hit@5']:<5}% | MRR: {res['mrr']:<6} | Latency: {res['avg_latency_ms']} ms")

    with open("data/evaluation/dev_lexical_experiments.json", "w", encoding="utf-8") as f:
        json.dump(all_results, f, ensure_ascii=False, indent=2)
    print("Saved experiment results to data/evaluation/dev_lexical_experiments.json")

if __name__ == '__main__':
    main()

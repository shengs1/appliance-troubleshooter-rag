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
from rag_chatbot.retrieval import (
    search_similar_documents,
    search_graph,
    build_chroma_where_filter,
    extract_question_entities as old_extract_entities
)
from scripts.test_improved_extraction import extract_question_entities_improved as new_extract_entities
from scripts.ablation_dev_weights import normalize_vietnamese_text, calculate_q2q_sim

def search_hybrid_custom(
    question: str,
    k: int = 5,
    chroma_collection = None,
    neo4j_driver = None,
    use_new_extractor: bool = False,
    w_q2q: float = 0.0,
) -> list[dict]:
    """Execute hybrid retrieval with chosen extractor and reranker configuration."""
    if not question or not question.strip():
        return []

    extractor_fn = new_extract_entities if use_new_extractor else old_extract_entities
    entities = extractor_fn(question)
    brand = entities.get("brand")
    device = entities.get("device")
    error_code = entities.get("error_code")

    fetch_k = 10

    # 1. ChromaDB search
    active_where = build_chroma_where_filter(brand=brand, device=device)
    chroma_raw = search_similar_documents(
        question, k=fetch_k, collection=chroma_collection, where=active_where
    )
    chroma_items = []
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

    # 2. Neo4j search using entities
    neo4j_items = []
    if brand or device or error_code:
        # Search Neo4j with extracted entities
        if error_code:
            cypher = """
            MATCH (e:ErrorCode)
            WHERE toUpper(e.code) = toUpper($error_code)
            MATCH (i:Issue)-[:HAS_ERROR_CODE]->(e)
            MATCH (q:Question)-[:ABOUT]->(i)
            MATCH (b:Brand {brand_id: q.brand_id})
            MATCH (d:Device {device_id: q.device_id})
            WHERE ($brand IS NULL OR toLower(b.name) = toLower($brand))
              AND ($device IS NULL OR toLower(d.name) = toLower($device))
            OPTIONAL MATCH (q)-[:ANSWERED_BY]->(a:Answer)
            OPTIONAL MATCH (q)-[:SOURCED_FROM]->(s:Source)
            RETURN 
                q.question_id AS question_id,
                q.question AS question,
                coalesce(a.answer, '') AS answer,
                b.name AS brand,
                d.name AS device,
                e.code AS error_code,
                coalesce(s.url, '') AS source_url
            LIMIT $limit
            """
        else:
            cypher = """
            MATCH (q:Question)-[:ABOUT]->(i:Issue)
            MATCH (b:Brand {brand_id: q.brand_id})
            MATCH (d:Device {device_id: q.device_id})
            WHERE ($brand IS NULL OR toLower(b.name) = toLower($brand))
              AND ($device IS NULL OR toLower(d.name) = toLower($device))
            OPTIONAL MATCH (i)-[:HAS_ERROR_CODE]->(e:ErrorCode)
            OPTIONAL MATCH (q)-[:ANSWERED_BY]->(a:Answer)
            OPTIONAL MATCH (q)-[:SOURCED_FROM]->(s:Source)
            RETURN 
                q.question_id AS question_id,
                q.question AS question,
                coalesce(a.answer, '') AS answer,
                b.name AS brand,
                d.name AS device,
                coalesce(e.code, '') AS error_code,
                coalesce(s.url, '') AS source_url
            LIMIT $limit
            """
        from rag_chatbot.neo4j_db import run_query
        raw_neo = run_query(cypher, parameters={"error_code": error_code, "brand": brand, "device": device, "limit": fetch_k}, driver=neo4j_driver)
        for r in raw_neo:
            neo4j_items.append({
                "question_id": r.get("question_id", ""),
                "question": r.get("question", ""),
                "answer": r.get("answer", ""),
                "brand": r.get("brand", ""),
                "device": r.get("device", ""),
                "error_code": r.get("error_code", ""),
                "source_url": r.get("source_url", ""),
                "retrieval_source": "neo4j",
                "distance": None,
            })

    # 3. Combine
    combined = {}
    for itm in chroma_items:
        combined[itm["question_id"]] = itm
    for itm in neo4j_items:
        qid = itm["question_id"]
        if qid in combined:
            combined[qid]["retrieval_source"] = "both"
            if not combined[qid]["answer"] and itm.get("answer"):
                combined[qid]["answer"] = itm["answer"]
        else:
            combined[qid] = itm

    # 4. Hard entity safety filter
    filtered = []
    for itm in combined.values():
        itm_b = itm.get("brand", "")
        itm_d = itm.get("device", "")
        if brand and itm_b and itm_b.lower() != brand.lower():
            continue
        if device and itm_d and itm_d.lower() != device.lower():
            continue
        filtered.append(itm)

    # 5. Rerank
    scored = []
    for itm in filtered:
        dist = itm.get("distance")
        semantic_score = max(0.0, 1.0 - float(dist)) if dist is not None else 0.0
        score = semantic_score

        itm_b = itm.get("brand", "")
        itm_d = itm.get("device", "")
        itm_c = itm.get("error_code", "")
        itm_q = itm.get("question", "")

        if brand and itm_b and brand.lower() == itm_b.lower():
            score += 0.08
        if device and itm_d and device.lower() == itm_d.lower():
            score += 0.08
        if error_code and itm_c:
            itm_codes = [c.strip().lower() for c in itm_c.split(',')]
            if error_code.lower() in itm_codes:
                score += 0.20
        if itm.get("retrieval_source") == "both":
            score += 0.02

        # Q2Q bonus
        if w_q2q > 0.0:
            sim = calculate_q2q_sim(question, itm_q)
            score += w_q2q * sim

        itm_copy = dict(itm)
        itm_copy["score"] = round(score, 4)
        scored.append((score, itm_copy))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [x[1] for x in scored][:k]

def run_benchmark_on_dataset(dataset_name, dataset, chroma_col, neo_driver, configs):
    results = {}
    n = len(dataset)
    print(f"\n=======================================================")
    print(f"BENCHMARK TRÊN TẬP: {dataset_name} ({n} câu)")
    print(f"=======================================================")
    print(f"{'Cấu hình':<32} | {'Strict Hit@1':<13} | {'Cluster Hit@1':<13} | {'Hit@3':<7} | {'Hit@5':<7} | {'MRR':<7} | {'Độ trễ'}")
    print("-" * 100)

    for cfg_key, cfg in configs.items():
        strict_h1 = 0
        cluster_h1 = 0
        h3 = 0
        h5 = 0
        total_mrr = 0.0
        latencies = []

        rescued_vs_base = []
        regressed_vs_base = []

        category_stats = {}

        for item in dataset:
            q = item.get("question") or item.get("query")
            primary_id = item.get("expected_primary_id") or item.get("question_id")
            equiv_ids = set(item.get("equivalent_ids", []))
            all_valid_ids = equiv_ids.union({primary_id})
            cat = item.get("category") or item.get("issue_type", "OTHER")

            t0 = time.perf_counter()
            docs = search_hybrid_custom(
                q,
                k=5,
                chroma_collection=chroma_col,
                neo4j_driver=neo_driver,
                use_new_extractor=cfg["use_new_extractor"],
                w_q2q=cfg["w_q2q"]
            )
            lat = (time.perf_counter() - t0) * 1000.0
            latencies.append(lat)

            retrieved_ids = [d["question_id"] for d in docs]
            top1_id = retrieved_ids[0] if retrieved_ids else ""

            is_strict_h1 = (top1_id == primary_id)
            is_cluster_h1 = (top1_id in all_valid_ids)

            if is_strict_h1: strict_h1 += 1
            if is_cluster_h1: cluster_h1 += 1

            if any(rid in all_valid_ids for rid in retrieved_ids[:3]): h3 += 1
            if any(rid in all_valid_ids for rid in retrieved_ids[:5]): h5 += 1

            rr = 0.0
            for rank_idx, rid in enumerate(retrieved_ids[:5], 1):
                if rid in all_valid_ids:
                    rr = 1.0 / rank_idx
                    break
            total_mrr += rr

            if cat not in category_stats:
                category_stats[cat] = {"total": 0, "strict_h1": 0, "cluster_h1": 0}
            category_stats[cat]["total"] += 1
            if is_strict_h1: category_stats[cat]["strict_h1"] += 1
            if is_cluster_h1: category_stats[cat]["cluster_h1"] += 1

        s_pct = round(strict_h1 / n * 100.0, 2)
        c_pct = round(cluster_h1 / n * 100.0, 2)
        h3_pct = round(h3 / n * 100.0, 2)
        h5_pct = round(h5 / n * 100.0, 2)
        mrr_val = round(total_mrr / n, 4)
        avg_lat = round(sum(latencies) / n, 2)

        results[cfg_key] = {
            "name": cfg["name"],
            "strict_hit1": s_pct,
            "cluster_hit1": c_pct,
            "hit3": h3_pct,
            "hit5": h5_pct,
            "mrr": mrr_val,
            "avg_latency_ms": avg_lat,
            "by_category": category_stats,
        }

        print(f"{cfg['name']:<32} | {s_pct:>5.1f}% ({strict_h1:>2}/{n}) | {c_pct:>5.1f}% ({cluster_h1:>2}/{n}) | {h3_pct:>5.1f}% | {h5_pct:>5.1f}% | {mrr_val:>6.4f} | {avg_lat:>6.2f} ms")

    return results

def main():
    chroma_col = get_or_create_collection()
    neo_driver = get_neo4j_driver()

    configs = {
        "A_baseline": {
            "name": "A. Baseline (Old Ext, No Q2Q)",
            "use_new_extractor": False,
            "w_q2q": 0.0
        },
        "B_new_extract": {
            "name": "B. Baseline + New Extractor",
            "use_new_extractor": True,
            "w_q2q": 0.0
        },
        "C_old_ext_q2q": {
            "name": "C. Baseline + Q2Q (w=0.04)",
            "use_new_extractor": False,
            "w_q2q": 0.04
        },
        "D_new_ext_q2q": {
            "name": "D. New Extractor + Q2Q (w=0.04)",
            "use_new_extractor": True,
            "w_q2q": 0.04
        }
    }

    # 1. Independent Set (60 câu)
    with open("data/evaluation/independent_eval_60.json", "r", encoding="utf-8") as f:
        ind_60 = json.load(f)
    res_ind = run_benchmark_on_dataset("Independent Set 60 câu", ind_60, chroma_col, neo_driver, configs)

    # 2. Dev Set (100 câu)
    with open("data/evaluation/reranking_dev_100.json", "r", encoding="utf-8") as f:
        dev_100 = json.load(f)
    res_dev = run_benchmark_on_dataset("Development Set 100 câu", dev_100, chroma_col, neo_driver, configs)

    # 3. Eval Set (200 câu)
    with open("data/evaluation/evaluation_set_200.json", "r", encoding="utf-8") as f:
        eval_200 = json.load(f)
    res_eval = run_benchmark_on_dataset("Evaluation Set 200 câu", eval_200, chroma_col, neo_driver, configs)

    final_payload = {
        "independent_60": res_ind,
        "dev_100": res_dev,
        "eval_200": res_eval,
    }
    with open("data/evaluation/controlled_benchmark_results.json", "w", encoding="utf-8") as f:
        json.dump(final_payload, f, ensure_ascii=False, indent=2)
    print("\nSaved full controlled benchmark results to data/evaluation/controlled_benchmark_results.json")

if __name__ == '__main__':
    main()

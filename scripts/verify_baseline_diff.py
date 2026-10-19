import sys
import json
from pathlib import Path
from rag_chatbot.retrieval import (
    search_hybrid,
    search_similar_documents,
    search_graph,
    build_chroma_where_filter,
    extract_question_entities,
)
from rag_chatbot.chroma_db import get_or_create_collection
from rag_chatbot.neo4j_db import get_neo4j_driver
from rag_chatbot.evaluation import load_evaluation_set, calculate_hit_at_k, calculate_mrr

def main():
    eval_set = load_evaluation_set("data/evaluation/evaluation_set_200.json")
    chroma_col = get_or_create_collection()
    neo_driver = get_neo4j_driver()

    diff_cases = []

    for item in eval_set:
        q = item["question"]
        exp = item["question_id"]
        item_brand = item.get("brand", "")
        item_device = item.get("device", "")

        # 1. Real search_hybrid (Phase 10B actual function call)
        res_real = search_hybrid(q, k=5, chroma_collection=chroma_col, neo4j_driver=neo_driver, use_reranking=False)
        real_ids = [d["question_id"] for d in res_real]
        hit1_real = calculate_hit_at_k(real_ids, exp, 1)

        # 2. What evaluation.py inline logic did (lines 301-305)
        ent = extract_question_entities(q)
        wf = build_chroma_where_filter(ent.get("brand"), ent.get("device"))
        c_raw = search_similar_documents(q, k=5, collection=chroma_col, where=wf)
        c_items = []
        for r in c_raw:
            meta = r.get("metadata", {})
            c_items.append({
                "question_id": str(meta.get("question_id", r.get("id", ""))),
                "brand": str(meta.get("brand", "")),
                "device": str(meta.get("device", "")),
                "retrieval_source": "chroma",
                "distance": r.get("distance"),
            })
        n_raw = search_graph(q, k=5, driver=neo_driver)
        comb = {}
        for ci in c_items:
            comb[ci["question_id"]] = ci
        for ni in n_raw:
            qid = ni["question_id"]
            if qid in comb:
                comb[qid]["retrieval_source"] = "both"
            else:
                comb[qid] = ni

        # evaluation.py used `brand` and `device` from eval_set item:
        fc = [
            x for x in comb.values()
            if (not item_brand or not x.get("brand") or x["brand"].lower() == item_brand.lower())
            and (not item_device or not x.get("device") or x["device"].lower() == item_device.lower())
        ]
        sb = sorted(fc, key=lambda x: (0 if x.get("retrieval_source") == "both" else 1))
        eval_ids = [d["question_id"] for d in sb[:5]]
        hit1_eval = calculate_hit_at_k(eval_ids, exp, 1)

        if hit1_real != hit1_eval:
            diff_cases.append({
                "qid": exp,
                "question": q,
                "item_brand": item_brand,
                "item_device": item_device,
                "extracted_brand": ent.get("brand"),
                "extracted_device": ent.get("device"),
                "real_top1": real_ids[0] if real_ids else None,
                "eval_top1": eval_ids[0] if eval_ids else None,
                "hit1_real": hit1_real,
                "hit1_eval": hit1_eval,
            })

    output_path = Path("data/evaluation/baseline_diff_cases.json")
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(diff_cases, f, ensure_ascii=False, indent=2)

    print(f"DONE. Total diff cases: {len(diff_cases)}. Saved to {output_path}")

if __name__ == "__main__":
    main()

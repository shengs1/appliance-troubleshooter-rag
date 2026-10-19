import json
import sys
sys.stdout.reconfigure(encoding="utf-8")

from rag_chatbot.evaluation import load_evaluation_set, calculate_hit_at_k
from rag_chatbot.retrieval import search_hybrid
from rag_chatbot.chroma_db import get_or_create_collection
from rag_chatbot.neo4j_db import get_neo4j_driver
from rag_chatbot.reranker import get_reranker

eval_set = load_evaluation_set("data/evaluation/evaluation_set_200.json")
col = get_or_create_collection()
drv = get_neo4j_driver()
model = get_reranker()

regressions = []
for item in eval_set:
    q = item["question"]
    exp = item["question_id"]
    f_res = search_hybrid(q, k=5, chroma_collection=col, neo4j_driver=drv, use_reranking=True, rerank_mode="fixed")
    f_ids = [d["question_id"] for d in f_res]
    if calculate_hit_at_k(f_ids, exp, 1):
        n_res = search_hybrid(q, k=5, chroma_collection=col, neo4j_driver=drv, use_reranking=True, rerank_mode="neural")
        n_ids = [d["question_id"] for d in n_res]
        if not calculate_hit_at_k(n_ids, exp, 1):
            n_rank = n_ids.index(exp) + 1 if exp in n_ids else None
            regressions.append({
                "question_id": exp,
                "question": q,
                "issue_type": item.get("issue_type"),
                "fixed_top1": f_ids[0],
                "neural_rank": n_rank,
                "neural_top1": n_ids[0] if n_ids else None
            })

with open("data/evaluation/neural_regressions_14.json", "w", encoding="utf-8") as f:
    json.dump(regressions, f, ensure_ascii=False, indent=2)

print(f"Saved {len(regressions)} regressions to neural_regressions_14.json")
for r in regressions:
    print(f"- {r['question_id']} ({r['issue_type']}): {r['question']}")
    print(f"  Fixed Top 1: {r['fixed_top1']} | Neural Top 1: {r['neural_top1']} (Exp rank: {r['neural_rank']})")

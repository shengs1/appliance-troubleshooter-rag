import json
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, ".")

from rag_chatbot.evaluation import load_evaluation_set
from rag_chatbot.chroma_db import get_or_create_collection
from rag_chatbot.neo4j_db import get_neo4j_driver
from scripts.benchmark_phase2_configurations import retrieve_candidate_pool, rerank_custom

indep_60 = load_evaluation_set("data/evaluation/independent_eval_60.json")
chroma_col = get_or_create_collection()
neo_driver = get_neo4j_driver()

print("Finding differences between pool=5 and pool=10 on Independent 60...")
for item in indep_60:
    q = item["query"]
    primary_id = item["expected_primary_id"]
    valid_ids = set(item.get("equivalent_ids", [])).union({primary_id})

    c5, _ = retrieve_candidate_pool(q, 5, chroma_col, neo_driver)
    r5, _ = rerank_custom(q, c5, exact_bonus=0.02)
    top1_c5 = r5[0]["question_id"] if r5 else ""

    c10, _ = retrieve_candidate_pool(q, 10, chroma_col, neo_driver)
    r10, _ = rerank_custom(q, c10, exact_bonus=0.02)
    top1_c10 = r10[0]["question_id"] if r10 else ""

    hit_c5 = top1_c5 in valid_ids
    hit_c10 = top1_c10 in valid_ids

    if hit_c5 and not hit_c10:
        print(f"REGRESSION in Pool=10: [{item['id']}] '{q}'")
        print(f"  Valid IDs: {valid_ids}")
        print(f"  Pool=5  Top1: {top1_c5} (CORRECT) - Rank: 1")
        print(f"  Pool=10 Top1: {top1_c10} (WRONG)   - Exp Rank in Pool 10: {[d['question_id'] for d in r10].index(top1_c5)+1 if top1_c5 in [d['question_id'] for d in r10] else '>5'}")
    elif not hit_c5 and hit_c10:
        print(f"IMPROVED in Pool=10: [{item['id']}] '{q}'")
        print(f"  Valid IDs: {valid_ids}")
        print(f"  Pool=5  Top1: {top1_c5} (WRONG)")
        print(f"  Pool=10 Top1: {top1_c10} (CORRECT)")

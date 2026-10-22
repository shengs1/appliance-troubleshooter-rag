import json
import sys

sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, ".")

from scripts.run_controlled_benchmark import search_hybrid_custom
from rag_chatbot.chroma_db import get_or_create_collection
from rag_chatbot.neo4j_db import get_neo4j_driver
from scripts.test_improved_extraction import extract_question_entities_improved as new_ext
from rag_chatbot.retrieval import extract_question_entities as old_ext

col = get_or_create_collection()
drv = get_neo4j_driver()

print("=== TÌM CA HỒI QUY TRÊN DEV 100 ===")
with open('data/evaluation/reranking_dev_100.json', 'r', encoding='utf-8') as f:
    dev = json.load(f)

for item in dev:
    q = item['question']
    exp = item['question_id']
    res_a = search_hybrid_custom(q, k=5, chroma_collection=col, neo4j_driver=drv, use_new_extractor=False, w_q2q=0.0)
    res_b = search_hybrid_custom(q, k=5, chroma_collection=col, neo4j_driver=drv, use_new_extractor=True, w_q2q=0.0)
    top_a = res_a[0]['question_id'] if res_a else ''
    top_b = res_b[0]['question_id'] if res_b else ''
    if top_a == exp and top_b != exp:
        print(f"REGRESSED in Dev: {exp} | A_Top1: {top_a} | B_Top1: {top_b}")
        print(f"  Query: '{q}'")
        print(f"  Old Ext: {old_ext(q)}")
        print(f"  New Ext: {new_ext(q)}")

print("\n=== TÌM CA HỒI QUY TRÊN EVAL 200 ===")
with open('data/evaluation/evaluation_set_200.json', 'r', encoding='utf-8') as f:
    eval_200 = json.load(f)

for item in eval_200:
    q = item['question']
    exp = item['question_id']
    res_a = search_hybrid_custom(q, k=5, chroma_collection=col, neo4j_driver=drv, use_new_extractor=False, w_q2q=0.0)
    res_b = search_hybrid_custom(q, k=5, chroma_collection=col, neo4j_driver=drv, use_new_extractor=True, w_q2q=0.0)
    top_a = res_a[0]['question_id'] if res_a else ''
    top_b = res_b[0]['question_id'] if res_b else ''
    if top_a == exp and top_b != exp:
        print(f"REGRESSED in Eval: {exp} | A_Top1: {top_a} | B_Top1: {top_b}")
        print(f"  Query: '{q}'")
        print(f"  Old Ext: {old_ext(q)}")
        print(f"  New Ext: {new_ext(q)}")

import json
import sys
import pandas as pd

sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, ".")

from rag_chatbot.evaluation import load_evaluation_set, calculate_hit_at_k
from rag_chatbot.chroma_db import get_or_create_collection
from rag_chatbot.neo4j_db import get_neo4j_driver
from rag_chatbot.retrieval import search_hybrid, extract_question_entities
from scripts.test_exact_question_bonus import rerank_with_exact_bonus, normalize_question_text

col = get_or_create_collection()
drv = get_neo4j_driver()

eval_200 = load_evaluation_set("data/evaluation/evaluation_set_200.json")

df = pd.read_excel('data/raw/dataset.xlsx', sheet_name='DATA_CLEAN_TECH')
df_by_id = {str(row['ID']).strip(): row for _, row in df.iterrows()}

failed_queries = []

for item in eval_200:
    q = item['question']
    exp = item['question_id']
    ent = extract_question_entities(q)
    raw = search_hybrid(q, k=10, chroma_collection=col, neo4j_driver=drv, use_reranking=False)
    ranked = rerank_with_exact_bonus(q, raw, ent, exact_match_bonus=0.04)[:5]
    top1 = ranked[0]['question_id'] if ranked else ''

    if top1 != exp:
        exp_row = df_by_id.get(exp)
        top1_row = df_by_id.get(top1)

        exp_q = str(exp_row.get('Câu_hỏi_đã_làm_sạch', '')) if exp_row is not None else ''
        top1_q = str(top1_row.get('Câu_hỏi_đã_làm_sạch', '')) if top1_row is not None else ''

        norm_exp = normalize_question_text(exp_q)
        norm_top1 = normalize_question_text(top1_q)

        same_exact_text = (norm_exp == norm_top1)

        failed_queries.append({
            "expected_id": exp,
            "top1_id": top1,
            "query": q,
            "exp_question": exp_q,
            "top1_question": top1_q,
            "same_exact_text": same_exact_text,
            "exp_dg": str(exp_row.get('Duplicate_Group', '')) if exp_row is not None else '',
            "top1_dg": str(top1_row.get('Duplicate_Group', '')) if top1_row is not None else '',
            "exp_score": next((d.get('score') for d in ranked if d['question_id'] == exp), None),
            "top1_score": ranked[0].get('score') if ranked else None,
        })

print(f"Tổng số ca còn trượt Hit@1 trên 200 câu: {len(failed_queries)}")
print(f"{'#':<3} | {'Exp':<6} | {'Top1':<6} | {'Same Exact Text?':<18} | {'Duplicate Group':<18} | {'Query'}")
print("-" * 90)
for idx, f in enumerate(failed_queries, 1):
    dg_info = f"{f['exp_dg']} vs {f['top1_dg']}" if f['exp_dg'] != f['top1_dg'] else f['exp_dg']
    print(f"{idx:<3} | {f['expected_id']:<6} | {f['top1_id']:<6} | {str(f['same_exact_text']):<18} | {dg_info:<18} | '{f['query'][:40]}'")

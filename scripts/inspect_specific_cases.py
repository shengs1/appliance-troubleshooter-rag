import json
import sys
import pandas as pd

sys.stdout.reconfigure(encoding='utf-8')

df = pd.read_excel('data/raw/dataset.xlsx', sheet_name='DATA_CLEAN_TECH')
df_by_id = {str(row['ID']).strip(): row for _, row in df.iterrows()}

special_ids = ["Q0535", "Q0558", "Q0611", "Q0624", "Q1082"]

with open('data/evaluation/detailed_26_failures_analysis.json', 'r', encoding='utf-8') as f:
    cases = json.load(f)

for c in cases:
    if c['expected_id'] in special_ids:
        exp_id = c['expected_id']
        top1_id = c['top1_info']['id']
        exp_row = df_by_id[exp_id]
        top1_row = df_by_id[top1_id]

        print(f"==================================================")
        print(f"CASE: Exp={exp_id} vs Top1={top1_id} | Exp Rank={c['expected_rank']}")
        print(f"Query: {c['query']}")
        print(f"Exp Brand: {exp_row.get('Hãng')} | Device: {exp_row.get('Loại_thiết_bị')} | Issue_ID: {exp_row.get('Issue_ID')}")
        print(f"Exp Q_clean: {exp_row.get('Câu_hỏi_đã_làm_sạch')}")
        exp_ans = str(exp_row.get('Câu_trả_lời_đã_làm_sạch', '')) if pd.notna(exp_row.get('Câu_trả_lời_đã_làm_sạch')) else ''
        top1_ans = str(top1_row.get('Câu_trả_lời_đã_làm_sạch', '')) if pd.notna(top1_row.get('Câu_trả_lời_đã_làm_sạch')) else ''
        print(f"Exp Answer: {exp_ans[:150]}...")
        print(f"---")
        print(f"Top1 Brand: {top1_row.get('Hãng')} | Device: {top1_row.get('Loại_thiết_bị')} | Issue_ID: {top1_row.get('Issue_ID')}")
        print(f"Top1 Q_clean: {top1_row.get('Câu_hỏi_đã_làm_sạch')}")
        print(f"Top1 Answer: {top1_ans[:150]}...")
        print(f"Top 5 candidates:")
        for cand in c['top_5_candidates']:
            print(f"   Rank {cand['rank']}: ID={cand['id']} | Score={cand['score']} | Dist={cand['distance']} | Expected={cand['is_expected']}")

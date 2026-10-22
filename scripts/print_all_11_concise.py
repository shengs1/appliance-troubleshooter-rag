import json
import sys
import pandas as pd

sys.stdout.reconfigure(encoding='utf-8')

df = pd.read_excel('data/raw/dataset.xlsx', sheet_name='DATA_CLEAN_TECH')
df_by_id = {str(row['ID']).strip(): row for _, row in df.iterrows()}

with open('data/evaluation/bonus_002_failures_analysis.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

for idx, f in enumerate(data['failures'], 1):
    exp = df_by_id.get(f['expected_id'])
    pred = df_by_id.get(f['predicted_top1_id'])
    print(f"#{idx}: Exp={f['expected_id']} vs Pred={f['predicted_top1_id']}")
    print(f"  Query: '{f['query']}'")
    print(f"  Exp Clean Q:  '{exp.get('Câu_hỏi_đã_làm_sạch')}'")
    print(f"  Pred Clean Q: '{pred.get('Câu_hỏi_đã_làm_sạch')}'")
    print(f"  Brand/Device/Code: Exp=({exp.get('Hãng')}, {exp.get('Loại_thiết_bị')}, {exp.get('Mã_lỗi')}) vs Pred=({pred.get('Hãng')}, {pred.get('Loại_thiết_bị')}, {pred.get('Mã_lỗi')})")
    print(f"  Duplicate Group:   Exp='{exp.get('Duplicate_Group')}' vs Pred='{pred.get('Duplicate_Group')}'")
    print(f"  Issue ID:          Exp='{exp.get('Issue_ID')}' vs Pred='{pred.get('Issue_ID')}'")
    print(f"  Exp Answer:        '{exp.get('Trả_lời')}'")
    print(f"  Pred Answer:       '{pred.get('Trả_lời')}'")
    print(f"  Exp Scores:        final={f['exp_data']['score']} (dist={f['exp_data']['distance']:.4f}, exact_bonus={f['exp_data']['bonuses'].get('exact_question', 0.0)})")
    print(f"  Pred Scores:       final={f['top1_data']['score']} (dist={f['top1_data']['distance']:.4f}, exact_bonus={f['top1_data']['bonuses'].get('exact_question', 0.0)})")
    print()

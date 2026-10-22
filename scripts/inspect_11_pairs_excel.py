import json
import sys
import pandas as pd

sys.stdout.reconfigure(encoding='utf-8')

df = pd.read_excel('data/raw/dataset.xlsx', sheet_name='DATA_CLEAN_TECH')
df_by_id = {str(row['ID']).strip(): row for _, row in df.iterrows()}

with open('data/evaluation/bonus_002_failures_analysis.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

pairs = []
for f in data['failures']:
    pairs.append((f['expected_id'], f['predicted_top1_id'], f['query'], f['expected_rank']))

print(f"Loaded {len(pairs)} failure pairs.\n")

fields = [
    'ID', 'Câu_hỏi_đã_làm_sạch', 'Hãng', 'Loại_thiết_bị', 'Mã_lỗi',
    'Issue_ID', 'Nguyên_nhân', 'Cách_khắc_phục', 'Trả_lời',
    'Nguồn_TT', 'Nguồn_URL', 'Duplicate_Group', 'Duplicate_Count'
]

summary_rows = []

for idx, (exp_id, pred_id, query, rank) in enumerate(pairs, 1):
    r_exp = df_by_id.get(exp_id)
    r_pred = df_by_id.get(pred_id)

    print(f"================================================================================")
    print(f"PAIR #{idx}: User Query: '{query}'")
    print(f"  Expected ID: {exp_id} (Rank in Retrieval: {rank})")
    print(f"  Predicted Top-1 ID: {pred_id}")
    print(f"--------------------------------------------------------------------------------")
    for f in fields:
        val_exp = r_exp.get(f) if r_exp is not None else None
        val_pred = r_pred.get(f) if r_pred is not None else None
        print(f"  {f:<22} | EXP: {str(val_exp):<35} | PRED: {str(val_pred)}")

    # Check relation
    dg_match = (str(r_exp.get('Duplicate_Group')) == str(r_pred.get('Duplicate_Group'))) and pd.notna(r_exp.get('Duplicate_Group'))
    issue_match = (str(r_exp.get('Issue_ID')) == str(r_pred.get('Issue_ID'))) and pd.notna(r_exp.get('Issue_ID'))
    code_match = (str(r_exp.get('Mã_lỗi')).strip().lower() == str(r_pred.get('Mã_lỗi')).strip().lower()) and pd.notna(r_exp.get('Mã_lỗi'))
    q_norm_exp = str(r_exp.get('Câu_hỏi_normalized', '')).strip().lower()
    q_norm_pred = str(r_pred.get('Câu_hỏi_normalized', '')).strip().lower()
    q_match = (q_norm_exp == q_norm_pred)

    cause_exp = str(r_exp.get('Nguyên_nhân', '')).strip()
    cause_pred = str(r_pred.get('Nguyên_nhân', '')).strip()
    fix_exp = str(r_exp.get('Cách_khắc_phục', '')).strip()
    fix_pred = str(r_pred.get('Cách_khắc_phục', '')).strip()
    ans_exp = str(r_exp.get('Trả_lời', '')).strip()
    ans_pred = str(r_pred.get('Trả_lời', '')).strip()

    print(f"--------------------------------------------------------------------------------")
    print(f"  RELATIONSHIP ANALYSIS:")
    print(f"  - Same Duplicate Group: {dg_match} ({r_exp.get('Duplicate_Group')} vs {r_pred.get('Duplicate_Group')})")
    print(f"  - Same Issue ID:        {issue_match} ({r_exp.get('Issue_ID')} vs {r_pred.get('Issue_ID')})")
    print(f"  - Same Error Code:      {code_match} ({r_exp.get('Mã_lỗi')} vs {r_pred.get('Mã_lỗi')})")
    print(f"  - Same Normalized Q:    {q_match}")
    print(f"  - Cause Comparison:     EXP='{cause_exp}' | PRED='{cause_pred}'")
    print(f"  - Fix Comparison:       EXP='{fix_exp}' | PRED='{fix_pred}'")
    print(f"  - Answer Comparison:    EXP='{ans_exp}' | PRED='{ans_pred}'")
    print(f"================================================================================\n")

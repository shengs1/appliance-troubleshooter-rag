import json
import sys
import pandas as pd

sys.stdout.reconfigure(encoding='utf-8')

df = pd.read_excel('data/raw/dataset.xlsx', sheet_name='DATA_CLEAN_TECH')
df_by_id = {str(row['ID']).strip(): row for _, row in df.iterrows()}

with open('data/evaluation/bonus_002_failures_analysis.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

print(f"Total failures at bonus 0.02: {len(data['failures'])}")
print('='*90)

for idx, item in enumerate(data['failures'], 1):
    exp_id = item['expected_id']
    pred_id = item['predicted_top1_id']
    exp_r = df_by_id.get(exp_id)
    pred_r = df_by_id.get(pred_id)

    exp_q = str(exp_r.get('Câu_hỏi_đã_làm_sạch', '')) if exp_r is not None else ""
    pred_q = str(pred_r.get('Câu_hỏi_đã_làm_sạch', '')) if pred_r is not None else ""

    exp_cause = str(exp_r.get('Nguyên_nhân', '')) if exp_r is not None else ""
    pred_cause = str(pred_r.get('Nguyên_nhân', '')) if pred_r is not None else ""

    exp_fix = str(exp_r.get('Cách_khắc_phục', '')) if exp_r is not None else ""
    pred_fix = str(pred_r.get('Cách_khắc_phục', '')) if pred_r is not None else ""

    exp_dg = str(exp_r.get('Duplicate_Group', '')) if exp_r is not None and pd.notna(exp_r.get('Duplicate_Group')) else ""
    pred_dg = str(pred_r.get('Duplicate_Group', '')) if pred_r is not None and pd.notna(pred_r.get('Duplicate_Group')) else ""

    exp_issue = str(exp_r.get('Issue_ID', '')) if exp_r is not None and pd.notna(exp_r.get('Issue_ID')) else ""
    pred_issue = str(pred_r.get('Issue_ID', '')) if pred_r is not None and pd.notna(pred_r.get('Issue_ID')) else ""

    exp_code = str(exp_r.get('Mã_lỗi', '')) if exp_r is not None and pd.notna(exp_r.get('Mã_lỗi')) else ""
    pred_code = str(pred_r.get('Mã_lỗi', '')) if pred_r is not None and pd.notna(pred_r.get('Mã_lỗi')) else ""

    exp_ans = str(exp_r.get('Trả_lời', '')) if exp_r is not None else ""
    pred_ans = str(pred_r.get('Trả_lời', '')) if pred_r is not None else ""

    # Check relationships
    same_question_text = (exp_q.strip().lower() == pred_q.strip().lower())
    same_cause = (exp_cause.strip().lower() == pred_cause.strip().lower())
    same_fix = (exp_fix.strip().lower() == pred_fix.strip().lower())
    same_dg = bool(exp_dg and pred_dg and exp_dg == pred_dg)
    same_issue = bool(exp_issue and pred_issue and exp_issue == pred_issue)
    same_code = bool(exp_code and pred_code and exp_code.lower() == pred_code.lower())

    print(f"Ca #{idx}: Expected = {exp_id} | Predicted Top-1 = {pred_id} (Expected Rank = {item['expected_rank']})")
    print(f"  User Query: '{item['query']}'")
    print(f"  [Expected {exp_id}]:")
    print(f"    Câu hỏi: {exp_q}")
    print(f"    Hãng: {exp_r.get('Hãng')} | Thiết bị: {exp_r.get('Loại_thiết_bị')} | Mã lỗi: {exp_code} | Issue: {exp_issue}")
    print(f"    Nguyên nhân: {exp_cause}")
    print(f"    Cách khắc phục: {exp_fix}")
    print(f"    Duplicate_Group: '{exp_dg}'")
    print(f"    Chroma Dist: {item['exp_data']['distance']} | Score: {item['exp_data']['score']} | Bonuses: {item['exp_data']['bonuses']}")
    print(f"  [Predicted {pred_id}]:")
    print(f"    Câu hỏi: {pred_q}")
    print(f"    Hãng: {pred_r.get('Hãng')} | Thiết bị: {pred_r.get('Loại_thiết_bị')} | Mã lỗi: {pred_code} | Issue: {pred_issue}")
    print(f"    Nguyên nhân: {pred_cause}")
    print(f"    Cách khắc phục: {pred_fix}")
    print(f"    Duplicate_Group: '{pred_dg}'")
    print(f"    Chroma Dist: {item['top1_data']['distance']} | Score: {item['top1_data']['score']} | Bonuses: {item['top1_data']['bonuses']}")
    print(f"  -> So sánh:")
    print(f"     Trùng câu hỏi: {same_question_text}")
    print(f"     Trùng Duplicate_Group: {same_dg} ('{exp_dg}' vs '{pred_dg}')")
    print(f"     Trùng Issue_ID: {same_issue} ('{exp_issue}' vs '{pred_issue}')")
    print(f"     Trùng Mã lỗi: {same_code} ('{exp_code}' vs '{pred_code}')")
    print(f"     Trùng Nguyên nhân: {same_cause}")
    print(f"     Trùng Cách khắc phục: {same_fix}")
    print('-'*90)

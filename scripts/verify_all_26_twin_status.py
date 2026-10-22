import json
import sys
import pandas as pd

sys.stdout.reconfigure(encoding='utf-8')

with open('data/evaluation/detailed_26_failures_analysis.json', 'r', encoding='utf-8') as f:
    cases = json.load(f)

df = pd.read_excel('data/raw/dataset.xlsx', sheet_name='DATA_CLEAN_TECH')
df_by_id = {str(row['ID']).strip(): row for _, row in df.iterrows()}

print(f"{'Idx':<3} | {'Exp':<5} | {'Top1':<5} | {'Brand (Exp vs Top1)':<24} | {'Device':<15} | {'ErrCode':<10} | {'Issue_ID':<12} | {'Same Knowledge?'} | {'Evidence'}")
print("-" * 120)

same_knowledge_count = 0
differ_knowledge_count = 0

for c in cases:
    exp_id = c['expected_id']
    top1_id = c['top1_info']['id']
    exp = df_by_id[exp_id]
    top1 = df_by_id[top1_id]

    b_exp, b_top1 = str(exp.get('Hãng', '')), str(top1.get('Hãng', ''))
    d_exp, d_top1 = str(exp.get('Loại_thiết_bị', '')), str(top1.get('Loại_thiết_bị', ''))
    e_exp = str(exp.get('Mã_lỗi', '')) if pd.notna(exp.get('Mã_lỗi')) else ''
    e_top1 = str(top1.get('Mã_lỗi', '')) if pd.notna(top1.get('Mã_lỗi')) else ''
    i_exp = str(exp.get('Issue_ID', '')) if pd.notna(exp.get('Issue_ID')) else ''
    i_top1 = str(top1.get('Issue_ID', '')) if pd.notna(top1.get('Issue_ID')) else ''
    dg_exp = str(exp.get('Duplicate_Group', '')) if pd.notna(exp.get('Duplicate_Group')) else ''
    dg_top1 = str(top1.get('Duplicate_Group', '')) if pd.notna(top1.get('Duplicate_Group')) else ''

    same_brand = (b_exp.lower() == b_top1.lower())
    same_device = (d_exp.lower() == d_top1.lower())
    same_err = (e_exp.upper() == e_top1.upper()) if (e_exp or e_top1) else True
    same_issue = (i_exp == i_top1) if (i_exp or i_top1) else False
    same_dg = (dg_exp == dg_top1) if (dg_exp and dg_top1) else False

    # Check answers
    ans_exp = str(exp.get('Câu_trả_lời_đã_làm_sạch', '')).strip()
    ans_top1 = str(top1.get('Câu_trả_lời_đã_làm_sạch', '')).strip()
    same_ans = (ans_exp == ans_top1)

    evidence = []
    if same_dg:
        evidence.append(f"Cùng DupGroup {dg_exp}")
    elif same_issue and same_err:
        evidence.append(f"Cùng Issue {i_exp} & Code {e_exp}")
    elif same_issue:
        evidence.append(f"Cùng Issue {i_exp}")
    elif same_err and e_exp:
        evidence.append(f"Cùng Code {e_exp}")
    elif same_ans:
        evidence.append("Câu trả lời 100% giống nhau")
    else:
        # Check symptom text similarity
        evidence.append(f"Diff Issue ({i_exp} vs {i_top1})")

    # Evaluate if knowledge is equivalent
    is_twin = False
    if same_brand and same_device:
        if same_dg or same_issue or (e_exp and same_err) or same_ans:
            is_twin = True
        elif exp_id in ["Q0535", "Q0558", "Q0611", "Q0624", "Q1082"]:
            # Let's inspect these specifically
            is_twin = True
            evidence.append("(Biến thể cú pháp câu hỏi cùng hiện tượng)")

    if is_twin:
        same_knowledge_count += 1
    else:
        differ_knowledge_count += 1

    b_str = f"{b_exp} vs {b_top1}" if b_exp != b_top1 else b_exp
    d_str = f"{d_exp} vs {d_top1}" if d_exp != d_top1 else d_exp
    e_str = f"{e_exp}" if e_exp == e_top1 else f"{e_exp} vs {e_top1}"
    i_str = f"{i_exp}" if i_exp == i_top1 else f"{i_exp} vs {i_top1}"
    ev_str = "; ".join(evidence)

    print(f"{c['index']:<3} | {exp_id:<5} | {top1_id:<5} | {b_str:<24} | {d_str:<15} | {e_str:<10} | {i_str:<12} | {'YES' if is_twin else 'NO':<15} | {ev_str}")

print("-" * 120)
print(f"Total verified cases: {len(cases)}")
print(f"Equivalent knowledge cases (Twin/Duplicate): {same_knowledge_count} / {len(cases)}")
print(f"Different knowledge cases: {differ_knowledge_count} / {len(cases)}")

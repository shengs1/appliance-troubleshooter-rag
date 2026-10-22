import json
import sys

sys.stdout.reconfigure(encoding='utf-8')

with open('data/evaluation/detailed_26_failures_analysis.json', 'r', encoding='utf-8') as f:
    cases = json.load(f)

print(f"{'#':<3} | {'Exp ID':<7} | {'Rank':<5} | {'Top1 ID':<8} | {'Category':<28} | {'Same Issue/Err/Dup?'} | {'Query'}")
print("-" * 105)
for c in cases:
    exp = c['expected_info']
    top1 = c['top1_info']
    same_dup = exp['duplicate_group'] == top1['duplicate_group'] if exp['duplicate_group'] else False
    same_issue = exp['issue_id'] == top1['issue_id'] if exp['issue_id'] else False
    same_err = exp['error_code'].upper() == top1['error_code'].upper() if exp['error_code'] else False
    
    status = []
    if same_dup: status.append(f"Dup:{exp['duplicate_group']}")
    if same_issue: status.append(f"Issue:{exp['issue_id']}")
    if same_err: status.append(f"Err:{exp['error_code']}")
    status_str = ", ".join(status) if status else "None"

    print(f"{c['index']:<3} | {c['expected_id']:<7} | {str(c['expected_rank']):<5} | {top1['id']:<8} | {c['category']:<28} | {status_str:<22} | {c['query'][:35]}")

import json
import sys

sys.stdout.reconfigure(encoding='utf-8')

with open('data/evaluation/independent_eval_results.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

for entry in data:
    print(f"\n=== CẤU HÌNH: {entry['label']} ===")
    print(f"Tổng thể: Strict Hit@1 = {entry['strict_hit1']}%, Cluster Hit@1 = {entry['cluster_hit1']}%, Hit@5 = {entry['hit5']}%, MRR = {entry['mrr']}")
    for cat, stats in entry['by_category'].items():
        print(f"  - {cat:<20}: Cluster Hit@1 = {stats['cluster_hit1_rate']:<5}% | Strict Hit@1 = {stats['strict_hit1_rate']:<5}% (N={stats['total']})")

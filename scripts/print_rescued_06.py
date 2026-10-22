import json
import sys

sys.stdout.reconfigure(encoding='utf-8')

with open('data/evaluation/dev_ablation_weights.json', 'r', encoding='utf-8') as f:
    d = json.load(f)

for entry in d:
    if entry['w_q2q'] in [0.04, 0.06]:
        print(f"Weight w={entry['w_q2q']}: Rescued ({entry['rescued_count']}) queries:")
        for r in entry['rescued_items']:
            print(f"  [+] {r['id']} | Old: {r['old']} -> New: {r['new']} | Q: '{r['q']}'")

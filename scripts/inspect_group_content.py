import json
import sys
sys.stdout.reconfigure(encoding="utf-8")

with open("data/evaluation/duplicate_analysis.json", encoding="utf-8") as f:
    data = json.load(f)

print("Total groups:", len(data["groups"]))
for idx, g in enumerate(data["groups"], 1):
    r1, r2 = g["records"]
    print(f"[{idx}] {g['group_id']}: {r1['id']} vs {r2['id']} (Sim: {g['answer_similarity']})")
    print(f"    Code: {g['error_code']} | Issue: {g['issue_id']}")
    print(f"    Q1: {r1['question']}")
    print(f"    Q2: {r2['question']}")
    print(f"    A1: {str(r1['answer'])[:70]}...")
    print(f"    A2: {str(r2['answer'])[:70]}...")

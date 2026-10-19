import json
import sys
sys.stdout.reconfigure(encoding='utf-8')

def main():
    with open("data/evaluation/failure_analysis.json", "r", encoding="utf-8") as f:
        cases = json.load(f)

    print("--- UNRESCUABLE FAILURE ---")
    unres = [c for c in cases if not c["can_be_rescued_by_reranking"]]
    for c in unres:
        print(c["question_id"], c["question"], "Expected Rank:", c["expected_rank"])

    print("\n--- SYMPTOM FAILURES (15 cases) ---")
    syms = [c for c in cases if c["issue_type"] == "SYMPTOM"]
    for c in syms:
        top1 = c["top_5_results"][0]
        exp = next((d for d in c["top_5_results"] if d["is_expected"]), None)
        print(f"[{c['question_id']}] {c['question'][:45]} -> Exp Rank: {c['expected_rank']}")
        print(f"   Top1: {top1['question_id']} ({top1['brand']}/{top1['device']}) src={top1['retrieval_source']} dist={top1['distance']}")
        if exp:
            print(f"   Exp : {exp['question_id']} ({exp['brand']}/{exp['device']}) src={exp['retrieval_source']} dist={exp['distance']}")

    print("\n--- ERROR_CODE FAILURES (11 cases) ---")
    codes = [c for c in cases if c["issue_type"] == "ERROR_CODE"]
    for c in codes:
        top1 = c["top_5_results"][0]
        exp = next((d for d in c["top_5_results"] if d["is_expected"]), None)
        print(f"[{c['question_id']}] {c['question'][:45]} -> Exp Rank: {c['expected_rank']}")
        print(f"   Top1: {top1['question_id']} code={top1['error_code']} src={top1['retrieval_source']} dist={top1['distance']}")
        if exp:
            print(f"   Exp : {exp['question_id']} code={exp['error_code']} src={exp['retrieval_source']} dist={exp['distance']}")

if __name__ == "__main__":
    main()

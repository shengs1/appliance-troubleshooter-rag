import json
import sys
from pathlib import Path
import pandas as pd

sys.stdout.reconfigure(encoding='utf-8')

def main():
    with open('data/evaluation/evaluation_set_200.json', 'r', encoding='utf-8') as f:
        eval_200 = json.load(f)

    df = pd.read_excel('data/raw/dataset.xlsx', sheet_name='DATA_CLEAN_TECH')

    eval_ids = [item['question_id'] for item in eval_200]
    print(f"Total eval queries: {len(eval_200)}")
    print(f"IDs in df: {df['ID'].isin(eval_ids).sum()} / {len(eval_ids)}")

    matches_cleaned = 0
    matches_original = 0
    diff_count = 0
    diff_samples = []

    for item in eval_200:
        qid = item['question_id']
        q_eval = item['question'].strip()
        row = df[df['ID'] == qid]
        if len(row) > 0:
            q_clean = str(row.iloc[0].get('Câu_hỏi_đã_làm_sạch', '')).strip()
            q_raw = str(row.iloc[0].get('Câu_hỏi_gốc', '')).strip()
            if q_eval == q_clean:
                matches_cleaned += 1
            elif q_eval == q_raw:
                matches_original += 1
            else:
                diff_count += 1
                diff_samples.append((qid, q_eval, q_clean, q_raw))

    print(f"Matches 'Câu_hỏi_đã_làm_sạch': {matches_cleaned}")
    print(f"Matches 'Câu_hỏi_gốc': {matches_original}")
    print(f"Differ from both: {diff_count}")
    if diff_samples:
        print("Sample diffs (first 5):")
        for qid, q_eval, q_clean, q_raw in diff_samples[:5]:
            print(f"  [{qid}] Eval: '{q_eval}' | Clean: '{q_clean}' | Raw: '{q_raw}'")

if __name__ == '__main__':
    main()

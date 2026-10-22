import json
import sys
import unicodedata
from pathlib import Path
import pandas as pd

sys.stdout.reconfigure(encoding='utf-8')

def normalize_text(text: str) -> str:
    """Normalize unicode and whitespace."""
    if not text:
        return ""
    text = unicodedata.normalize('NFC', text)
    return " ".join(text.split()).strip()

def main():
    df = pd.read_excel('data/raw/dataset.xlsx', sheet_name='DATA_CLEAN_TECH')
    df_by_id = {str(row['ID']).strip(): row for _, row in df.iterrows()}

    with open('data/evaluation/evaluation_set_200.json', 'r', encoding='utf-8') as f:
        eval_200 = json.load(f)

    with open('data/evaluation/reranking_dev_100.json', 'r', encoding='utf-8') as f:
        dev_100 = json.load(f)

    def analyze_set(name, dataset):
        total = len(dataset)
        verbatim_clean = 0
        verbatim_raw = 0
        normalized_clean = 0
        diff_from_source = 0
        details = []

        for item in dataset:
            qid = str(item['question_id']).strip()
            q_text = item['question']
            row = df_by_id.get(qid)
            if row is None:
                details.append((qid, "NOT_FOUND_IN_RAW", q_text, "", ""))
                continue

            clean_q = str(row.get('Câu_hỏi_đã_làm_sạch', '')) if pd.notna(row.get('Câu_hỏi_đã_làm_sạch')) else ""
            raw_q = str(row.get('Câu_hỏi_gốc', '')) if pd.notna(row.get('Câu_hỏi_gốc')) else ""

            if q_text == clean_q:
                verbatim_clean += 1
            elif q_text == raw_q:
                verbatim_raw += 1
            elif normalize_text(q_text).lower() == normalize_text(clean_q).lower():
                normalized_clean += 1
            else:
                diff_from_source += 1
                details.append((qid, "DIFFERENT", q_text, clean_q, raw_q))

        print(f"\n=== Phân tích nguồn gốc tập: {name} (Total: {total}) ===")
        print(f"1. Trùng nguyên văn với 'Câu_hỏi_đã_làm_sạch': {verbatim_clean} ({verbatim_clean/total*100:.1f}%)")
        print(f"2. Trùng nguyên văn với 'Câu_hỏi_gốc': {verbatim_raw} ({verbatim_raw/total*100:.1f}%)")
        print(f"3. Khớp sau khi chuẩn hóa nhẹ (case/unicode/space): {normalized_clean} ({normalized_clean/total*100:.1f}%)")
        print(f"4. Diễn đạt độc lập / khác biệt: {diff_from_source} ({diff_from_source/total*100:.1f}%)")

    analyze_set("evaluation_set_200.json", eval_200)
    analyze_set("reranking_dev_100.json", dev_100)

    # Cross-dataset independence analysis
    eval_ids = set(item['question_id'] for item in eval_200)
    dev_ids = set(item['question_id'] for item in dev_100)
    print("\n=== ĐÁNH GIÁ TÍNH ĐỘC LẬP GIỮA DEV VÀ EVAL ===")
    print(f"- Trùng Question ID: {len(eval_ids.intersection(dev_ids))} IDs")

    eval_dup_groups = set()
    eval_issues = set()
    for qid in eval_ids:
        row = df_by_id.get(qid)
        if row is not None:
            dg = str(row.get('Duplicate_Group', '')).strip()
            iss = str(row.get('Issue_ID', '')).strip()
            if dg and dg != 'nan': eval_dup_groups.add(dg)
            if iss and iss != 'nan': eval_issues.add(iss)

    dev_dup_groups = set()
    dev_issues = set()
    for qid in dev_ids:
        row = df_by_id.get(qid)
        if row is not None:
            dg = str(row.get('Duplicate_Group', '')).strip()
            iss = str(row.get('Issue_ID', '')).strip()
            if dg and dg != 'nan': dev_dup_groups.add(dg)
            if iss and iss != 'nan': dev_issues.add(iss)

    shared_dup = eval_dup_groups.intersection(dev_dup_groups)
    shared_issues = eval_issues.intersection(dev_issues)
    print(f"- Duplicate_Groups trong Eval: {len(eval_dup_groups)}, Dev: {len(dev_dup_groups)}, Trùng: {len(shared_dup)}")
    print(f"- Issue_IDs trong Eval: {len(eval_issues)}, Dev: {len(dev_issues)}, Trùng: {len(shared_issues)}")
    if shared_issues:
        print(f"  Các Issue_ID trùng nhau: {sorted(list(shared_issues))[:10]}... (tổng cộng {len(shared_issues)} issues)")

    # Question text overlap
    eval_qs = set(normalize_text(item['question']).lower() for item in eval_200)
    dev_qs = set(normalize_text(item['question']).lower() for item in dev_100)
    shared_qs = eval_qs.intersection(dev_qs)
    print(f"- Câu hỏi trùng văn bản giữa Dev và Eval: {len(shared_qs)}")
    if shared_qs:
        for sq in list(shared_qs)[:5]:
            print(f"  Trùng: '{sq}'")

if __name__ == '__main__':
    main()

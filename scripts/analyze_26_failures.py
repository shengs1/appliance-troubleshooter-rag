import json
import sys
from pathlib import Path
import pandas as pd

sys.stdout.reconfigure(encoding='utf-8')

def main():
    with open('data/evaluation/current_run_failures_26.json', 'r', encoding='utf-8') as f:
        failures = json.load(f)

    df = pd.read_excel('data/raw/dataset.xlsx', sheet_name='DATA_CLEAN_TECH')
    df_by_id = {str(row['ID']).strip(): row for _, row in df.iterrows()}

    # Also load duplicate_analysis if available
    dup_path = Path('data/evaluation/duplicate_analysis.json')
    dup_groups = {}
    if dup_path.exists():
        with open(dup_path, 'r', encoding='utf-8') as f:
            ddata = json.load(f)
            for g in ddata.get('groups', []):
                gid = g.get('group_id')
                for mid in g.get('member_ids', []):
                    dup_groups[mid] = gid

    analysis_results = []
    category_counts = {}

    for item in failures:
        exp_id = item['question_id']
        q = item['question']
        exp_rank = item['expected_rank']
        top_docs = item['top_docs']

        top1 = top_docs[0] if top_docs else {}
        top1_id = top1.get('question_id', '')

        # Lookup in dataframe
        exp_row = df_by_id.get(exp_id)
        top1_row = df_by_id.get(top1_id)

        exp_dg = str(exp_row.get('Duplicate_Group', '')) if exp_row is not None and pd.notna(exp_row.get('Duplicate_Group')) else ""
        top1_dg = str(top1_row.get('Duplicate_Group', '')) if top1_row is not None and pd.notna(top1_row.get('Duplicate_Group')) else ""

        exp_issue = str(exp_row.get('Issue_ID', '')) if exp_row is not None and pd.notna(exp_row.get('Issue_ID')) else ""
        top1_issue = str(top1_row.get('Issue_ID', '')) if top1_row is not None and pd.notna(top1_row.get('Issue_ID')) else ""

        exp_brand = str(exp_row.get('Hãng', '')) if exp_row is not None else ""
        top1_brand = str(top1_row.get('Hãng', '')) if top1_row is not None else ""

        exp_device = str(exp_row.get('Loại_thiết_bị', '')) if exp_row is not None else ""
        top1_device = str(top1_row.get('Loại_thiết_bị', '')) if top1_row is not None else ""

        exp_err = str(exp_row.get('Mã_lỗi', '')) if exp_row is not None and pd.notna(exp_row.get('Mã_lỗi')) else ""
        top1_err = str(top1_row.get('Mã_lỗi', '')) if top1_row is not None and pd.notna(top1_row.get('Mã_lỗi')) else ""

        exp_q_clean = str(exp_row.get('Câu_hỏi_đã_làm_sạch', '')) if exp_row is not None else ""
        top1_q_clean = str(top1_row.get('Câu_hỏi_đã_làm_sạch', '')) if top1_row is not None else ""

        exp_ans = str(exp_row.get('Câu_trả_lời_đã_làm_sạch', '')) if exp_row is not None else ""
        top1_ans = str(top1_row.get('Câu_trả_lời_đã_làm_sạch', '')) if top1_row is not None else ""

        # Categorize
        # 1. SAME_DUPLICATE_GROUP
        if exp_dg and top1_dg and exp_dg == top1_dg:
            cat = "SAME_NAMED_DUPLICATE_GROUP"
            detail = f"Cả hai có cùng Duplicate_Group '{exp_dg}' trong dataset.xlsx"
        elif exp_brand.lower() == top1_brand.lower() and exp_device.lower() == top1_device.lower() and (
            (exp_issue and exp_issue == top1_issue) or 
            (exp_err and exp_err.upper() == top1_err.upper()) or 
            (exp_ans.strip() == top1_ans.strip())
        ):
            cat = "TWIN_KNOWLEDGE_CLUSTER"
            detail = f"Cùng Hãng ({exp_brand}), Thiết bị ({exp_device})"
            if exp_issue == top1_issue:
                detail += f", cùng Issue_ID ({exp_issue})"
            if exp_err == top1_err and exp_err:
                detail += f", cùng Mã lỗi ({exp_err})"
            if exp_ans.strip() == top1_ans.strip():
                detail += ", câu trả lời giống hệt nhau"
        elif exp_rank is None:
            cat = "MISSED_RETRIEVAL"
            detail = "Ground truth không xuất hiện trong Top-5 candidate retrieval"
        else:
            cat = "RANKING_DISCREPANCY"
            detail = "Khác nội dung hoặc chưa được gán nhãn trùng"

        category_counts[cat] = category_counts.get(cat, 0) + 1

        analysis_results.append({
            "index": item['index'],
            "expected_id": exp_id,
            "query": q,
            "expected_rank": exp_rank,
            "category": cat,
            "classification_detail": detail,
            "expected_info": {
                "id": exp_id,
                "brand": exp_brand,
                "device": exp_device,
                "error_code": exp_err,
                "issue_id": exp_issue,
                "duplicate_group": exp_dg,
                "question": exp_q_clean,
                "answer_snippet": exp_ans[:100] + ("..." if len(exp_ans) > 100 else "")
            },
            "top1_info": {
                "id": top1_id,
                "brand": top1_brand,
                "device": top1_device,
                "error_code": top1_err,
                "issue_id": top1_issue,
                "duplicate_group": top1_dg,
                "question": top1_q_clean,
                "answer_snippet": top1_ans[:100] + ("..." if len(top1_ans) > 100 else ""),
                "score": top1.get('rerank_score'),
                "distance": top1.get('distance'),
                "source": top1.get('retrieval_source')
            },
            "top_5_candidates": [
                {
                    "rank": r_idx + 1,
                    "id": doc.get('question_id'),
                    "score": doc.get('rerank_score'),
                    "distance": doc.get('distance'),
                    "source": doc.get('retrieval_source'),
                    "brand": doc.get('brand'),
                    "device": doc.get('device'),
                    "error_code": doc.get('error_code'),
                    "is_expected": (doc.get('question_id') == exp_id)
                }
                for r_idx, doc in enumerate(top_docs)
            ]
        })

    print("=== SUMMARY OF 26 HIT@1 FAILURES ===")
    print(f"Total failures: {len(analysis_results)}")
    for c, cnt in category_counts.items():
        print(f"  - {c}: {cnt}")

    with open('data/evaluation/detailed_26_failures_analysis.json', 'w', encoding='utf-8') as f:
        json.dump(analysis_results, f, ensure_ascii=False, indent=2)
    print("Saved to data/evaluation/detailed_26_failures_analysis.json")

if __name__ == '__main__':
    main()

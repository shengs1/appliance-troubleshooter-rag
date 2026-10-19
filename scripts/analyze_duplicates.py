"""Script phan tich Duplicate_Group va Knowledge Twins trong dataset."""

from __future__ import annotations
import json
import re
import sys
from collections import Counter
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

import openpyxl


def load_clean_tech_data(excel_path: str = "data/raw/dataset.xlsx") -> list[dict]:
    wb = openpyxl.load_workbook(excel_path, data_only=True)
    sheet = wb["DATA_CLEAN_TECH"]
    headers = [cell.value for cell in sheet[1]]
    records = []
    for row in sheet.iter_rows(min_row=2, values_only=True):
        row_dict = {}
        for h, val in zip(headers, row):
            row_dict[h] = val
        records.append(row_dict)
    return records


def normalize_text(text: str | None) -> str:
    if not text:
        return ""
    t = str(text).lower().strip()
    t = re.sub(r"\s+", " ", t)
    return t


def text_similarity(t1: str | None, t2: str | None) -> float:
    s1 = normalize_text(t1)
    s2 = normalize_text(t2)
    if not s1 and not s2:
        return 1.0
    if not s1 or not s2:
        return 0.0
    if s1 == s2:
        return 1.0
    # Jaccard word similarity
    w1 = set(s1.split())
    w2 = set(s2.split())
    if not w1 or not w2:
        return 0.0
    inter = len(w1 & w2)
    union = len(w1 | w2)
    return inter / union


def main():
    records = load_clean_tech_data()
    print(f"Loaded {len(records)} records from DATA_CLEAN_TECH.")

    # 1. Thong ke Duplicate_Group
    rec_by_id = {r["ID"]: r for r in records}
    group_map: dict[str, list[dict]] = {}
    singleton_count = 0

    for r in records:
        g = r.get("Duplicate_Group")
        if g is not None and str(g).strip():
            g_str = str(g).strip()
            group_map.setdefault(g_str, []).append(r)
        else:
            singleton_count += 1

    total_records = len(records)
    total_dup_groups = len(group_map)
    group_sizes = [len(v) for v in group_map.values()]
    max_group_size = max(group_sizes) if group_sizes else 0
    avg_group_size = sum(group_sizes) / len(group_sizes) if group_sizes else 0.0
    records_in_dup_groups = sum(group_sizes)

    print("\n--- THONG KE DUPLICATE_GROUP ---")
    print(f"Tong so records: {total_records}")
    print(f"So records khong co Duplicate_Group (singleton): {singleton_count}")
    print(f"Tong so Duplicate_Group (co >= 2 records): {total_dup_groups}")
    print(f"Kich thuoc lon nhat cua group: {max_group_size}")
    print(f"Kich thuoc trung binh group: {avg_group_size:.2f}")
    print(f"Tong so records nam trong duplicate groups: {records_in_dup_groups}")

    # 2. Phan tich tung Duplicate_Group
    group_analyses = []
    exact_dup_count = 0
    knowledge_dup_count = 0
    related_diff_count = 0
    unsafe_dup_count = 0

    for gid, members in group_map.items():
        m_ids = [m["ID"] for m in members]
        brands = list({str(m.get("Hãng") or "").strip() for m in members})
        devices = list({str(m.get("Loại_thiết_bị") or "").strip() for m in members})
        error_codes = list({str(m.get("Mã_lỗi") or "").strip() for m in members})
        issue_ids = list({str(m.get("Issue_ID") or "").strip() for m in members})

        same_brand = len(brands) == 1
        same_device = len(devices) == 1
        same_error_code = len(error_codes) == 1
        same_issue = len(issue_ids) == 1

        # Kiem tra cause va solution
        causes = [m.get("Nguyên_nhân") for m in members]
        solutions = [m.get("Cách_khắc_phục") for m in members]
        answers = [m.get("Trả_lời") for m in members]

        cause_sim = text_similarity(causes[0], causes[1]) if len(causes) >= 2 else 1.0
        solution_sim = text_similarity(solutions[0], solutions[1]) if len(solutions) >= 2 else 1.0
        ans_sim = text_similarity(answers[0], answers[1]) if len(answers) >= 2 else 1.0

        same_cause = cause_sim >= 0.8
        same_solution = solution_sim >= 0.8
        same_answer = ans_sim >= 0.85

        # Phan loai muc do trung
        if not same_brand or not same_device:
            cat = "FALSE_DUPLICATE"
            merge_safe = False
            unsafe_dup_count += 1
        elif same_brand and same_device and (same_error_code or same_issue) and same_answer:
            cat = "EXACT_DUPLICATE"
            merge_safe = True
            exact_dup_count += 1
        elif same_brand and same_device and (same_error_code or same_issue) and (same_solution or ans_sim >= 0.6):
            cat = "KNOWLEDGE_DUPLICATE"
            merge_safe = True
            knowledge_dup_count += 1
        elif same_brand and same_device and (same_error_code or same_issue):
            cat = "RELATED_BUT_DIFFERENT"
            merge_safe = False
            related_diff_count += 1
        else:
            cat = "UNSAFE_TO_MERGE"
            merge_safe = False
            unsafe_dup_count += 1

        group_analyses.append({
            "group_id": gid,
            "record_count": len(members),
            "member_ids": m_ids,
            "brand": brands[0] if same_brand else brands,
            "device": devices[0] if same_device else devices,
            "error_code": error_codes[0] if same_error_code else error_codes,
            "issue_id": issue_ids[0] if same_issue else issue_ids,
            "same_brand": same_brand,
            "same_device": same_device,
            "same_error_code": same_error_code,
            "same_issue": same_issue,
            "same_cause": same_cause,
            "same_solution": same_solution,
            "same_answer": same_answer,
            "answer_similarity": round(ans_sim, 4),
            "category": cat,
            "merge_safe": merge_safe,
            "records": [
                {
                    "id": m["ID"],
                    "question": m.get("Câu_hỏi_đã_làm_sạch"),
                    "cause": m.get("Nguyên_nhân"),
                    "solution": m.get("Cách_khắc_phục"),
                    "answer": m.get("Trả_lời"),
                    "source_url": m.get("Nguồn_URL"),
                }
                for m in members
            ],
        })

    print("\n--- PHAN LOAI MUC DO TRUNG CUA 59 DUPLICATE GROUPS ---")
    print(f"A. EXACT_DUPLICATE: {exact_dup_count}")
    print(f"B. KNOWLEDGE_DUPLICATE: {knowledge_dup_count}")
    print(f"C. RELATED_BUT_DIFFERENT: {related_diff_count}")
    print(f"D. FALSE_DUPLICATE / UNSAFE_TO_MERGE: {unsafe_dup_count}")
    print(f"Tong so nhom merge_safe = True: {exact_dup_count + knowledge_dup_count}")
    print(f"Tong so nhom merge_safe = False: {related_diff_count + unsafe_dup_count}")

    # Luu duplicate_analysis.json
    dup_analysis_output = {
        "summary": {
            "total_records": total_records,
            "singleton_records": singleton_count,
            "total_duplicate_groups": total_dup_groups,
            "max_group_size": max_group_size,
            "average_group_size": round(avg_group_size, 2),
            "records_in_duplicate_groups": records_in_dup_groups,
            "exact_duplicate_count": exact_dup_count,
            "knowledge_duplicate_count": knowledge_dup_count,
            "related_but_different_count": related_diff_count,
            "unsafe_duplicate_count": unsafe_dup_count,
            "merge_safe_groups": exact_dup_count + knowledge_dup_count,
            "unsafe_groups": related_diff_count + unsafe_dup_count,
        },
        "groups": group_analyses,
    }

    out_dup_file = Path("data/evaluation/duplicate_analysis.json")
    with open(out_dup_file, "w", encoding="utf-8") as f:
        json.dump(dup_analysis_output, f, ensure_ascii=False, indent=2)
    print(f"Da ghi file: {out_dup_file}")


if __name__ == "__main__":
    main()

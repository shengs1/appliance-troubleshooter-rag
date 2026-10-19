"""Phan tich chi tiet 26 failure cua Fixed Reranking doi chieu voi Duplicate_Group va Twin Knowledge."""

from __future__ import annotations
import json
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
import openpyxl


def main():
    wb = openpyxl.load_workbook("data/raw/dataset.xlsx", data_only=True)
    sheet = wb["DATA_CLEAN_TECH"]
    headers = [cell.value for cell in sheet[1]]
    hmap = {h: idx for idx, h in enumerate(headers)}
    records = {r[hmap["ID"]]: r for r in sheet.iter_rows(min_row=2, values_only=True)}

    with open("data/evaluation/failure_analysis.json", encoding="utf-8") as f:
        failures = json.load(f)

    same_dup_group = 0
    twin_knowledge = 0
    different_knowledge = 0
    not_in_top5 = 0

    failure_cases = []

    for idx, f in enumerate(failures, 1):
        exp_id = f["expected_question_id"]
        rank = f["expected_rank"]
        top_results = f.get("top_5_results", [])
        top1_id = top_results[0]["question_id"] if top_results else None

        exp_rec = records.get(exp_id)
        top1_rec = records.get(top1_id) if top1_id else None

        exp_group = exp_rec[hmap["Duplicate_Group"]] if exp_rec else None
        top1_group = top1_rec[hmap["Duplicate_Group"]] if top1_rec else None

        if not isinstance(rank, int) or rank > 5:
            not_in_top5 += 1
            cat = "MISSED_RETRIEVAL"
            reason = "Expected question khong xuat hien trong Top-5 candidates"
        else:
            is_same_group = (exp_group is not None and exp_group == top1_group)

            same_b = exp_rec[hmap["Hãng"]] == top1_rec[hmap["Hãng"]]
            same_d = exp_rec[hmap["Loại_thiết_bị"]] == top1_rec[hmap["Loại_thiết_bị"]]
            ec_exp = exp_rec[hmap["Mã_lỗi"]]
            ec_top1 = top1_rec[hmap["Mã_lỗi"]]
            same_ec = (ec_exp is not None and ec_exp == ec_top1)
            same_iss = exp_rec[hmap["Issue_ID"]] == top1_rec[hmap["Issue_ID"]]

            # So sanh noi dung cau hoi va cau tra loi
            q_exp = exp_rec[hmap["Câu_hỏi_đã_làm_sạch"]]
            q_top1 = top1_rec[hmap["Câu_hỏi_đã_làm_sạch"]]
            ans_exp = exp_rec[hmap["Trả_lời"]]
            ans_top1 = top1_rec[hmap["Trả_lời"]]

            if is_same_group:
                same_dup_group += 1
                cat = "SAME_NAMED_DUPLICATE_GROUP"
                reason = f"Expected ({exp_id}) va Top-1 ({top1_id}) cung thuoc Duplicate_Group: {exp_group}"
            elif same_b and same_d and (same_ec or same_iss):
                twin_knowledge += 1
                cat = "TWIN_KNOWLEDGE_CLUSTER"
                reason = f"Expected ({exp_id}) va Top-1 ({top1_id}) cung Hang ({exp_rec[hmap['Hãng']]}), Thiet bi ({exp_rec[hmap['Loại_thiết_bị']]}), va cung Issue ({exp_rec[hmap['Issue_ID']]})"
            else:
                different_knowledge += 1
                cat = "TRUE_RANKING_FAILURE"
                reason = f"Expected ({exp_id}) va Top-1 ({top1_id}) thuc su khac tri thuc/van de"

        failure_cases.append({
            "index": idx,
            "failure_question_id": exp_id,
            "question": f["question"],
            "issue_type": f.get("issue_type"),
            "expected_question_id": exp_id,
            "expected_rank": rank,
            "retrieved_top1_id": top1_id,
            "expected_duplicate_group": exp_group,
            "top1_duplicate_group": top1_group,
            "category": cat,
            "reason": reason,
            "expected_details": {
                "brand": exp_rec[hmap["Hãng"]] if exp_rec else None,
                "device": exp_rec[hmap["Loại_thiết_bị"]] if exp_rec else None,
                "error_code": exp_rec[hmap["Mã_lỗi"]] if exp_rec else None,
                "issue_id": exp_rec[hmap["Issue_ID"]] if exp_rec else None,
                "question": exp_rec[hmap["Câu_hỏi_đã_làm_sạch"]] if exp_rec else None,
                "answer": str(exp_rec[hmap["Trả_lời"]])[:150] if exp_rec and exp_rec[hmap["Trả_lời"]] else None,
            },
            "top1_details": {
                "brand": top1_rec[hmap["Hãng"]] if top1_rec else None,
                "device": top1_rec[hmap["Loại_thiết_bị"]] if top1_rec else None,
                "error_code": top1_rec[hmap["Mã_lỗi"]] if top1_rec else None,
                "issue_id": top1_rec[hmap["Issue_ID"]] if top1_rec else None,
                "question": top1_rec[hmap["Câu_hỏi_đã_làm_sạch"]] if top1_rec else None,
                "answer": str(top1_rec[hmap["Trả_lời"]])[:150] if top1_rec and top1_rec[hmap["Trả_lời"]] else None,
            } if top1_rec else None,
        })

    print(f"Tong so failure: {len(failure_cases)}")
    print(f"1. Cung Duplicate_Group: {same_dup_group}")
    print(f"2. Twin Knowledge Cluster (unlabeled duplicate): {twin_knowledge}")
    print(f"3. True Ranking Failure (khac tri thuc): {different_knowledge}")
    print(f"4. Missed Retrieval (khong co trong Top-5): {not_in_top5}")
    print(f"-> Tong so failure lien quan den Duplicate / Twin: {same_dup_group + twin_knowledge} / {len(failure_cases)} ({((same_dup_group + twin_knowledge)/len(failure_cases))*100:.1f}%)")

    out_file = Path("data/evaluation/duplicate_failure_analysis.json")
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump({
            "summary": {
                "total_failures": len(failure_cases),
                "same_named_duplicate_group": same_dup_group,
                "twin_knowledge_cluster": twin_knowledge,
                "total_duplicate_related": same_dup_group + twin_knowledge,
                "true_ranking_failure": different_knowledge,
                "missed_retrieval": not_in_top5,
            },
            "cases": failure_cases,
        }, f, ensure_ascii=False, indent=2)
    print(f"Da ghi file: {out_file}")


if __name__ == "__main__":
    main()

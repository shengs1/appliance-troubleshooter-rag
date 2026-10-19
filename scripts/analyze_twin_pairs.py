"""Phan tich chi tiet 14 cap twin records giua cac failure/regression."""

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

    pairs = [
        ("Q0036", "Q0103"),
        ("Q0059", "Q0138"),
        ("Q0157", "Q0307"),
        ("Q0319", "Q0235"),
        ("Q0323", "Q0162"),
        ("Q0331", "Q0194"),
        ("Q0332", "Q0195"),
        ("Q0343", "Q0206"),
        ("Q0346", "Q0210"),
        ("Q0538", "Q0662"),
        ("Q0542", "Q0666"),
        ("Q0700", "Q0715"),
        ("Q1056", "Q1059"),
        ("Q1080", "Q1082"),
    ]

    pair_results = []

    for a, b in pairs:
        ra = records[a]
        rb = records[b]

        same_brand = ra[hmap["Hãng"]] == rb[hmap["Hãng"]]
        same_device = ra[hmap["Loại_thiết_bị"]] == rb[hmap["Loại_thiết_bị"]]
        ec_a = ra[hmap["Mã_lỗi"]]
        ec_b = rb[hmap["Mã_lỗi"]]
        same_ec = (ec_a or "") == (ec_b or "")
        same_issue = ra[hmap["Issue_ID"]] == rb[hmap["Issue_ID"]]

        # Kiem tra xem co phai cung kien thuc khong
        # Neu cung Hang, cung Thiet bi, va (cung Ma loi hoac cung Issue ID)
        is_same_knowledge = same_brand and same_device and (same_ec or same_issue)

        pair_info = {
            "pair": f"{a} / {b}",
            "record_a": a,
            "record_b": b,
            "same_knowledge": is_same_knowledge,
            "brand": ra[hmap["Hãng"]],
            "device": ra[hmap["Loại_thiết_bị"]],
            "error_code_a": ec_a,
            "error_code_b": ec_b,
            "issue_id_a": ra[hmap["Issue_ID"]],
            "issue_id_b": rb[hmap["Issue_ID"]],
            "duplicate_group_a": ra[hmap["Duplicate_Group"]],
            "duplicate_group_b": rb[hmap["Duplicate_Group"]],
            "question_a": ra[hmap["Câu_hỏi_đã_làm_sạch"]],
            "question_b": rb[hmap["Câu_hỏi_đã_làm_sạch"]],
            "answer_a": ra[hmap["Trả_lời"]],
            "answer_b": rb[hmap["Trả_lời"]],
            "cause_a": ra[hmap["Nguyên_nhân"]],
            "cause_b": rb[hmap["Nguyên_nhân"]],
            "solution_a": ra[hmap["Cách_khắc_phục"]],
            "solution_b": rb[hmap["Cách_khắc_phục"]],
            "source_a": ra[hmap["Nguồn_URL"]],
            "source_b": rb[hmap["Nguồn_URL"]],
            "assessment": (
                "Cùng kiến thức kỹ thuật hoàn toàn (Exact/Knowledge Duplicate)"
                if is_same_knowledge
                else "Khác kiến thức kỹ thuật"
            ),
        }
        pair_results.append(pair_info)

    out_file = Path("data/evaluation/twin_pairs_analysis.json")
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(pair_results, f, ensure_ascii=False, indent=2)

    print(f"Da phan tich {len(pair_results)} cap twin records.")
    for p in pair_results:
        print(f"- {p['pair']}: same_knowledge={p['same_knowledge']} | Brand: {p['brand']}, Device: {p['device']}, Code: {p['error_code_a']} (Issue: {p['issue_id_a']})")
        print(f"  Q_A: {p['question_a']}")
        print(f"  Q_B: {p['question_b']}")


if __name__ == "__main__":
    main()

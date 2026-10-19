import sys
import json
from pathlib import Path
import pandas as pd
sys.stdout.reconfigure(encoding='utf-8')

def main():
    eval_200_path = Path("data/evaluation/evaluation_set_200.json")
    with open(eval_200_path, "r", encoding="utf-8") as f:
        eval_200 = json.load(f)

    eval_200_ids = set(item["question_id"] for item in eval_200)

    df = pd.read_excel("data/raw/dataset.xlsx", sheet_name="DATA_CLEAN_TECH")
    
    eval_dup_groups = set()
    for _, row in df[df["ID"].isin(eval_200_ids)].iterrows():
        dg = row.get("Duplicate_Group")
        if pd.notna(dg) and str(dg).strip():
            eval_dup_groups.add(str(dg).strip())

    print(f"Eval set 200: {len(eval_200_ids)} IDs, {len(eval_dup_groups)} duplicate groups")

    candidates = []
    for _, row in df.iterrows():
        qid = str(row["ID"]).strip()
        if qid in eval_200_ids:
            continue
        dg = row.get("Duplicate_Group")
        if pd.notna(dg) and str(dg).strip() in eval_dup_groups:
            continue

        brand = str(row.get("Hãng", "")).strip()
        device = str(row.get("Loại_thiết_bị", "")).strip()
        issue_type = str(row.get("Loại_sự_cố", "")).strip()
        error_code = str(row.get("Mã_lỗi", "")).strip() if pd.notna(row.get("Mã_lỗi")) else ""
        if error_code == "nan":
            error_code = ""
        q_text = str(row.get("Câu_hỏi_đã_làm_sạch", "")).strip() or str(row.get("Câu_hỏi_gốc", "")).strip()

        if not q_text or not brand or not device:
            continue

        candidates.append({
            "question_id": qid,
            "question": q_text,
            "brand": brand,
            "device": device,
            "error_code": error_code,
            "issue_type": issue_type,
            "duplicate_group": str(dg).strip() if pd.notna(dg) else "",
        })

    print(f"Remaining candidates after excluding eval 200 IDs and duplicate groups: {len(candidates)}")

    candidates.sort(key=lambda x: x["question_id"])

    selected = []
    selected_ids = set()

    targets = {
        ("LG", "ERROR_CODE"): 15,
        ("LG", "SYMPTOM"): 15,
        ("Panasonic", "ERROR_CODE"): 18,
        ("Panasonic", "SYMPTOM"): 17,
        ("Samsung", "ERROR_CODE"): 17,
        ("Samsung", "SYMPTOM"): 18,
    }

    counts = {k: 0 for k in targets}

    for c in candidates:
        b = c["brand"]
        it = c["issue_type"]
        key = (b, it)
        if key in targets and counts[key] < targets[key]:
            selected.append(c)
            selected_ids.add(c["question_id"])
            counts[key] += 1

    if len(selected) < 100:
        for c in candidates:
            if c["question_id"] not in selected_ids:
                selected.append(c)
                selected_ids.add(c["question_id"])
                if len(selected) == 100:
                    break

    selected.sort(key=lambda x: x["question_id"])

    print(f"Selected DEV SET: {len(selected)} items")
    by_b = {}
    by_it = {}
    by_dev = {}
    for item in selected:
        by_b[item["brand"]] = by_b.get(item["brand"], 0) + 1
        by_it[item["issue_type"]] = by_it.get(item["issue_type"], 0) + 1
        by_dev[item["device"]] = by_dev.get(item["device"], 0) + 1

    print("Brand breakdown:", by_b)
    print("Issue type breakdown:", by_it)
    print("Device breakdown:", by_dev)

    out_path = Path("data/evaluation/reranking_dev_100.json")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(selected, f, ensure_ascii=False, indent=2)
    print("Saved dev set to", out_path)

if __name__ == "__main__":
    main()

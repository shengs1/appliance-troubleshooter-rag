import json
import sys
from pathlib import Path
import pandas as pd

sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, ".")

from scripts.run_controlled_benchmark import search_hybrid_custom
from rag_chatbot.chroma_db import get_or_create_collection
from rag_chatbot.neo4j_db import get_neo4j_driver

col = get_or_create_collection()
drv = get_neo4j_driver()

df = pd.read_excel('data/raw/dataset.xlsx', sheet_name='DATA_CLEAN_TECH')
df_by_id = {str(row['ID']).strip(): row for _, row in df.iterrows()}

with open("data/evaluation/independent_eval_60.json", "r", encoding="utf-8") as f:
    queries = json.load(f)

classification_counts = {
    "EXACT_MATCH": 0,
    "EQUIVALENT_KNOWLEDGE_DIFFERENT_ID": 0,
    "INSUFFICIENT_INFO_AMBIGUOUS": 0,
    "WRONG_KNOWLEDGE": 0,
    "MISSED_RETRIEVAL": 0,
}

detailed_cases = []

for q in queries:
    qid = q["id"]
    query_text = q["query"]
    primary_id = q["expected_primary_id"]
    equiv_ids = set(q.get("equivalent_ids", []))
    all_valid_ids = equiv_ids.union({primary_id})
    category = q.get("category", "")

    # Run configuration D (New Extractor + Q2Q)
    docs = search_hybrid_custom(
        query_text, k=5, chroma_collection=col, neo4j_driver=drv, use_new_extractor=True, w_q2q=0.04
    )
    retrieved_ids = [d["question_id"] for d in docs]
    top1_id = retrieved_ids[0] if retrieved_ids else ""

    exp_row = df_by_id.get(primary_id)
    top1_row = df_by_id.get(top1_id)

    exp_brand = str(exp_row.get("Hãng", "")) if exp_row is not None else ""
    top1_brand = str(top1_row.get("Hãng", "")) if top1_row is not None else ""

    exp_dev = str(exp_row.get("Loại_thiết_bị", "")) if exp_row is not None else ""
    top1_dev = str(top1_row.get("Loại_thiết_bị", "")) if top1_row is not None else ""

    exp_err = str(exp_row.get("Mã_lỗi", "")) if exp_row is not None and pd.notna(exp_row.get("Mã_lỗi")) else ""
    top1_err = str(top1_row.get("Mã_lỗi", "")) if top1_row is not None and pd.notna(top1_row.get("Mã_lỗi")) else ""

    # Classify
    if top1_id == primary_id:
        cls = "EXACT_MATCH"
        reason = "Khớp chính xác ground-truth ID"
    elif top1_id in equiv_ids:
        cls = "EQUIVALENT_KNOWLEDGE_DIFFERENT_ID"
        reason = f"Đúng tri thức nhưng khác ID (Top-1 là {top1_id}, thuộc danh sách tương đương)"
    elif category == "PARTIAL_INFO" and (not q.get("brand") or not q.get("device")):
        cls = "INSUFFICIENT_INFO_AMBIGUOUS"
        reason = f"Câu hỏi thiếu thông tin hãng/thiết bị, Top-1 chọn {top1_brand} {top1_dev} thay vì {exp_brand} {exp_dev}"
    elif exp_brand and top1_brand and exp_brand.lower() != top1_brand.lower():
        cls = "WRONG_KNOWLEDGE"
        reason = f"Sai hãng: kỳ vọng {exp_brand}, trả về {top1_brand}"
    elif exp_dev and top1_dev and exp_dev.lower() != top1_dev.lower():
        cls = "WRONG_KNOWLEDGE"
        reason = f"Sai thiết bị: kỳ vọng {exp_dev}, trả về {top1_dev}"
    elif primary_id not in retrieved_ids:
        cls = "MISSED_RETRIEVAL"
        reason = "Bản ghi kỳ vọng không nằm trong Top 5"
    else:
        cls = "WRONG_KNOWLEDGE"
        reason = f"Khác nội dung sự cố giữa {primary_id} và {top1_id}"

    classification_counts[cls] += 1
    detailed_cases.append({
        "id": qid,
        "query": query_text,
        "category": category,
        "expected_primary_id": primary_id,
        "top1_id": top1_id,
        "classification": cls,
        "reason": reason,
        "top_5": retrieved_ids
    })

print("=== PHÂN LOẠI NGUYÊN NHÂN TRÊN BỘ 60 CÂU ĐỘC LẬP ===")
for cls, count in classification_counts.items():
    print(f"  {cls:<35}: {count:>2} ({count/60*100:.1f}%)")

with open("data/evaluation/independent_failure_breakdown.json", "w", encoding="utf-8") as f:
    json.dump({"summary": classification_counts, "cases": detailed_cases}, f, ensure_ascii=False, indent=2)
print("Saved to data/evaluation/independent_failure_breakdown.json")

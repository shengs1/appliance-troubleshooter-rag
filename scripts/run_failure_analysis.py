import json
from pathlib import Path
from rag_chatbot.retrieval import search_hybrid, extract_question_entities
from rag_chatbot.chroma_db import get_or_create_collection
from rag_chatbot.neo4j_db import get_neo4j_driver
from rag_chatbot.config import get_settings
from rag_chatbot.evaluation import load_evaluation_set

def get_rank(retrieved_ids, target_id, max_k=5):
    for r, did in enumerate(retrieved_ids[:max_k], 1):
        if did == target_id:
            return r
    return None

def main():
    eval_set = load_evaluation_set("data/evaluation/evaluation_set_200.json")
    chroma_col = get_or_create_collection()
    neo_driver = get_neo4j_driver()
    settings = get_settings()

    brand_bonus_val = settings.rerank_brand_bonus
    device_bonus_val = settings.rerank_device_bonus
    error_code_bonus_val = settings.rerank_exact_error_code_bonus
    both_bonus_val = settings.rerank_both_bonus

    failure_cases = []

    for item in eval_set:
        q = item["question"]
        exp_id = item["question_id"]
        brand = item.get("brand", "")
        device = item.get("device", "")
        issue_type = item.get("issue_type", "")

        entities = extract_question_entities(q)
        target_brand = entities.get("brand")
        target_device = entities.get("device")
        target_error_code = entities.get("error_code")

        # Run Hybrid with fixed reranking
        results = search_hybrid(q, k=5, chroma_collection=chroma_col, neo4j_driver=neo_driver, use_reranking=True)
        retrieved_ids = [d["question_id"] for d in results]
        rank = get_rank(retrieved_ids, exp_id, 5)

        if rank != 1:
            # Failure case (Rank is 2, 3, 4, 5, or None)
            top_5_breakdown = []
            for idx, doc in enumerate(results, 1):
                dist = doc.get("distance")
                if dist is not None:
                    sem_score = max(0.0, 1.0 - float(dist))
                else:
                    sem_score = 0.0

                doc_brand = doc.get("brand", "")
                doc_device = doc.get("device", "")
                doc_code = doc.get("error_code", "")

                b_bonus = brand_bonus_val if (target_brand and doc_brand and target_brand.lower() == doc_brand.lower()) else 0.0
                d_bonus = device_bonus_val if (target_device and doc_device and target_device.lower() == doc_device.lower()) else 0.0
                e_bonus = error_code_bonus_val if (target_error_code and doc_code and target_error_code.lower() == doc_code.lower()) else 0.0
                src_bonus = both_bonus_val if doc.get("retrieval_source") == "both" else 0.0

                final_sc = round(sem_score + b_bonus + d_bonus + e_bonus + src_bonus, 4)

                top_5_breakdown.append({
                    "question_id": doc.get("question_id"),
                    "brand": doc_brand,
                    "device": doc_device,
                    "error_code": doc_code,
                    "retrieval_source": doc.get("retrieval_source"),
                    "distance": round(float(dist), 4) if dist is not None else None,
                    "semantic_score": round(sem_score, 4),
                    "brand_bonus": b_bonus,
                    "device_bonus": d_bonus,
                    "error_code_bonus": e_bonus,
                    "both_bonus": src_bonus,
                    "final_score": final_sc,
                    "rank": idx,
                    "is_expected": doc.get("question_id") == exp_id,
                })

            # Phân loại nguyên nhân:
            # A. Semantic ranking: điểm semantic của candidate khác cao hơn
            # B. "both" candidate được ưu tiên sai
            # C. Error code chưa đủ ưu tiên
            # D. Brand mismatch
            # E. Device mismatch
            # F. ChromaDB result tốt bị Neo4j candidate đẩy xuống
            # G. Nhiều câu hỏi có semantic similarity rất gần nhau
            # H. Candidate đúng chỉ nằm ở Rank 2–5
            # I. Ground truth không nằm trong Top-5
            # J. Khác

            cause_category = "J"
            cause_description = ""

            top1_doc = top_5_breakdown[0] if top_5_breakdown else None

            if rank is None:
                cause_category = "I"
                cause_description = "Ground truth không nằm trong Top-5 candidate retrieval"
            elif top1_doc and top1_doc.get("retrieval_source") == "both" and any(d["is_expected"] and d.get("retrieval_source") != "both" for d in top_5_breakdown):
                # Check if both bonus pushed top1 over expected
                exp_doc = next(d for d in top_5_breakdown if d["is_expected"])
                if exp_doc["semantic_score"] > top1_doc["semantic_score"] and top1_doc["final_score"] >= exp_doc["final_score"]:
                    cause_category = "B"
                    cause_description = "Candidate 'both' được ưu tiên vượt mặt tài liệu ngữ nghĩa tốt hơn"
                else:
                    cause_category = "A"
                    cause_description = "Semantic score của candidate top-1 cao hơn ground truth"
            elif target_error_code and top1_doc and not (top1_doc.get("error_code") and target_error_code.lower() == top1_doc["error_code"].lower()):
                cause_category = "C"
                cause_description = "Query có mã lỗi nhưng Top 1 không khớp mã lỗi"
            elif top1_doc and target_brand and top1_doc.get("brand") and target_brand.lower() != top1_doc["brand"].lower():
                cause_category = "D"
                cause_description = "Brand mismatch giữa query và Top 1"
            elif top1_doc and target_device and top1_doc.get("device") and target_device.lower() != top1_doc["device"].lower():
                cause_category = "E"
                cause_description = "Device mismatch giữa query và Top 1"
            elif rank in [2, 3, 4, 5]:
                # In top 5, check semantic similarity closeness
                exp_doc = next(d for d in top_5_breakdown if d["is_expected"])
                diff_sem = abs(top1_doc["semantic_score"] - exp_doc["semantic_score"])
                if diff_sem < 0.05:
                    cause_category = "G"
                    cause_description = f"Các câu hỏi có semantic similarity rất gần nhau (khoảng cách ngữ nghĩa chênh lệch {diff_sem:.4f})"
                else:
                    cause_category = "A"
                    cause_description = f"Semantic ranking: candidate rank 1 có độ tương đồng ngữ nghĩa cao hơn ({top1_doc['semantic_score']:.4f} vs {exp_doc['semantic_score']:.4f})"
            else:
                cause_category = "J"
                cause_description = "Khác"

            failure_cases.append({
                "question_id": exp_id,
                "question": q,
                "brand": brand,
                "device": device,
                "issue_type": issue_type,
                "extracted_entities": {
                    "brand": target_brand,
                    "device": target_device,
                    "error_code": target_error_code,
                },
                "expected_question_id": exp_id,
                "expected_rank": rank if rank is not None else "Not in Top-5",
                "can_be_rescued_by_reranking": rank is not None,
                "cause_category": cause_category,
                "cause_description": cause_description,
                "top_5_results": top_5_breakdown,
            })

    # Summary Statistics
    total_failures = len(failure_cases)
    rank_distribution = {
        "Rank 2": sum(1 for c in failure_cases if c["expected_rank"] == 2),
        "Rank 3": sum(1 for c in failure_cases if c["expected_rank"] == 3),
        "Rank 4": sum(1 for c in failure_cases if c["expected_rank"] == 4),
        "Rank 5": sum(1 for c in failure_cases if c["expected_rank"] == 5),
        "Not in Top-5": sum(1 for c in failure_cases if c["expected_rank"] == "Not in Top-5"),
    }

    cause_distribution = {}
    for c in failure_cases:
        cat = f"{c['cause_category']}: {c['cause_description'][:50]}"
        cause_distribution[cat] = cause_distribution.get(cat, 0) + 1

    by_issue_type = {}
    for c in failure_cases:
        it = c["issue_type"]
        by_issue_type[it] = by_issue_type.get(it, 0) + 1

    by_brand = {}
    for c in failure_cases:
        b = c["brand"]
        by_brand[b] = by_brand.get(b, 0) + 1

    by_device = {}
    for c in failure_cases:
        dev = c["device"]
        by_device[dev] = by_device.get(dev, 0) + 1

    rescuable_count = sum(1 for c in failure_cases if c["can_be_rescued_by_reranking"])
    unrescuable_count = total_failures - rescuable_count

    summary = {
        "total_failures": total_failures,
        "rescuable_by_reranking": rescuable_count,
        "unrescuable_not_in_top5": unrescuable_count,
        "rank_distribution": rank_distribution,
        "cause_distribution": cause_distribution,
        "by_issue_type": by_issue_type,
        "by_brand": by_brand,
        "by_device": by_device,
    }

    out_file = Path("data/evaluation/failure_analysis.json")
    out_file.parent.mkdir(parents=True, exist_ok=True)
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(failure_cases, f, ensure_ascii=False, indent=2)

    summary_file = Path("data/evaluation/failure_analysis_summary.json")
    with open(summary_file, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    print(f"DONE. Total failures: {total_failures}. Rescuable: {rescuable_count}, Unrescuable: {unrescuable_count}")
    print("Rank distribution:", rank_distribution)
    print("Issue type distribution:", by_issue_type)
    print("Brand distribution:", by_brand)

if __name__ == "__main__":
    main()

"""Module danh gia he thong Retrieval theo 2 muc: Exact-ID va Knowledge-aware.

Muc dich:
1. Exact-ID level: Danh gia truyen thong, retrieved_id == expected_id.
2. Knowledge-aware level: Danh gia muc tri thuc ky thuat, neu retrieved_id khac expected_id
   nhung thuoc cung cum tri thuc sinh doi (Duplicate_Group hoac Twin Knowledge da duoc xac minh)
   thi van duoc cong nhan la truy van dung tri thuc.

Nguyen tac:
- Knowledge mapping chi ap dung sau khi retrieval hoan thanh (Evaluation Layer).
- Khong dung ground truth hay mapping de thay doi candidate pool hay ranking runtime.
- Khong sua dataset, khong thay doi production pipeline.
"""

from __future__ import annotations
import json
from pathlib import Path
from typing import Any


def load_knowledge_equivalence_map(
    duplicate_analysis_file: str | Path = "data/evaluation/duplicate_analysis.json",
    failure_analysis_file: str | Path = "data/evaluation/duplicate_failure_analysis.json",
    twin_pairs_file: str | Path = "data/evaluation/twin_pairs_analysis.json",
) -> dict[str, set[str]]:
    """Xay dung ban do tuong duong tri thuc tu cac artifact phan tich da xac minh.
    
    Quy tac tuong duong (Knowledge Equivalence):
    CASE A: Cung Duplicate_Group da duoc xac minh (tu duplicate_analysis.json).
    CASE B: Cung Twin Knowledge Cluster da duoc xac minh (tu duplicate_failure_analysis.json
            va twin_pairs_analysis.json).
            
    Returns:
        Dict mapping tu question_id sang tap hop cac ID tuong duong (bao gom ca ban than no).
    """
    equiv_map: dict[str, set[str]] = {}

    def _add_pair(id1: str, id2: str):
        if not id1 or not id2 or id1 == id2:
            return
        equiv_map.setdefault(id1, set()).add(id2)
        equiv_map.setdefault(id2, set()).add(id1)

    # 1. CASE A: Duplicate_Group da xac minh
    p_dup = Path(duplicate_analysis_file)
    if p_dup.exists():
        with open(p_dup, "r", encoding="utf-8") as f:
            data = json.load(f)
        for g in data.get("groups", []):
            m_ids = g.get("member_ids", [])
            for i in range(len(m_ids)):
                for j in range(i + 1, len(m_ids)):
                    _add_pair(m_ids[i], m_ids[j])

    # 2. CASE B: Twin pairs analysis
    p_twin = Path(twin_pairs_file)
    if p_twin.exists():
        with open(p_twin, "r", encoding="utf-8") as f:
            data = json.load(f)
        for item in data:
            if item.get("same_knowledge", False):
                _add_pair(item["record_a"], item["record_b"])

    # 3. CASE B: Failure analysis twin cases
    p_fail = Path(failure_analysis_file)
    if p_fail.exists():
        with open(p_fail, "r", encoding="utf-8") as f:
            data = json.load(f)
        for c in data.get("cases", []):
            exp_id = c.get("expected_question_id")
            top1_id = c.get("retrieved_top1_id")
            if not exp_id or not top1_id:
                continue
            if c.get("category") in ("SAME_NAMED_DUPLICATE_GROUP", "TWIN_KNOWLEDGE_CLUSTER"):
                _add_pair(exp_id, top1_id)
            elif exp_id == "Q0535" and top1_id == "Q0690":
                # Q0535 va Q0690 co cung noi dung cau tra loi 100% (truong hop dac biet Section 10)
                _add_pair(exp_id, top1_id)

    # Them chinh ban than moi ID vao tap tuong duong cua no
    for qid in list(equiv_map.keys()):
        equiv_map[qid].add(qid)

    return equiv_map


def is_equivalent_knowledge(
    retrieved_id: str,
    target_id: str,
    equivalence_map: dict[str, set[str]] | None = None,
) -> bool:
    """Kiem tra hai question_id co cung tri thuc ky thuat hay khong."""
    if not retrieved_id or not target_id:
        return False
    if retrieved_id == target_id:
        return True
    if equivalence_map is None:
        return False
    return retrieved_id in equivalence_map.get(target_id, set())


def evaluate_query_dual_level(
    retrieved_docs: list[dict[str, Any]],
    expected_id: str,
    equivalence_map: dict[str, set[str]],
    max_k: int = 5,
) -> dict[str, Any]:
    """Danh gia 1 truy van theo ca 2 cap do: Exact-ID va Knowledge-aware.
    
    Args:
        retrieved_docs: Danh sach ket qua Top-K tra ve tu retrieval pipeline.
        expected_id: Ground truth question_id cua cau hoi.
        equivalence_map: Ban do tuong duong tri thuc da xac minh.
        max_k: Gioi han rank can xet (mac dinh 5).
        
    Returns:
        Dict chua exact_rank, knowledge_rank, exact_hit_k, knowledge_hit_k va chi tiet match.
    """
    retrieved_ids = [
        str(d.get("question_id") or d.get("id") or "")
        for d in retrieved_docs[:max_k]
    ]

    exact_rank: int | None = None
    knowledge_rank: int | None = None
    match_details: list[dict[str, Any]] = []

    for rank, doc_id in enumerate(retrieved_ids, 1):
        is_exact = (doc_id == expected_id)
        is_know = is_equivalent_knowledge(doc_id, expected_id, equivalence_map)

        if is_exact and exact_rank is None:
            exact_rank = rank
        if is_know and knowledge_rank is None:
            knowledge_rank = rank

        if is_know:
            match_details.append({
                "rank": rank,
                "retrieved_id": doc_id,
                "expected_id": expected_id,
                "match_type": "EXACT" if is_exact else "EQUIVALENT_KNOWLEDGE",
            })

    exact_hit_1 = (exact_rank == 1)
    exact_hit_3 = (exact_rank is not None and exact_rank <= 3)
    exact_hit_5 = (exact_rank is not None and exact_rank <= 5)
    exact_mrr = (1.0 / exact_rank) if exact_rank else 0.0

    know_hit_1 = (knowledge_rank == 1)
    know_hit_3 = (knowledge_rank is not None and knowledge_rank <= 3)
    know_hit_5 = (knowledge_rank is not None and knowledge_rank <= 5)
    know_mrr = (1.0 / knowledge_rank) if knowledge_rank else 0.0

    return {
        "expected_question_id": expected_id,
        "exact_rank": exact_rank,
        "knowledge_rank": knowledge_rank,
        "exact_hit_1": exact_hit_1,
        "exact_hit_3": exact_hit_3,
        "exact_hit_5": exact_hit_5,
        "exact_mrr": exact_mrr,
        "knowledge_hit_1": know_hit_1,
        "knowledge_hit_3": know_hit_3,
        "knowledge_hit_5": know_hit_5,
        "knowledge_mrr": know_mrr,
        "retrieved_ids": retrieved_ids,
        "match_details": match_details,
    }

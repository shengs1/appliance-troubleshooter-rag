"""Kiem thu chuc nang nap du lieu va tim kiem tuong dong ChromaDB (Phase 3).

Cac test case bao gom:
1. Kiem tra load dataset bang pandas du 1.090 ban ghi.
2. Kiem tra dinh dang van ban document duoc tao tu dong du lieu thuc te (Q0358).
3. Kiem tra metadata chua day du 10 truong scalar theo dung DATA_MODEL.md.
4. Kiem tra xu ly an toan khi dong khong co ma loi (khong tu che du lieu).
5. Kiem tra tim kiem ngu nghia (Semantic Search) tim dung ban ghi Q0358 cho cau hoi test.
"""

import chromadb
import pytest

from rag_chatbot.chroma_db import get_embedding_function, get_or_create_collection
from rag_chatbot.ingest import (
    load_raw_dataset,
    prepare_document_metadata,
    prepare_document_text,
)
from rag_chatbot.retrieval import search_similar_documents


def test_load_dataset_has_1090_records():
    """Kiem tra dataset.xlsx duoc doc thanh cong va co dung 1.090 ban ghi."""
    df = load_raw_dataset("data/raw/dataset.xlsx")
    assert len(df) == 1090
    assert "ID" in df.columns
    assert "Hãng" in df.columns
    assert "Loại_thiết_bị" in df.columns
    assert "Mã_lỗi" in df.columns
    assert "Câu_hỏi_đã_làm_sạch" in df.columns
    assert "Trả_lời" in df.columns


def test_prepare_document_text_q0358():
    """Kiem tra viec tao noi dung page_content tu ban ghi thuc te Q0358."""
    df = load_raw_dataset("data/raw/dataset.xlsx")
    row_q0358 = df[df["ID"] == "Q0358"].iloc[0]

    doc_text = prepare_document_text(row_q0358)

    # Kiem tra cac thanh phan quan trong co mat trong noi dung
    assert "Hãng: Samsung" in doc_text
    assert "Thiết bị: Điều hòa" in doc_text
    assert "Mã lỗi: CF" in doc_text
    assert "Máy điều hòa Samsung lỗi CF" in doc_text
    assert "Mã CF là nhắc vệ sinh bộ lọc" in doc_text
    assert "Hãy vệ sinh hoặc thay bộ lọc" in doc_text


def test_prepare_document_metadata_q0358():
    """Kiem tra metadata cua Q0358 chua dung va du 10 truong scalar theo DATA_MODEL.md."""
    df = load_raw_dataset("data/raw/dataset.xlsx")
    row_q0358 = df[df["ID"] == "Q0358"].iloc[0]

    metadata = prepare_document_metadata(row_q0358)

    expected_fields = [
        "question_id",
        "brand",
        "device",
        "error_code",
        "issue_type",
        "issue_id",
        "answer_type",
        "source_id",
        "source_url",
        "domain",
    ]

    for field in expected_fields:
        assert field in metadata, f"Thieu truong metadata: {field}"
        # Tat ca metadata phai la kieu chuoi don gian (scalar string)
        assert isinstance(metadata[field], str)

    assert metadata["question_id"] == "Q0358"
    assert metadata["brand"] == "Samsung"
    assert metadata["device"] == "Điều hòa"
    assert metadata["error_code"] == "CF"
    assert metadata["issue_id"] == "I0249"
    assert metadata["answer_type"] == "CAUSE_SOLUTION"
    assert metadata["source_id"] == "S008"
    assert "samsung.com" in metadata["source_url"]


def test_prepare_document_metadata_preserves_missing_error_code():
    """Kiem tra ban ghi trieu chung khong co ma loi: giu nguyen chuoi rong, khong tu che ma."""
    df = load_raw_dataset("data/raw/dataset.xlsx")
    # Tim ban ghi co loai su co la SYMPTOM (khong co ma loi)
    symptom_rows = df[df["Loại_sự_cố"] == "SYMPTOM"]
    assert len(symptom_rows) > 0

    sample_row = symptom_rows.iloc[0]
    metadata = prepare_document_metadata(sample_row)

    # error_code phai la chuoi rong neu ma loi khong co
    if not sample_row.get("Mã_lỗi") or str(sample_row.get("Mã_lỗi")).strip() == "":
        assert metadata["error_code"] == ""


def test_semantic_search_retrieves_q0358(tmp_path):
    """Kiem tra tim kiem ngu nghia tim dung ban ghi Q0358 khi hoi ve loi CF dieu hoa Samsung."""
    # Tao collection co lap trong thu muc tam (tmp_path)
    client = chromadb.PersistentClient(path=str(tmp_path))
    ef = get_embedding_function()
    col = client.create_collection(
        name="test_electronics_troubleshooting",
        embedding_function=ef,
    )

    df = load_raw_dataset("data/raw/dataset.xlsx")
    
    # Lay 5 ban ghi thuc te gom Q0358 va cac ban ghi khac lam du lieu mau
    sample_ids = ["Q0001", "Q0002", "Q0010", "Q0358", "Q0500"]
    sample_rows = df[df["ID"].isin(sample_ids)]

    ids = [str(r["ID"]) for _, r in sample_rows.iterrows()]
    docs = [prepare_document_text(r) for _, r in sample_rows.iterrows()]
    metas = [prepare_document_metadata(r) for _, r in sample_rows.iterrows()]

    col.add(ids=ids, documents=docs, metadatas=metas)

    # Cau hoi kiem thu tuong tu vi du trong yeu cau
    query = "Máy điều hòa Samsung lỗi CF là gì?"
    results = search_similar_documents(question=query, k=3, collection=col)

    retrieved_ids = [r["id"] for r in results]
    assert "Q0358" in retrieved_ids, f"Q0358 khong xuat hien trong ket qua: {retrieved_ids}"

    # Kiem tra ket qua dung dau tien hoac trong top
    top_result = results[0]
    assert top_result["id"] == "Q0358"
    assert top_result["metadata"]["brand"] == "Samsung"
    assert top_result["metadata"]["error_code"] == "CF"

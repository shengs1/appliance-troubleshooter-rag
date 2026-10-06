"""Module nap du lieu (Data Ingestion Pipeline) cho ChromaDB.

Nhiem vu:
1. Doc file Excel data/raw/dataset.xlsx tu sheet 'DATA_CLEAN_TECH' bang pandas.
2. Chuyen doi moi dong Q&A thanh mot ChromaDB document day du thong tin.
3. Trich xuat metadata scalar theo dung DATA_MODEL.md.
4. Nap (upsert) toan bo 1.090 ban ghi vao collection 'electronics_troubleshooting'.
"""

from pathlib import Path
from typing import Any
import pandas as pd

from rag_chatbot.chroma_db import get_or_create_collection
from rag_chatbot.config import get_settings


def load_raw_dataset(file_path: str | Path = "data/raw/dataset.xlsx") -> pd.DataFrame:
    """Doc sheet DATA_CLEAN_TECH tu file Excel bang pandas.
    
    Tra ve DataFrame gom dung 1.090 dong du lieu da lam sach.
    """
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"Khong tim thay file dataset tai: {path}")

    # Doc sheet DATA_CLEAN_TECH
    df = pd.read_excel(path, sheet_name="DATA_CLEAN_TECH")
    return df


def prepare_document_text(row: dict | pd.Series) -> str:
    """Tao noi dung page_content cho document ChromaDB tu mot dong du lieu.
    
    Ket hop cac thong tin ky thuat huu ich:
    - Hang
    - Thiet bi
    - Ma loi hoac loai su co
    - Cau hoi da lam sach
    - Nguyen nhan (neu co)
    - Cach khac phuc (neu co)
    - Toan van cau tra loi
    """
    # Lay cac gia tri va loai bo NaN neu co
    brand = str(row.get("Hãng", "")).strip() if pd.notna(row.get("Hãng")) else ""
    device = str(row.get("Loại_thiết_bị", "")).strip() if pd.notna(row.get("Loại_thiết_bị")) else ""
    error_code = str(row.get("Mã_lỗi", "")).strip() if pd.notna(row.get("Mã_lỗi")) else ""
    issue_type = str(row.get("Loại_sự_cố", "")).strip() if pd.notna(row.get("Loại_sự_cố")) else ""
    cleaned_question = str(row.get("Câu_hỏi_đã_làm_sạch", "")).strip() if pd.notna(row.get("Câu_hỏi_đã_làm_sạch")) else ""
    cause = str(row.get("Nguyên_nhân", "")).strip() if pd.notna(row.get("Nguyên_nhân")) else ""
    solution = str(row.get("Cách_khắc_phục", "")).strip() if pd.notna(row.get("Cách_khắc_phục")) else ""
    full_answer = str(row.get("Trả_lời", "")).strip() if pd.notna(row.get("Trả_lời")) else ""

    parts: list[str] = []
    if brand:
        parts.append(f"Hãng: {brand}")
    if device:
        parts.append(f"Thiết bị: {device}")
    if error_code:
        parts.append(f"Mã lỗi: {error_code}")
    elif issue_type:
        parts.append(f"Sự cố: {issue_type}")
    if cleaned_question:
        parts.append(f"Câu hỏi: {cleaned_question}")
    if cause:
        parts.append(f"Nguyên nhân: {cause}")
    if solution:
        parts.append(f"Cách khắc phục: {solution}")
    if full_answer:
        parts.append(f"Câu trả lời: {full_answer}")

    return "\n".join(parts)


def prepare_document_metadata(row: dict | pd.Series) -> dict[str, str]:
    """Tao metadata scalar dua tren DATA_MODEL.md.
    
    Quy tac:
    - Khong tu bia dat gia tri bi thieu.
    - Neu khong co ma loi, giu gia tri rong ("").
    - Bao ton cac co ERROR_CODE_UNKNOWN, MULTIPLE_ERROR_CODES va nguon ben thu ba.
    """
    error_code_val = row.get("Mã_lỗi")
    error_code_str = str(error_code_val).strip() if pd.notna(error_code_val) else ""

    return {
        "question_id": str(row.get("ID", "")).strip(),
        "brand": str(row.get("Hãng", "")).strip() if pd.notna(row.get("Hãng")) else "",
        "device": str(row.get("Loại_thiết_bị", "")).strip() if pd.notna(row.get("Loại_thiết_bị")) else "",
        "error_code": error_code_str,
        "issue_type": str(row.get("Loại_sự_cố", "")).strip() if pd.notna(row.get("Loại_sự_cố")) else "",
        "issue_id": str(row.get("Issue_ID", "")).strip() if pd.notna(row.get("Issue_ID")) else "",
        "answer_type": str(row.get("Loại_câu_trả_lời", "")).strip() if pd.notna(row.get("Loại_câu_trả_lời")) else "",
        "source_id": str(row.get("Source_ID", "")).strip() if pd.notna(row.get("Source_ID")) else "",
        "source_url": str(row.get("Nguồn_URL", "")).strip() if pd.notna(row.get("Nguồn_URL")) else "",
        "domain": str(row.get("Domain", "")).strip() if pd.notna(row.get("Domain")) else "",
    }


def run_ingestion(
    excel_path: str | Path = "data/raw/dataset.xlsx",
    collection_name: str | None = None,
    batch_size: int = 100,
    collection: Any = None,
) -> int:
    """Chay toan bo quy trinh nap du lieu tu dataset.xlsx vao ChromaDB.
    
    Args:
        excel_path: Duong dan toi file dataset.xlsx.
        collection_name: Ten collection ChromaDB (mac dinh: electronics_troubleshooting).
        batch_size: So luong ban ghi nap moi dot de toi uu bo nho va toc do.
        collection: Collection tuy chon (dung khi kiem thu).
        
    Returns:
        Tong so ban ghi da duoc nap thanh cong vao ChromaDB (1.090).
    """
    settings = get_settings()
    target_collection_name = collection_name or settings.chroma_collection_name

    print(f"1. Dang doc du lieu tu: {excel_path} (sheet: DATA_CLEAN_TECH)...")
    df = load_raw_dataset(excel_path)
    total_records = len(df)
    print(f"-> Da doc {total_records} ban ghi.")

    print(f"2. Ket noi toi collection '{target_collection_name}' trong ChromaDB...")
    target_collection = collection or get_or_create_collection(
        collection_name=target_collection_name
    )

    # Chuyen doi DataFrame sang danh sach ID, Document, Metadata
    ids: list[str] = []
    documents: list[str] = []
    metadatas: list[dict[str, str]] = []

    for _, row in df.iterrows():
        doc_id = str(row.get("ID", "")).strip()
        doc_text = prepare_document_text(row)
        doc_meta = prepare_document_metadata(row)

        ids.append(doc_id)
        documents.append(doc_text)
        metadatas.append(doc_meta)

    print(f"3. Bat dau nap {total_records} documents vao ChromaDB theo batch (size={batch_size})...")
    # Nap theo batch de tranh qua tai bo nho va de theo doi tien do
    for start_idx in range(0, total_records, batch_size):
        end_idx = min(start_idx + batch_size, total_records)
        batch_ids = ids[start_idx:end_idx]
        batch_docs = documents[start_idx:end_idx]
        batch_metas = metadatas[start_idx:end_idx]

        target_collection.upsert(
            ids=batch_ids,
            documents=batch_docs,
            metadatas=batch_metas,
        )
        print(f"   - Da nap tu ban ghi {start_idx + 1} den {end_idx}/{total_records}")

    print(f"-> Hoan tat nap toan bo {total_records} ban ghi vao ChromaDB!")
    return total_records


if __name__ == "__main__":
    run_ingestion()

"""Module quan ly co so du lieu vector ChromaDB.

Nhiem vu:
1. Khoi tao ket noi PersistentClient toi thu muc luu tru ChromaDB.
2. Khoi tao ham tinh vector embedding (su dung BAAI/bge-m3 qua sentence-transformers).
3. Tao hoac lay collection 'electronics_troubleshooting'.
4. Cung cap ham truy van tuong dong ngu nghia (Semantic Similarity Search).
"""

from __future__ import annotations
from typing import Any
import chromadb
from chromadb.utils import embedding_functions

from rag_chatbot.config import get_settings


def get_chroma_client(persist_directory: str | None = None) -> Any:
    """Khoi tao va tra ve ChromaDB PersistentClient.
    
    Du lieu vector se duoc luu xuong o dia (disk) tai thu muc duoc chi dinh
    de khong bi mat khi ung dung dung lai.
    """
    settings = get_settings()
    target_dir = persist_directory or settings.chroma_persist_directory
    return chromadb.PersistentClient(path=target_dir)


def get_embedding_function(model_name: str | None = None) -> Any:
    """Khoi tao ham tinh vector embedding bang mo hinh sentence-transformers.
    
    Mac dinh su dung mo hinh 'BAAI/bge-m3' tu cau hinh he thong.
    Mo hinh nay ho tro rat tot tieng Viet va chuyen ve tim kiem van ban ky thuat.
    """
    settings = get_settings()
    target_model = model_name or settings.embedding_model_name
    return embedding_functions.SentenceTransformerEmbeddingFunction(
        model_name=target_model
    )


def get_or_create_collection(
    client: Any = None,
    collection_name: str | None = None,
    embedding_function: Any = None,
) -> Any:
    """Lay collection da co hoac tao moi neu chua ton tai trong ChromaDB."""
    settings = get_settings()
    active_client = client or get_chroma_client()
    target_name = collection_name or settings.chroma_collection_name
    active_ef = embedding_function or get_embedding_function()

    return active_client.get_or_create_collection(
        name=target_name,
        embedding_function=active_ef,
    )


def query_similar_documents(
    query_text: str,
    n_results: int = 5,
    collection: Any = None,
    where: dict | None = None,
) -> list[dict]:
    """Tim kiem top-k tai lieu tuong dong ngu nghia voi cau hoi nguoi dung.
    
    Args:
        query_text: Cau hoi hoac mo ta su co can tim kiem.
        n_results: So luong tai lieu tuong dong can tra ve (mac dinh k = 5).
        collection: Chroma collection doi tuong; neu None se tu lay collection mac dinh.
        where: Bo loc metadata tuy chon (vi du: {"brand": "Samsung"}).
        
    Returns:
        Danh sach dict gom: id, document, metadata, va distance (khoang cach vector).
    """
    active_col = collection or get_or_create_collection()

    kwargs: dict[str, Any] = {
        "query_texts": [query_text],
        "n_results": n_results,
    }
    if where:
        kwargs["where"] = where

    raw_results = active_col.query(**kwargs)

    # Chuan hoa ket qua tra ve ve danh sach dict ro rang, de doc va de giai thich
    results: list[dict] = []
    if raw_results and raw_results.get("ids") and len(raw_results["ids"]) > 0:
        ids = raw_results["ids"][0]
        docs = raw_results["documents"][0] if raw_results.get("documents") else []
        metas = raw_results["metadatas"][0] if raw_results.get("metadatas") else []
        dists = raw_results["distances"][0] if raw_results.get("distances") else []

        for i in range(len(ids)):
            results.append({
                "id": ids[i],
                "document": docs[i] if i < len(docs) else "",
                "metadata": metas[i] if i < len(metas) else {},
                "distance": dists[i] if i < len(dists) else None,
            })

    return results

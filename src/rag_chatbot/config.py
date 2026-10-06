"""Module quan ly cau hinh ung dung (Configuration Management).

Su dung pydantic-settings de:
1. Doc bien moi truong tu file .env (neu co).
2. Gan gia tri mac dinh an toan khi chua co file .env.
3. Kiem tra kieu du lieu hop le (type validation).
"""

from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Lop luu tru toan bo cau hinh cho he thong RAG."""

    # Cau hinh ung dung chung
    app_name: str = "rag-chatbot"
    app_env: str = "development"
    debug: bool = True

    # Cau hinh ket noi Neo4j (Graph Database)
    neo4j_uri: str = "bolt://localhost:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: str = "password123"

    # Cau hinh ket noi ChromaDB (Vector Database)
    chroma_persist_directory: str = "./chroma_data"
    chroma_collection_name: str = "electronics_troubleshooting"

    # Cau hinh mo hinh embedding
    embedding_model_name: str = "BAAI/bge-m3"

    # Cau hinh mo hinh LLM cuc bo (Ollama)
    ollama_base_url: str = "http://localhost:11434"
    llm_model_name: str = "qwen2.5:7b"

    # Cau hinh Pydantic Settings
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",  # Bo qua cac bien moi truong khong khai bao
    )


@lru_cache
def get_settings() -> Settings:
    """Tra ve doi tuong Settings (duoc cache lai de tranh doc file lap di lap lai)."""
    return Settings()

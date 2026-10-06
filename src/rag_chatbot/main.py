"""Diem khoi dau ung dung (Application Entry Point).

Cung cap ham main() don gian de kiem tra cau hinh va khoi dong he thong.
"""

from rag_chatbot.config import get_settings


def main() -> None:
    """Ham chay chinh de kiem tra thong tin he thong."""
    settings = get_settings()
    print("=" * 60)
    print(f"Khoi dong ung dung: {settings.app_name}")
    print(f"Moi truong: {settings.app_env} (Debug: {settings.debug})")
    print(f"Neo4j URI: {settings.neo4j_uri}")
    print(f"ChromaDB Path: {settings.chroma_persist_directory}")
    print(f"Embedding Model: {settings.embedding_model_name}")
    print(f"LLM Model: {settings.llm_model_name}")
    print("=" * 60)
    print("He thong san sang tiep tuc trien khai cac phase tiep theo.")


if __name__ == "__main__":
    main()

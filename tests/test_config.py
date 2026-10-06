"""Unit tests cho module quan ly cau hinh (config.py).

Cac test case:
1. Kiem tra cac gia tri mac dinh co dung theo yeu cau he thong hay khong.
2. Kiem tra kha nang ghi de cau hinh khi truyen bien moi truong.
"""

from rag_chatbot.config import Settings, get_settings


def test_default_settings():
    """Kiem tra cac gia tri mac dinh cua Settings."""
    settings = Settings()

    assert settings.app_name == "rag-chatbot"
    assert settings.app_env == "development"
    assert settings.debug is True
    assert settings.neo4j_uri == "bolt://localhost:7687"
    assert settings.neo4j_user == "neo4j"
    assert settings.chroma_collection_name == "electronics_troubleshooting"
    assert settings.embedding_model_name == "BAAI/bge-m3"
    assert settings.llm_model_name == "qwen2.5:7b"


def test_custom_environment_settings(monkeypatch):
    """Kiem tra kha nang doc bien moi truong tu he thong."""
    # Gia lap cac bien moi truong thay doi
    monkeypatch.setenv("APP_NAME", "my-custom-chatbot")
    monkeypatch.setenv("NEO4J_URI", "bolt://127.0.0.1:7687")
    monkeypatch.setenv("LLM_MODEL_NAME", "llama3.1:8b")
    monkeypatch.setenv("DEBUG", "false")

    custom_settings = Settings()

    assert custom_settings.app_name == "my-custom-chatbot"
    assert custom_settings.neo4j_uri == "bolt://127.0.0.1:7687"
    assert custom_settings.llm_model_name == "llama3.1:8b"
    assert custom_settings.debug is False


def test_get_settings_function():
    """Kiem tra ham helper get_settings hoat dong dung."""
    settings = get_settings()
    assert isinstance(settings, Settings)

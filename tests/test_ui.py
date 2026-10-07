"""Kiem thu giao dien Gradio UI va tich hop FastAPI (Phase 9).

Cac test case bao gom:
1. Import ui.py thanh cong.
2. build_demo() khoi tao Blocks thanh cong.
3. chat_fn voi cau hoi rong giu nguyen lich su va reset o nhap lieu.
4. chat_fn voi mock generate_rag_answer cap nhat lich su hoi thoai chinh xac.
5. FastAPI app duoc khoi tao thanh cong voi Gradio da mount.
6. Endpoint /chat-ui tra ve ma 200.
7. Endpoint /health va / van hoat dong on dinh sau khi mount Gradio.
"""

from unittest.mock import patch
import gradio as gr
from fastapi.testclient import TestClient

from rag_chatbot.ui import build_demo, chat_fn
from rag_chatbot.main import app

client = TestClient(app)


def test_import_ui():
    """Kiem tra import cac ham trong ui.py thanh cong."""
    assert callable(build_demo)
    assert callable(chat_fn)


def test_build_demo():
    """Kiem tra build_demo() tao ra doi tuong Gradio Blocks hop le."""
    demo = build_demo()
    assert isinstance(demo, gr.Blocks)


def test_chat_fn_empty_input():
    """Kiem tra chat_fn voi cau hoi rong se khong goi RAG va giu nguyen lich su."""
    initial_history = [{"role": "user", "content": "hello"}]
    new_history, reset_input = chat_fn("   ", initial_history)
    assert new_history == initial_history
    assert reset_input == ""


def test_chat_fn_with_mocked_answer():
    """Kiem tra chat_fn cap nhat dung tin nhan nguoi dung va cau tra loi cua bot."""
    mock_rag_result = {
        "question": "Máy điều hòa Samsung lỗi CF là gì?",
        "answer": "Mã CF là nhắc vệ sinh bộ lọc.",
        "retrieved_documents": [
            {
                "question_id": "Q0358",
                "source_url": "https://www.samsung.com/vn/support/doc1",
            }
        ],
        "llm_status": "success",
    }

    with patch("rag_chatbot.ui.generate_rag_answer", return_value=mock_rag_result):
        history, reset_input = chat_fn("Máy điều hòa Samsung lỗi CF là gì?", [])

        assert len(history) == 2
        assert history[0]["role"] == "user"
        assert history[0]["content"] == "Máy điều hòa Samsung lỗi CF là gì?"
        assert history[1]["role"] == "assistant"
        assert "Mã CF là nhắc vệ sinh bộ lọc." in history[1]["content"]
        assert "https://www.samsung.com/vn/support/doc1" in history[1]["content"]
        assert reset_input == ""


def test_fastapi_app_created_with_ui():
    """Kiem tra app FastAPI duoc khoi tao thanh cong."""
    assert app is not None
    assert app.title == "Vietnamese Electronics Troubleshooting RAG API"


def test_ui_endpoint_accessible():
    """Kiem tra endpoint /chat-ui phan hoi HTTP 200."""
    response = client.get("/chat-ui")
    assert response.status_code == 200


def test_health_and_root_endpoints_with_ui():
    """Kiem tra cac endpoint /health va / van hoat dong binh thuong sau khi mount Gradio."""
    res_health = client.get("/health")
    assert res_health.status_code == 200
    assert res_health.json() == {"status": "ok"}

    res_root = client.get("/")
    assert res_root.status_code == 200
    assert "running" in res_root.json()["message"].lower()

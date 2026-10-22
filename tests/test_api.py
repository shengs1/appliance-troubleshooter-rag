"""Kiem thu API layer FastAPI (Phase 7 va Phase cap nhat Quan ly nguoi dung).

Cac test case bao gom:
1. GET /: Kiem tra tra ve message bao he thong dang chay.
2. GET /health: Kiem tra tra ve status ok nhanh chong.
3. POST /chat chua dang nhap: Kiem tra bi tu choi voi HTTP 401.
4. POST /chat voi cau hoi rong: Kiem tra bi tu choi voi HTTP 400.
5. POST /chat voi mock generate_rag_answer(): Kiem tra cau truc ChatResponse hop le va co conversation_id.
6. POST /chat voi trang thai llm_status='unavailable': Kiem tra tra ve thong tin ro rang.
7. POST /chat voi pipeline nem ngoai le: Kiem tra tra ve HTTP 500 va khong luu do dang.
8. POST /chat tich hop thuc te voi cau hoi Q0358 (Máy điều hòa Samsung lỗi CF là gì?).
"""

from unittest.mock import patch
import uuid
import pytest
from fastapi.testclient import TestClient

from rag_chatbot.main import app

client = TestClient(app)


@pytest.fixture
def auth_client() -> TestClient:
    """Fixture tao mot client da dang ky va dang nhap thanh cong."""
    c = TestClient(app)
    username = f"api_user_{uuid.uuid4().hex[:8]}"
    password = "password123"
    c.post("/auth/register", json={"username": username, "password": password})
    login_res = c.post("/auth/login", json={"username": username, "password": password})
    assert login_res.status_code == 200
    return c


def test_root_endpoint():
    """Kiem tra GET / tra ve 200 va message he thong dang hoat dong."""
    response = client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert "message" in data
    assert "running" in data["message"].lower()


def test_health_endpoint():
    """Kiem tra GET /health tra ve status ok."""
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_chat_rejects_unauthenticated_request():
    """Kiem tra POST /chat tu choi request chua dang nhap voi HTTP 401."""
    unauth_client = TestClient(app)
    response = unauth_client.post("/chat", json={"question": "Samsung lỗi CF là gì?"})
    assert response.status_code == 401
    assert "chưa đăng nhập" in response.json()["detail"].lower()


def test_chat_rejects_empty_question(auth_client: TestClient):
    """Kiem tra POST /chat tu choi cau hoi rong hoac chi co khoang trang bang HTTP 400."""
    # Truong hop 1: Chuoi rong
    res_empty = auth_client.post("/chat", json={"question": ""})
    assert res_empty.status_code == 400
    assert "Câu hỏi không được để trống" in res_empty.json()["detail"]

    # Truong hop 2: Chi chua khoang trang
    res_spaces = auth_client.post("/chat", json={"question": "   \n  \t "})
    assert res_spaces.status_code == 400
    assert "Câu hỏi không được để trống" in res_spaces.json()["detail"]


def test_chat_with_mocked_rag_answer(auth_client: TestClient):
    """Kiem tra POST /chat tra ve day du cac truong question, answer, llm_status, retrieved_documents, sources, conversation_id."""
    mock_rag_result = {
        "question": "Máy điều hòa Samsung lỗi CF là gì?",
        "answer": "Mã CF là nhắc vệ sinh bộ lọc không khí.",
        "context": "Context sample",
        "prompt": "Prompt sample",
        "retrieved_documents": [
            {
                "question_id": "Q0358",
                "brand": "Samsung",
                "device": "Điều hòa",
                "error_code": "CF",
                "answer": "Mã CF là nhắc vệ sinh bộ lọc.",
                "source_url": "https://www.samsung.com/vn/support/doc1",
            }
        ],
        "llm_status": "success",
    }

    with patch("rag_chatbot.main.generate_rag_answer", return_value=mock_rag_result):
        response = auth_client.post(
            "/chat",
            json={"question": "Máy điều hòa Samsung lỗi CF là gì?"},
        )
        assert response.status_code == 200
        data = response.json()

        assert data["question"] == "Máy điều hòa Samsung lỗi CF là gì?"
        assert data["answer"] == "Mã CF là nhắc vệ sinh bộ lọc không khí."
        assert data["llm_status"] == "success"
        assert len(data["retrieved_documents"]) == 1
        assert data["retrieved_documents"][0]["question_id"] == "Q0358"
        assert "https://www.samsung.com/vn/support/doc1" in data["sources"]
        assert data.get("conversation_id") is not None


def test_chat_handles_llm_unavailable_status(auth_client: TestClient):
    """Kiem tra POST /chat khi Local LLM offline van tra ve llm_status='unavailable' va thong bao ro rang."""
    mock_rag_result = {
        "question": "Máy giặt LG lỗi IE",
        "answer": "[Thông báo dịch vụ Local LLM]: Không thể kết nối tới dịch vụ Local LLM.",
        "context": "Context sample",
        "prompt": "Prompt sample",
        "retrieved_documents": [],
        "llm_status": "unavailable",
    }

    with patch("rag_chatbot.main.generate_rag_answer", return_value=mock_rag_result):
        response = auth_client.post("/chat", json={"question": "Máy giặt LG lỗi IE"})
        assert response.status_code == 200
        data = response.json()
        assert data["llm_status"] == "unavailable"
        assert "[Thông báo dịch vụ Local LLM]" in data["answer"]
        assert data.get("conversation_id") is not None


def test_chat_handles_internal_pipeline_exception(auth_client: TestClient):
    """Kiem tra POST /chat tra ve HTTP 500 khi pipeline RAG gap loi bat ngo."""
    with patch("rag_chatbot.main.generate_rag_answer", side_effect=RuntimeError("Lỗi kết nối cơ sở dữ liệu")):
        response = auth_client.post("/chat", json={"question": "Lỗi bất kỳ"})
        assert response.status_code == 500
        data = response.json()
        assert "Lỗi hệ thống khi xử lý câu hỏi" in data["detail"]


def test_chat_integration_with_real_q0358(auth_client: TestClient):
    """Kiem tra POST /chat tich hop thuc te qua toan bo RAG pipeline voi vi du Q0358 (neu co Neo4j hoat dong)."""
    try:
        from rag_chatbot.neo4j_db import get_neo4j_driver
        drv = get_neo4j_driver()
        drv.verify_connectivity()
    except Exception:
        pytest.skip("Neo4j database service is offline; bo qua test tich hop thuc te.")

    response = auth_client.post(
        "/chat",
        json={"question": "Máy điều hòa Samsung lỗi CF là gì?"},
    )
    assert response.status_code == 200
    data = response.json()

    assert data["question"] == "Máy điều hòa Samsung lỗi CF là gì?"
    assert data["llm_status"] in ["success", "unavailable"]

    # Kiem tra tai lieu truy van duoc chua dung ban ghi Q0358
    retrieved_ids = [doc.get("question_id") for doc in data["retrieved_documents"]]
    assert "Q0358" in retrieved_ids

    # Kiem tra nguon doi chieu cua Samsung duoc trich xuat vao danh sach sources
    assert any("samsung.com" in s for s in data["sources"])
    assert data.get("conversation_id") is not None

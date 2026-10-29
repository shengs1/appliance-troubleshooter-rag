"""Kiem thu giao dien va tich hop UI cho he thong RAG Chatbot (Chainlit UI & FastAPI API).

Cac test case bao gom:
1. Kiem tra chat_service.chat_fn xu ly cau hoi va format cau tra loi.
2. chat_fn voi cau hoi rong giu nguyen lich su va reset o nhap lieu.
3. chat_fn voi mock generate_rag_answer cap nhat lich su hoi thoai chinh xac kem nguon dan.
4. FastAPI app duoc khoi tao thanh cong voi title va cac endpoint he thong.
5. Endpoint /health va / hoat dong on dinh.
6. Endpoint /chat-ui va /admin-ui cu cua Gradio da duoc go bo hoan toan (tra ve 404).
7. Chainlit app entrypoint duoc import hop le va san sang phuc vu nguoi dung.
8. Kiem tra source attribution lua chon dung thiet bi.
"""

from unittest.mock import patch
from fastapi.testclient import TestClient

from rag_chatbot.chat_service import chat_fn
from rag_chatbot.main import app
from rag_chatbot.retrieval import extract_matching_sources

client = TestClient(app)


def test_chat_fn_empty_input():
    """Kiem tra chat_fn voi cau hoi rong se khong goi RAG va giu nguyen lich su."""
    initial_history = [{"role": "user", "content": "hello"}]
    new_history, reset_input = chat_fn("   ", initial_history)
    assert new_history == initial_history
    assert reset_input == ""


def test_chat_fn_with_mocked_answer():
    """Kiem tra chat_fn cap nhat dung tin nhan nguoi dung va cau tra loi cua bot kem nguon."""
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

    with patch("rag_chatbot.chat_service.generate_rag_answer", return_value=mock_rag_result):
        history, reset_input = chat_fn("Máy điều hòa Samsung lỗi CF là gì?", [])

        assert len(history) == 2
        assert history[0]["role"] == "user"
        assert history[0]["content"] == "Máy điều hòa Samsung lỗi CF là gì?"
        assert history[1]["role"] == "assistant"
        assert "Mã CF là nhắc vệ sinh bộ lọc." in history[1]["content"]
        assert "https://www.samsung.com/vn/support/doc1" in history[1]["content"]
        assert reset_input == ""


def test_fastapi_app_created():
    """Kiem tra app FastAPI duoc khoi tao thanh cong."""
    assert app is not None
    assert app.title == "Vietnamese Electronics Troubleshooting RAG API"


def test_gradio_ui_endpoints_removed():
    """Kiem tra cac endpoint Gradio cu (/chat-ui va /admin-ui) da bi loai bo khoi FastAPI."""
    res_chat_ui = client.get("/chat-ui")
    assert res_chat_ui.status_code == 404

    res_admin_ui = client.get("/admin-ui")
    assert res_admin_ui.status_code == 404


def test_health_and_root_endpoints():
    """Kiem tra cac endpoint /health va / van hoat dong binh thuong."""
    res_health = client.get("/health")
    assert res_health.status_code == 200
    assert res_health.json() == {"status": "ok"}

    res_root = client.get("/")
    assert res_root.status_code == 200
    assert "running" in res_root.json()["message"].lower()


def test_chainlit_app_entrypoint_valid():
    """Kiem tra module chainlit_app hop le va san sang thuc thi."""
    import rag_chatbot.chainlit_app as cl_app
    assert hasattr(cl_app, "oauth_callback")
    assert hasattr(cl_app, "main")


def test_source_attribution_rejects_mismatched_device():
    """Kiem tra source attribution loai bo tai lieu sai loai thiet bi."""
    question = "Máy lạnh Samsung của tôi không lạnh"
    docs_with_wrong_device = [
        {
            "question_id": "Q0997",
            "brand": "Samsung",
            "device": "Tủ lạnh",
            "source_url": "https://www.samsung.com/vn/refrigerator-doc",
        }
    ]
    sources = extract_matching_sources(docs_with_wrong_device, question)
    assert len(sources) == 0


def test_source_attribution_selects_correct_device():
    """Kiem tra source attribution chon dung link Dieu hoa khi co ca link Tu lanh va Dieu hoa."""
    question = "Máy lạnh Samsung của tôi không lạnh"
    mixed_docs = [
        {
            "question_id": "Q0997",
            "brand": "Samsung",
            "device": "Tủ lạnh",
            "source_url": "https://www.samsung.com/vn/refrigerator-doc",
        },
        {
            "question_id": "Q0606",
            "brand": "Samsung",
            "device": "Điều hòa",
            "source_url": "https://www.samsung.com/vn/air-conditioner-doc",
        },
    ]
    sources = extract_matching_sources(mixed_docs, question)
    assert sources == ["https://www.samsung.com/vn/air-conditioner-doc"]


def test_chainlit_file_upload_disabled_in_config():
    """Kiem tra tinh nang upload file da duoc tat hoan toan trong .chainlit/config.toml."""
    import pathlib
    import tomli

    config_path = pathlib.Path(".chainlit/config.toml")
    assert config_path.exists()
    with open(config_path, "rb") as f:
        cfg = tomli.load(f)

    assert "features" in cfg
    assert "spontaneous_file_upload" in cfg["features"]
    assert cfg["features"]["spontaneous_file_upload"]["enabled"] is False
    assert cfg["features"]["spontaneous_file_upload"].get("accept") == []


def test_chat_composer_placeholder_vietnamese():
    """Kiem tra placeholder o nhap lieu duoc Viet hoa chuan xac."""
    import json
    import pathlib

    trans_path = pathlib.Path(".chainlit/translations/en-US.json")
    assert trans_path.exists()
    with open(trans_path, "r", encoding="utf-8") as f:
        trans = json.load(f)

    placeholder = trans.get("chat", {}).get("input", {}).get("placeholder")
    assert placeholder == "Nhập câu hỏi của bạn..."


def test_custom_assets_and_admin_header_button_present():
    """Kiem tra cac file public/custom.js va public/custom.css chua logic Admin Header Button."""
    import pathlib

    js_path = pathlib.Path("public/custom.js")
    css_path = pathlib.Path("public/custom.css")
    logo_path = pathlib.Path("public/branding/dhv-logo.png")

    assert js_path.exists()
    assert css_path.exists()
    assert logo_path.exists()

    js_code = js_path.read_text(encoding="utf-8")
    assert "dhv-admin-header-btn" in js_code
    assert "/admin/bridge-token" in js_code
    assert "Nhập câu hỏi của bạn..." in js_code

    css_code = css_path.read_text(encoding="utf-8")
    assert ".dhv-admin-header-btn" in css_code
    assert "lucide-paperclip" in css_code


def test_fastapi_browser_redirects_and_navigation_links():
    """Kiem tra co che chuyen huong tu dong cua FastAPI va cac lien ket dang nhap tro toi port 8001."""
    import pathlib

    # 1. Kiem tra FastAPI chuyen huong trinh duyet sang Chainlit UI
    res_browser = client.get("/", headers={"Accept": "text/html,application/xhtml+xml"}, follow_redirects=False)
    assert res_browser.status_code in [302, 307]
    assert "8001" in res_browser.headers.get("location", "")

    res_login = client.get("/login", follow_redirects=False)
    assert res_login.status_code in [302, 307]
    assert "8001/login" in res_login.headers.get("location", "")

    res_logout = client.get("/logout", follow_redirects=False)
    assert res_logout.status_code in [302, 307]
    assert "8001/logout" in res_logout.headers.get("location", "")

    # 2. Kiem tra cac trang HTML chua logic getFrontendLoginUrl/BaseUrl va link tro toi 8001
    reset_html = pathlib.Path("public/reset-password.html").read_text(encoding="utf-8")
    assert "getFrontendLoginUrl" in reset_html
    assert "8001" in reset_html

    forgot_html = pathlib.Path("public/forgot-password.html").read_text(encoding="utf-8")
    assert "getFrontendLoginUrl" in forgot_html
    assert "8001" in forgot_html

    register_html = pathlib.Path("public/register.html").read_text(encoding="utf-8")
    assert "getFrontendLoginUrl" in register_html
    assert "8001" in register_html

    admin_html = pathlib.Path("public/admin.html").read_text(encoding="utf-8")
    assert "getFrontendBaseUrl" in admin_html
    assert "8001" in admin_html


def test_composer_capsule_and_circular_send_button_styles():
    """Kiem tra Chat Composer co phong cach vien thuoc (capsule) va nut gui tron theo Anh 2."""
    import pathlib

    css_path = pathlib.Path("public/custom.css")
    assert css_path.exists()
    css_code = css_path.read_text(encoding="utf-8")

    # 1. Kiem tra khung nhap capsule / pill
    assert "#message-composer" in css_code
    assert "border-radius: 9999px" in css_code
    assert "flex-direction: row" in css_code

    # 2. Kiem tra nut gui hinh tron xoe voi mui ten
    assert "#chat-submit" in css_code
    assert "border-radius: 50%" in css_code
    assert "#2563eb" in css_code  # Mau xanh duong dam Image 2


def test_chainlit_readme_contains_sample_questions():
    """Kiem tra cac file chainlit.md va chainlit_en-US.md co danh sach cau hoi mau ro rang."""
    import pathlib

    for filename in ["chainlit.md", "chainlit_en-US.md"]:
        p = pathlib.Path(filename)
        assert p.exists(), f"{filename} khong ton tai"
        content = p.read_text(encoding="utf-8")
        assert "Câu hỏi gợi ý mẫu" in content
        assert "Điều hòa Panasonic báo lỗi F16" in content
        assert "Tủ lạnh LG lỗi SB" in content
        assert "Máy giặt Samsung rung lắc" in content
        assert "Bếp từ Panasonic báo lỗi U04" in content





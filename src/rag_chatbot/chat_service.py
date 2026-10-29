"""Dich vu xu ly hoi dap va dinh dang cau tra loi RAG (Chat Service)."""

from __future__ import annotations

from typing import Any
from rag_chatbot.rag import generate_rag_answer
from rag_chatbot.retrieval import extract_matching_sources


def chat_fn(
    message: str,
    history: list[dict[str, str]] | None = None,
) -> tuple[list[dict[str, str]], str]:
    """Xu ly mot cau hoi cua nguoi dung va them cau tra loi tu pipeline RAG."""
    clean_message = message.strip()
    current_history = list(history or [])

    if not clean_message:
        return current_history, ""

    result = generate_rag_answer(clean_message)
    answer = result.get("answer", "")

    # Trich xuat nguon tham khao tu tai lieu phu hop nhat neu khong bi tu choi
    sources: list[str] = []
    retrieved_docs = result.get("retrieved_documents", [])
    if result.get("llm_status") != "refused_scope" and retrieved_docs:
        sources = extract_matching_sources(retrieved_docs, clean_message)

    validation = result.get("validation")
    if validation and validation.get("status") == "pass" and result.get("llm_status") == "success":
        answer += "\n\n*(Đã kiểm tra câu trả lời theo tài liệu nguồn)*"

    if sources:
        answer += "\n\n**Nguồn tham khảo:**\n" + "\n".join(
            f"- {source}" for source in sources
        )

    current_history.extend(
        [
            {"role": "user", "content": clean_message},
            {"role": "assistant", "content": answer},
        ]
    )

    return current_history, ""


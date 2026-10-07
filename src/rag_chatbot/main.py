"""Diem khoi dau va API layer cua ung dung RAG Chatbot (Phase 7 - FastAPI).

Nhiem vu:
1. Tao ung dung FastAPI phuc vu truy van RAG qua giao dien REST API.
2. Cung cap cac endpoint don gian, ro rang:
   - GET /: Kiem tra trang thai hoat dong co ban cua ung dung.
   - GET /health: Kiem tra suc khoe he thong nhe nhang (khong load lai database).
   - POST /chat: Tiep nhan cau hoi, goi generate_rag_answer() tu Phase 6 va tra ve ket qua JSON.
"""

from __future__ import annotations
from typing import Any
from fastapi import FastAPI, HTTPException, status
from pydantic import BaseModel, Field

from rag_chatbot.rag import generate_rag_answer


# 1. Khoi tao ung dung FastAPI
app = FastAPI(
    title="Vietnamese Electronics Troubleshooting RAG API",
    description="API tra cuu huong dan xu ly su co thiet bi dien tu gia dung su dung RAG",
    version="0.1.0",
)


# 2. Mo hinh du lieu Pydantic (Request / Response)
class ChatRequest(BaseModel):
    """Du lieu dau vao cho endpoint POST /chat."""
    question: str = Field(..., description="Cau hoi cua nguoi dung")


class ChatResponse(BaseModel):
    """Du lieu phan hoi cho endpoint POST /chat."""
    question: str
    answer: str
    llm_status: str
    retrieved_documents: list[dict[str, Any]]
    sources: list[str]


# 3. Cac endpoint API

@app.get("/", summary="Root endpoint")
def root() -> dict[str, str]:
    """Endpoint goc thong bao trang thai he thong."""
    return {"message": "RAG Chatbot API is running"}


@app.get("/health", summary="Health check endpoint")
def health() -> dict[str, str]:
    """Endpoint kiem tra suc khoe nhe nhang, khong truy van nang ne."""
    return {"status": "ok"}


@app.post(
    "/chat",
    response_model=ChatResponse,
    summary="Chat endpoint - Truy van RAG",
)
def chat(request: ChatRequest) -> ChatResponse:
    """Tiep nhan cau hoi cua nguoi dung va tra ve cau tra loi tu he thong RAG."""
    # Kiem tra cau hoi khong duoc rong hoac chi chua khoang trang
    clean_question = request.question.strip()
    if not clean_question:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Câu hỏi không được để trống.",
        )

    try:
        # Goi quy trinh RAG da hoan thien o Phase 6
        rag_result = generate_rag_answer(clean_question)

        # Trich xuat danh sach nguon tham khao doc nhat tu cac tai lieu truy van
        sources: list[str] = []
        for doc in rag_result.get("retrieved_documents", []):
            url = doc.get("source_url")
            if url and url not in sources:
                sources.append(url)

        return ChatResponse(
            question=rag_result["question"],
            answer=rag_result["answer"],
            llm_status=rag_result["llm_status"],
            retrieved_documents=rag_result.get("retrieved_documents", []),
            sources=sources,
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Lỗi hệ thống khi xử lý câu hỏi: {exc}",
        )

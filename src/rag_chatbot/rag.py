"""Module dieu phoi RAG (Retrieval-Augmented Generation) voi Local LLM.

Nhiem vu trong Phase 6:
1. Tiep nhan cau hoi cua nguoi dung.
2. Thuc hien Hybrid Retrieval de lay cac tai lieu ky thuat phu hop nhat.
3. Xay dung doan van ban ngu canh (Context) de doc va truyen tai du lieu.
4. Tao Prompt huong dan nghiem ngat, chong ao giac (Grounding Prompt).
5. Goi Local LLM (Ollama / Qwen2.5) de sinh cau tra loi cuoi cung.
"""

from __future__ import annotations
from typing import Any
import requests

from rag_chatbot.config import get_settings
from rag_chatbot.retrieval import search_hybrid


def build_context(retrieved_docs: list[dict[str, Any]]) -> str:
    """Xay dung doan van ban ngu canh (context) tu cac tai lieu truy van duoc.
    
    Trinh bay ro rang thong tin: Hang, Thiet bi, Ma loi, Cau hoi tham khao, 
    Huong dan xu ly va Nguon tai lieu de mo hinh LLM co can cu chinh xac.
    """
    if not retrieved_docs:
        return "Không tìm thấy tài liệu kỹ thuật nào liên quan trong cơ sở tri thức."

    context_blocks: list[str] = []
    for idx, doc in enumerate(retrieved_docs, 1):
        source_type = doc.get("retrieval_source", "unknown")
        block = [
            f"--- TÀI LIỆU THAM KHẢO {idx} (Nguồn tìm kiếm: {source_type}) ---",
            f"- Hãng: {doc.get('brand', '')}",
            f"- Thiết bị: {doc.get('device', '')}",
        ]
        if doc.get("error_code"):
            block.append(f"- Mã lỗi: {doc.get('error_code')}")
        
        block.append(f"- Câu hỏi tham khảo: {doc.get('question', '')}")
        block.append(f"- Hướng dẫn xử lý: {doc.get('answer', '')}")
        
        if doc.get("source_url"):
            block.append(f"- Nguồn đối chiếu: {doc.get('source_url')}")
            
        context_blocks.append("\n".join(block))

    return "\n\n".join(context_blocks)


def create_prompt(question: str, context: str) -> str:
    """Tao prompt huong dan mo hinh LLM tra loi dua tren ngu canh duoc cung cap.
    
    Cac quy tac chong ao giac (Hallucination prevention):
    1. Chi tra loi dua tren phan NGỮ CẢNH KỸ THUẬT.
    2. Khong tu bia dat ma loi, nguyen nhan hoac cach sua khi tai lieu khong co.
    3. Neu khong du thong tin, noi ro la du lieu hien tai chua du.
    4. Giu nguyen ma loi, ten hang, loai thiet bi.
    5. Dan nguon link tai lieu o cuoi cau tra loi khi co san.
    """
    prompt = f"""Bạn là trợ lý AI chuyên nghiệp hỗ trợ chẩn đoán và hướng dẫn khắc phục sự cố thiết bị điện tử gia dụng.
Nhiệm vụ của bạn là giải đáp câu hỏi của người dùng dựa DUY NHẤT vào phần NGỮ CẢNH KỸ THUẬT dưới đây.

CÁC NGUYÊN TẮC BẮT BUỘC:
1. Chỉ sử dụng thông tin kỹ thuật có trong phần NGỮ CẢNH. Tuyệt đối KHÔNG tự sáng tác mã lỗi, nguyên nhân hoặc cách khắc phục không có trong tài liệu.
2. Nếu ngữ cảnh không có thông tin hoặc không đủ dữ liệu để giải đáp, hãy thông báo rõ ràng rằng cơ sở tri thức chưa có đủ thông tin xử lý cho trường hợp này.
3. Luôn giữ chính xác tên hãng, loại thiết bị và mã lỗi kỹ thuật.
4. Trình bày câu trả lời rõ ràng, bao gồm: Nguyên nhân sự cố (nếu có) và Hướng dẫn khắc phục từng bước (nếu có).
5. Nếu ngữ cảnh có đường link nguồn, hãy ghi rõ nguồn tham khảo ở cuối câu trả lời để người dùng tiện kiểm chứng.

NGỮ CẢNH KỸ THUẬT:
{context}

CÂU HỎI CỦA NGƯỜI DÙNG:
{question}

CÂU TRẢ LỜI CỦA BẠN:"""
    return prompt


def call_local_llm(
    prompt: str,
    model: str | None = None,
    base_url: str | None = None,
    timeout: int = 60,
) -> str:
    """Goi API toi Local LLM (Ollama) de sinh cau tra loi.
    
    Su dung HTTP POST toi /api/generate cua Ollama theo cau hinh tu config.py.
    """
    settings = get_settings()
    target_model = model or settings.llm_model_name
    endpoint = (base_url or settings.ollama_base_url).rstrip("/") + "/api/generate"

    payload = {
        "model": target_model,
        "prompt": prompt,
        "stream": False,
    }

    try:
        response = requests.post(endpoint, json=payload, timeout=timeout)
        response.raise_for_status()
        data = response.json()
        return data.get("response", "").strip()
    except requests.exceptions.ConnectionError:
        raise ConnectionError(
            f"Không thể kết nối tới dịch vụ Local LLM tại {endpoint}. "
            f"Vui lòng kiểm tra dịch vụ Ollama đã được khởi động chưa (ví dụ: ollama serve)."
        )
    except Exception as exc:
        raise RuntimeError(f"Lỗi khi gọi Local LLM: {exc}")


def generate_rag_answer(
    question: str,
    k: int = 5,
    model: str | None = None,
    base_url: str | None = None,
) -> dict[str, Any]:
    """Quy trinh RAG hoan chinh:
    Cau hoi -> search_hybrid() -> build_context() -> create_prompt() -> call_local_llm() -> Ket qua.
    
    Args:
        question: Cau hoi cua nguoi dung.
        k: So luong tai lieu tham khao can lay (mac dinh 5).
        model: Ten mo hinh LLM tuy chon (mac dinh qwen2.5:7b).
        base_url: URL dich vu Local LLM tuy chon.
        
    Returns:
        Dict chua:
        - 'question': Cau hoi cua nguoi dung
        - 'answer': Cau tra loi tu LLM (hoac thong bao tinh trang neu LLM chua bat)
        - 'context': Noi dung ngu canh da xay dung
        - 'prompt': Toan bo prompt da chuyen toi LLM
        - 'retrieved_documents': Danh sach ban ghi lay tu Hybrid Retrieval
        - 'llm_status': 'success' hoac 'unavailable'
    """
    # 1. Truy van ket hop Hybrid Retrieval
    retrieved_docs = search_hybrid(question, k=k)

    # 2. Xay dung ngu canh tu tai lieu
    context = build_context(retrieved_docs)

    # 3. Tao prompt chong ao giac
    prompt = create_prompt(question, context)

    # 4. Goi Local LLM
    try:
        answer = call_local_llm(prompt, model=model, base_url=base_url)
        llm_status = "success"
    except (ConnectionError, RuntimeError) as err:
        answer = f"[Thông báo dịch vụ Local LLM]: {err}"
        llm_status = "unavailable"

    return {
        "question": question,
        "answer": answer,
        "context": context,
        "prompt": prompt,
        "retrieved_documents": retrieved_docs,
        "llm_status": llm_status,
    }


def generate_answer(query: str) -> str:
    """Ham giao tiep don gian sinh cau tra loi cho cau hoi."""
    result = generate_rag_answer(query)
    return result["answer"]


if __name__ == "__main__":
    sample_question = "Máy điều hòa Samsung lỗi CF là gì?"
    print(f"=== CHẠY THỬ NGHIỆM RAG PIPELINE ===")
    print(f"Câu hỏi: {sample_question}\n")

    rag_result = generate_rag_answer(sample_question, k=3)
    print("--- 1. NGỮ CẢNH TRUY VẤN (CONTEXT) ---")
    print(rag_result["context"])
    print("\n--- 2. PROMPT GỬI CHO LLM ---")
    print(rag_result["prompt"][:500] + "...\n")
    print(f"--- 3. TRẠNG THÁI LOCAL LLM: {rag_result['llm_status']} ---")
    print("--- 4. CÂU TRẢ LỜI CỦA LLM ---")
    print(rag_result["answer"])

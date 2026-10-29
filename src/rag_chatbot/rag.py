"""Module điều phối quy trình RAG (Retrieval-Augmented Generation) kết hợp Local LLM.

Quy trình:
1. Tiếp nhận câu hỏi và kiểm tra phạm vi hỗ trợ (scope check).
2. Tìm kiếm tài liệu kỹ thuật liên quan qua Hybrid Retrieval (ChromaDB + Neo4j).
3. Xây dựng ngữ cảnh kỹ thuật và gửi prompt tới Local LLM (Ollama / Qwen2.5).
4. Kiểm định câu trả lời chống ảo giác và ngăn chặn ký tự ngoại ngữ không mong muốn.
"""

from __future__ import annotations
import re
from typing import Any
import requests

from rag_chatbot.answer_validator import SAFE_FALLBACK_MESSAGE, validate_answer
from rag_chatbot.config import get_settings
from rag_chatbot.retrieval import extract_question_entities, search_hybrid
from rag_chatbot.scope import REFUSAL_MESSAGE, should_refuse


# Regex phat hien ky tu chu Han / CJK Unicode
CJK_CHAR_REGEX = re.compile(r"[\u4e00-\u9fff\u3400-\u4dbf]")


def contains_unexpected_cjk(text: str) -> bool:
    """Kiem tra xem van ban co chua ky tu chu Han / CJK khong mong muon hay khong."""
    if not text:
        return False
    return bool(CJK_CHAR_REGEX.search(text))


def create_cjk_rewrite_prompt(question: str, context: str, initial_answer: str) -> str:
    """Tao prompt huong dan LLM viet lai cau tra loi hoan toan bang tieng Viet khi phat hien chu Han."""
    return f"""Bạn là trợ lý AI chuyên nghiệp hỗ trợ khắc phục sự cố điện tử gia dụng.
Câu trả lời trước đó của bạn bị lẫn ký tự chữ Hán/tiếng Trung. Hãy viết lại câu trả lời HOÀN TOÀN bằng tiếng Việt chuẩn xác, giữ nguyên các thông tin kỹ thuật, tên hãng, loại thiết bị và mã lỗi. Tuyệt đối KHÔNG chứa bất kỳ chữ Hán nào.

NGỮ CẢNH KỸ THUẬT:
{context}

CÂU HỎI CỦA NGƯỜI DÙNG:
{question}

CÂU TRẢ LỜI CẦN VIẾT LẠI (BỊ LẪN KÝ TỰ):
{initial_answer}

CÂU TRẢ LỜI VIẾT LẠI (100% TIẾNG VIỆT):"""


def strip_sources_from_answer(text: str) -> str:
    """Loai bo bat ky dong chua URL, nguon tham khao hoac nguon doi chieu ma LLM co the tu y sinh ra."""
    if not text:
        return ""

    cleaned_lines: list[str] = []
    for line in text.splitlines():
        line_stripped = line.strip()
        lower_line = line_stripped.lower()
        if (
            lower_line.startswith("nguồn đối chiếu:")
            or lower_line.startswith("nguồn tham khảo:")
            or lower_line.startswith("**nguồn tham khảo:**")
            or lower_line.startswith("**nguồn đối chiếu:**")
            or lower_line.startswith("- nguồn đối chiếu:")
            or lower_line.startswith("- nguồn tham khảo:")
            or re.match(r"^(?:-\s*)?<?https?://\S+>?$", line_stripped)
        ):
            continue
        cleaned_lines.append(line)

    return "\n".join(cleaned_lines).strip()


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
    5. KHONG tu xuat URL hay nguon tham khao (he thong se tu dong hien thi rieng).
    """
    prompt = f"""Bạn là trợ lý AI chuyên nghiệp hỗ trợ chẩn đoán và hướng dẫn khắc phục sự cố thiết bị điện tử gia dụng.
Nhiệm vụ của bạn là giải đáp câu hỏi của người dùng dựa DUY NHẤT vào phần NGỮ CẢNH KỸ THUẬT dưới đây.

CÁC NGUYÊN TẮC BẮT BUỘC:
1. Chỉ sử dụng thông tin kỹ thuật được nêu rõ ràng trong phần NGỮ CẢNH. Tuyệt đối KHÔNG tự suy diễn nguyên nhân từ kiến thức phổ thông, không tự sáng tác sự kiện kỹ thuật mới, không thêm lời khuyên chung chung hay khuyến cáo an toàn/dịch vụ nếu tài liệu không đề cập.
2. Trả lời ngắn gọn, trực tiếp và giữ nguyên đúng ý nghĩa của dữ liệu được cung cấp.
3. Nếu ngữ cảnh không có thông tin hoặc không đủ dữ liệu để giải đáp, hãy thông báo rõ ràng rằng cơ sở tri thức chưa có đủ thông tin xử lý cho trường hợp này.
4. Luôn giữ chính xác tên hãng, loại thiết bị và mã lỗi kỹ thuật.
5. Tuyệt đối KHÔNG tự chèn đường dẫn URL, không ghi "Nguồn tham khảo", không ghi "Nguồn đối chiếu", không tạo danh sách link hay markdown link trong câu trả lời (phần nguồn sẽ do hệ thống hiển thị riêng). Chỉ trả về nội dung giải đáp kỹ thuật.
6. NGÔN NGỮ BẮT BUỘC: Trả lời HOÀN TOÀN bằng tiếng Việt tự nhiên và chuẩn xác. Tuyệt đối KHÔNG sử dụng tiếng Trung (chữ Hán/Hanzi), tiếng Nhật, tiếng Hàn hoặc ngôn ngữ nào khác (ngoại trừ tên thương hiệu quốc tế và mã lỗi như Samsung, Panasonic, CF, F16, H97). Toàn bộ nội dung phân tích, hướng dẫn và giải thích phải viết bằng tiếng Việt.

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
    timeout: int = 90,
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
    except requests.exceptions.ReadTimeout:
        raise TimeoutError("Thời gian chờ phản hồi từ Local LLM đã quá hạn (timeout).")
    except requests.exceptions.ConnectionError:
        raise ConnectionError(
            f"Không thể kết nối tới dịch vụ Local LLM tại {endpoint}. "
            f"Vui lòng kiểm tra dịch vụ Ollama đã được khởi động chưa (ví dụ: ollama serve)."
        )
    except requests.exceptions.Timeout:
        raise TimeoutError("Thời gian chờ phản hồi từ Local LLM đã quá hạn (timeout).")
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

    # 2. Kiem tra pham vi cau hoi (Scope Check - Phase 10A)
    if should_refuse(retrieved_docs, question=question):
        return {
            "question": question,
            "answer": REFUSAL_MESSAGE,
            "context": "",
            "prompt": "",
            "retrieved_documents": retrieved_docs,
            "llm_status": "refused_scope",
            "validation": {
                "status": "refused_scope",
                "grounded": True,
                "brand_consistent": True,
                "device_consistent": True,
                "error_code_consistent": True,
                "hallucination_detected": False,
                "source_consistent": True,
                "reasons": ["Câu hỏi nằm ngoài phạm vi hỗ trợ (Out-of-Scope)."],
            },
        }

    # 3. Xay dung ngu canh tu tai lieu
    context = build_context(retrieved_docs)

    # 4. Tao prompt chong ao giac
    prompt = create_prompt(question, context)

    # 5. Goi Local LLM
    try:
        raw_answer = call_local_llm(prompt, model=model, base_url=base_url)
        answer = strip_sources_from_answer(raw_answer)
        llm_status = "success"

        # Kiem tra ky tu CJK / chu Han khong mong muon va thu lai toi da 1 lan
        if contains_unexpected_cjk(answer):
            try:
                rewrite_prompt = create_cjk_rewrite_prompt(question, context, answer)
                retry_raw = call_local_llm(rewrite_prompt, model=model, base_url=base_url)
                retry_answer = strip_sources_from_answer(retry_raw)
                if not contains_unexpected_cjk(retry_answer):
                    answer = retry_answer
                else:
                    answer = "Hệ thống đã nhận diện câu trả lời chứa ký tự không phù hợp và đã chuẩn hóa. Vui lòng tham khảo tài liệu kỹ thuật được cung cấp bên dưới hoặc thử đặt câu hỏi cụ thể hơn."
            except Exception:
                pass
    except Exception as err:
        llm_status = "unavailable"
        # 1. Neu trong tai lieu tim duoc tu Chroma / Neo4j da co huong dan xu ly cu the:
        # Cung cap truc tiep huong dan da duoc xac thuc tu CSDL thay vi bao loi vo ich cho nguoi dung
        top_answer = ""
        for d in retrieved_docs:
            if d.get("answer") and d.get("answer").strip():
                top_answer = d["answer"].strip()
                break

        if top_answer:
            answer = (
                f"{top_answer}\n\n"
                f"*(Lưu ý: Hướng dẫn kỹ thuật trên được trích xuất trực tiếp từ Cơ sở tri thức do mô hình Local LLM đang phản hồi chậm).* "
            )
        elif isinstance(err, TimeoutError) or "timed out" in str(err).lower() or "timeout" in str(err).lower():
            answer = (
                "⚠️ **Thời gian phản hồi quá lâu:** Mô hình AI cục bộ (Ollama) đang bận hoặc phản hồi chậm hơn thời gian quy định (90 giây). "
                "Vui lòng thử lại sau giây lát hoặc kiểm tra ứng dụng Ollama trên máy tính."
            )
        elif isinstance(err, ConnectionError) or "kết nối" in str(err).lower() or "connection" in str(err).lower():
            answer = (
                "⚠️ **Không thể kết nối tới mô hình AI (Ollama):** Dịch vụ Local LLM chưa được khởi động trên máy tính (cổng 11434). "
                "Vui lòng mở ứng dụng Ollama hoặc chạy lệnh `ollama serve` trong terminal."
            )
        else:
            answer = (
                "⚠️ **Hệ thống đang bận:** Đã xảy ra lỗi kỹ thuật khi tạo phản hồi tự nhiên. "
                "Vui lòng kiểm tra dịch vụ AI cục bộ hoặc thử lại sau giây lát."
            )

    # 6. Kiem dinh va xac thuc cau tra loi (Phase Answer Validation)
    if llm_status == "success":
        entities = extract_question_entities(question)
        validation = validate_answer(
            question=question,
            answer=answer,
            retrieved_documents=retrieved_docs,
            entities=entities,
        )
        # Neu validator FAIL: khong tra answer chua kiem chung ma dung thong bao an toan
        if validation["status"] == "fail":
            answer = SAFE_FALLBACK_MESSAGE
    else:
        validation = {
            "status": "fail",
            "grounded": False,
            "brand_consistent": False,
            "device_consistent": False,
            "error_code_consistent": False,
            "hallucination_detected": False,
            "source_consistent": False,
            "reasons": ["Dịch vụ Local LLM không khả dụng."],
        }

    return {
        "question": question,
        "answer": answer,
        "context": context,
        "prompt": prompt,
        "retrieved_documents": retrieved_docs,
        "llm_status": llm_status,
        "validation": validation,
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

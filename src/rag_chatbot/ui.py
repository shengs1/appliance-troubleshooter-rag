"""Gradio UI for the appliance troubleshooting RAG chatbot."""

from __future__ import annotations

import gradio as gr

from rag_chatbot.rag import generate_rag_answer


SUGGESTIONS = [
    "Samsung lỗi CF là gì?",
    "LG lỗi IE xử lý thế nào?",
    "Panasonic lỗi F11 là gì?",
]


CUSTOM_CSS = """
body {
    background: #0b0f19 !important;
}

/* Keep the visible application at a readable width. */
#app-shell {
    width: 960px !important;
    max-width: calc(100vw - 40px) !important;
    margin: 0 auto !important;
}

/* Header */
#header-row {
    margin-bottom: 10px !important;
}

#app-header {
    margin: 0 !important;
}

#app-header h1 {
    margin: 0 0 4px 0;
    color: #f8fafc;
    font-size: 1.55rem;
    font-weight: 700;
}

#app-header p {
    margin: 0;
    color: #94a3b8;
    font-size: 0.9rem;
}

/* Small clear button */
#clear-btn {
    width: 38px !important;
    min-width: 38px !important;
    max-width: 38px !important;
}

#clear-btn button {
    width: 38px !important;
    height: 38px !important;
    min-width: 38px !important;
    padding: 0 !important;
    border-radius: 8px !important;
    font-size: 1rem !important;
}

/* Chatbot */
#chat-window {
    height: 320px !important;
    min-height: 320px !important;
    border-radius: 10px !important;
    margin-bottom: 10px !important;
}

/* Examples / Suggestions */
#suggestions {
    margin: 0 0 10px 0 !important;
    background: transparent !important;
    border: none !important;
}

#suggestions table,
#suggestions tbody {
    display: flex !important;
    flex-wrap: wrap !important;
    gap: 8px !important;
    background: transparent !important;
    border: none !important;
}

#suggestions tr {
    display: inline-flex !important;
    width: auto !important;
    cursor: pointer !important;
    border: 1px solid #334155 !important;
    border-radius: 9999px !important;
    background: #1e293b !important;
    padding: 4px 14px !important;
    transition: all 0.15s ease !important;
}

#suggestions tr:hover {
    background: #334155 !important;
    border-color: #f97316 !important;
}

#suggestions td {
    padding: 0 !important;
    border: none !important;
    white-space: nowrap !important;
    font-size: 0.85rem !important;
    color: #cbd5e1 !important;
}

/* Input */
#input-row {
    margin: 0 !important;
}

#msg-input textarea {
    min-height: 48px !important;
    height: 48px !important;
    max-height: 48px !important;
    resize: none !important;
}

#send-btn {
    width: 80px !important;
    min-width: 80px !important;
    max-width: 90px !important;
}

#send-btn button {
    min-height: 48px !important;
    height: 48px !important;
    width: 100% !important;
    border-radius: 8px !important;
    background: #f97316 !important;
    border-color: #ea580c !important;
    color: #ffffff !important;
    font-weight: 600 !important;
}

#send-btn button:hover {
    background: #ea580c !important;
}

/* Hide Gradio footer */
footer,
.gradio-footer {
    display: none !important;
}
"""


def chat_fn(
    message: str,
    history: list[dict[str, str]] | None = None,
) -> tuple[list[dict[str, str]], str]:
    """Process one user question and append the RAG response."""
    clean_message = message.strip()
    current_history = list(history or [])

    if not clean_message:
        return current_history, ""

    result = generate_rag_answer(clean_message)
    answer = result.get("answer", "")

    # Trich xuat nguon tham khao tu tai lieu phu hop nhat (top 1) neu khong bi tu choi
    sources: list[str] = []
    retrieved_docs = result.get("retrieved_documents", [])
    if result.get("llm_status") != "refused_scope" and retrieved_docs:
        top_url = retrieved_docs[0].get("source_url")
        if top_url:
            sources.append(top_url)
        else:
            top_brand = retrieved_docs[0].get("brand")
            for doc in retrieved_docs:
                url = doc.get("source_url")
                if url and (not top_brand or doc.get("brand") == top_brand):
                    sources.append(url)
                    break

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


def build_demo() -> gr.Blocks:
    """Build the Gradio interface."""
    welcome = (
        "Chào bạn! Tôi có thể hỗ trợ tra cứu mã lỗi và khắc phục sự cố "
        "thiết bị điện tử gia dụng.\n\n"
        "Nhập câu hỏi hoặc chọn một câu hỏi mẫu để bắt đầu."
    )

    with gr.Blocks(
        title="Trợ lý Sự cố Điện gia dụng",
        fill_width=False,
    ) as demo:
        # Create the input before the examples, but render it later
        # so the visual order remains: chatbot -> suggestions -> input.
        msg_input = gr.Textbox(
            placeholder="Nhập câu hỏi của bạn...",
            show_label=False,
            container=False,
            lines=1,
            max_lines=1,
            scale=1,
            min_width=160,
            render=False,
            elem_id="msg-input",
        )

        with gr.Column(elem_id="app-shell", variant="compact"):
            with gr.Row(elem_id="header-row", variant="compact"):
                gr.HTML(
                    """
                    <div id="app-header">
                        <h1>Trợ lý Sự cố Điện gia dụng</h1>
                        <p>Tra cứu mã lỗi và hỗ trợ khắc phục sự cố thiết bị điện tử gia dụng.</p>
                    </div>
                    """,
                    scale=1,
                )

                clear_btn = gr.Button(
                    "🗑️",
                    size="sm",
                    variant="secondary",
                    scale=0,
                    min_width=38,
                    elem_id="clear-btn",
                )

            chatbot = gr.Chatbot(
                placeholder=welcome,
                height=320,
                show_label=False,
                elem_id="chat-window",
            )

            # Native Gradio examples: clicking an example fills the input.
            gr.Examples(
                examples=[[question] for question in SUGGESTIONS],
                inputs=msg_input,
                label="Gợi ý câu hỏi",
                examples_per_page=3,
                elem_id="suggestions",
            )

            with gr.Row(
                elem_id="input-row",
                variant="compact",
                equal_height=True,
            ):
                msg_input.render()

                send_btn = gr.Button(
                    "Gửi",
                    variant="primary",
                    scale=0,
                    min_width=80,
                    elem_id="send-btn",
                )

        send_btn.click(
            fn=chat_fn,
            inputs=[msg_input, chatbot],
            outputs=[chatbot, msg_input],
        )

        msg_input.submit(
            fn=chat_fn,
            inputs=[msg_input, chatbot],
            outputs=[chatbot, msg_input],
        )

        clear_btn.click(
            fn=lambda: ([], ""),
            inputs=None,
            outputs=[chatbot, msg_input],
        )

    return demo


if __name__ == "__main__":
    build_demo().launch()

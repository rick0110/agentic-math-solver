from __future__ import annotations

from pathlib import Path
import threading
import webbrowser

from ..config import AppConfig
from ..orchestrator import SwarmOrchestrator


def launch_app(config: AppConfig) -> None:
    try:
        import gradio as gr
    except ImportError as exc:
        raise RuntimeError("Install the UI extra with: pip install -e .[ui]") from exc

    solver = SwarmOrchestrator(config)

    def backend_summary() -> str:
        model = config.model
        weight_path = model.weights_path or "not set"
        prompt_dir = str(config.resolved_prompt_dir())
        output_dir = str(config.resolved_output_dir())
        return (
            f"Endpoint: {model.endpoint}\n"
            f"Model: {model.model_name}\n"
            f"Weights source: {model.weights_source}\n"
            f"Weights path: {weight_path}\n"
            f"Prompts: {prompt_dir}\n"
            f"Output: {output_dir}"
        )

    def respond(message: str, history: list[tuple[str, str]]):
        result = solver.solve(message)
        assistant = (
            f"**Answer:** {result.final_answer}\n\n"
            f"**Votes:** {result.vote_counts}\n\n"
            f"**Judge used:** {result.used_judge}\n\n"
            f"**Judge notes:** {result.judge_notes or 'none'}\n\n"
            f"**Backend:**\n{backend_summary()}"
        )
        history = history + [(message, assistant)]
        return history, history

    ui_css = """
    .gradio-container {
        font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, sans-serif;
    }
    .app-header {
        border: 1px solid rgba(255,255,255,0.08);
        border-radius: 20px;
        padding: 18px 20px;
        background: linear-gradient(135deg, #0f172a 0%, #111827 45%, #1f2937 100%);
        color: white;
        margin-bottom: 16px;
    }
    .app-title { font-size: 28px; font-weight: 700; margin-bottom: 6px; }
    .app-subtitle { color: rgba(255,255,255,0.72); line-height: 1.4; }
    .status-card {
        border-radius: 16px;
        background: #0b1220;
        color: #dbeafe;
        padding: 14px 16px;
        border: 1px solid rgba(96,165,250,0.2);
        white-space: pre-wrap;
    }
    """

    with gr.Blocks() as demo:
        gr.Markdown(
            """
            <div class="app-header">
              <div class="app-title">Agentic Math Solver</div>
              <div class="app-subtitle">Chat web local, com múltiplos agentes, juiz de consenso e backend configurável por endpoint local.</div>
            </div>
            """
        )
        with gr.Row():
            with gr.Column(scale=3):
                chatbot = gr.Chatbot(label="Conversation", height=620, layout="bubble", buttons=["copy", "copy_all"])
                message = gr.Textbox(
                    label="Send a problem",
                    placeholder="Digite um problema de matemática aqui...",
                    lines=4,
                )
                with gr.Row():
                    send = gr.Button("Send", variant="primary")
                    clear = gr.Button("Clear")
            with gr.Column(scale=1):
                status = gr.Markdown(f"<div class='status-card'>{backend_summary()}</div>")

        state = gr.State([])

        def _submit(message_text: str, history: list[tuple[str, str]]):
            if not message_text.strip():
                return history, history, history
            new_history, state_history = respond(message_text.strip(), history or [])
            return "", new_history, state_history

        message.submit(_submit, inputs=[message, state], outputs=[message, chatbot, state])
        send.click(_submit, inputs=[message, state], outputs=[message, chatbot, state])
        clear.click(lambda: ([], []), outputs=[chatbot, state])

    launch_result = demo.launch(
        server_name="127.0.0.1",
        server_port=7860,
        share=False,
        inbrowser=True,
        prevent_thread_lock=True,
        theme=gr.themes.Soft(),
        css=ui_css,
    )
    url = getattr(launch_result, "url", "http://127.0.0.1:7860")
    print(f"Open the UI at: {url}")
    try:
        webbrowser.open(url)
    except Exception:
        pass
    threading.Event().wait()

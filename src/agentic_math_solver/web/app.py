from __future__ import annotations

from pathlib import Path
import os
import socket
import threading
import webbrowser

from flask import Flask, jsonify, render_template, request

from ..config import AppConfig
from ..orchestrator import SwarmOrchestrator


def _pick_available_port(host: str, preferred: int, search_width: int = 25) -> int:
    for candidate in range(preferred, preferred + search_width):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            if sock.connect_ex((host, candidate)) != 0:
                return candidate
    raise RuntimeError(
        f"No free TCP port found in range {preferred}-{preferred + search_width - 1}."
    )


def create_app(config: AppConfig) -> Flask:
    base_dir = Path(__file__).resolve().parent
    app = Flask(
        __name__,
        template_folder=str(base_dir / "templates"),
        static_folder=str(base_dir / "static"),
    )

    solver = SwarmOrchestrator(config)

    def backend_snapshot() -> dict[str, str]:
        model = config.model
        return {
            "backend": model.backend,
            "endpoint": model.endpoint,
            "model_name": model.model_name,
            "model_id": model.model_id,
            "device": model.device,
            "weights_source": model.weights_source,
            "weights_path": model.weights_path or "not set",
            "prompt_dir": str(config.resolved_prompt_dir()),
            "output_dir": str(config.resolved_output_dir()),
        }

    @app.get("/")
    def index():
        return render_template("index.html", backend=backend_snapshot())

    @app.get("/api/health")
    def health():
        ready = solver.client.healthcheck()
        return jsonify({"ok": True, "model_ready": ready, "backend": backend_snapshot()})

    @app.post("/api/chat")
    def chat():
        payload = request.get_json(silent=True) or {}
        message = str(payload.get("message", "")).strip()
        if not message:
            return jsonify({"ok": False, "error": "Mensagem vazia."}), 400

        try:
            result = solver.solve(message)
            return jsonify(
                {
                    "ok": True,
                    "answer": result.final_answer,
                    "used_judge": result.used_judge,
                    "vote_counts": result.vote_counts,
                    "judge_notes": result.judge_notes,
                    "backend": backend_snapshot(),
                }
            )
        except Exception as exc:
            return jsonify({"ok": False, "error": str(exc), "backend": backend_snapshot()}), 500

    return app


def launch_app(config: AppConfig) -> None:
    app = create_app(config)
    host = "127.0.0.1"
    preferred_port = int(os.getenv("AGEMATH_WEB_PORT", "7860"))
    port = _pick_available_port(host, preferred_port)
    if port != preferred_port:
        print(f"Port {preferred_port} is busy. Using {port} instead.")
    url = f"http://{host}:{port}"

    def open_browser() -> None:
        try:
            webbrowser.open(url)
        except Exception:
            pass

    threading.Timer(1.0, open_browser).start()
    print(f"Open the UI at: {url}")
    app.run(host=host, port=port, debug=False, use_reloader=False, threaded=True)

from __future__ import annotations

from pathlib import Path
import base64
import json
import os
import socket
import threading
import uuid
import webbrowser

from flask import Flask, Response, jsonify, render_template, request, send_file

from ..config import AppConfig
from ..list_parser import extract_text, llm_split_problems, split_into_problems
from ..orchestrator import SwarmOrchestrator
from ..pdf_report import SolvedProblem, build_solved_list_pdf


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
    list_jobs: dict[str, Path] = {}

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

    def apply_options(options: dict) -> None:
        if not options:
            return
        model_val = options.get("model")
        if model_val:
            solver.config.model.model_id = model_val
            solver.config.model.model_name = model_val
        thinking_val = options.get("thinking")
        if thinking_val == "fast":
            solver.config.agent_count = 1
            solver.config.use_judge = False
        elif thinking_val == "deep":
            solver.config.agent_count = 4
            solver.config.use_judge = True

    def ndjson(event_iterable) -> Response:
        def generate():
            try:
                for event in event_iterable():
                    yield json.dumps(event, ensure_ascii=False) + "\n"
            except Exception as exc:
                yield json.dumps({"type": "error", "message": str(exc)}, ensure_ascii=False) + "\n"

        return Response(generate(), mimetype="application/x-ndjson")

    def decode_upload(file_data: dict) -> bytes:
        raw_b64 = file_data.get("data", "")
        if "," in raw_b64:
            raw_b64 = raw_b64.split(",", 1)[1]
        return base64.b64decode(raw_b64)

    @app.get("/")
    def index():
        return render_template("index.html", backend=backend_snapshot())

    @app.get("/api/health")
    def health():
        ready = solver.client.healthcheck()
        return jsonify({"ok": True, "model_ready": ready, "backend": backend_snapshot()})

    @app.post("/api/chat/stream")
    def chat_stream():
        payload = request.get_json(silent=True) or {}
        message = str(payload.get("message", "")).strip()
        if not message:
            return jsonify({"ok": False, "error": "Mensagem vazia."}), 400

        files = payload.get("files", [])
        apply_options(payload.get("options", {}))

        from ..file_processor import process_uploaded_files

        file_context = process_uploaded_files(files, config.resolved_output_dir())
        full_message = (file_context + message) if file_context else message

        def events():
            for event in solver.solve_stream(full_message):
                if event["type"].startswith("_"):
                    continue
                yield event

        return ndjson(events)

    @app.post("/api/list/upload")
    def list_upload():
        payload = request.get_json(silent=True) or {}
        file_data = payload.get("file")
        if not file_data or not file_data.get("data"):
            return jsonify({"ok": False, "error": "Nenhum arquivo enviado."}), 400

        apply_options(payload.get("options", {}))

        name = file_data.get("name", "lista")
        raw_bytes = decode_upload(file_data)

        def events():
            try:
                text = extract_text(name, raw_bytes)
            except ValueError as exc:
                yield {"type": "error", "message": str(exc)}
                return

            problems_text = split_into_problems(text)
            if len(problems_text) < 2:
                problems_text = llm_split_problems(text, solver.client)

            if not problems_text or not text.strip():
                yield {"type": "error", "message": "Não foi possível extrair questões do arquivo enviado."}
                return

            yield {
                "type": "list_parsed",
                "count": len(problems_text),
                "previews": [p[:160] for p in problems_text],
            }

            solved: list[SolvedProblem] = []
            for idx, statement in enumerate(problems_text, start=1):
                agent_results = []
                final_info = None
                for event in solver.solve_stream(statement):
                    if event["type"] == "_agent_results":
                        agent_results = event["results"]
                        continue
                    if event["type"] == "final":
                        final_info = event
                    yield {**event, "problem_index": idx}

                if final_info is None:
                    continue

                solved.append(
                    SolvedProblem(
                        index=idx,
                        statement=statement,
                        final_answer=final_info["final_answer"],
                        educational_summary=final_info["educational_summary"],
                        used_judge=final_info["used_judge"],
                        vote_counts=final_info["vote_counts"],
                        agent_summaries=[(r.agent_name, r.persona, r.answer) for r in agent_results],
                    )
                )

            if not solved:
                yield {"type": "error", "message": "Nenhuma questão pôde ser resolvida."}
                return

            job_id = uuid.uuid4().hex
            output_dir = config.resolved_output_dir() / "lists"
            pdf_path = output_dir / f"{job_id}.pdf"
            build_solved_list_pdf(
                title=f"Lista Resolvida - {Path(name).stem}",
                problems=solved,
                output_path=pdf_path,
                model_name=config.model.model_name,
            )
            list_jobs[job_id] = pdf_path

            yield {"type": "pdf_ready", "url": f"/api/list/download/{job_id}", "filename": pdf_path.name}

        return ndjson(events)

    @app.get("/api/list/download/<job_id>")
    def list_download(job_id: str):
        path = list_jobs.get(job_id)
        if not path or not path.exists():
            return jsonify({"ok": False, "error": "PDF não encontrado ou expirado."}), 404
        return send_file(path, as_attachment=True, download_name="lista_resolvida.pdf")

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

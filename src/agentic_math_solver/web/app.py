from __future__ import annotations

from pathlib import Path
import base64
import json
import os
import socket
import threading
import time
import uuid
import webbrowser
from urllib import error as urllib_error, request as urllib_request

from flask import Flask, Response, jsonify, render_template, request, send_file

from ..config import AppConfig
from ..conversation_store import ConversationStore, InvalidConversationId
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
    conversations = ConversationStore(config.resolved_output_dir() / "conversations")
    # Estado pra calcular tokens/s: os contadores do vLLM (/metrics) são cumulativos
    # desde que o servidor subiu, então a taxa é a diferença entre duas leituras
    # dividida pelo tempo entre elas — guarda a última leitura pra comparar na próxima.
    metrics_state: dict[str, float | None] = {
        "prompt_tokens": None,
        "generation_tokens": None,
        "timestamp": None,
    }

    def backend_snapshot() -> dict[str, str]:
        model = config.model
        return {
            "backend": model.backend,
            "endpoint": model.endpoint,
            "model_name": model.model_name,
            "model_id": model.model_id,
            "device": model.device,
            "torch_dtype": model.torch_dtype,
            "weights_source": model.weights_source,
            "weights_path": model.weights_path or "not set",
            "temperature": model.temperature,
            "top_p": model.top_p,
            "top_k": model.top_k,
            "max_tokens": model.max_tokens,
            "timeout_seconds": model.timeout_seconds,
            "agent_count": config.agent_count,
            "use_judge": config.use_judge,
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
            # solver.client guarda sua própria cópia (model_name ou model_id, conforme
            # o backend) capturada uma vez no __init__ do orchestrator — mudar só o
            # `config` acima nunca chegava nela, então trocar o modelo pela UI não tinha
            # nenhum efeito na requisição real. Seta os dois; o client em uso só lê o
            # atributo que ele de fato tem, o outro fica sem uso (inofensivo).
            solver.client.model_name = model_val
            solver.client.model_id = model_val

        # temperature/top_p/top_k são lidos direto de solver.config.model a cada
        # chamada (não ficam presos num client construído uma vez, como model_name
        # ficava) — mudar aqui já vale pra próxima solicitação, sem gambiarra extra.
        temperature_raw = options.get("temperature")
        if temperature_raw not in (None, ""):
            try:
                solver.config.model.temperature = float(temperature_raw)
            except (TypeError, ValueError):
                pass

        if "top_p" in options:
            top_p_raw = options["top_p"]
            try:
                solver.config.model.top_p = float(top_p_raw) if top_p_raw not in (None, "") else None
            except (TypeError, ValueError):
                pass

        if "top_k" in options:
            top_k_raw = options["top_k"]
            try:
                solver.config.model.top_k = int(top_k_raw) if top_k_raw not in (None, "") else None
            except (TypeError, ValueError):
                pass

        thinking_val = options.get("thinking")
        if thinking_val == "fast":
            solver.config.agent_count = 1
            solver.config.use_judge = False
        elif thinking_val == "deep":
            solver.config.agent_count = 4
            solver.config.use_judge = True

    def fetch_vllm_metrics() -> dict[str, float]:
        """GETs the vLLM OpenAI-compatible server's Prometheus /metrics endpoint (same
        host:port as the API, no /v1 suffix) and parses it into a flat {name: value}
        dict. Only meaningful for the `remote` backend — vLLM is the one computing/
        exposing these; there's nothing equivalent for the in-process `cpu` backend."""
        base = config.model.endpoint.rsplit("/v1", 1)[0].rstrip("/")
        req = urllib_request.Request(f"{base}/metrics", method="GET")
        with urllib_request.urlopen(req, timeout=3) as resp:
            text = resp.read().decode("utf-8", errors="ignore")

        values: dict[str, float] = {}
        for line in text.splitlines():
            if not line or line.startswith("#"):
                continue
            name_and_labels, _, value = line.rpartition(" ")
            if not name_and_labels:
                continue
            name = name_and_labels.split("{", 1)[0].strip()
            try:
                values[name] = float(value)
            except ValueError:
                continue
        return values

    def compute_rate(previous: float | None, current: float | None, elapsed: float) -> float | None:
        if previous is None or current is None or elapsed <= 0:
            return None
        return max(0.0, (current - previous) / elapsed)

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

    @app.get("/api/backend/stats")
    def backend_stats():
        if config.model.backend.lower() not in {"remote"}:
            return jsonify({"ok": False, "error": "Estatísticas ao vivo só disponíveis com backend remote (vLLM)."}), 400

        try:
            metrics = fetch_vllm_metrics()
        except (urllib_error.URLError, OSError, TimeoutError) as exc:
            return jsonify({"ok": False, "error": f"Não foi possível ler métricas do vLLM: {exc}"}), 502

        now = time.time()
        prompt_tokens = metrics.get("vllm:prompt_tokens_total")
        generation_tokens = metrics.get("vllm:generation_tokens_total")
        elapsed = (now - metrics_state["timestamp"]) if metrics_state["timestamp"] is not None else 0.0

        stats = {
            "running_requests": metrics.get("vllm:num_requests_running"),
            "waiting_requests": metrics.get("vllm:num_requests_waiting"),
            "gpu_cache_usage_percent": metrics.get("vllm:gpu_cache_usage_perc"),
            "generation_tokens_per_sec": compute_rate(metrics_state["generation_tokens"], generation_tokens, elapsed),
            "prompt_tokens_per_sec": compute_rate(metrics_state["prompt_tokens"], prompt_tokens, elapsed),
        }

        metrics_state["prompt_tokens"] = prompt_tokens
        metrics_state["generation_tokens"] = generation_tokens
        metrics_state["timestamp"] = now

        return jsonify({"ok": True, "stats": stats})

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
                final_info = None
                for event in solver.solve_stream(statement):
                    if event["type"].startswith("_"):
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

    @app.get("/api/conversations")
    def list_conversations():
        return jsonify({"ok": True, "conversations": conversations.list()})

    @app.get("/api/conversations/<conv_id>")
    def get_conversation(conv_id: str):
        try:
            data = conversations.get(conv_id)
        except InvalidConversationId as exc:
            return jsonify({"ok": False, "error": str(exc)}), 400
        if data is None:
            return jsonify({"ok": False, "error": "Conversa não encontrada."}), 404
        return jsonify({"ok": True, "conversation": data})

    @app.put("/api/conversations/<conv_id>")
    def save_conversation(conv_id: str):
        payload = request.get_json(silent=True) or {}
        title = str(payload.get("title", "Nova Conversa"))
        messages = payload.get("messages", [])
        if not isinstance(messages, list):
            return jsonify({"ok": False, "error": "Formato de mensagens inválido."}), 400
        try:
            data = conversations.save(conv_id, title=title, messages=messages)
        except InvalidConversationId as exc:
            return jsonify({"ok": False, "error": str(exc)}), 400
        return jsonify({"ok": True, "conversation": data})

    @app.patch("/api/conversations/<conv_id>")
    def rename_conversation(conv_id: str):
        payload = request.get_json(silent=True) or {}
        title = str(payload.get("title", "")).strip()
        if not title:
            return jsonify({"ok": False, "error": "Título vazio."}), 400
        try:
            data = conversations.rename(conv_id, title)
        except InvalidConversationId as exc:
            return jsonify({"ok": False, "error": str(exc)}), 400
        if data is None:
            return jsonify({"ok": False, "error": "Conversa não encontrada."}), 404
        return jsonify({"ok": True, "conversation": data})

    @app.delete("/api/conversations/<conv_id>")
    def delete_conversation(conv_id: str):
        try:
            deleted = conversations.delete(conv_id)
        except InvalidConversationId as exc:
            return jsonify({"ok": False, "error": str(exc)}), 400
        if not deleted:
            return jsonify({"ok": False, "error": "Conversa não encontrada."}), 404
        return jsonify({"ok": True})

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

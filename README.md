# Agentic Math Solver

Local-first, modular scaffold for an experimental multi-agent math solver.

The original notebook was Kaggle-oriented and monolithic. This repository turns that idea into a project that is easier to evolve in the directions you requested:

- local machine execution instead of Kaggle-only paths
- modular prompt management in a dedicated `prompts/` directory
- separate orchestration, judge, client, and UI layers
- clean extension points for distributed GPUs, hardware acceleration, and a graphical chatbot interface

## What lives where

- `src/agentic_math_solver/` contains the Python package.
- `prompts/` contains editable prompt templates and agent personas.
- `README.md` documents the architecture and local workflow.
- `qwen3_5_multi_agent_4_with_judges.ipynb` is the legacy notebook and can now be treated as an archive/reference artifact.

## Architecture

The project is intentionally split into small layers:

1. `config.py` resolves local paths, model settings, and runtime options.
2. `prompts.py` loads prompt templates from disk.
3. `llm_client.py` talks to a local OpenAI-compatible endpoint.
4. `agents/` contains the worker agents and the judge logic.
5. `orchestrator.py` coordinates voting, arbitration, and trace collection.
6. `cli.py` provides a local command-line entry point.
7. `web/app.py` exposes a Flask backend and serves the web frontend.
8. `web/templates/`, `web/static/` contain the HTML, CSS, and JavaScript UI.

This separation matters if you later want to:

- fan agents out across multiple GPUs
- swap in a different inference backend
- add caching, batching, or hardware-specific kernels
- connect a browser-based chat UI or desktop UI without rewriting the solver core

## Local setup

Create a virtual environment and install the package in editable mode:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .
```

The editable install pulls in Flask, which is required for the web UI.

## Configure the local model endpoint

The default client expects an OpenAI-compatible HTTP endpoint, which is the cleanest way to run locally with a self-hosted model server.

Environment variables:

- `AGEMATH_MODEL_BACKEND` - `remote` for an OpenAI-compatible server or `cpu` for a local Transformers model on CPU
- `AGEMATH_MODEL_ENDPOINT` - base URL, for example `http://127.0.0.1:8000/v1`
- `AGEMATH_MODEL_NAME` - model name exposed by the server
- `AGEMATH_MODEL_ID` - Hugging Face model id or local path used when `AGEMATH_MODEL_BACKEND=cpu`
- `AGEMATH_MODEL_DEVICE` - device for the CPU backend, usually `cpu`
- `AGEMATH_MODEL_TORCH_DTYPE` - torch dtype for the CPU backend, usually `float32`
- `AGEMATH_MODEL_WEIGHTS_SOURCE` - human-readable origin of the weights, for example `local checkpoint` or `Hugging Face cache`
- `AGEMATH_MODEL_WEIGHTS_PATH` - optional filesystem path to the checkpoint folder if you run your own server
- `AGEMATH_API_KEY` - optional, defaults to `EMPTY`
- `AGEMATH_PROMPT_DIR` - override the prompt directory if needed
- `AGEMATH_OUTPUT_DIR` - where traces and artifacts are written

Example:

```bash
export AGEMATH_MODEL_ENDPOINT=http://127.0.0.1:8000/v1
export AGEMATH_MODEL_NAME=qwen3.5-local
```

For a tiny CPU model, switch the backend and install the extra:

```bash
pip install -e .[cpu]
export AGEMATH_MODEL_BACKEND=cpu
export AGEMATH_MODEL_ID=sshleifer/tiny-gpt2
export AGEMATH_MODEL_DEVICE=cpu
export AGEMATH_MODEL_TORCH_DTYPE=float32
```

If you want a slightly more capable but still small CPU model, try `distilgpt2` or `TinyLlama/TinyLlama-1.1B-Chat-v1.0`. For a smoke test, `sshleifer/tiny-gpt2` is the lightest option.
The current default CPU preset uses `Qwen/Qwen2.5-0.5B-Instruct`, which is a better fit for instruction-following on CPU than tiny GPT-2.

## Run locally

Solve a single problem from the command line:

```bash
python -m agentic_math_solver solve --problem "Find the sum of the first 10 positive integers."
```

Or read the problem from a file:

```bash
python -m agentic_math_solver solve --problem-file examples/problem.txt
```

Launch the graphical chatbot interface:

```bash
python -m agentic_math_solver serve
```

The web UI behaves like a lightweight ChatGPT-style workspace: chat history on the left, backend status on the right, and local-only model routing.

It is powered by a Flask backend plus a single-page frontend built with plain HTML, CSS, and JavaScript.

## Where the weights come from

This project does not embed model weights in the repository. The application calls a local OpenAI-compatible server, and that server is responsible for loading the checkpoint from a path or cache that you configure.

By default, the code assumes:

- the weights are stored locally on disk or in the runtime cache of your inference server
- the app connects to that server through `AGEMATH_MODEL_ENDPOINT`

If `AGEMATH_MODEL_BACKEND=cpu`, the app loads the checkpoint directly with `transformers` on the local machine instead of calling a remote server.

If you want the app to document the checkpoint source clearly, set:

```bash
export AGEMATH_MODEL_WEIGHTS_SOURCE="local checkpoint"
export AGEMATH_MODEL_WEIGHTS_PATH="/models/qwen3.5-27b-fp8"
```

In the original Kaggle notebook, the weights were referenced from a Kaggle-mounted path under `/kaggle/input/...`; the new local project deliberately removes that hard dependency.

## Web UI files

- `src/agentic_math_solver/web/app.py` contains the Flask application and the `/api/chat` endpoint.
- `src/agentic_math_solver/web/templates/index.html` defines the page structure.
- `src/agentic_math_solver/web/static/styles.css` defines the visual design.
- `src/agentic_math_solver/web/static/app.js` handles chat interactions in the browser.

## Prompt workflow

Prompts are regular text files, which makes them easy to version, diff, and tune independently of code.

Recommended files:

- `prompts/system.md`
- `prompts/formalist.md`
- `prompts/architect.md`
- `prompts/sentinel.md`
- `prompts/oracle.md`
- `prompts/judge.md`
- `prompts/summary.md`

You can edit those files without touching the orchestration code.

## Distributed and hardware-acceleration roadmap

The code is already separated so the following upgrades can be added incrementally:

- multi-GPU scheduling for one agent per device
- micro-batching across agent calls
- a distributed queue for candidate generation and verification
- backend adapters for TensorRT-LLM, vLLM, SGLang, llama.cpp, or custom kernels
- cached tool execution for repeated symbolic checks
- an async event loop for parallel UI and solver execution

The main rule is to keep these concerns behind adapter interfaces rather than mixing them into prompts or UI code.

## Notebook status

The notebook in the repository still captures the original experiment. The new project layout is the recommended path for future development, because it keeps the solver portable, local-first, and easier to evolve.

## Next steps

1. Point the client at your local inference server.
2. Replace the starter prompts with your preferred solver style.
3. Extend the UI or add a distributed execution backend.

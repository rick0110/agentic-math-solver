# Agentic Math Solver

The Agentic Math Solver is a multi-agent system designed to solve from simple to complex math problems. It was developed to help students solving problems in several levels of difficulty. The main proposal of this project is build an agentic system that run locally. Firstly, it only supports *CUDA* devices, but it will be extended to support CPU integrated devices. A future version of this software will be a mobile application to run in the integrated GPU of mobile devices (but it is importanto to highlight that the application will be heavyweight to run locally in mobile devices - so if we get any success in getting a partnership with a cloud provider, we will provide a cloud version of the application to run in mobile devices).

## Motivation of the project
This project was started with the *AIMO 3* competition, which required the development of an AI based solution to solve olimpic math problems. Despite industrial models reached at incredible results in math problem solving, they usually require massive computational resousces to run. In contrast, open source models are relatively lightweight and have good performance in language modeling. In addition, these models are usually fine-tuned to perform well in instruction following tasks and achieve very good results in math knowledge. The remaining problem is that these models frequently hallucinate. To resolve this problem, we developed a multi-agent system with tool integrated reasoning and self supervision to solve math problems rigorously. This approach achieve a score of 35 question in high difficulty olympic math problems in the *AIMO 3* competition, which is a very good result for a local solution. 

## Key Features

- **Agentic Structures & Tools**: Agents have access to Python execution, Web Search (`duckduckgo-search`), and MCP (Model Context Protocol) integration to rigorously solve problems step-by-step.
- **Live Multi-Agent Streaming**: The swarm (Formalist, Architect, Sentinel, Oracle) and the Judge stream their reasoning token-by-token to the browser over NDJSON, rendered as live-updating cards so you can watch each persona think in real time instead of waiting for a single final response.
- **Problem-List Solver → PDF**: Upload a full exercise list (digital PDF, scanned/photographed PDF, or a plain image) and the app splits it into individual questions, solves each one live with the full swarm, and generates a formatted, downloadable PDF with every statement, the agents' votes, and a step-by-step solution. Scanned pages are OCR'd on the GPU with `easyocr`; digital PDFs are parsed with `pypdf`/`pymupdf`.
- **Persistent Chat History**: Conversations are saved server-side (one JSON file per chat under `outputs/conversations/`), so history survives clearing the browser. The sidebar supports searching, renaming, and deleting conversations.
- **LaTeX-Safe Markdown Rendering**: Responses are rendered with `marked.js` + MathJax, with math segments (`$...$`, `$$...$$`, `\(...\)`, `\[...\]`) shielded from Markdown mangling so formulas always render correctly.
- **Local-First Inference**: Connects to any local OpenAI-compatible endpoint (like vLLM or Ollama) to run local models on your GPU — from small 1.5B models for fast iteration up to quantized 7B+ math-specialized models — with a fallback CPU Transformers implementation.
- **Judge-Based Arbitration**: Employs multiple persona-driven agents and a Judge agent that evaluates and arbitrates final answers if consensus is not reached. Note that the Judge is itself model-driven and can side with the wrong answer on hard problems — treat a "non-unanimous consensus" badge as a signal to double-check, not a guarantee.

## Repository Structure

```
agentic-math-solver/
├── README.md                  # This file
├── pyproject.toml             # Package configuration and dependencies
├── prompts/                   # Editable system prompts and personas
└── src/
    └── agentic_math_solver/
        ├── agents/             # Agent definitions (SwarmAgent, JudgeAgent)
        ├── web/                # Flask UI backend and frontend assets (templates, static)
        ├── config.py           # Configuration and environment variables
        ├── llm_client.py       # Client integrations (OpenAI compatible, Local CPU), streaming chat
        ├── orchestrator.py     # Multi-agent orchestration, streaming events, judge routing
        ├── tools.py            # Tool registry (Python, Web Search, MCP)
        ├── list_parser.py      # PDF/image text extraction (+ OCR) and question splitting
        ├── pdf_report.py       # Solved-list PDF generation (reportlab)
        ├── conversation_store.py  # Server-side chat persistence (JSON files)
        ├── file_processor.py   # Ad-hoc file attachments in chat
        └── ...
```

## Setup Instructions

1. **Environment Setup**:
   Create a virtual environment and install the package along with its dependencies:
   ```bash
   python -m venv .venv
   source .venv/bin/activate
   pip install -e .
   ```
   This installs Flask, duckduckgo-search, mcp, `reportlab`/`pypdf`/`pymupdf` (PDF list solver), `easyocr` (GPU-accelerated OCR for scanned lists), and other core requirements.

2. **Model Endpoint Configuration**:
   Run an OpenAI-compatible server (vLLM or Ollama) on your local GPU, then point the app at it:
   ```bash
   export AGEMATH_MODEL_BACKEND=remote
   export AGEMATH_MODEL_ENDPOINT=http://127.0.0.1:8000/v1
   export AGEMATH_MODEL_NAME=your-local-model
   ```

   Example: serving a small model with vLLM for fast iteration:
   ```bash
   vllm serve Qwen/Qwen2.5-Math-1.5B-Instruct --port 8000 --max-model-len 4096
   ```

   Example: serving a heavier, math-specialized 7B model quantized to 4-bit with `bitsandbytes` so it fits on a 16GB GPU alongside the swarm's concurrent requests (`pip install bitsandbytes` first):
   ```bash
   vllm serve Qwen/Qwen2.5-Math-7B-Instruct --port 8000 \
     --max-model-len 4096 --gpu-memory-utilization 0.85 \
     --quantization bitsandbytes --load-format bitsandbytes
   ```
   Notes from testing on an RTX 4080: `--max-model-len` cannot exceed the model's own `max_position_embeddings` (4096 for Qwen2.5-Math-7B-Instruct); on some environments `flashinfer`'s JIT-compiled sampler fails to build against the local CUDA toolchain, in which case set `VLLM_USE_FLASHINFER_SAMPLER=0` before `vllm serve` to fall back to the native PyTorch sampler.

   *(Optional)* If you want to use the local CPU fallback (not recommended for complex discursive reasoning):
   ```bash
   pip install -e .[cpu]
   export AGEMATH_MODEL_BACKEND=cpu
   export AGEMATH_MODEL_ID=Qwen/Qwen2.5-0.5B-Instruct
   ```

3. **Useful environment variables** (see `config.py` for the full list):

   | Variable | Purpose | Default |
   | --- | --- | --- |
   | `AGEMATH_MODEL_BACKEND` | `remote` (OpenAI-compatible server) or `cpu` (local Transformers) | `remote` |
   | `AGEMATH_MODEL_ENDPOINT` | Base URL of the OpenAI-compatible server | `http://127.0.0.1:8000/v1` |
   | `AGEMATH_MODEL_NAME` | Model name to request from the endpoint | `local-model` |
   | `AGEMATH_MAX_TOKENS` | Max tokens per agent generation | `2048` |
   | `AGEMATH_TIMEOUT_SECONDS` | HTTP timeout per request to the model server | `120` |
   | `AGEMATH_AGENT_COUNT` | Number of swarm agents (1-4) | `4` (remote) / `1` (cpu) |
   | `AGEMATH_WEB_PORT` | Port for the web UI | `7860` |
   | `AGEMATH_OUTPUT_DIR` | Where conversations, solved-list PDFs, and uploads are stored | `./outputs` |

## Usage

### Web Interface
Launch the graphical chatbot interface:
```bash
python -m agentic_math_solver serve
```
The interface will be available at `http://127.0.0.1:7860`. The UI provides a ChatGPT-style layout with:
- Live status of your local backend, plus a searchable, renameable chat history persisted to disk.
- Real-time cards for each agent (and the Judge, when invoked) streaming their reasoning as it's generated.
- A "Resolver Lista (PDF)" action in the `+` menu: upload an exercise list and get back each question solved live, followed by a downloadable PDF with the full solutions.

### Command Line
Solve a problem directly from the command line:
```bash
python -m agentic_math_solver solve --problem "If x^2 + 5x + 6 = 0, find the roots using the quadratic formula."
```

## Agentic Capabilities

When agents tackle discursive problems, they are prompted to provide a step-by-step rigorous solution and can autonomously emit tool calls.
Supported tools:
- **`python`**: Executes local Python code to perform numerical checks, symbolic manipulation (via `sympy`), or simulations.
- **`search`**: Uses DuckDuckGo to look up math theorems or constants.
- **`mcp`**: Hooks into the Model Context Protocol for semantic context retrieval.

The orchestrator manages up to 5 loop iterations per agent to receive and inject tool outputs before extracting the final `\boxed{answer}`. All agent, tool, judge, and summary events are streamed as they happen (see `SwarmOrchestrator.solve_stream` in `orchestrator.py`), with `solve()` provided as a blocking wrapper for the CLI and other non-streaming callers.

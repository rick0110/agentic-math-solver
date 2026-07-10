# Agentic Math Solver

A modular, local-first multi-agent math solver equipped with tool-calling capabilities (ReAct-style reasoning) and a premium, responsive graphical interface. This project was evolved from an experimental monolithic notebook into a production-ready scaffold for discursive mathematical problem solving.

## Key Features

- **Agentic Structures & Tools**: Agents have access to Python execution, Web Search (`duckduckgo-search`), and MCP (Model Context Protocol) integration to rigorously solve problems step-by-step.
- **Advanced Graphical Interface**: A modern, dark-themed, glassmorphic UI built with plain HTML/CSS/JS, served via a Flask backend. It supports auto-resizing text areas, Markdown parsing, and visual feedback for agent states.
- **Local-First Inference**: Connects to any local OpenAI-compatible endpoint (like vLLM, Ollama) to run lightweight 7-14B models on local GPUs, with a fallback CPU Transformers implementation.
- **Judge-Based Arbitration**: Employs multiple persona-driven agents (Architect, Formalist, Sentinel, Oracle) and a Judge agent that evaluates and arbitrates final answers if consensus is not reached.

## Repository Structure

```
agentic-math-solver/
├── README.md               # This file
├── pyproject.toml          # Package configuration and dependencies
├── prompts/                # Editable system prompts and personas
└── src/
    └── agentic_math_solver/
        ├── agents/         # Agent definitions (SwarmAgent, JudgeAgent)
        ├── web/            # Flask UI backend and frontend assets (templates, static)
        ├── config.py       # Configuration and environment variables
        ├── llm_client.py   # Client integrations (OpenAI compatible, Local CPU)
        ├── orchestrator.py # Multi-agent orchestration and judge routing
        ├── tools.py        # Tool registry (Python, Web Search, MCP)
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
   This will install Flask, duckduckgo-search, mcp, and other requirements.

2. **Model Endpoint Configuration**:
   To test with local 7-14B models (e.g. Qwen2.5-7B, Llama-3-8B), we recommend running an OpenAI-compatible server (like vLLM or Ollama) on your local GPU.

   Configure the environment variables to point to your endpoint:
   ```bash
   export AGEMATH_MODEL_BACKEND=remote
   export AGEMATH_MODEL_ENDPOINT=http://127.0.0.1:8000/v1
   export AGEMATH_MODEL_NAME=your-local-model
   ```

   *(Optional)* If you want to use the local CPU fallback (not recommended for complex discursive reasoning):
   ```bash
   pip install -e .[cpu]
   export AGEMATH_MODEL_BACKEND=cpu
   export AGEMATH_MODEL_ID=Qwen/Qwen2.5-0.5B-Instruct
   ```

## Usage

### Web Interface
Launch the graphical chatbot interface:
```bash
python -m agentic_math_solver serve
```
The interface will be available at `http://127.0.0.1:7860`. The premium UI provides a ChatGPT-style layout with live status of your local backend, tool execution traces, and agent arbitration results.

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

The orchestrator manages up to 5 loop iterations per agent to receive and inject tool outputs before extracting the final `\boxed{answer}`.

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import os


@dataclass(slots=True)
class ModelConfig:
    backend: str = "remote"
    endpoint: str = "http://127.0.0.1:8000/v1"
    model_name: str = "local-model"
    model_id: str = "Qwen/Qwen2.5-0.5B-Instruct"
    device: str = "cpu"
    torch_dtype: str = "float32"
    weights_source: str = "local model server"
    weights_path: str = ""
    api_key: str = "EMPTY"
    temperature: float = 0.2
    top_p: float | None = None
    top_k: int | None = None
    repetition_penalty: float | None = 1.15
    max_tokens: int = 2048
    timeout_seconds: int = 120


@dataclass(slots=True)
class AppConfig:
    root_dir: Path = field(default_factory=lambda: Path(__file__).resolve().parents[2])
    prompt_dir: Path | None = None
    output_dir: Path | None = None
    model: ModelConfig = field(default_factory=ModelConfig)
    agent_count: int = 4
    use_judge: bool = True
    # Por padrão o Judge só roda quando os agentes discordam (mais barato). Ligar isso faz
    # o Judge verificar SEMPRE, mesmo com consenso 4/4 — útil porque as 4 personas são o
    # mesmo modelo com prompts diferentes, então podem compartilhar o mesmo erro sistemático
    # e "concordar" no valor errado sem que a votação por maioria perceba.
    judge_always_verify: bool = False

    @classmethod
    def from_env(cls) -> "AppConfig":
        root_dir = Path(__file__).resolve().parents[2]
        prompt_dir = Path(os.getenv("AGEMATH_PROMPT_DIR", root_dir / "prompts"))
        output_dir = Path(os.getenv("AGEMATH_OUTPUT_DIR", root_dir / "outputs"))
        model = ModelConfig(
            backend=os.getenv("AGEMATH_MODEL_BACKEND", "remote"),
            endpoint=os.getenv("AGEMATH_MODEL_ENDPOINT", "http://127.0.0.1:8000/v1"),
            model_name=os.getenv("AGEMATH_MODEL_NAME", "local-model"),
            model_id=os.getenv("AGEMATH_MODEL_ID", "Qwen/Qwen2.5-0.5B-Instruct"),
            device=os.getenv("AGEMATH_MODEL_DEVICE", "cpu"),
            torch_dtype=os.getenv("AGEMATH_MODEL_TORCH_DTYPE", "float32"),
            weights_source=os.getenv("AGEMATH_MODEL_WEIGHTS_SOURCE", "local model server"),
            weights_path=os.getenv("AGEMATH_MODEL_WEIGHTS_PATH", ""),
            api_key=os.getenv("AGEMATH_API_KEY", "EMPTY"),
            temperature=float(os.getenv("AGEMATH_TEMPERATURE", "0.2")),
            top_p=(float(os.getenv("AGEMATH_TOP_P")) if os.getenv("AGEMATH_TOP_P") else None),
            top_k=(int(os.getenv("AGEMATH_TOP_K")) if os.getenv("AGEMATH_TOP_K") else None),
            repetition_penalty=(
                float(os.getenv("AGEMATH_REPETITION_PENALTY"))
                if os.getenv("AGEMATH_REPETITION_PENALTY")
                else 1.15
            ),
            max_tokens=int(os.getenv("AGEMATH_MAX_TOKENS", "2048")),
            timeout_seconds=int(os.getenv("AGEMATH_TIMEOUT_SECONDS", "120")),
        )
        agent_count = int(os.getenv("AGEMATH_AGENT_COUNT", "1" if model.backend.lower() in {"cpu", "local_cpu", "transformers"} else "4"))
        judge_always_verify = os.getenv("AGEMATH_JUDGE_ALWAYS_VERIFY", "0").lower() in {"1", "true", "yes"}
        return cls(
            root_dir=root_dir,
            prompt_dir=prompt_dir,
            output_dir=output_dir,
            model=model,
            agent_count=agent_count,
            judge_always_verify=judge_always_verify,
        )

    def resolved_prompt_dir(self) -> Path:
        return self.prompt_dir or self.root_dir / "prompts"

    def resolved_output_dir(self) -> Path:
        return self.output_dir or self.root_dir / "outputs"

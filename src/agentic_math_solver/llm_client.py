from __future__ import annotations

from dataclasses import dataclass
import json
import re
import threading
from typing import Any
from urllib import error, request


@dataclass(slots=True)
class ChatMessage:
    role: str
    content: str


class OpenAICompatibleClient:
    def __init__(self, endpoint: str, model_name: str, api_key: str = "EMPTY", timeout_seconds: int = 120):
        self.endpoint = endpoint.rstrip("/")
        self.model_name = model_name
        self.api_key = api_key
        self.timeout_seconds = timeout_seconds

    def chat(self, messages: list[dict[str, str]], *, temperature: float = 0.2, max_tokens: int = 2048) -> str:
        payload: dict[str, Any] = {
            "model": self.model_name,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        data = json.dumps(payload).encode("utf-8")
        req = request.Request(
            f"{self.endpoint}/chat/completions",
            data=data,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            },
            method="POST",
        )
        with request.urlopen(req, timeout=self.timeout_seconds) as resp:
            body = json.loads(resp.read().decode("utf-8"))
        choices = body.get("choices", [])
        if not choices:
            return ""
        message = choices[0].get("message", {})
        return message.get("content", "") or ""

    def healthcheck(self) -> bool:
        req = request.Request(f"{self.endpoint}/models", method="GET")
        try:
            with request.urlopen(req, timeout=self.timeout_seconds) as resp:
                return resp.status == 200
        except error.URLError:
            return False


class LocalCpuTransformersClient:
    def __init__(self, model_id: str, device: str = "cpu", torch_dtype: str = "float32", max_new_tokens: int = 256):
        self.model_id = model_id
        self.device = device
        self.torch_dtype = torch_dtype
        self.max_new_tokens = max_new_tokens
        self._tokenizer = None
        self._model = None
        self._load_lock = threading.Lock()

    def _load(self) -> None:
        if self._tokenizer is not None and self._model is not None:
            return
        with self._load_lock:
            if self._tokenizer is not None and self._model is not None:
                return

            try:
                import torch
                from transformers.models.auto import AutoModelForCausalLM, AutoTokenizer
            except ModuleNotFoundError as exc:
                raise RuntimeError(
                    "CPU backend requires 'transformers' and 'torch'. Install with: pip install -e .[cpu]"
                ) from exc

            dtype = getattr(torch, self.torch_dtype, torch.float32)
            tokenizer = AutoTokenizer.from_pretrained(self.model_id, use_fast=True)
            model = AutoModelForCausalLM.from_pretrained(self.model_id, torch_dtype=dtype, low_cpu_mem_usage=True)
            model.to(self.device)
            model.eval()

            self._tokenizer = tokenizer
            self._model = model

    def _max_context_tokens(self) -> int:
        assert self._model is not None
        config = getattr(self._model, "config", None)
        for attr in ("max_position_embeddings", "n_positions", "seq_length"):
            value = getattr(config, attr, None)
            if isinstance(value, int) and value > 0:
                return value
        return 512

    def _build_prompt(self, messages: list[dict[str, str]]) -> str:
        chunks: list[str] = []
        for message in messages:
            role = message.get("role", "user")
            content = (message.get("content", "") or "").strip()
            if not content:
                continue
            chunks.append(f"{role.title()}: {content}")
        chunks.append("Assistant:")
        return "\n".join(chunks)

    def _build_inputs(self, messages: list[dict[str, str]], max_input_tokens: int):
        assert self._tokenizer is not None
        if hasattr(self._tokenizer, "apply_chat_template"):
            try:
                rendered = self._tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
                return self._tokenizer(rendered, return_tensors="pt", truncation=True, max_length=max_input_tokens)
            except Exception:
                pass
        prompt = self._build_prompt(messages)
        return self._tokenizer(prompt, return_tensors="pt", truncation=True, max_length=max_input_tokens)

    def chat(self, messages: list[dict[str, str]], *, temperature: float = 0.0, max_tokens: int = 256) -> str:
        self._load()
        assert self._tokenizer is not None and self._model is not None

        try:
            import torch
        except ModuleNotFoundError as exc:
            raise RuntimeError("CPU backend requires 'torch'. Install with: pip install -e .[cpu]") from exc

        max_context_tokens = self._max_context_tokens()
        generation_tokens = max(1, min(max_tokens or self.max_new_tokens, max(16, max_context_tokens // 8)))
        max_input_tokens = max(1, max_context_tokens - generation_tokens - 1)
        inputs = self._build_inputs(messages, max_input_tokens)
        inputs = {key: value.to(self.device) for key, value in inputs.items()}

        with torch.no_grad():
            output_ids = self._model.generate(
                **inputs,
                do_sample=False,
                max_new_tokens=generation_tokens,
                pad_token_id=self._tokenizer.eos_token_id,
            )

        generated = self._tokenizer.decode(output_ids[0], skip_special_tokens=True)
        rendered_prompt = None
        if hasattr(self._tokenizer, "apply_chat_template"):
            try:
                rendered_prompt = self._tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
            except Exception:
                rendered_prompt = None
        if rendered_prompt and generated.startswith(rendered_prompt):
            generated = generated[len(rendered_prompt):]
        generated = generated.strip()
        generated = re.sub(r"^Assistant:\s*", "", generated)
        return generated

    def healthcheck(self) -> bool:
        try:
            self._load()
            return True
        except Exception:
            return False

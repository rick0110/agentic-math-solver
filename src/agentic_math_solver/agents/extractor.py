from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any

from ..llm_client import OpenAICompatibleClient
from ..prompts import PromptLibrary
from ..utils import extract_answer, normalize_answer, truncate_preserving_ends

# Só 1 candidato por chamada aqui (vs. até 4 no Juiz), então o orçamento pode ser mais
# generoso — mas um único raw_response já pode sozinho passar do contexto do modelo se o
# agente usou os 5 passos de tool call, então ainda precisa truncar. Ver judge.py.
_MAX_RAW_RESPONSE_CHARS = 3000


@dataclass(slots=True)
class ExtractorAgent:
    """Fallback used only when an agent's raw response has no \\boxed{} answer.

    Small models are unreliable at self-enforcing output syntax, so a raw regex miss
    could mean either "this is genuinely a proof with no short final value" or "the
    model reached an answer but forgot to format it". This runs as a cheap, focused
    second opinion instead of trusting the regex miss either way.
    """

    def extract_stream(
        self,
        problem: str,
        raw_response: str,
        client: OpenAICompatibleClient,
        prompts: PromptLibrary,
        *,
        max_tokens: int,
        temperature: float = 0.0,
    ) -> Iterator[dict[str, Any]]:
        system_prompt = prompts.load("extractor")
        truncated_response = truncate_preserving_ends(raw_response, _MAX_RAW_RESPONSE_CHARS)
        user_prompt = f"Problem:\n{problem}\n\nAgent's raw response:\n{truncated_response}"

        yield {"type": "extractor_start"}

        text = ""
        for piece in client.chat_stream(
            [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=temperature,
            max_tokens=max_tokens,
        ):
            text += piece
            yield {"type": "extractor_token", "delta": piece}

        boxed = extract_answer(text)
        if boxed is not None:
            yield {"type": "extractor_done", "kind": "boxed", "answer": normalize_answer(boxed), "text": text.strip()}
        else:
            yield {"type": "extractor_done", "kind": "derivation", "answer": None, "text": text.strip()}

    def extract(
        self,
        problem: str,
        raw_response: str,
        client: OpenAICompatibleClient,
        prompts: PromptLibrary,
        *,
        max_tokens: int,
        temperature: float = 0.0,
    ) -> tuple[str, str | None, str]:
        """Returns (kind, answer, text) where kind is "boxed" or "derivation"."""
        final_event: dict[str, Any] | None = None
        for event in self.extract_stream(problem, raw_response, client, prompts, max_tokens=max_tokens, temperature=temperature):
            if event["type"] == "extractor_done":
                final_event = event
        assert final_event is not None
        return final_event["kind"], final_event["answer"], final_event["text"]
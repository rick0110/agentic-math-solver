from __future__ import annotations

from dataclasses import dataclass

from ..llm_client import OpenAICompatibleClient
from ..prompts import PromptLibrary
from ..types import AgentResult
from ..utils import extract_answer, normalize_answer


@dataclass(slots=True)
class SwarmAgent:
    agent_name: str
    persona_key: str

    def run(self, problem: str, client: OpenAICompatibleClient, prompts: PromptLibrary, *, max_tokens: int, temperature: float) -> AgentResult:
        system_prompt = prompts.load("system")
        persona_prompt = prompts.load(self.persona_key)
        summary_prompt = prompts.load("summary") if prompts.exists("summary") else ""
        user_prompt = (
            f"Problem:\n{problem}\n\n"
            f"Use the persona below and answer with a single final integer if possible.\n\n"
            f"Persona:\n{persona_prompt}\n\n"
            f"Short summary format to keep in mind:\n{summary_prompt}"
        )
        raw_response = client.chat(
            [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=temperature,
            max_tokens=max_tokens,
        )
        answer = extract_answer(raw_response)
        if answer is not None:
            answer = normalize_answer(answer)
        return AgentResult(
            agent_name=self.agent_name,
            persona=self.persona_key,
            answer=answer,
            raw_response=raw_response,
            summary=raw_response[:500],
        )

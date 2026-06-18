from __future__ import annotations

from dataclasses import dataclass

from ..llm_client import OpenAICompatibleClient
from ..prompts import PromptLibrary
from ..types import AgentResult
from ..utils import extract_answer, normalize_answer


@dataclass(slots=True)
class JudgeAgent:
    def decide(
        self,
        problem: str,
        candidate_results: list[AgentResult],
        client: OpenAICompatibleClient,
        prompts: PromptLibrary,
        *,
        max_tokens: int,
        temperature: float,
    ) -> tuple[int | None, str]:
        judge_prompt = prompts.load("judge")
        summary_lines = []
        for result in candidate_results:
            summary_lines.append(
                f"Agent: {result.agent_name}\n"
                f"Persona: {result.persona}\n"
                f"Answer: {result.answer}\n"
                f"Summary: {result.summary}"
            )
        user_prompt = (
            f"Problem:\n{problem}\n\n"
            f"Candidate answers:\n" + "\n\n".join(summary_lines)
        )
        raw_response = client.chat(
            [
                {"role": "system", "content": judge_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=temperature,
            max_tokens=max_tokens,
        )
        answer = extract_answer(raw_response)
        if answer is not None:
            answer = normalize_answer(answer)
        return answer, raw_response

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any

from ..llm_client import OpenAICompatibleClient
from ..prompts import PromptLibrary
from ..types import AgentResult
from ..utils import extract_answer, normalize_answer


@dataclass(slots=True)
class JudgeAgent:
    def decide_stream(
        self,
        problem: str,
        candidate_results: list[AgentResult],
        client: OpenAICompatibleClient,
        prompts: PromptLibrary,
        *,
        max_tokens: int,
        temperature: float,
    ) -> Iterator[dict[str, Any]]:
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

        yield {"type": "judge_start"}

        raw_response = ""
        for piece in client.chat_stream(
            [
                {"role": "system", "content": judge_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=temperature,
            max_tokens=max_tokens,
        ):
            raw_response += piece
            yield {"type": "judge_token", "delta": piece}

        answer = extract_answer(raw_response)
        if answer is not None:
            answer = normalize_answer(answer)

        yield {"type": "judge_done", "answer": answer, "notes": raw_response}

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
        final_event: dict[str, Any] | None = None
        for event in self.decide_stream(problem, candidate_results, client, prompts, max_tokens=max_tokens, temperature=temperature):
            if event["type"] == "judge_done":
                final_event = event
        assert final_event is not None
        return final_event["answer"], final_event["notes"]

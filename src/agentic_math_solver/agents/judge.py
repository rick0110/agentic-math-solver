from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any

from ..llm_client import OpenAICompatibleClient
from ..prompts import PromptLibrary
from ..types import AgentResult
from ..utils import extract_answer, normalize_answer, render_journal, truncate_preserving_ends

# Orçamento conservador de caracteres por candidato no prompt do Juiz. O modelo tem um
# teto de contexto fixo (ex.: 4096 tokens no Qwen2.5-Math-7B-Instruct — não dá pra só
# aumentar --max-model-len, é max_position_embeddings do próprio modelo), e a resposta
# do Juiz já reserva `max_tokens` desse total. Sem truncar, o raw_response de um agente
# sozinho (até 5 passos de tool call, cada um podendo chegar a max_tokens) já pode passar
# do contexto inteiro — somando 4 agentes, o request estoura de longe e o servidor derruba
# com 400 Bad Request. Ajuste esse valor se mudar de modelo/--max-model-len.
_MAX_CANDIDATE_CHARS = 1200


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
        top_p: float | None = None,
        top_k: int | None = None,
    ) -> Iterator[dict[str, Any]]:
        judge_prompt = prompts.load("judge")
        summary_lines = []
        for index, result in enumerate(candidate_results):
            
            label = chr(ord("A") + index)
            boxed = result.answer or "none — see full derivation below"
            reasoning = truncate_preserving_ends(result.raw_response, _MAX_CANDIDATE_CHARS)
            journal = result.journal or {}
            has_journal = any(journal.get(key) for key in ("proven_lemmas", "dead_ends", "current_hypothesis"))
            journal_text = render_journal(journal) if has_journal else "(agent did not use tools — no journal)"
            summary_lines.append(
                f"Candidate {label}\n"
                f"Persona: {result.persona}\n"
                f"Boxed answer: {boxed}\n"
                f"{journal_text}\n\n"
                f"Full reasoning:\n{reasoning}"
            )
        user_prompt = (
            f"Problem:\n{problem}\n\n"
            f"Candidate answers:\n" + "\n\n".join(summary_lines)
        )

        yield {"type": "judge_start"}

        system_message = {"role": "system", "content": judge_prompt}
        user_message = {"role": "user", "content": user_prompt}
        messages = [system_message, user_message]

        from ..tools import extract_tool_call, run_tool

        raw_response = ""
        response = ""
        for step in range(4):
            yield {"type": "agent_request", "agent": "judge", "step": step + 1, "messages": messages}

            response = ""
            for piece in client.chat_stream(
                messages,
                temperature=temperature,
                max_tokens=max_tokens,
                top_p=top_p,
                top_k=top_k,
            ):
                response += piece
                yield {"type": "judge_token", "delta": piece}

            raw_response += response
            yield {"type": "agent_step_done", "agent": "judge", "step": step + 1, "response": response}

            tool_name, tool_input = extract_tool_call(response)
            if not tool_name:
                break

            yield {"type": "agent_tool_start", "agent": "judge", "tool": tool_name, "step": step + 1, "input": tool_input}
            tool_output = run_tool(tool_name, tool_input)
            yield {"type": "agent_tool_result", "agent": "judge", "tool": tool_name, "step": step + 1, "output": tool_output}

            messages = [
                system_message,
                user_message,
                {"role": "assistant", "content": response},
                {"role": "user", "content": f"Tool '{tool_name}' result:\n{tool_output}"},
            ]

        answer = extract_answer(response)
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
        top_p: float | None = None,
        top_k: int | None = None,
    ) -> tuple[int | None, str]:
        final_event: dict[str, Any] | None = None
        for event in self.decide_stream(
            problem, candidate_results, client, prompts,
            max_tokens=max_tokens, temperature=temperature, top_p=top_p, top_k=top_k,
        ):
            if event["type"] == "judge_done":
                final_event = event
        assert final_event is not None
        return final_event["answer"], final_event["notes"]

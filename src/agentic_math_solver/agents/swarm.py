from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any

from ..llm_client import OpenAICompatibleClient
from ..prompts import PromptLibrary
from ..types import AgentResult
from ..utils import extract_answer, normalize_answer


def _render_journal(journal: dict[str, Any]) -> str:
    lemmas = "\n".join(f"- {item}" for item in journal["proven_lemmas"]) or "(none yet)"
    dead_ends = "\n".join(f"- {item}" for item in journal["dead_ends"]) or "(none yet)"
    hypothesis = journal["current_hypothesis"] or "(none yet)"
    return (
        "Journal so far (carried forward instead of your full prior text):\n"
        f"Proven lemmas:\n{lemmas}\n\n"
        f"Dead ends:\n{dead_ends}\n\n"
        f"Current hypothesis:\n{hypothesis}"
    )


@dataclass(slots=True)
class SwarmAgent:
    agent_name: str
    persona_key: str

    def run_stream(
        self, problem: str, client: OpenAICompatibleClient, prompts: PromptLibrary, *, max_tokens: int, temperature: float
    ) -> Iterator[dict[str, Any]]:
        from ..tools import extract_journal_update, extract_tool_call, run_tool

        system_prompt = prompts.load("system")
        persona_prompt = prompts.load(self.persona_key)
        summary_prompt = prompts.load("summary") if prompts.exists("summary") else ""
        user_prompt = (
            f"Problem:\n{problem}\n\n"
            f"Use the persona below. Follow the final-answer format rules from the system "
            f"prompt: use \\boxed{{...}} only if the problem has a short, well-defined final "
            f"value; otherwise write out the complete formal derivation with no \\boxed{{}}.\n\n"
            f"Persona:\n{persona_prompt}\n\n"
            f"Short summary format to keep in mind:\n{summary_prompt}\n\n"
            f"You have access to tools:\n"
            f"- python: Run python code. Output format: ```python\ncode\n```\n"
            f"- search: Web search. Output format: ```search\nquery\n```\n"
            f"- mcp: MCP context query. Output format: ```mcp\nquery\n```\n"
            f"If you use a tool, WAIT for the result before giving your final answer.\n\n"
            f"If you use a tool, also keep a compact journal so your own long history doesn't "
            f"need to be reread each turn — right after the tool block, add:\n"
            f"```journal\n"
            f'{{"proven_lemmas": ["..."], "dead_ends": ["..."], "current_hypothesis": "..."}}\n'
            f"```\n"
            f"Only list items that are NEW since your last journal — they accumulate "
            f"automatically. Omit any of the three fields you have nothing new to add to."
        )
        system_message = {"role": "system", "content": system_prompt}
        user_message = {"role": "user", "content": user_prompt}
        messages = [system_message, user_message]

        yield {"type": "agent_start", "agent": self.agent_name, "persona": self.persona_key}

        trace: list[dict[str, Any]] = []
        raw_response = ""
        response = ""
        journal: dict[str, Any] = {"proven_lemmas": [], "dead_ends": [], "current_hypothesis": ""}

        for step in range(5):
            response = ""
            for piece in client.chat_stream(messages, temperature=temperature, max_tokens=max_tokens):
                response += piece
                yield {"type": "agent_token", "agent": self.agent_name, "delta": piece}

            raw_response += f"\n\nStep {step + 1} Output:\n{response}"

            journal_update = extract_journal_update(response)
            if journal_update:
                journal["proven_lemmas"].extend(journal_update.get("proven_lemmas") or [])
                journal["dead_ends"].extend(journal_update.get("dead_ends") or [])
                if journal_update.get("current_hypothesis"):
                    journal["current_hypothesis"] = journal_update["current_hypothesis"]
                yield {
                    "type": "agent_tool_result",
                    "agent": self.agent_name,
                    "tool": "journal",
                    "output": f"{len(journal['proven_lemmas'])} lema(s) provado(s), {len(journal['dead_ends'])} beco(s) sem saída",
                }

            tool_name, tool_input = extract_tool_call(response)
            if not tool_name:
                break

            yield {"type": "agent_tool_start", "agent": self.agent_name, "tool": tool_name, "input": tool_input}
            tool_output = run_tool(tool_name, tool_input)
            trace.append({"step": step, "tool": tool_name, "output": tool_output})
            yield {"type": "agent_tool_result", "agent": self.agent_name, "tool": tool_name, "output": tool_output}

            # Em vez de acumular o histórico bruto de todas as rodadas (o que faz o
            # prompt crescer sem limite ao longo das até 5 iterações), reconstrói o
            # contexto da PRÓXIMA rodada a partir do diário estruturado + só o
            # resultado da ferramenta mais recente. `raw_response` continua guardando
            # tudo, para o trace/Juiz — só o que volta pro modelo fica limitado.
            messages = [
                system_message,
                user_message,
                {"role": "assistant", "content": _render_journal(journal)},
                {"role": "user", "content": f"Tool '{tool_name}' result:\n{tool_output}"},
            ]

        answer = extract_answer(response)
        if answer is not None:
            answer = normalize_answer(answer)

        yield {
            "type": "agent_done",
            "agent": self.agent_name,
            "persona": self.persona_key,
            "answer": answer,
            "summary": response[:500],
            "raw_response": raw_response.strip(),
            "trace": trace,
        }

    def run(self, problem: str, client: OpenAICompatibleClient, prompts: PromptLibrary, *, max_tokens: int, temperature: float) -> AgentResult:
        final_event: dict[str, Any] | None = None
        for event in self.run_stream(problem, client, prompts, max_tokens=max_tokens, temperature=temperature):
            if event["type"] == "agent_done":
                final_event = event

        assert final_event is not None
        return AgentResult(
            agent_name=final_event["agent"],
            persona=final_event["persona"],
            answer=final_event["answer"],
            raw_response=final_event["raw_response"],
            summary=final_event["summary"],
            trace=final_event["trace"],
        )
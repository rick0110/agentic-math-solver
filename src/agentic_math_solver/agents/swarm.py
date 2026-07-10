from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any

from ..llm_client import OpenAICompatibleClient
from ..prompts import PromptLibrary
from ..types import AgentResult
from ..utils import extract_answer, normalize_answer


@dataclass(slots=True)
class SwarmAgent:
    agent_name: str
    persona_key: str

    def run_stream(
        self, problem: str, client: OpenAICompatibleClient, prompts: PromptLibrary, *, max_tokens: int, temperature: float
    ) -> Iterator[dict[str, Any]]:
        from ..tools import extract_tool_call, run_tool

        system_prompt = prompts.load("system")
        persona_prompt = prompts.load(self.persona_key)
        summary_prompt = prompts.load("summary") if prompts.exists("summary") else ""
        user_prompt = (
            f"Problem:\n{problem}\n\n"
            f"Use the persona below and answer with a single final integer inside \\boxed{{number}} if possible.\n\n"
            f"Persona:\n{persona_prompt}\n\n"
            f"Short summary format to keep in mind:\n{summary_prompt}\n\n"
            f"You have access to tools:\n"
            f"- python: Run python code. Output format: ```python\ncode\n```\n"
            f"- search: Web search. Output format: ```search\nquery\n```\n"
            f"- mcp: MCP context query. Output format: ```mcp\nquery\n```\n"
            f"If you use a tool, WAIT for the result before giving your final answer."
        )
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        yield {"type": "agent_start", "agent": self.agent_name, "persona": self.persona_key}

        trace: list[dict[str, Any]] = []
        raw_response = ""
        response = ""

        for step in range(5):
            response = ""
            for piece in client.chat_stream(messages, temperature=temperature, max_tokens=max_tokens):
                response += piece
                yield {"type": "agent_token", "agent": self.agent_name, "delta": piece}

            raw_response += f"\n\nStep {step + 1} Output:\n{response}"
            messages.append({"role": "assistant", "content": response})

            tool_name, tool_input = extract_tool_call(response)
            if tool_name:
                yield {"type": "agent_tool_start", "agent": self.agent_name, "tool": tool_name, "input": tool_input}
                tool_output = run_tool(tool_name, tool_input)
                trace.append({"step": step, "tool": tool_name, "output": tool_output})
                yield {"type": "agent_tool_result", "agent": self.agent_name, "tool": tool_name, "output": tool_output}
                messages.append({"role": "user", "content": f"Tool '{tool_name}' result:\n{tool_output}"})
            else:
                break

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

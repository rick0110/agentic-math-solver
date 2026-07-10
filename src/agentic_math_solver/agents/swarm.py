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
        from ..tools import extract_and_run_tools
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
        
        trace = []
        raw_response = ""
        
        for step in range(5):
            response = client.chat(
                messages,
                temperature=temperature,
                max_tokens=max_tokens,
            )
            raw_response += f"\n\nStep {step + 1} Output:\n{response}"
            messages.append({"role": "assistant", "content": response})
            
            tool_name, tool_output = extract_and_run_tools(response)
            if tool_name:
                trace.append({"step": step, "tool": tool_name, "output": tool_output})
                messages.append({"role": "user", "content": f"Tool '{tool_name}' result:\n{tool_output}"})
            else:
                break
                
        answer = extract_answer(response)
        if answer is not None:
            answer = normalize_answer(answer)
        return AgentResult(
            agent_name=self.agent_name,
            persona=self.persona_key,
            answer=answer,
            raw_response=raw_response.strip(),
            summary=response[:500],
            trace=trace,
        )

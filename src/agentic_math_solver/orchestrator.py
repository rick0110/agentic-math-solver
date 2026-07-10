from __future__ import annotations

from collections import Counter
from collections.abc import Iterator
import queue
import threading
from typing import Any

from .agents.judge import JudgeAgent
from .agents.swarm import SwarmAgent
from .config import AppConfig
from .llm_client import LocalCpuTransformersClient, OpenAICompatibleClient
from .prompts import PromptLibrary
from .types import AgentResult, SolveResult
from .utils import normalize_answer


class SwarmOrchestrator:
    def __init__(self, config: AppConfig):
        self.config = config
        self.prompts = PromptLibrary(config.resolved_prompt_dir())
        if config.model.backend.lower() in {"cpu", "local_cpu", "transformers"}:
            self.client = LocalCpuTransformersClient(
                model_id=config.model.model_id,
                device=config.model.device,
                torch_dtype=config.model.torch_dtype,
                max_new_tokens=config.model.max_tokens,
            )
        else:
            self.client = OpenAICompatibleClient(
                endpoint=config.model.endpoint,
                model_name=config.model.model_name,
                api_key=config.model.api_key,
                timeout_seconds=config.model.timeout_seconds,
            )
        self.judge = JudgeAgent()
        self._all_agents = [
            SwarmAgent("agent-1", "formalist"),
            SwarmAgent("agent-2", "architect"),
            SwarmAgent("agent-3", "sentinel"),
            SwarmAgent("agent-4", "oracle"),
        ]

    @property
    def agents(self) -> list[SwarmAgent]:
        return self._all_agents[: max(1, self.config.agent_count)]

    def solve_stream(self, problem: str) -> Iterator[dict[str, Any]]:
        """Runs the swarm and yields wire-safe event dicts as they happen.

        Internal-only events (not meant to be forwarded to a client) use a
        leading underscore in their "type" so callers can filter them out.
        """
        event_queue: queue.Queue = queue.Queue()
        agent_results: dict[str, AgentResult] = {}

        def run_agent(agent: SwarmAgent) -> None:
            final_event: dict[str, Any] | None = None
            try:
                for event in agent.run_stream(
                    problem,
                    self.client,
                    self.prompts,
                    max_tokens=self.config.model.max_tokens,
                    temperature=self.config.model.temperature,
                ):
                    event_queue.put(event)
                    if event["type"] == "agent_done":
                        final_event = event
            except Exception as exc:
                final_event = {
                    "type": "agent_done",
                    "agent": agent.agent_name,
                    "persona": agent.persona_key,
                    "answer": None,
                    "summary": "",
                    "raw_response": "",
                    "trace": [],
                    "error": str(exc),
                }
                event_queue.put(final_event)
            finally:
                if final_event is not None:
                    agent_results[agent.agent_name] = AgentResult(
                        agent_name=final_event["agent"],
                        persona=final_event["persona"],
                        answer=final_event["answer"],
                        raw_response=final_event["raw_response"],
                        summary=final_event["summary"],
                        trace=final_event["trace"],
                    )
                event_queue.put({"type": "_agent_thread_done"})

        threads = [threading.Thread(target=run_agent, args=(agent,), daemon=True) for agent in self.agents]
        for thread in threads:
            thread.start()

        finished = 0
        while finished < len(threads):
            event = event_queue.get()
            if event["type"] == "_agent_thread_done":
                finished += 1
                continue
            yield event

        results = [agent_results[agent.agent_name] for agent in self.agents if agent.agent_name in agent_results]
        yield {"type": "_agent_results", "results": results}

        answers = [result.answer for result in results if result.answer is not None]
        vote_counts = Counter(answers)

        if not vote_counts:
            message = "O sistema falhou em extrair uma solução válida do modelo."
            yield {"type": "summary_start"}
            yield {"type": "summary_token", "delta": message}
            yield {"type": "summary_done"}
            yield {
                "type": "final",
                "final_answer": "Não foi possível chegar a uma resposta final.",
                "used_judge": False,
                "vote_counts": {},
                "judge_notes": "No agent produced a parseable answer.",
                "educational_summary": message,
            }
            return

        top_answer, top_votes = vote_counts.most_common(1)[0]
        final_answer = normalize_answer(top_answer)
        used_judge = False
        judge_notes = ""

        if len(vote_counts) > 1 and top_votes < 3 and self.config.use_judge:
            used_judge = True
            judge_answer = None
            for event in self.judge.decide_stream(
                problem,
                results,
                self.client,
                self.prompts,
                max_tokens=self.config.model.max_tokens,
                temperature=max(0.0, min(0.4, self.config.model.temperature)),
            ):
                yield event
                if event["type"] == "judge_done":
                    judge_answer = event["answer"]
                    judge_notes = event["notes"]
            if judge_answer is not None:
                final_answer = normalize_answer(judge_answer)

        summary = ""
        yield {"type": "summary_start"}
        for piece in self._stream_educational_summary(problem, final_answer):
            summary += piece
            yield {"type": "summary_token", "delta": piece}
        yield {"type": "summary_done"}

        yield {
            "type": "final",
            "final_answer": final_answer,
            "used_judge": used_judge,
            "vote_counts": dict(vote_counts),
            "judge_notes": judge_notes,
            "educational_summary": summary,
        }

    def solve(self, problem: str) -> SolveResult:
        agent_results: list[AgentResult] = []
        final_event: dict[str, Any] | None = None
        for event in self.solve_stream(problem):
            if event["type"] == "_agent_results":
                agent_results = event["results"]
            elif event["type"] == "final":
                final_event = event

        assert final_event is not None
        return SolveResult(
            final_answer=final_event["final_answer"],
            used_judge=final_event["used_judge"],
            vote_counts=final_event["vote_counts"],
            agent_results=agent_results,
            judge_notes=final_event["judge_notes"],
            educational_summary=final_event["educational_summary"],
        )

    def _stream_educational_summary(self, problem: str, final_answer: str) -> Iterator[str]:
        messages = [
            {
                "role": "system",
                "content": (
                    "Você é um professor de matemática experiente e didático. Sua tarefa é pegar um problema e sua "
                    "resposta final, e produzir uma explicação passo a passo excelente. Use Markdown, caixas de "
                    "código e equações matemáticas (no formato LaTeX com $$ ou $). Resuma a lógica de forma clara e "
                    "educativa."
                ),
            },
            {
                "role": "user",
                "content": f"Problema: {problem}\nResposta Final Verificada: {final_answer}\n\nPor favor, explique passo a passo como chegar a essa resposta.",
            },
        ]
        try:
            yield from self.client.chat_stream(messages, temperature=0.3, max_tokens=self.config.model.max_tokens)
        except Exception as exc:
            yield f"Erro ao gerar resumo educacional: {str(exc)}"

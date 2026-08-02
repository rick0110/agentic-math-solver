from __future__ import annotations

from collections import Counter
from collections.abc import Iterator
import queue
import threading
from typing import Any

from .agents.extractor import ExtractorAgent
from .agents.judge import JudgeAgent
from .agents.swarm import SwarmAgent
from .config import AppConfig
from .llm_client import LocalCpuTransformersClient, OpenAICompatibleClient
from .prompts import PromptLibrary
from .types import AgentResult, SolveResult
from .utils import normalize_answer, truncate_preserving_ends

# Orçamento de caracteres pra derivação vencedora que embasa o resumo educacional —
# mesmo raciocínio do _MAX_CANDIDATE_CHARS do Judge (agents/judge.py): evita estourar
# o contexto fixo do modelo ao colar um raw_response inteiro num prompt novo.
_MAX_DERIVATION_CHARS = 2000


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
        self.extractor = ExtractorAgent()
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
                    top_p=self.config.model.top_p,
                    top_k=self.config.model.top_k,
                ):
                    if event["type"] != "agent_done":
                        event_queue.put(event)
                        continue

                    final_event = event
                    
                    if event["answer"] is None and event["raw_response"].strip():
                        event_queue.put({
                            "type": "agent_tool_start",
                            "agent": agent.agent_name,
                            "tool": "extractor",
                            "input": "",
                        })
                        kind, extracted_answer, _ = self.extractor.extract(
                            problem,
                            event["raw_response"],
                            self.client,
                            self.prompts,
                            max_tokens=self.config.model.max_tokens,
                        )
                        preview = extracted_answer if kind == "boxed" else "demonstração formal confirmada (sem valor curto)"
                        event_queue.put({
                            "type": "agent_tool_result",
                            "agent": agent.agent_name,
                            "tool": "extractor",
                            "output": preview,
                        })
                        final_event = {**event, "answer": extracted_answer if kind == "boxed" else None}
                    event_queue.put(final_event)
            except Exception as exc:
                final_event = {
                    "type": "agent_done",
                    "agent": agent.agent_name,
                    "persona": agent.persona_key,
                    "answer": None,
                    "summary": "",
                    "raw_response": "",
                    "trace": [],
                    "journal": {},
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
                        journal=final_event.get("journal") or {},
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

        if not results or all(not result.raw_response.strip() for result in results):
            message = "O sistema falhou em obter qualquer resposta utilizável do modelo."
            yield {"type": "summary_start"}
            yield {"type": "summary_token", "delta": message}
            yield {"type": "summary_done"}
            yield {
                "type": "final",
                "final_answer": "Não foi possível chegar a uma resposta final.",
                "used_judge": False,
                "vote_counts": {},
                "judge_notes": "Nenhum agente produziu uma resposta utilizável.",
                "educational_summary": message,
            }
            return

        
        answers = [result.answer for result in results if result.answer is not None]
        vote_counts = Counter(answers)

        disagreement = (
            not vote_counts
            or len(answers) < len(results)
            or (len(vote_counts) > 1 and vote_counts.most_common(1)[0][1] < 3)
        )
        # Consenso 4/4 não é garantia de correção: as 4 personas são o mesmo modelo com
        # prompts diferentes, então podem compartilhar o mesmo erro sistemático. Com
        # `judge_always_verify` ligado, o Judge roda mesmo sem discordância — só pra checar.
        needs_judge = disagreement or self.config.judge_always_verify

        used_judge = False
        judge_notes = ""
        judge_raw_text = ""
        final_answer = normalize_answer(vote_counts.most_common(1)[0][0]) if vote_counts else None

        if needs_judge and self.config.use_judge:
            used_judge = True
            judge_answer = None
            for event in self.judge.decide_stream(
                problem,
                results,
                self.client,
                self.prompts,
                max_tokens=self.config.model.max_tokens,
                temperature=max(0.0, min(0.4, self.config.model.temperature)),
                top_p=self.config.model.top_p,
                top_k=self.config.model.top_k,
            ):
                yield event
                if event["type"] == "judge_done":
                    judge_answer = event["answer"]
                    judge_notes = event["notes"]
                    judge_raw_text = event["notes"]
            if judge_answer is not None:
                final_answer = normalize_answer(judge_answer)

        summary = ""
        if final_answer is not None:
            
            winners = [r for r in results if r.answer is not None and normalize_answer(r.answer) == final_answer]
            if winners:
                derivation = max(winners, key=lambda r: len(r.raw_response)).raw_response
            elif used_judge and judge_raw_text.strip():
                derivation = judge_raw_text
            else:
                derivation = max(results, key=lambda r: len(r.raw_response)).raw_response

            yield {"type": "summary_start"}
            for piece in self._stream_educational_summary(problem, final_answer, derivation):
                summary += piece
                yield {"type": "summary_token", "delta": piece}
            yield {"type": "summary_done"}
        else:
            
            summary = judge_raw_text or max(results, key=lambda r: len(r.raw_response)).raw_response
            final_answer = "Ver solução passo a passo abaixo"
            yield {"type": "summary_start"}
            yield {"type": "summary_token", "delta": summary}
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

    def _stream_educational_summary(self, problem: str, final_answer: str, derivation: str) -> Iterator[str]:
        derivation_text = (
            truncate_preserving_ends(derivation.strip(), _MAX_DERIVATION_CHARS)
            if derivation and derivation.strip()
            else "(nenhuma derivação disponível — explique com seu próprio raciocínio)"
        )
        messages = [
            {
                "role": "system",
                "content": (
                    "Você é um professor de matemática experiente e didático. Você recebe um problema, a resposta "
                    "final já verificada, e a derivação bruta que já foi produzida e validada (por um dos agentes "
                    "solucionadores ou pelo Juiz) para chegar nela. Sua tarefa é REESCREVER essa derivação de forma "
                    "didática e completa — passo a passo, formal, justificando cada passo matemático — sem inventar "
                    "um caminho diferente do que já foi verificado. Use Markdown, caixas de código e equações "
                    "matemáticas (no formato LaTeX com $$ ou $)."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"Problema: {problem}\nResposta Final Verificada: {final_answer}\n\n"
                    f"Derivação bruta já verificada (use como base — não invente outro caminho):\n{derivation_text}\n\n"
                    f"Por favor, reescreva essa derivação de forma didática, passo a passo."
                ),
            },
        ]
        try:
            yield from self.client.chat_stream(
                messages,
                temperature=0.3,
                max_tokens=self.config.model.max_tokens,
                top_p=self.config.model.top_p,
                top_k=self.config.model.top_k,
            )
        except Exception as exc:
            yield f"Erro ao gerar resumo educacional: {str(exc)}"
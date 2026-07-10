from __future__ import annotations

from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed

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
        self.agents = [
            SwarmAgent("agent-1", "formalist"),
            SwarmAgent("agent-2", "architect"),
            SwarmAgent("agent-3", "sentinel"),
            SwarmAgent("agent-4", "oracle"),
        ][: config.agent_count]

    def solve(self, problem: str) -> SolveResult:
        results: list[AgentResult] = []
        with ThreadPoolExecutor(max_workers=len(self.agents)) as executor:
            futures = [
                executor.submit(
                    agent.run,
                    problem,
                    self.client,
                    self.prompts,
                    max_tokens=self.config.model.max_tokens,
                    temperature=self.config.model.temperature,
                )
                for agent in self.agents
            ]
            for future in as_completed(futures):
                results.append(future.result())

        answers = [result.answer for result in results if result.answer is not None]
        vote_counts = Counter(answers)

        if not vote_counts:
            return SolveResult(final_answer="Não foi possível chegar a uma resposta final.", used_judge=False, vote_counts={}, agent_results=results, judge_notes="No agent produced a parseable answer.", educational_summary="O sistema falhou em extrair uma solução válida do modelo.")

        top_answer, top_votes = vote_counts.most_common(1)[0]
        if len(vote_counts) == 1 or top_votes >= 3 or not self.config.use_judge:
            final_ans = normalize_answer(top_answer)
            summary = self._generate_educational_summary(problem, final_ans)
            return SolveResult(final_answer=final_ans, used_judge=False, vote_counts=dict(vote_counts), agent_results=results, educational_summary=summary)

        judge_answer, judge_notes = self.judge.decide(
            problem,
            results,
            self.client,
            self.prompts,
            max_tokens=self.config.model.max_tokens,
            temperature=max(0.0, min(0.4, self.config.model.temperature)),
        )
        if judge_answer is None:
            final_ans = normalize_answer(top_answer)
            summary = self._generate_educational_summary(problem, final_ans)
            return SolveResult(final_answer=final_ans, used_judge=True, vote_counts=dict(vote_counts), agent_results=results, judge_notes=judge_notes, educational_summary=summary)

        final_ans = normalize_answer(judge_answer)
        summary = self._generate_educational_summary(problem, final_ans)
        return SolveResult(final_answer=final_ans, used_judge=True, vote_counts=dict(vote_counts), agent_results=results, judge_notes=judge_notes, educational_summary=summary)

    def _generate_educational_summary(self, problem: str, final_answer: str) -> str:
        messages = [
            {"role": "system", "content": "Você é um professor de matemática experiente e didático. Sua tarefa é pegar um problema e sua resposta final, e produzir uma explicação passo a passo excelente. Use Markdown, caixas de código e equações matemáticas (no formato LaTeX com $$ ou $). Resuma a lógica de forma clara e educativa."},
            {"role": "user", "content": f"Problema: {problem}\nResposta Final Verificada: {final_answer}\n\nPor favor, explique passo a passo como chegar a essa resposta."}
        ]
        try:
            return self.client.chat(messages, temperature=0.3, max_tokens=self.config.model.max_tokens)
        except Exception as e:
            return f"Erro ao gerar resumo educacional: {str(e)}"

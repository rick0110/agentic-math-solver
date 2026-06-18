from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class AgentResult:
    agent_name: str
    persona: str
    answer: int | None
    raw_response: str
    summary: str = ""
    trace: list[dict[str, Any]] = field(default_factory=list)


@dataclass(slots=True)
class SolveResult:
    final_answer: int
    used_judge: bool
    vote_counts: dict[int, int]
    agent_results: list[AgentResult]
    judge_notes: str = ""

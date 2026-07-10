from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class AgentResult:
    agent_name: str
    persona: str
    answer: str | None
    raw_response: str
    summary: str = ""
    trace: list[dict[str, Any]] = field(default_factory=list)


@dataclass(slots=True)
class SolveResult:
    final_answer: str
    used_judge: bool
    vote_counts: dict[str, int]
    agent_results: list[AgentResult]
    judge_notes: str = ""
    educational_summary: str = ""

from __future__ import annotations

import re
from typing import Any


BOXED_PATTERN = re.compile(r"\\boxed\{((?:[^{}]|{[^{}]*})*)\}")


def render_journal(journal: dict[str, Any]) -> str:
    """Renders an agent's compact carry-forward journal (proven lemmas, dead ends,
    current hypothesis) as text. Used both to feed an agent its own prior state back
    in the next tool-use step (swarm.py) and to give the Judge a dense, untruncated
    digest of each candidate instead of relying only on the raw response."""
    lemmas = "\n".join(f"- {item}" for item in journal.get("proven_lemmas") or []) or "(none yet)"
    dead_ends = "\n".join(f"- {item}" for item in journal.get("dead_ends") or []) or "(none yet)"
    hypothesis = journal.get("current_hypothesis") or "(none yet)"
    return (
        "Journal so far (carried forward instead of full prior text):\n"
        f"Proven lemmas:\n{lemmas}\n\n"
        f"Dead ends:\n{dead_ends}\n\n"
        f"Current hypothesis:\n{hypothesis}"
    )


def extract_answer(text: str) -> str | None:
    boxed = BOXED_PATTERN.findall(text)
    if boxed:
        return boxed[-1].strip()
    return None


def normalize_answer(answer: str) -> str:
    return answer.strip()


def truncate_preserving_ends(text: str, max_chars: int) -> str:
    """Keeps the start (approach) and end (conclusion/answer) of a long response,
    cutting only the middle — where exploration/discarded attempts usually live, not
    the decisive content. Used to keep secondary LLM calls (Judge, Extractor) that
    embed another agent's raw response from silently blowing past the model's context
    window (a fixed ceiling like max_position_embeddings, not something you can just
    raise via --max-model-len) and getting a 400 from the server."""
    text = text.strip()
    if len(text) <= max_chars:
        return text
    head = max_chars // 3
    tail = max_chars - head
    omitted = len(text) - max_chars
    return f"{text[:head]}\n...[{omitted} caracteres omitidos]...\n{text[-tail:]}"

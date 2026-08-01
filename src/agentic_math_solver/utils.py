from __future__ import annotations

import re


BOXED_PATTERN = re.compile(r"\\boxed\{((?:[^{}]|{[^{}]*})*)\}")


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

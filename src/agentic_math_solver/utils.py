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

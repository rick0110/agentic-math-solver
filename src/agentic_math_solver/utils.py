from __future__ import annotations

import re


BOXED_PATTERN = re.compile(r"\\boxed\{\s*(-?\d+)\s*\}")
INTEGER_PATTERN = re.compile(r"(?<!\d)-?\d+(?!\d)")


def extract_answer(text: str) -> int | None:
    boxed = BOXED_PATTERN.findall(text)
    if boxed:
        return int(boxed[-1])

    integers = INTEGER_PATTERN.findall(text)
    if integers:
        try:
            return int(integers[-1])
        except ValueError:
            return None
    return None


def normalize_answer(answer: int) -> int:
    return answer % 100000 if answer < 0 or answer > 99999 else answer

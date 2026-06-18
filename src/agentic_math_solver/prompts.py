from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(slots=True)
class PromptLibrary:
    prompt_dir: Path

    def load(self, name: str) -> str:
        path = self.prompt_dir / f"{name}.md"
        return path.read_text(encoding="utf-8").strip()

    def exists(self, name: str) -> bool:
        return (self.prompt_dir / f"{name}.md").exists()

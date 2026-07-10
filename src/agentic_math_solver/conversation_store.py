from __future__ import annotations

from datetime import datetime, timezone
import json
import re
import threading
from pathlib import Path
from typing import Any

_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


class InvalidConversationId(ValueError):
    pass


class ConversationStore:
    """Persists chat conversations as one JSON file per conversation on disk,
    so history survives clearing the browser (unlike localStorage)."""

    def __init__(self, base_dir: Path):
        self.base_dir = base_dir
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    def _path(self, conv_id: str) -> Path:
        if not _ID_PATTERN.match(conv_id):
            raise InvalidConversationId(f"ID de conversa inválido: {conv_id!r}")
        return self.base_dir / f"{conv_id}.json"

    def list(self) -> list[dict[str, Any]]:
        items = []
        for path in self.base_dir.glob("*.json"):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                continue
            items.append(
                {
                    "id": data.get("id", path.stem),
                    "title": data.get("title") or "Nova Conversa",
                    "created_at": data.get("created_at", ""),
                    "updated_at": data.get("updated_at", ""),
                    "message_count": len(data.get("messages", [])),
                }
            )
        items.sort(key=lambda item: item["updated_at"], reverse=True)
        return items

    def get(self, conv_id: str) -> dict[str, Any] | None:
        path = self._path(conv_id)
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return None

    def save(self, conv_id: str, *, title: str, messages: list[dict[str, Any]]) -> dict[str, Any]:
        path = self._path(conv_id)
        now = datetime.now(timezone.utc).isoformat()
        created_at = now
        with self._lock:
            if path.exists():
                try:
                    existing = json.loads(path.read_text(encoding="utf-8"))
                    created_at = existing.get("created_at", now)
                except (json.JSONDecodeError, OSError):
                    pass
            data = {
                "id": conv_id,
                "title": title.strip() or "Nova Conversa",
                "messages": messages,
                "created_at": created_at,
                "updated_at": now,
            }
            path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        return data

    def rename(self, conv_id: str, title: str) -> dict[str, Any] | None:
        existing = self.get(conv_id)
        if existing is None:
            return None
        return self.save(conv_id, title=title, messages=existing.get("messages", []))

    def delete(self, conv_id: str) -> bool:
        path = self._path(conv_id)
        if path.exists():
            path.unlink()
            return True
        return False

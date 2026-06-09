"""
SharedMemory — file-backed, versioned key-value store shared across all agents.

Agents read and write named artifacts (code snippets, schemas, plans, decisions).
Every write is appended to a history so agents can see how an artifact evolved.
Thread-safe via a file lock.
"""

from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class SharedMemory:
    """
    Persistent key-value store backed by a single JSON file.

    Keys use dot-notation namespacing:
        decisions.auth_strategy
        artifacts.backend.user_router
        feedback.backend.user_router
        context.project_goals
    """

    def __init__(self, path: str | Path = ".agent_memory.json"):
        self._path = Path(path)
        self._lock = threading.Lock()
        self._store: dict = self._load()

    # ── Persistence ───────────────────────────────────────────────────────────

    def _load(self) -> dict:
        if self._path.exists():
            try:
                return json.loads(self._path.read_text())
            except Exception:
                pass
        return {"kv": {}, "history": {}}

    def _save(self) -> None:
        self._path.write_text(json.dumps(self._store, indent=2))

    # ── Public API ────────────────────────────────────────────────────────────

    def write(self, key: str, value: Any, agent: str, summary: str = "") -> None:
        """Store a value under *key*, logging who wrote it and when."""
        with self._lock:
            entry = {
                "value": value,
                "agent": agent,
                "written_at": _now(),
                "summary": summary,
            }
            self._store["kv"][key] = entry
            self._store["history"].setdefault(key, []).append(entry)
            self._save()

    def read(self, key: str) -> Any | None:
        """Return the current value for *key*, or None if not set."""
        with self._lock:
            entry = self._store["kv"].get(key)
            return entry["value"] if entry else None

    def read_with_meta(self, key: str) -> dict | None:
        """Return value + metadata (agent, written_at, summary)."""
        with self._lock:
            return self._store["kv"].get(key)

    def history(self, key: str) -> list[dict]:
        """Return all past versions of *key* in chronological order."""
        with self._lock:
            return list(self._store["history"].get(key, []))

    def list_keys(self, prefix: str = "") -> list[str]:
        """List all keys, optionally filtered by prefix."""
        with self._lock:
            keys = list(self._store["kv"].keys())
            return [k for k in keys if k.startswith(prefix)] if prefix else keys

    def snapshot(self) -> dict[str, Any]:
        """Return a flat dict of key → value for quick inspection."""
        with self._lock:
            return {k: v["value"] for k, v in self._store["kv"].items()}

    def clear(self) -> None:
        with self._lock:
            self._store = {"kv": {}, "history": {}}
            self._save()

    def summary(self) -> str:
        """Human-readable summary of all stored keys and their latest authors."""
        with self._lock:
            if not self._store["kv"]:
                return "(memory is empty)"
            lines = []
            for key, entry in self._store["kv"].items():
                snippet = str(entry["value"])[:60].replace("\n", " ")
                lines.append(f"  {key}  [{entry['agent']}]  {snippet}…")
            return "\n".join(lines)

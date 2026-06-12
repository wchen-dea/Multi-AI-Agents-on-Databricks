"""
SharedMemory — MongoDB-backed, versioned key-value store shared across all agents.

Agents read and write named artifacts (code snippets, schemas, plans, decisions).
Every write is appended as an immutable version so agents can inspect evolution.
"""

from __future__ import annotations

import logging
import os
import threading
from datetime import datetime, timezone
from typing import Any

from pymongo import ASCENDING, DESCENDING, MongoClient
from pymongo.collection import Collection
from pymongo.errors import PyMongoError


DEFAULT_MONGODB_URI = "mongodb://localhost:27017"
DEFAULT_MONGODB_DB = "agentic_application"
DEFAULT_MONGODB_COLLECTION = "shared_memory"

LOGGER = logging.getLogger(__name__)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class SharedMemory:
    """
    Persistent key-value store backed by MongoDB.

    Keys use dot-notation namespacing:
        decisions.auth_strategy
        artifacts.backend.user_router
        feedback.backend.user_router
        context.project_goals
    """

    def __init__(
        self,
        _unused_path: str | None = None,
        *,
        uri: str | None = None,
        db_name: str | None = None,
        collection_name: str | None = None,
    ):
        self._lock = threading.Lock()
        self._fallback_store: dict[str, list[dict[str, Any]]] = {}
        self._uri = uri
        self._db_name = db_name
        self._collection_name = collection_name
        self._collection = self._connect()

    def _connect(self) -> Collection | None:
        uri = self._uri or os.getenv("MONGODB_URI", DEFAULT_MONGODB_URI)
        db_name = self._db_name or os.getenv("MONGODB_DB", DEFAULT_MONGODB_DB)
        collection_name = self._collection_name or os.getenv("MONGODB_MEMORY_COLLECTION", DEFAULT_MONGODB_COLLECTION)
        try:
            client = MongoClient(uri, serverSelectionTimeoutMS=1000)
            client.admin.command("ping")
            collection = client[db_name][collection_name]
            collection.create_index([("key", ASCENDING), ("written_at", DESCENDING)])
            collection.create_index([("key", ASCENDING)], unique=False)
            return collection
        except PyMongoError as exc:
            LOGGER.warning("MongoDB unavailable, using in-memory SharedMemory fallback: %s", exc)
            return None

    def _latest_docs(self) -> dict[str, dict[str, Any]]:
        if self._collection is None:
            latest: dict[str, dict[str, Any]] = {}
            for key, versions in self._fallback_store.items():
                if not versions:
                    continue
                doc = versions[-1]
                latest[key] = {
                    "value": doc.get("value"),
                    "agent": doc.get("agent", ""),
                    "written_at": doc.get("written_at", ""),
                    "summary": doc.get("summary", ""),
                }
            return latest

        docs = self._collection.find({}, {"_id": 0, "key": 1, "value": 1, "agent": 1, "written_at": 1, "summary": 1}).sort(
            [("key", ASCENDING), ("written_at", DESCENDING)]
        )
        latest: dict[str, dict[str, Any]] = {}
        for doc in docs:
            key = doc["key"]
            if key not in latest:
                latest[key] = {
                    "value": doc.get("value"),
                    "agent": doc.get("agent", ""),
                    "written_at": doc.get("written_at", ""),
                    "summary": doc.get("summary", ""),
                }
        return latest

    # ── Public API ────────────────────────────────────────────────────────────

    def write(self, key: str, value: Any, agent: str, summary: str = "") -> None:
        """Store a value under *key*, logging who wrote it and when."""
        with self._lock:
            doc = {
                "key": key,
                "value": value,
                "agent": agent,
                "written_at": _now(),
                "summary": summary,
            }
            if self._collection is None:
                self._fallback_store.setdefault(key, []).append(doc)
                return
            self._collection.insert_one(doc)

    def read(self, key: str) -> Any | None:
        """Return the current value for *key*, or None if not set."""
        with self._lock:
            if self._collection is None:
                versions = self._fallback_store.get(key, [])
                return versions[-1].get("value") if versions else None
            doc = self._collection.find_one({"key": key}, sort=[("written_at", DESCENDING)])
            return doc.get("value") if doc else None

    def read_with_meta(self, key: str) -> dict | None:
        """Return value + metadata (agent, written_at, summary)."""
        with self._lock:
            if self._collection is None:
                versions = self._fallback_store.get(key, [])
                if not versions:
                    return None
                doc = versions[-1]
                return {
                    "value": doc.get("value"),
                    "agent": doc.get("agent", ""),
                    "written_at": doc.get("written_at", ""),
                    "summary": doc.get("summary", ""),
                }
            doc = self._collection.find_one(
                {"key": key},
                {"_id": 0, "value": 1, "agent": 1, "written_at": 1, "summary": 1},
                sort=[("written_at", DESCENDING)],
            )
            return doc

    def history(self, key: str) -> list[dict]:
        """Return all past versions of *key* in chronological order."""
        with self._lock:
            if self._collection is None:
                return list(self._fallback_store.get(key, []))
            cursor = self._collection.find(
                {"key": key},
                {"_id": 0, "value": 1, "agent": 1, "written_at": 1, "summary": 1},
            ).sort("written_at", ASCENDING)
            return list(cursor)

    def list_keys(self, prefix: str = "") -> list[str]:
        """List all keys, optionally filtered by prefix."""
        with self._lock:
            if self._collection is None:
                keys = sorted(self._fallback_store)
                return [k for k in keys if k.startswith(prefix)] if prefix else keys
            keys = sorted(self._collection.distinct("key"))
            return [k for k in keys if k.startswith(prefix)] if prefix else keys

    def snapshot(self) -> dict[str, Any]:
        """Return a flat dict of key → value for quick inspection."""
        with self._lock:
            latest = self._latest_docs()
            return {k: v["value"] for k, v in latest.items()}

    def clear(self) -> None:
        with self._lock:
            if self._collection is None:
                self._fallback_store.clear()
                return
            self._collection.delete_many({})

    def summary(self) -> str:
        """Human-readable summary of all stored keys and their latest authors."""
        with self._lock:
            latest = self._latest_docs()
            if not latest:
                return "(memory is empty)"
            lines = []
            for key, entry in latest.items():
                snippet = str(entry["value"])[:60].replace("\n", " ")
                lines.append(f"  {key}  [{entry['agent']}]  {snippet}…")
            return "\n".join(lines)
"""
MessageBus — inter-agent communication channel.

Agents post typed messages (context, artifact, question, feedback, decision).
Any agent can read messages addressed to it or broadcast to all.
All messages are persisted so the supervisor can audit the full exchange.
"""

from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

MessageType = Literal["context", "artifact", "question", "feedback", "decision", "broadcast"]

BROADCAST = "__all__"


class Message:
    __slots__ = ("id", "from_agent", "to", "type", "subject", "content", "timestamp", "read_by")

    def __init__(
        self,
        id: int,
        from_agent: str,
        to: str,
        type: MessageType,
        subject: str,
        content: str,
        timestamp: str,
    ):
        self.id = id
        self.from_agent = from_agent
        self.to = to
        self.type = type
        self.subject = subject
        self.content = content
        self.timestamp = timestamp
        self.read_by: list[str] = []

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "from": self.from_agent,
            "to": self.to,
            "type": self.type,
            "subject": self.subject,
            "content": self.content,
            "timestamp": self.timestamp,
            "read_by": self.read_by,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Message":
        m = cls(
            id=d["id"],
            from_agent=d["from"],
            to=d["to"],
            type=d["type"],
            subject=d["subject"],
            content=d["content"],
            timestamp=d["timestamp"],
        )
        m.read_by = d.get("read_by", [])
        return m

    def __repr__(self) -> str:
        return f"Message(#{self.id} {self.from_agent}→{self.to} [{self.type}] {self.subject!r})"


class MessageBus:
    """
    Thread-safe, file-backed inter-agent message bus.

    Usage:
        bus.post("backend", to="ai_engineer", type="artifact",
                 subject="API schema", content="...")
        msgs = bus.read("ai_engineer")
    """

    def __init__(self, path: str | Path = ".agent_messages.json"):
        self._path = Path(path)
        self._lock = threading.Lock()
        self._messages: list[Message] = self._load()

    # ── Persistence ───────────────────────────────────────────────────────────

    def _load(self) -> list[Message]:
        if self._path.exists():
            try:
                data = json.loads(self._path.read_text())
                return [Message.from_dict(d) for d in data]
            except Exception:
                pass
        return []

    def _save(self) -> None:
        self._path.write_text(json.dumps([m.to_dict() for m in self._messages], indent=2))

    # ── Public API ────────────────────────────────────────────────────────────

    def post(
        self,
        from_agent: str,
        to: str,
        type: MessageType,
        subject: str,
        content: str,
    ) -> Message:
        """Send a message from *from_agent* to *to* (agent name or BROADCAST)."""
        with self._lock:
            msg = Message(
                id=len(self._messages),
                from_agent=from_agent,
                to=to,
                type=type,
                subject=subject,
                content=content,
                timestamp=datetime.now(timezone.utc).isoformat(),
            )
            self._messages.append(msg)
            self._save()
            return msg

    def broadcast(self, from_agent: str, type: MessageType, subject: str, content: str) -> Message:
        return self.post(from_agent, BROADCAST, type, subject, content)

    def read(
        self,
        agent: str,
        unread_only: bool = False,
        type_filter: MessageType | None = None,
    ) -> list[Message]:
        """Return messages addressed to *agent* or broadcast to all."""
        with self._lock:
            out = []
            for m in self._messages:
                if m.to not in (agent, BROADCAST):
                    continue
                if unread_only and agent in m.read_by:
                    continue
                if type_filter and m.type != type_filter:
                    continue
                if agent not in m.read_by:
                    m.read_by.append(agent)
                out.append(m)
            if out:
                self._save()
            return out

    def thread(self, agent_a: str, agent_b: str) -> list[Message]:
        """Return all messages exchanged between two agents (either direction)."""
        with self._lock:
            return [
                m for m in self._messages
                if {m.from_agent, m.to} == {agent_a, agent_b}
            ]

    def all_messages(self) -> list[Message]:
        with self._lock:
            return list(self._messages)

    def clear(self) -> None:
        with self._lock:
            self._messages = []
            self._save()

    def summary(self) -> str:
        with self._lock:
            if not self._messages:
                return "(no messages)"
            lines = []
            for m in self._messages[-20:]:  # last 20
                lines.append(
                    f"  #{m.id:3d} {m.from_agent:15s} → {m.to:15s}  [{m.type:8s}]  {m.subject[:50]}"
                )
            return "\n".join(lines)

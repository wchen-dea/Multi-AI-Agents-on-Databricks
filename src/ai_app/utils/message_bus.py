"""
MessageBus — inter-agent communication channel backed by RabbitMQ.

Agents post typed messages (context, artifact, question, feedback, decision).
Any agent can read messages addressed to it or broadcast to all.
All messages are persisted in a durable RabbitMQ queue so the supervisor
can audit the full exchange.

RabbitMQ connection is configured via the RABBITMQ_URL environment variable
(default: amqp://guest:guest@localhost:5672/).

Exchange topology
-----------------
- Exchange  : ``agent_messages``  (topic, durable)
- Routing key pattern: ``<to_agent>``  (or ``__all__`` for broadcasts)
- Each caller binds a personal durable queue  ``agent_inbox.<agent_name>``
  and a shared audit queue ``agent_inbox.__audit__`` that receives everything.
"""

from __future__ import annotations

import json
import logging
import os
import threading
from datetime import datetime, timezone
from typing import Literal

import pika
import pika.exceptions

MessageType = Literal["context", "artifact", "question", "feedback", "decision", "broadcast"]

BROADCAST = "__all__"
_EXCHANGE = "agent_messages"
_AUDIT_QUEUE = "agent_inbox.__audit__"
LOGGER = logging.getLogger(__name__)


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
    Thread-safe inter-agent message bus backed by RabbitMQ.

    Public API is identical to the previous file-backed implementation so that
    no other code needs to change.

    Usage::

        bus = MessageBus()                       # reads RABBITMQ_URL from env
        bus.post("backend", to="ai_engineer", type="artifact",
                 subject="API schema", content="...")
        msgs = bus.read("ai_engineer")

    The ``path`` parameter is accepted but ignored (kept for backwards
    compatibility with callers that pass a file path).
    """

    def __init__(
        self,
        path: str | None = None,  # ignored; kept for API compatibility
        url: str | None = None,
    ):
        self._url = url or os.environ.get("RABBITMQ_URL", "amqp://guest:guest@localhost:5672/")
        self._lock = threading.Lock()
        # In-process audit log so summary() / all_messages() / thread() work
        # without re-consuming from RabbitMQ.
        self._audit: list[Message] = []
        self._next_id = 0
        self._in_memory_mode = False

        self._conn: pika.BlockingConnection | None = None
        self._channel: pika.adapters.blocking_connection.BlockingChannel | None = None
        try:
            self._connect()
            self._setup_exchange()
        except Exception as exc:
            self._in_memory_mode = True
            self._conn = None
            self._channel = None
            LOGGER.warning("RabbitMQ unavailable, using in-memory MessageBus fallback: %s", exc)

    # ── Connection management ─────────────────────────────────────────────────

    def _connect(self) -> None:
        params = pika.URLParameters(self._url)
        params.heartbeat = 60
        params.blocked_connection_timeout = 30
        self._conn = pika.BlockingConnection(params)
        self._channel = self._conn.channel()

    def _ensure_connection(self) -> None:
        """Reconnect if the channel or connection has been closed."""
        if self._in_memory_mode:
            return
        try:
            if self._conn is None or self._conn.is_closed:
                self._connect()
                self._setup_exchange()
            elif self._channel is None or self._channel.is_closed:
                self._channel = self._conn.channel()
                self._setup_exchange()
        except pika.exceptions.AMQPConnectionError:
            self._connect()
            self._setup_exchange()

    def _setup_exchange(self) -> None:
        if self._channel is None:
            return
        ch = self._channel
        # Durable topic exchange so routing survives broker restarts
        ch.exchange_declare(exchange=_EXCHANGE, exchange_type="topic", durable=True)
        # Audit queue receives every message via wildcard binding
        ch.queue_declare(queue=_AUDIT_QUEUE, durable=True)
        ch.queue_bind(queue=_AUDIT_QUEUE, exchange=_EXCHANGE, routing_key="#")

    def _agent_queue(self, agent: str) -> str:
        return f"agent_inbox.{agent}"

    def _ensure_agent_queue(self, agent: str) -> str:
        """Declare (idempotent) a durable inbox queue for *agent* and return its name."""
        if self._channel is None:
            return self._agent_queue(agent)
        queue_name = self._agent_queue(agent)
        self._channel.queue_declare(queue=queue_name, durable=True)
        # Bind to messages addressed directly to this agent
        self._channel.queue_bind(queue=queue_name, exchange=_EXCHANGE, routing_key=agent)
        # Also receive broadcasts
        self._channel.queue_bind(queue=queue_name, exchange=_EXCHANGE, routing_key=BROADCAST)
        return queue_name

    # ── Public API ────────────────────────────────────────────────────────────

    def post(
        self,
        from_agent: str,
        to: str,
        type: MessageType,
        subject: str,
        content: str,
    ) -> Message:
        """Publish a message from *from_agent* to *to* (agent name or BROADCAST)."""
        with self._lock:
            msg = Message(
                id=self._next_id,
                from_agent=from_agent,
                to=to,
                type=type,
                subject=subject,
                content=content,
                timestamp=datetime.now(timezone.utc).isoformat(),
            )
            self._next_id += 1

            if self._in_memory_mode:
                self._audit.append(msg)
                return msg

            self._ensure_connection()
            # Make sure the recipient's inbox queue exists before publishing
            if to != BROADCAST:
                self._ensure_agent_queue(to)

            self._channel.basic_publish(
                exchange=_EXCHANGE,
                routing_key=to,
                body=json.dumps(msg.to_dict()).encode(),
                properties=pika.BasicProperties(
                    delivery_mode=2,  # persistent
                    content_type="application/json",
                ),
            )
            self._audit.append(msg)
            return msg

    def broadcast(self, from_agent: str, type: MessageType, subject: str, content: str) -> Message:
        return self.post(from_agent, BROADCAST, type, subject, content)

    def read(
        self,
        agent: str,
        unread_only: bool = False,
        type_filter: MessageType | None = None,
    ) -> list[Message]:
        """
        Pull all pending messages from the agent's RabbitMQ inbox (non-blocking).

        *unread_only* and *type_filter* are applied after consuming — already-read
        messages are not re-queued, so RabbitMQ naturally enforces "unread_only".
        When *unread_only* is False messages still won't be re-delivered (RabbitMQ
        semantics); callers that need replay should use *all_messages()* or *thread()*.
        """
        with self._lock:
            if self._in_memory_mode:
                out: list[Message] = []
                for m in self._audit:
                    if m.to not in (agent, BROADCAST):
                        continue
                    if type_filter and m.type != type_filter:
                        continue

                    has_read = agent in m.read_by
                    if unread_only and has_read:
                        continue
                    if not has_read:
                        m.read_by.append(agent)
                    out.append(m)
                return out

            self._ensure_connection()
            queue_name = self._ensure_agent_queue(agent)
            out: list[Message] = []
            audit_by_id = {a.id: a for a in self._audit}

            while True:
                method, _props, body = self._channel.basic_get(queue=queue_name, auto_ack=True)
                if method is None:
                    break  # no more messages
                try:
                    d = json.loads(body.decode())
                    m = Message.from_dict(d)
                except Exception:
                    continue

                if type_filter and m.type != type_filter:
                    continue

                if agent not in m.read_by:
                    m.read_by.append(agent)

                # Keep audit log in sync
                existing = audit_by_id.get(m.id)
                if existing is None:
                    self._audit.append(m)
                    audit_by_id[m.id] = m
                else:
                    existing.read_by = m.read_by

                out.append(m)

            return out

    def thread(self, agent_a: str, agent_b: str) -> list[Message]:
        """Return all messages exchanged between two agents (either direction)."""
        with self._lock:
            return [
                m for m in self._audit
                if {m.from_agent, m.to} == {agent_a, agent_b}
            ]

    def all_messages(self) -> list[Message]:
        """Return all messages seen since this MessageBus instance was created."""
        with self._lock:
            return list(self._audit)

    def clear(self) -> None:
        """
        Purge all agent inbox queues and clear the in-process audit log.
        Use with care — messages are permanently deleted.
        """
        with self._lock:
            if self._in_memory_mode:
                self._audit.clear()
                self._next_id = 0
                return
            self._ensure_connection()
            try:
                self._channel.queue_purge(_AUDIT_QUEUE)
            except Exception:
                pass
            self._audit.clear()
            self._next_id = 0

    def summary(self) -> str:
        with self._lock:
            if not self._audit:
                return "(message bus is empty)"
            lines = []
            for m in self._audit[-50:]:
                snippet = m.content[:60].replace("\n", " ")
                lines.append(f"#{m.id} {m.from_agent} → {m.to} [{m.type}] {m.subject}: {snippet}…")
            return "\n".join(lines)

    def close(self) -> None:
        """Close the RabbitMQ connection gracefully."""
        try:
            if self._conn and not self._conn.is_closed:
                self._conn.close()
        except Exception:
            pass
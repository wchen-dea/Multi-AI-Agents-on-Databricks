"""
BaseSpecialistAgent — shared agentic loop, file/shell tools, memory, and message bus.
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import anthropic

from ..utils import SharedMemory, MessageBus, BROADCAST
from ..integrations import DataSourceType, MCPDataSourceGateway

MODEL = "claude-opus-4-7"
MAX_TOKENS = 8096
MAX_ITERATIONS = 20

LOGGER = logging.getLogger(__name__)

# ── Shared tool schemas ───────────────────────────────────────────────────────

COMMON_TOOLS: list[dict] = [
    # ── File tools ────────────────────────────────────────────────────────────
    {
        "name": "write_file",
        "description": "Write content to a file, creating directories as needed.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "content": {"type": "string"},
            },
            "required": ["path", "content"],
        },
    },
    {
        "name": "read_file",
        "description": "Read the content of a file.",
        "input_schema": {
            "type": "object",
            "properties": {"path": {"type": "string"}},
            "required": ["path"],
        },
    },
    {
        "name": "run_shell",
        "description": "Run a shell command in the project root.",
        "input_schema": {
            "type": "object",
            "properties": {"command": {"type": "string"}},
            "required": ["command"],
        },
    },
    {
        "name": "list_files",
        "description": "List files in a directory.",
        "input_schema": {
            "type": "object",
            "properties": {"path": {"type": "string", "default": "."}},
        },
    },
    {
        "name": "mcp_retrieve",
        "description": (
            "Retrieve knowledge context from Databricks-backed MCP data sources. "
            "Sources: databricks_uc | databricks_feature_store | databricks_lakebase_mcp."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "source_type": {
                    "type": "string",
                    "enum": [
                        "databricks_uc",
                        "databricks_feature_store",
                        "databricks_lakebase_mcp",
                    ],
                },
                "query": {"type": "string"},
                "top_k": {"type": "integer", "default": 5},
            },
            "required": ["source_type", "query"],
        },
    },
    # ── Memory tools ──────────────────────────────────────────────────────────
    {
        "name": "memory_write",
        "description": (
            "Store a value in shared memory so other agents can read it. "
            "Use dot-namespaced keys, e.g. 'artifacts.backend.schema', "
            "'decisions.auth_strategy', 'context.project_goals'."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "key": {"type": "string", "description": "Dot-namespaced key."},
                "value": {"type": "string", "description": "Content to store."},
                "summary": {"type": "string", "description": "One-line description of what this is."},
            },
            "required": ["key", "value"],
        },
    },
    {
        "name": "memory_read",
        "description": "Read a value from shared memory by key.",
        "input_schema": {
            "type": "object",
            "properties": {"key": {"type": "string"}},
            "required": ["key"],
        },
    },
    {
        "name": "memory_list",
        "description": "List all keys in shared memory, optionally filtered by prefix.",
        "input_schema": {
            "type": "object",
            "properties": {"prefix": {"type": "string", "default": ""}},
        },
    },
    # ── Message bus tools ─────────────────────────────────────────────────────
    {
        "name": "send_message",
        "description": (
            "Send a typed message to another specialist or broadcast to all. "
            "Types: context | artifact | question | feedback | decision | broadcast. "
            "Specialists: frontend, backend, ml_engineer, ai_engineer, "
            "fullstack, data_engineer, data_scientist, supervisor."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "to": {"type": "string", "description": "Recipient agent name or '__all__' to broadcast."},
                "type": {
                    "type": "string",
                    "enum": ["context", "artifact", "question", "feedback", "decision", "broadcast"],
                },
                "subject": {"type": "string"},
                "content": {"type": "string"},
            },
            "required": ["to", "type", "subject", "content"],
        },
    },
    {
        "name": "read_messages",
        "description": "Read messages sent to you (or broadcast to all).",
        "input_schema": {
            "type": "object",
            "properties": {
                "unread_only": {"type": "boolean", "default": True},
                "type_filter": {
                    "type": "string",
                    "enum": ["context", "artifact", "question", "feedback", "decision", "broadcast"],
                    "description": "Optional: filter by message type.",
                },
            },
        },
    },
]


@dataclass
class AgentResult:
    specialist: str
    task: str
    output: str
    files_written: list[str] = field(default_factory=list)
    commands_run: list[str] = field(default_factory=list)
    memory_keys_written: list[str] = field(default_factory=list)
    messages_sent: list[str] = field(default_factory=list)
    success: bool = True
    error: str = ""


class BaseSpecialistAgent:
    name: str = "specialist"
    role: str = "software engineer"
    system_prompt: str = "You are a helpful software engineer."
    extra_tools: list[dict] = []

    def __init__(
        self,
        client: anthropic.Anthropic,
        project_root: str = ".",
        verbose: bool = True,
        memory: SharedMemory | None = None,
        bus: MessageBus | None = None,
    ):
        self.client = client
        self.project_root = Path(project_root).resolve()
        self.verbose = verbose
        self.memory = memory or SharedMemory(self.project_root / ".agent_memory.json")
        self.bus = bus or MessageBus(self.project_root / ".agent_messages.json")
        self.tools = COMMON_TOOLS + self.extra_tools

    # ── Tool execution ────────────────────────────────────────────────────────

    def _write_file(self, path: str, content: str) -> str:
        full = self.project_root / path
        full.parent.mkdir(parents=True, exist_ok=True)
        full.write_text(content, encoding="utf-8")
        return f"Written: {path} ({len(content)} chars)"

    def _read_file(self, path: str) -> str:
        full = self.project_root / path
        return full.read_text(encoding="utf-8") if full.exists() else f"ERROR: {path} not found"

    def _run_shell(self, command: str) -> str:
        result = subprocess.run(
            command, shell=True, capture_output=True, text=True,
            cwd=self.project_root, timeout=120,
        )
        out = result.stdout[-2000:] if result.stdout else ""
        err = result.stderr[-1000:] if result.stderr else ""
        return (out + ("\n" + err if err else "")).strip() or "(no output)"

    def _list_files(self, path: str = ".") -> str:
        full = self.project_root / path
        if not full.exists():
            return f"ERROR: {path} not found"
        entries = sorted(str(p.relative_to(self.project_root)) for p in full.rglob("*") if p.is_file())
        return "\n".join(entries[:100]) or "(empty)"

    def _mcp_retrieve(self, source_type: str, query: str, top_k: int = 5) -> str:
        try:
            source = DataSourceType(source_type)
            gateway = MCPDataSourceGateway.from_env(source)
            docs = gateway.retrieve(query=query, top_k=top_k)
            if not docs:
                return "No documents returned."
            lines = [f"[{i}] {doc}" for i, doc in enumerate(docs, start=1)]
            return "\n\n".join(lines)
        except KeyError as exc:
            return (
                "ERROR: Missing required environment variable for MCP retrieval: "
                f"{exc}. Required: DATABRICKS_MCP_URL (and optional DATABRICKS_TOKEN/tool vars)."
            )
        except ValueError as exc:
            return f"ERROR: {exc}"
        except Exception as exc:
            return f"ERROR: MCP retrieval failed: {exc}"

    def _memory_write(self, key: str, value: str, summary: str = "") -> str:
        self.memory.write(key, value, agent=self.name, summary=summary)
        return f"Stored in memory: {key}"

    def _memory_read(self, key: str) -> str:
        val = self.memory.read(key)
        if val is None:
            keys = self.memory.list_keys()
            return f"Key '{key}' not found. Available keys: {keys}"
        return str(val)

    def _memory_list(self, prefix: str = "") -> str:
        keys = self.memory.list_keys(prefix)
        if not keys:
            return f"No keys{f' with prefix {prefix!r}' if prefix else ''}."
        lines = []
        for k in keys:
            meta = self.memory.read_with_meta(k)
            if meta:
                lines.append(f"  {k}  [{meta['agent']}]  {meta['summary'] or str(meta['value'])[:50]}")
        return "\n".join(lines)

    def _send_message(self, to: str, type: str, subject: str, content: str) -> str:
        msg = self.bus.post(
            from_agent=self.name,
            to=to if to != "broadcast" else BROADCAST,
            type=type,  # type: ignore
            subject=subject,
            content=content,
        )
        return f"Message #{msg.id} sent to {to}: {subject!r}"

    def _read_messages(self, unread_only: bool = True, type_filter: str | None = None) -> str:
        msgs = self.bus.read(self.name, unread_only=unread_only, type_filter=type_filter)  # type: ignore
        if not msgs:
            return "No messages."
        parts = []
        for m in msgs:
            parts.append(
                f"--- Message #{m.id} from {m.from_agent} [{m.type}] ---\n"
                f"Subject: {m.subject}\n{m.content}"
            )
        return "\n\n".join(parts)

    def _dispatch_tool(self, name: str, inputs: dict) -> str:
        if name == "write_file":
            return self._write_file(inputs["path"], inputs["content"])
        if name == "read_file":
            return self._read_file(inputs["path"])
        if name == "run_shell":
            return self._run_shell(inputs["command"])
        if name == "list_files":
            return self._list_files(inputs.get("path", "."))
        if name == "mcp_retrieve":
            return self._mcp_retrieve(
                source_type=inputs["source_type"],
                query=inputs["query"],
                top_k=inputs.get("top_k", 5),
            )
        if name == "memory_write":
            return self._memory_write(inputs["key"], inputs["value"], inputs.get("summary", ""))
        if name == "memory_read":
            return self._memory_read(inputs["key"])
        if name == "memory_list":
            return self._memory_list(inputs.get("prefix", ""))
        if name == "send_message":
            return self._send_message(inputs["to"], inputs["type"], inputs["subject"], inputs["content"])
        if name == "read_messages":
            return self._read_messages(inputs.get("unread_only", True), inputs.get("type_filter"))
        return f"ERROR: unknown tool {name}"

    # ── Agentic loop ──────────────────────────────────────────────────────────

    def run(self, task: str, context: str = "") -> AgentResult:
        agent_logger = LOGGER.getChild(self.name)
        if self.verbose:
            agent_logger.info("[%s] %s", self.name.upper(), task[:70])

        result = AgentResult(specialist=self.name, task=task)

        # Inject current memory state and any unread messages into context
        mem_summary = self.memory.summary()
        unread = self.bus.read(self.name, unread_only=True)
        inbox = (
            "\n".join(
                f"  #{m.id} from={m.from_agent} [{m.type}] {m.subject}: {m.content[:200]}"
                for m in unread
            )
            if unread
            else "  (none)"
        )

        preamble = (
            f"=== SHARED MEMORY ===\n{mem_summary}\n\n"
            f"=== YOUR INBOX (unread messages from other agents) ===\n{inbox}"
        )
        full_task = f"{preamble}\n\n=== YOUR TASK ===\n{task}"
        if context:
            full_task += f"\n\n=== CONTEXT FROM SUPERVISOR ===\n{context}"

        messages: list[dict] = [{"role": "user", "content": full_task}]
        system = [
            {
                "type": "text",
                "text": (
                    f"{self.system_prompt}\n\n"
                    "You have access to shared memory (memory_write/read/list) and a message bus "
                        "(send_message/read_messages) to collaborate with other agents. "
                        "For external knowledge, you can call mcp_retrieve against Databricks-backed sources. "
                    "Always store key decisions and artifacts to shared memory so teammates can build on your work. "
                    "Read your inbox at the start and reply to any questions directed at you."
                ),
                "cache_control": {"type": "ephemeral"},
            }
        ]

        for _ in range(MAX_ITERATIONS):
            response = self.client.messages.create(
                model=MODEL,
                max_tokens=MAX_TOKENS,
                thinking={"type": "adaptive"},
                system=system,
                tools=self.tools,
                messages=messages,
            )

            messages.append({"role": "assistant", "content": response.content})

            if response.stop_reason == "end_turn":
                for block in response.content:
                    if hasattr(block, "text"):
                        result.output = block.text
                break

            if response.stop_reason != "tool_use":
                result.output = f"Unexpected stop: {response.stop_reason}"
                break

            tool_results: list[dict] = []
            for block in response.content:
                if block.type != "tool_use":
                    continue
                tool_output = self._dispatch_tool(block.name, block.input)

                if self.verbose:
                    agent_logger.info("[%s] %s", block.name, json.dumps(block.input)[:60])

                # Track side effects
                if block.name == "write_file":
                    result.files_written.append(block.input.get("path", ""))
                elif block.name == "run_shell":
                    result.commands_run.append(block.input.get("command", ""))
                elif block.name == "memory_write":
                    result.memory_keys_written.append(block.input.get("key", ""))
                elif block.name == "send_message":
                    result.messages_sent.append(
                        f"{block.input.get('to')}:{block.input.get('subject','')}"
                    )

                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": tool_output,
                })

            messages.append({"role": "user", "content": tool_results})
        else:
            result.output = "Max iterations reached."
            result.success = False

        if self.verbose:
            agent_logger.info("[%s] %s…", self.name.upper(), result.output[:100].replace(chr(10), " "))

        return result

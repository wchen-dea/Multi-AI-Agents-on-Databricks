"""
BaseSpecialistAgent — shared agentic loop using Pydantic AI for tool registration,
typed dependency injection, and structured output validation.

Tool schemas are auto-generated from Python type hints via pydantic-ai; no manual
JSON schema blobs are needed. Dependencies are injected through RunContext[SpecialistDeps].
AgentResult is a validated Pydantic model.
"""

from __future__ import annotations

import logging
import os
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Annotated, Literal

import anthropic
from pydantic import BaseModel, Field
from pydantic_ai import Agent, RunContext
from pydantic_ai.models.anthropic import AnthropicModel, AnthropicModelSettings

from ..utils import SharedMemory, MessageBus, BROADCAST
from ..integrations import DataSourceType, MCPDataSourceGateway
from ..settings import MODEL, MAX_TOKENS
LOGGER = logging.getLogger(__name__)

MessageType = Literal["context", "artifact", "question", "feedback", "decision", "broadcast"]


# ── Typed dependencies ────────────────────────────────────────────────────────

@dataclass
class SpecialistDeps:
    """Dependencies injected into every tool call via RunContext."""
    memory: SharedMemory
    bus: MessageBus
    project_root: Path
    agent_name: str
    verbose: bool
    result: "AgentResult"


# ── Structured output ─────────────────────────────────────────────────────────

class AgentResult(BaseModel):
    specialist: str
    task: str
    output: str = ""
    files_written: list[str] = Field(default_factory=list)
    commands_run: list[str] = Field(default_factory=list)
    memory_keys_written: list[str] = Field(default_factory=list)
    messages_sent: list[str] = Field(default_factory=list)
    success: bool = True
    error: str = ""


# ── Base specialist ───────────────────────────────────────────────────────────

class BaseSpecialistAgent:
    name: str = "specialist"
    role: str = "software engineer"
    system_prompt: str = "You are a helpful software engineer."

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
        self.memory = memory or SharedMemory()
        self.bus = bus or MessageBus()
        self._agent = self._build_agent()

    # ── Agent construction ────────────────────────────────────────────────────

    def _build_agent(self) -> Agent[SpecialistDeps, str]:
        model = AnthropicModel(MODEL, anthropic_client=self.client)
        settings = AnthropicModelSettings(
            max_tokens=MAX_TOKENS,
            thinking={"type": "adaptive"},
        )
        agent: Agent[SpecialistDeps, str] = Agent(
            model,
            deps_type=SpecialistDeps,
            result_type=str,
            system_prompt=(
                f"{self.system_prompt}\n\n"
                "You have access to shared memory (memory_write/read/list) and a message bus "
                "(send_message/read_messages) to collaborate with other agents. "
                "For external knowledge, call mcp_retrieve against Databricks-backed sources. "
                "Always store key decisions and artifacts to shared memory so teammates can build on your work. "
                "Read your inbox at the start and reply to any questions directed at you."
            ),
            model_settings=settings,
        )
        self._register_common_tools(agent)
        self._register_extra_tools(agent)
        return agent

    def _register_common_tools(self, agent: Agent[SpecialistDeps, str]) -> None:  # noqa: C901
        """Register shared file, shell, memory, messaging, and MCP tools."""

        @agent.tool
        def write_file(ctx: RunContext[SpecialistDeps], path: str, content: str) -> str:
            """Write content to a file, creating directories as needed."""
            full = ctx.deps.project_root / path
            full.parent.mkdir(parents=True, exist_ok=True)
            full.write_text(content, encoding="utf-8")
            ctx.deps.result.files_written.append(path)
            if ctx.deps.verbose:
                LOGGER.info("[%s] write_file %s", ctx.deps.agent_name, path)
            return f"Written: {path} ({len(content)} chars)"

        @agent.tool
        def read_file(ctx: RunContext[SpecialistDeps], path: str) -> str:
            """Read the content of a file."""
            full = ctx.deps.project_root / path
            return full.read_text(encoding="utf-8") if full.exists() else f"ERROR: {path} not found"

        @agent.tool
        def run_shell(ctx: RunContext[SpecialistDeps], command: str) -> str:
            """Run a shell command in the project root."""
            proc = subprocess.run(
                command, shell=True, capture_output=True, text=True,
                cwd=ctx.deps.project_root, timeout=120,
            )
            ctx.deps.result.commands_run.append(command)
            if ctx.deps.verbose:
                LOGGER.info("[%s] run_shell %s", ctx.deps.agent_name, command[:60])
            out = proc.stdout[-2000:] if proc.stdout else ""
            err = proc.stderr[-1000:] if proc.stderr else ""
            return (out + ("\n" + err if err else "")).strip() or "(no output)"

        @agent.tool
        def list_files(ctx: RunContext[SpecialistDeps], path: str = ".") -> str:
            """List files in a directory."""
            full = ctx.deps.project_root / path
            if not full.exists():
                return f"ERROR: {path} not found"
            entries = sorted(
                str(p.relative_to(ctx.deps.project_root))
                for p in full.rglob("*") if p.is_file()
            )
            return "\n".join(entries[:100]) or "(empty)"

        @agent.tool
        def mcp_retrieve(
            ctx: RunContext[SpecialistDeps],
            source_type: Literal[
                "databricks_uc",
                "databricks_feature_store",
                "databricks_lakebase_mcp",
            ],
            query: str,
            top_k: int = 5,
        ) -> str:
            """Retrieve knowledge context from Databricks-backed MCP data sources.

            Sources: databricks_uc | databricks_feature_store | databricks_lakebase_mcp.
            """
            if ctx.deps.agent_name == "ml_engineer" and source_type != "databricks_feature_store":
                return (
                    "ERROR: ml_engineer is restricted to Feature Store retrieval only. "
                    "Use source_type='databricks_feature_store'."
                )
            try:
                source = DataSourceType(source_type)
                gateway = MCPDataSourceGateway.from_env(source)
                docs = gateway.retrieve(query=query, top_k=top_k)
                if not docs:
                    return "No documents returned."
                return "\n\n".join(f"[{i}] {doc}" for i, doc in enumerate(docs, start=1))
            except KeyError as exc:
                return (
                    f"ERROR: Missing required environment variable for MCP retrieval: {exc}. "
                    "Required: DATABRICKS_MCP_URL (and optional DATABRICKS_TOKEN/tool vars)."
                )
            except Exception as exc:
                return f"ERROR: MCP retrieval failed: {exc}"

        @agent.tool
        def memory_write(
            ctx: RunContext[SpecialistDeps],
            key: Annotated[str, Field(description="Dot-namespaced key, e.g. 'artifacts.backend.schema'.")],
            value: str,
            summary: Annotated[str, Field(description="One-line description of what this is.")] = "",
        ) -> str:
            """Store a value in shared memory so other agents can read it."""
            ctx.deps.memory.write(key, value, agent=ctx.deps.agent_name, summary=summary)
            ctx.deps.result.memory_keys_written.append(key)
            return f"Stored in memory: {key}"

        @agent.tool
        def memory_read(ctx: RunContext[SpecialistDeps], key: str) -> str:
            """Read a value from shared memory by key."""
            val = ctx.deps.memory.read(key)
            if val is None:
                keys = ctx.deps.memory.list_keys()
                return f"Key '{key}' not found. Available keys: {keys}"
            return str(val)

        @agent.tool
        def memory_list(ctx: RunContext[SpecialistDeps], prefix: str = "") -> str:
            """List all keys in shared memory, optionally filtered by prefix."""
            keys = ctx.deps.memory.list_keys(prefix)
            if not keys:
                return f"No keys{f' with prefix {prefix!r}' if prefix else ''}."
            lines = []
            for k in keys:
                meta = ctx.deps.memory.read_with_meta(k)
                if meta:
                    lines.append(
                        f"  {k}  [{meta['agent']}]  {meta['summary'] or str(meta['value'])[:50]}"
                    )
            return "\n".join(lines)

        @agent.tool
        def send_message(
            ctx: RunContext[SpecialistDeps],
            to: Annotated[
                str,
                Field(
                    description=(
                        "Recipient agent name or '__all__' to broadcast. "
                        "Specialists: frontend, backend, ml_engineer, ai_engineer, "
                        "fullstack, data_engineer, data_scientist, supervisor."
                    )
                ),
            ],
            type: MessageType,
            subject: str,
            content: str,
        ) -> str:
            """Send a typed message to another specialist or broadcast to all."""
            msg = ctx.deps.bus.post(
                from_agent=ctx.deps.agent_name,
                to=to if to != "broadcast" else BROADCAST,
                type=type,  # type: ignore[arg-type]
                subject=subject,
                content=content,
            )
            ctx.deps.result.messages_sent.append(f"{to}:{subject}")
            return f"Message #{msg.id} sent to {to}: {subject!r}"

        @agent.tool
        def read_messages(
            ctx: RunContext[SpecialistDeps],
            unread_only: bool = True,
            type_filter: MessageType | None = None,
        ) -> str:
            """Read messages sent to you (or broadcast to all)."""
            msgs = ctx.deps.bus.read(
                ctx.deps.agent_name,
                unread_only=unread_only,
                type_filter=type_filter,  # type: ignore[arg-type]
            )
            if not msgs:
                return "No messages."
            return "\n\n".join(
                f"--- Message #{m.id} from {m.from_agent} [{m.type}] ---\n"
                f"Subject: {m.subject}\n{m.content}"
                for m in msgs
            )

    def _register_extra_tools(self, agent: Agent[SpecialistDeps, str]) -> None:
        """Override in subclasses to register specialist-specific tools."""

    # ── Public run ────────────────────────────────────────────────────────────

    def run(self, task: str, context: str = "") -> AgentResult:
        agent_logger = LOGGER.getChild(self.name)
        if self.verbose:
            agent_logger.info("[%s] %s", self.name.upper(), task[:70])

        result = AgentResult(specialist=self.name, task=task)

        mem_summary = self.memory.summary()
        unread = self.bus.read(self.name, unread_only=True)
        inbox = (
            "\n".join(
                f"  #{m.id} from={m.from_agent} [{m.type}] {m.subject}: {m.content[:200]}"
                for m in unread
            )
            if unread else "  (none)"
        )

        full_task = (
            f"=== SHARED MEMORY ===\n{mem_summary}\n\n"
            f"=== YOUR INBOX (unread messages from other agents) ===\n{inbox}\n\n"
            f"=== YOUR TASK ===\n{task}"
        )
        if context:
            full_task += f"\n\n=== CONTEXT FROM SUPERVISOR ===\n{context}"

        deps = SpecialistDeps(
            memory=self.memory,
            bus=self.bus,
            project_root=self.project_root,
            agent_name=self.name,
            verbose=self.verbose,
            result=result,
        )

        try:
            run_result = self._agent.run_sync(full_task, deps=deps)
            result.output = run_result.data
        except Exception as exc:
            result.success = False
            result.error = str(exc)
            result.output = f"Agent run failed: {exc}"
            agent_logger.error("[%s] %s", self.name.upper(), exc)

        if self.verbose:
            agent_logger.info(
                "[%s] %s\u2026", self.name.upper(), result.output[:100].replace("\n", " ")
            )

        return result

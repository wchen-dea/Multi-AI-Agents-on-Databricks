"""
SupervisorAgent — orchestrates all specialists with shared memory, message bus,
and a structured feedback loop.

Flow:
  1. Supervisor analyzes the task (reading existing memory for context)
  2. Dispatches sub-tasks to specialists (parallel where independent)
  3. Specialists communicate via memory + message bus
  4. Supervisor can trigger peer review: ask Specialist B to critique Specialist A's work
  5. Originating specialist can revise based on feedback
  6. Supervisor synthesizes final output
"""

from __future__ import annotations

import concurrent.futures
import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import anthropic

from .memory import SharedMemory
from .message_bus import MessageBus, BROADCAST
from .agents import (
    AgentResult,
    AIEngineerAgent,
    BackendAgent,
    DataEngineerAgent,
    DataScientistAgent,
    FrontendAgent,
    FullStackAgent,
    MLEngineerAgent,
)

MODEL = "claude-opus-4-7"
MAX_TOKENS = 8096
MAX_ITERATIONS = 40

LOGGER = logging.getLogger(__name__)

SPECIALIST_REGISTRY = {
    "frontend": FrontendAgent,
    "backend": BackendAgent,
    "ml_engineer": MLEngineerAgent,
    "ai_engineer": AIEngineerAgent,
    "fullstack": FullStackAgent,
    "data_engineer": DataEngineerAgent,
    "data_scientist": DataScientistAgent,
}

# ── Tool schemas ──────────────────────────────────────────────────────────────

def _specialist_tool(name: str, role: str, desc: str) -> dict:
    return {
        "name": f"call_{name}",
        "description": f"Delegate a sub-task to the {role}. {desc}",
        "input_schema": {
            "type": "object",
            "properties": {
                "task": {"type": "string", "description": "Self-contained task for the specialist."},
                "context": {"type": "string", "description": "Optional context from other specialists.", "default": ""},
            },
            "required": ["task"],
        },
    }


SUPERVISOR_TOOLS = [
    _specialist_tool("frontend",      "Frontend Engineer",   "React, TypeScript, Tailwind, a11y, state management."),
    _specialist_tool("backend",       "Backend Engineer",    "FastAPI, databases, auth, REST APIs, Python services."),
    _specialist_tool("ml_engineer",   "ML Engineer",         "PyTorch, scikit-learn, training pipelines, MLOps."),
    _specialist_tool("ai_engineer",   "AI Engineer",         "LLM apps, RAG, Claude tool use, prompt engineering."),
    _specialist_tool("fullstack",     "Full-Stack Engineer", "End-to-end features, Next.js, Docker, CI/CD."),
    _specialist_tool("data_engineer", "Data Engineer",       "ETL/ELT, Airflow, dbt, Spark, streaming, SQL."),
    _specialist_tool("data_scientist","Data Scientist",      "EDA, statistics, A/B tests, forecasting."),
    {
        "name": "call_specialists_parallel",
        "description": "Call multiple independent specialists simultaneously.",
        "input_schema": {
            "type": "object",
            "properties": {
                "calls": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "specialist": {"type": "string", "enum": list(SPECIALIST_REGISTRY)},
                            "task": {"type": "string"},
                            "context": {"type": "string", "default": ""},
                        },
                        "required": ["specialist", "task"],
                    },
                }
            },
            "required": ["calls"],
        },
    },
    # ── Feedback tools ────────────────────────────────────────────────────────
    {
        "name": "request_peer_review",
        "description": (
            "Ask one specialist to review and critique another's work. "
            "The reviewer reads the artifact from shared memory, posts feedback "
            "back to memory and the message bus, and the original author can then revise. "
            "Use this for quality checks, cross-domain validation, and iterative improvement."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "reviewer": {"type": "string", "enum": list(SPECIALIST_REGISTRY), "description": "Specialist who will review."},
                "author": {"type": "string", "description": "Specialist whose work is being reviewed."},
                "artifact_key": {"type": "string", "description": "Shared memory key of the artifact to review."},
                "review_criteria": {"type": "string", "description": "What to look for: correctness, security, performance, etc."},
            },
            "required": ["reviewer", "author", "artifact_key", "review_criteria"],
        },
    },
    {
        "name": "request_revision",
        "description": (
            "Ask a specialist to revise their work based on feedback in shared memory. "
            "Pass the feedback_key (where feedback is stored) and the original artifact_key."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "specialist": {"type": "string", "enum": list(SPECIALIST_REGISTRY)},
                "artifact_key": {"type": "string", "description": "Memory key of the artifact to revise."},
                "feedback_key": {"type": "string", "description": "Memory key where feedback was stored."},
            },
            "required": ["specialist", "artifact_key", "feedback_key"],
        },
    },
    # ── Memory tools (supervisor) ─────────────────────────────────────────────
    {
        "name": "memory_write",
        "description": "Write a value to shared memory from the supervisor.",
        "input_schema": {
            "type": "object",
            "properties": {
                "key": {"type": "string"},
                "value": {"type": "string"},
                "summary": {"type": "string", "default": ""},
            },
            "required": ["key", "value"],
        },
    },
    {
        "name": "memory_read",
        "description": "Read a value from shared memory.",
        "input_schema": {
            "type": "object",
            "properties": {"key": {"type": "string"}},
            "required": ["key"],
        },
    },
    {
        "name": "memory_list",
        "description": "List all keys in shared memory.",
        "input_schema": {
            "type": "object",
            "properties": {"prefix": {"type": "string", "default": ""}},
        },
    },
    {
        "name": "broadcast_message",
        "description": "Broadcast a message to all agents (stored in message bus).",
        "input_schema": {
            "type": "object",
            "properties": {
                "type": {"type": "string", "enum": ["context", "decision", "broadcast"]},
                "subject": {"type": "string"},
                "content": {"type": "string"},
            },
            "required": ["type", "subject", "content"],
        },
    },
    {
        "name": "read_all_messages",
        "description": "Read the full message bus log — all inter-agent exchanges.",
        "input_schema": {"type": "object", "properties": {}},
    },
]

# ── System prompt ─────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """You are a senior engineering supervisor who orchestrates a team of specialist agents using shared memory and a message bus.

Your team:
  frontend       — React, TypeScript, Tailwind, accessibility
  backend        — FastAPI, databases, auth, REST APIs
  ml_engineer    — PyTorch, scikit-learn, MLOps, experiment tracking
  ai_engineer    — Claude/LLM apps, RAG, tool use, prompt engineering
  fullstack      — Next.js, monorepos, Docker, CI/CD
  data_engineer  — ETL/ELT, Airflow, dbt, Spark, streaming
  data_scientist — EDA, statistics, A/B tests, forecasting

Collaboration model:
1. Write high-level decisions and goals to shared memory FIRST so all agents have context.
2. Dispatch sub-tasks — specialists read memory and past messages automatically.
3. Use call_specialists_parallel for independent work; sequential for dependent work.
4. After key artifacts are produced, use request_peer_review for cross-domain validation:
   - Backend schema → ai_engineer reviews for LLM-friendliness
   - ML pipeline → data_scientist reviews feature logic
   - API design → frontend reviews for usability
5. Use request_revision when feedback uncovers real issues worth fixing.
6. Synthesize everything into a final report with files, decisions, and next steps.

Always store important decisions in memory (decisions.*) and final artifacts (artifacts.*).
Be decisive — make reasonable assumptions, don't ask clarifying questions."""


@dataclass
class SupervisorResult:
    task: str
    specialist_results: list[AgentResult] = field(default_factory=list)
    final_output: str = ""
    total_files: list[str] = field(default_factory=list)
    memory_snapshot: dict = field(default_factory=dict)
    message_log: list[dict] = field(default_factory=list)
    success: bool = True


class SupervisorAgent:
    def __init__(
        self,
        client: anthropic.Anthropic,
        project_root: str = ".",
        verbose: bool = True,
        max_workers: int = 4,
    ):
        self.client = client
        self.project_root = str(Path(project_root).resolve())
        self.verbose = verbose
        self.max_workers = max_workers

        # Shared across supervisor + all specialists
        root = Path(self.project_root)
        self.memory = SharedMemory(root / ".agent_memory.json")
        self.bus = MessageBus(root / ".agent_messages.json")

        self._specialist_results: list[AgentResult] = []

    # ── Specialist factory ────────────────────────────────────────────────────

    def _make_specialist(self, name: str) -> Any:
        cls = SPECIALIST_REGISTRY[name]
        return cls(
            client=self.client,
            project_root=self.project_root,
            verbose=self.verbose,
            memory=self.memory,
            bus=self.bus,
        )

    def _call_specialist(self, name: str, task: str, context: str = "") -> AgentResult:
        agent = self._make_specialist(name)
        result = agent.run(task=task, context=context)
        self._specialist_results.append(result)
        return result

    def _call_parallel(self, calls: list[dict]) -> list[AgentResult]:
        results: list[AgentResult] = []
        with concurrent.futures.ThreadPoolExecutor(max_workers=self.max_workers) as pool:
            futures = {
                pool.submit(self._call_specialist, c["specialist"], c["task"], c.get("context", "")): c
                for c in calls
            }
            for fut in concurrent.futures.as_completed(futures):
                try:
                    results.append(fut.result())
                except Exception as e:
                    c = futures[fut]
                    results.append(AgentResult(
                        specialist=c["specialist"], task=c["task"],
                        output=f"ERROR: {e}", success=False, error=str(e),
                    ))
        return results

    # ── Feedback helpers ──────────────────────────────────────────────────────

    def _request_peer_review(
        self, reviewer: str, author: str, artifact_key: str, review_criteria: str
    ) -> str:
        artifact = self.memory.read(artifact_key)
        if artifact is None:
            return f"ERROR: artifact key '{artifact_key}' not in memory. Available: {self.memory.list_keys()}"

        review_task = (
            f"Review the following artifact produced by the {author} agent.\n\n"
            f"ARTIFACT KEY: {artifact_key}\n"
            f"ARTIFACT:\n{artifact}\n\n"
            f"REVIEW CRITERIA: {review_criteria}\n\n"
            f"Provide structured feedback:\n"
            f"1. What is correct and well-done\n"
            f"2. Issues found (bugs, security, performance, design)\n"
            f"3. Specific actionable suggestions\n\n"
            f"Store your feedback in memory under 'feedback.{artifact_key}' "
            f"and send a 'feedback' message to the {author} agent."
        )

        if self.verbose:
            LOGGER.info("[PEER REVIEW] %s reviews %s's %s", reviewer, author, artifact_key)

        result = self._call_specialist(reviewer, review_task)
        return json.dumps({
            "reviewer": reviewer,
            "artifact_key": artifact_key,
            "feedback_key": f"feedback.{artifact_key}",
            "review_output": result.output,
            "success": result.success,
        }, indent=2)

    def _request_revision(self, specialist: str, artifact_key: str, feedback_key: str) -> str:
        artifact = self.memory.read(artifact_key)
        feedback = self.memory.read(feedback_key)

        if artifact is None:
            return f"ERROR: artifact '{artifact_key}' not in memory."
        if feedback is None:
            return f"ERROR: feedback '{feedback_key}' not in memory."

        revision_task = (
            f"Revise your previous work based on peer feedback.\n\n"
            f"ORIGINAL ARTIFACT ({artifact_key}):\n{artifact}\n\n"
            f"FEEDBACK ({feedback_key}):\n{feedback}\n\n"
            f"Address all issues raised. Store the revised artifact back to memory "
            f"under '{artifact_key}' (overwrite) and also write files as needed. "
            f"Send a 'context' message to supervisor summarizing what you changed."
        )

        if self.verbose:
            LOGGER.info("[REVISION] %s revising %s", specialist, artifact_key)

        result = self._call_specialist(specialist, revision_task)
        return json.dumps({
            "specialist": specialist,
            "artifact_key": artifact_key,
            "revision_output": result.output,
            "files_written": result.files_written,
            "success": result.success,
        }, indent=2)

    # ── Tool dispatch ─────────────────────────────────────────────────────────

    def _dispatch_tool(self, tool_name: str, inputs: dict) -> str:
        # Parallel dispatch
        if tool_name == "call_specialists_parallel":
            calls = inputs["calls"]
            if self.verbose:
                LOGGER.info("[PARALLEL] %s", [c["specialist"] for c in calls])
            results = self._call_parallel(calls)
            return json.dumps(
                [{"specialist": r.specialist, "output": r.output,
                  "files_written": r.files_written, "memory_keys": r.memory_keys_written,
                  "success": r.success}
                 for r in results],
                indent=2,
            )

        # Feedback loop
        if tool_name == "request_peer_review":
            return self._request_peer_review(
                inputs["reviewer"], inputs["author"],
                inputs["artifact_key"], inputs["review_criteria"],
            )
        if tool_name == "request_revision":
            return self._request_revision(
                inputs["specialist"], inputs["artifact_key"], inputs["feedback_key"],
            )

        # Memory (supervisor)
        if tool_name == "memory_write":
            self.memory.write(inputs["key"], inputs["value"], agent="supervisor", summary=inputs.get("summary", ""))
            return f"Stored: {inputs['key']}"
        if tool_name == "memory_read":
            val = self.memory.read(inputs["key"])
            return str(val) if val is not None else f"Key '{inputs['key']}' not found."
        if tool_name == "memory_list":
            keys = self.memory.list_keys(inputs.get("prefix", ""))
            return "\n".join(keys) if keys else "(empty)"

        # Message bus (supervisor)
        if tool_name == "broadcast_message":
            msg = self.bus.broadcast(
                from_agent="supervisor",
                type=inputs["type"],  # type: ignore
                subject=inputs["subject"],
                content=inputs["content"],
            )
            return f"Broadcast #{msg.id}: {inputs['subject']}"
        if tool_name == "read_all_messages":
            return self.bus.summary()

        # Single specialist
        specialist_name = tool_name.removeprefix("call_")
        if specialist_name not in SPECIALIST_REGISTRY:
            return f"ERROR: unknown tool {tool_name}"

        if self.verbose:
            LOGGER.info("[%s] %s", specialist_name.upper(), inputs.get("task", "")[:70])

        result = self._call_specialist(
            specialist_name,
            inputs.get("task", ""),
            inputs.get("context", ""),
        )
        return json.dumps({
            "specialist": result.specialist,
            "output": result.output,
            "files_written": result.files_written,
            "memory_keys": result.memory_keys_written,
            "messages_sent": result.messages_sent,
            "success": result.success,
        }, indent=2)

    # ── Main loop ─────────────────────────────────────────────────────────────

    def run(self, task: str) -> SupervisorResult:
        if self.verbose:
            LOGGER.info("[SUPERVISOR] %s", task[:80])

        sr = SupervisorResult(task=task)
        mem_summary = self.memory.summary()

        preamble = f"=== EXISTING SHARED MEMORY ===\n{mem_summary}\n\n=== TASK ===\n{task}"
        messages: list[dict] = [{"role": "user", "content": preamble}]
        system = [{"type": "text", "text": SYSTEM_PROMPT, "cache_control": {"type": "ephemeral"}}]

        for _ in range(MAX_ITERATIONS):
            response = self.client.messages.create(
                model=MODEL,
                max_tokens=MAX_TOKENS,
                thinking={"type": "adaptive"},
                system=system,
                tools=SUPERVISOR_TOOLS,
                messages=messages,
            )

            messages.append({"role": "assistant", "content": response.content})

            if response.stop_reason == "end_turn":
                for block in response.content:
                    if hasattr(block, "text"):
                        sr.final_output = block.text
                break

            if response.stop_reason != "tool_use":
                sr.final_output = f"Unexpected stop: {response.stop_reason}"
                break

            tool_results: list[dict] = []
            for block in response.content:
                if block.type != "tool_use":
                    continue
                if self.verbose and block.name not in ("memory_read", "memory_list"):
                    LOGGER.info("[%s] %s", block.name, json.dumps(block.input)[:80])
                output = self._dispatch_tool(block.name, block.input)
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": output,
                })
            messages.append({"role": "user", "content": tool_results})
        else:
            sr.final_output = "Max iterations reached."
            sr.success = False

        sr.specialist_results = self._specialist_results
        sr.total_files = [f for r in self._specialist_results for f in r.files_written]
        sr.memory_snapshot = self.memory.snapshot()
        sr.message_log = [m.to_dict() for m in self.bus.all_messages()]

        return sr

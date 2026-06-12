"""Shared orchestration contracts used by supervisor implementations."""

from __future__ import annotations

from .agents.registry import SPECIALIST_CATALOG, SPECIALIST_NAMES


def _specialist_tool(name: str, role: str, description: str) -> dict:
    return {
        "name": f"call_{name}",
        "description": f"Delegate a sub-task to the {role}. {description}",
        "input_schema": {
            "type": "object",
            "properties": {
                "task": {
                    "type": "string",
                    "description": "Self-contained task for the specialist.",
                },
                "context": {
                    "type": "string",
                    "description": "Optional context from other specialists.",
                    "default": "",
                },
            },
            "required": ["task"],
        },
    }


def build_supervisor_tools() -> list[dict]:
    specialist_tools = [
        _specialist_tool(spec.key, spec.role, spec.description)
        for spec in SPECIALIST_CATALOG
    ]
    shared_tools = [
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
                                "specialist": {
                                    "type": "string",
                                    "enum": list(SPECIALIST_NAMES),
                                },
                                "task": {"type": "string"},
                                "context": {
                                    "type": "string",
                                    "default": "",
                                },
                            },
                            "required": ["specialist", "task"],
                        },
                    }
                },
                "required": ["calls"],
            },
        },
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
                    "reviewer": {
                        "type": "string",
                        "enum": list(SPECIALIST_NAMES),
                        "description": "Specialist who will review.",
                    },
                    "author": {
                        "type": "string",
                        "description": "Specialist whose work is being reviewed.",
                    },
                    "artifact_key": {
                        "type": "string",
                        "description": "Shared memory key of the artifact to review.",
                    },
                    "review_criteria": {
                        "type": "string",
                        "description": "What to look for: correctness, security, performance, etc.",
                    },
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
                    "specialist": {
                        "type": "string",
                        "enum": list(SPECIALIST_NAMES),
                    },
                    "artifact_key": {
                        "type": "string",
                        "description": "Memory key of the artifact to revise.",
                    },
                    "feedback_key": {
                        "type": "string",
                        "description": "Memory key where feedback was stored.",
                    },
                },
                "required": ["specialist", "artifact_key", "feedback_key"],
            },
        },
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
                    "type": {
                        "type": "string",
                        "enum": ["context", "decision", "broadcast"],
                    },
                    "subject": {"type": "string"},
                    "content": {"type": "string"},
                },
                "required": ["type", "subject", "content"],
            },
        },
        {
            "name": "read_all_messages",
            "description": "Read the full message bus log - all inter-agent exchanges.",
            "input_schema": {"type": "object", "properties": {}},
        },
    ]
    return specialist_tools + shared_tools


SUPERVISOR_TOOLS = build_supervisor_tools()

SYSTEM_PROMPT = """You are a senior engineering supervisor who orchestrates a team of specialist agents using shared memory and a message bus.

Your team:
  frontend       - React, TypeScript, Tailwind, accessibility
  backend        - FastAPI, databases, auth, REST APIs
  ml_engineer    - PyTorch, scikit-learn, MLOps, experiment tracking
  ai_engineer    - Claude/LLM apps, RAG, tool use, prompt engineering
  fullstack      - Next.js, monorepos, Docker, CI/CD
  data_engineer  - ETL/ELT, Airflow, dbt, Spark, streaming
  data_scientist - EDA, statistics, A/B tests, forecasting

Collaboration model:
1. Write high-level decisions and goals to shared memory FIRST so all agents have context.
2. Dispatch sub-tasks - specialists read memory and past messages automatically.
3. Use call_specialists_parallel for independent work; sequential for dependent work.
4. After key artifacts are produced, use request_peer_review for cross-domain validation:
   - Backend schema -> ai_engineer reviews for LLM-friendliness
   - ML pipeline -> data_scientist reviews feature logic
   - API design -> frontend reviews for usability
5. Use request_revision when feedback uncovers real issues worth fixing.
6. Synthesize everything into a final report with files, decisions, and next steps.

Always store important decisions in memory (decisions.*) and final artifacts (artifacts.*).
Be decisive - make reasonable assumptions, don't ask clarifying questions."""

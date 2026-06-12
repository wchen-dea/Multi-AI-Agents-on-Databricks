"""Runtime factory for explicit environment-driven application wiring."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import anthropic

from .supervisor import SupervisorAgent
from .supervisor_langgraph import LangGraphSupervisorAgent
from .utils import MessageBus, SharedMemory

ImplementationType = Literal["classic", "langgraph"]


@dataclass(frozen=True)
class RuntimeConfig:
    project_root: str
    implementation: ImplementationType = "classic"
    max_workers: int = 4
    verbose: bool = True
    anthropic_api_key: str = ""
    mongodb_uri: str | None = None
    mongodb_db: str | None = None
    mongodb_collection: str | None = None
    rabbitmq_url: str | None = None


@dataclass
class RuntimeContext:
    config: RuntimeConfig
    client: anthropic.Anthropic
    memory: SharedMemory
    bus: MessageBus
    supervisor: SupervisorAgent | LangGraphSupervisorAgent


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def config_from_env(
    project_root: str,
    implementation: ImplementationType | None = None,
    max_workers: int | None = None,
    verbose: bool = True,
) -> RuntimeConfig:
    return RuntimeConfig(
        project_root=project_root,
        implementation=implementation or os.getenv("AI_APP_IMPLEMENTATION", "classic"),
        max_workers=max_workers if max_workers is not None else _env_int("SUPERVISOR_MAX_WORKERS", 4),
        verbose=verbose,
        anthropic_api_key=os.getenv("ANTHROPIC_API_KEY", ""),
        mongodb_uri=os.getenv("MONGODB_URI"),
        mongodb_db=os.getenv("MONGODB_DB"),
        mongodb_collection=os.getenv("MONGODB_MEMORY_COLLECTION"),
        rabbitmq_url=os.getenv("RABBITMQ_URL"),
    )


def build_runtime(config: RuntimeConfig) -> RuntimeContext:
    if not config.anthropic_api_key:
        raise ValueError("ANTHROPIC_API_KEY not set. Copy .env.example to .env and add your key.")

    project = Path(config.project_root)
    project.mkdir(parents=True, exist_ok=True)

    client = anthropic.Anthropic(api_key=config.anthropic_api_key)
    memory = SharedMemory(
        uri=config.mongodb_uri,
        db_name=config.mongodb_db,
        collection_name=config.mongodb_collection,
    )
    bus = MessageBus(url=config.rabbitmq_url)

    supervisor_cls: type[SupervisorAgent | LangGraphSupervisorAgent]
    supervisor_cls = SupervisorAgent if config.implementation == "classic" else LangGraphSupervisorAgent
    supervisor = supervisor_cls(
        client=client,
        project_root=str(project.resolve()),
        verbose=config.verbose,
        max_workers=config.max_workers,
        memory=memory,
        bus=bus,
    )

    return RuntimeContext(
        config=config,
        client=client,
        memory=memory,
        bus=bus,
        supervisor=supervisor,
    )

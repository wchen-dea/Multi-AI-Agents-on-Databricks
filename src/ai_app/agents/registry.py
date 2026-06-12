"""Specialist catalog and registry helpers."""

from __future__ import annotations

from dataclasses import dataclass

from .ai_engineer import AIEngineerAgent
from .backend import BackendAgent
from .data_engineer import DataEngineerAgent
from .data_scientist import DataScientistAgent
from .frontend import FrontendAgent
from .fullstack import FullStackAgent
from .ml_engineer import MLEngineerAgent


@dataclass(frozen=True)
class SpecialistSpec:
    key: str
    role: str
    description: str
    agent_cls: type


SPECIALIST_CATALOG: tuple[SpecialistSpec, ...] = (
    SpecialistSpec(
        key="frontend",
        role="Frontend Engineer",
        description="React, TypeScript, Tailwind, a11y, state management.",
        agent_cls=FrontendAgent,
    ),
    SpecialistSpec(
        key="backend",
        role="Backend Engineer",
        description="FastAPI, databases, auth, REST APIs, Python services.",
        agent_cls=BackendAgent,
    ),
    SpecialistSpec(
        key="ml_engineer",
        role="ML Engineer",
        description="PyTorch, scikit-learn, training pipelines, MLOps.",
        agent_cls=MLEngineerAgent,
    ),
    SpecialistSpec(
        key="ai_engineer",
        role="AI Engineer",
        description="LLM apps, RAG, Claude tool use, prompt engineering.",
        agent_cls=AIEngineerAgent,
    ),
    SpecialistSpec(
        key="fullstack",
        role="Full-Stack Engineer",
        description="End-to-end features, Next.js, Docker, CI/CD.",
        agent_cls=FullStackAgent,
    ),
    SpecialistSpec(
        key="data_engineer",
        role="Data Engineer",
        description="ETL/ELT, Airflow, dbt, Spark, streaming, SQL.",
        agent_cls=DataEngineerAgent,
    ),
    SpecialistSpec(
        key="data_scientist",
        role="Data Scientist",
        description="EDA, statistics, A/B tests, forecasting.",
        agent_cls=DataScientistAgent,
    ),
)

SPECIALIST_REGISTRY = {spec.key: spec.agent_cls for spec in SPECIALIST_CATALOG}
SPECIALIST_NAMES = tuple(spec.key for spec in SPECIALIST_CATALOG)

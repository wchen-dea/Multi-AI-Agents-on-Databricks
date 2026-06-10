# Agentic Application

Agentic Application is a supervisor-driven multi-agent engineering system powered by Claude (`claude-opus-4-7`).

The platform coordinates specialist agents through shared memory, typed messaging, and feedback loops so teams can generate production-ready code and artifacts collaboratively.

## Why This Project

- Multi-agent orchestration with explicit specialist roles.
- Collaboration primitives for memory sharing and inter-agent messaging.
- Databricks-backed retrieval through an MCP gateway.
- Packaging and deployment support with `uv`, wheel builds, and Databricks CI/CD.

## Specialist Agents

| Agent | Focus |
| --- | --- |
| frontend | React, TypeScript, Tailwind, accessibility |
| backend | FastAPI, SQLAlchemy, auth, API design |
| ml_engineer | Model training pipelines and MLOps workflows |
| ai_engineer | LLM applications, RAG, tool use, prompts |
| fullstack | End-to-end product implementation |
| data_engineer | ETL/ELT, orchestration, data platform |
| data_scientist | EDA, experiments, statistical analysis |

## Quick Start

```bash
uv sync
cp .env.example .env
# set required variables (at minimum: ANTHROPIC_API_KEY)
uv run multi-ai-agent --task "build a user authentication system"
```

## Useful Commands

```bash
make sync
make run TASK="build a RAG chatbot"
make run-quiet TASK="build a data pipeline"
make run-reset TASK="redesign the recommendation engine"
make build-wheel
```

For runtime operations and deployment details, see the runbook.

## Documentation

- [Architecture](docs/architecture.md)
- [Runbook](docs/runbook.md)
- [ADRs](docs/adrs/README.md)
- [Container Setup](container/README.md)

## Project Structure

```text
agentic-application/
├── src/
│   └── ai_app/
│       ├── main.py
│       ├── supervisor.py
│       ├── integrations/
│       ├── agents/
│       ├── utils/
│       │   ├── memory.py
│       │   └── message_bus.py
│       └── resources/
├── docs/
│   ├── adrs/
│   ├── architecture.md
│   └── runbook.md
├── container/
│   ├── Dockerfile
│   ├── docker-compose.yml
│   └── README.md
├── .github/workflows/
├── scripts/
├── pyproject.toml
└── uv.lock
```

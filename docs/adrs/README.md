# Architecture Decision Records (ADRs)

This directory contains Architecture Decision Records for major technical decisions in the project.

## ADR Index

- [ADR-0001: Use Supervisor-Specialist Multi-Agent Orchestration](0001-supervisor-specialist-orchestration.md)
- [ADR-0002: Use MongoDB for Shared Memory](0002-mongodb-shared-memory.md)
- [ADR-0003: Use RabbitMQ for Inter-Agent Messaging](0003-rabbitmq-message-bus.md)
- [ADR-0004: Define Databricks MCP Gateway Constraints](0004-databricks-mcp-gateway-constraints.md)
- [ADR-0005: Use Pydantic AI for Tool Registration, Typed Deps, and Structured Output](0005-pydantic-ai-tool-layer.md)

## ADR Status Values

- Proposed: Decision is under review.
- Accepted: Decision is approved and in use.
- Superseded: Decision is replaced by a newer ADR.
- Deprecated: Decision remains documented but should not be used for new work.

## How To Add A New ADR

1. Copy `template.md` to a new numbered file, such as `0006-short-title.md`.
2. Fill in metadata plus the required section order:
   Context, Decision, Consequences, Alternatives Considered.
3. Add the new ADR link to the ADR Index in this file.

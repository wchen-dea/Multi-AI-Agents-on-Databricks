# ADR-0003: Use RabbitMQ for Inter-Agent Messaging

- Status: Accepted
- Date: 2026-06-09
- Deciders: Agentic Application maintainers
- Technical Story: N/A

## Context

Agents require asynchronous, typed communication with reliable delivery semantics. Earlier file-based messaging approaches were insufficient for durable inboxes and operational observability in multi-agent workflows.

## Decision

Use RabbitMQ as the primary inter-agent message bus, implemented in `src/ai_app/utils/message_bus.py`.

- Configure broker connection through `RABBITMQ_URL`.
- Use a durable topic exchange `agent_messages`.
- Create durable per-agent inbox queues (`agent_inbox.<agent>`) and an audit queue (`agent_inbox.__audit__`).

## Consequences

- Improves message durability, routing flexibility, and multi-agent reliability.
- Enables stronger operational debugging through an audit-friendly messaging topology.
- Adds an infrastructure dependency on RabbitMQ and related configuration.

## Alternatives Considered

- File-backed message log: Minimal setup but weak delivery guarantees and scaling.
- Direct in-process messaging: Simpler but unsuitable for durable, decoupled workflows.

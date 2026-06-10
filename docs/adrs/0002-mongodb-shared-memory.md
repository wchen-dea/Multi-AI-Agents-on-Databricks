# ADR-0002: Use MongoDB for Shared Memory

- Status: Accepted
- Date: 2026-06-09
- Deciders: Agentic Application maintainers

## Context

Agents need a shared, persistent memory store for artifacts, decisions, and feedback history. The store must support concurrent updates, simple key-based access, and history-oriented inspection.

## Decision

Use MongoDB as the shared memory backend, implemented in `src/ai_app/utils/memory.py`.

- Connection is configured through `MONGODB_URI`.
- Logical grouping uses `MONGODB_DB` and `MONGODB_MEMORY_COLLECTION`.
- Writes are append-oriented with metadata for chronology and auditing.

## Consequences

- Durable, queryable storage that supports multi-agent workflows and reruns.
- Straightforward operational model with common local/container deployment paths.
- Introduces dependency on MongoDB availability and configuration.

## Alternatives Considered

- In-memory process store: Fast but non-durable and not suitable across runs.
- File-backed JSON store: Easy to start but weak concurrency and scaling characteristics.

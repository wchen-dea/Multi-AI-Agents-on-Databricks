# ADR-0001: Use Supervisor-Specialist Multi-Agent Orchestration

- Status: Accepted
- Date: 2026-06-09
- Deciders: Agentic Application maintainers
- Technical Story: N/A

## Context

The application must coordinate multiple specialist agents while preserving role-specific behavior and maintaining high-level quality control. A single flat agent cannot provide consistent domain separation or robust peer-review loops for complex engineering tasks.

## Decision

Adopt a supervisor-specialist architecture with explicit control and collaboration boundaries:

- A `SupervisorAgent` decomposes user tasks, routes work, requests peer review, and synthesizes outputs.
- Specialist agents (`frontend`, `backend`, `ml_engineer`, `ai_engineer`, `fullstack`, `data_engineer`, `data_scientist`) execute delegated tasks.
- Shared coordination primitives are provided through shared memory and typed inter-agent messaging.

## Consequences

- Improves task decomposition, role clarity, and output quality through explicit review and revision loops.
- Increases orchestration complexity and depends on stable collaboration primitives.
- Makes specialist behavior easier to evolve independently over time.

## Alternatives Considered

- Single general-purpose agent: Simpler design but weaker specialization and quality controls.
- Fully decentralized peer-to-peer agents: Flexible but harder to govern, audit, and tune.

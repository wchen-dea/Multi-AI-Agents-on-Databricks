# ADR-0004: Define Databricks MCP Gateway Constraints

- Status: Accepted
- Date: 2026-06-09
- Deciders: Agentic Application maintainers
- Technical Story: N/A

## Context

The project integrates multiple Databricks-backed retrieval sources behind a single gateway (`MCPDataSourceGateway`). Without explicit constraints, source behavior, payload shape, and runtime configuration can drift over time. That drift can lead to fragile integrations and unclear agent expectations.

## Decision

Constrain Databricks MCP integration to a read-oriented, source-typed gateway contract:

- `MCPDataSourceGateway.from_env(...)` requires `DATABRICKS_MCP_URL` and supports optional `DATABRICKS_TOKEN`.
- Source selection is explicit via `DataSourceType`:
  - `databricks_uc`
  - `databricks_feature_store`
  - `databricks_lakebase_mcp`
- Tool names are configurable by environment and default to:
  - `unity_catalog_search`
  - `feature_store_search`
  - `lakebase_search`
- Retrieval requests are normalized to include catalog/schema/query/top_k plus source-specific table and column fields.
- Response parsing supports `documents`, nested `result.documents`, and fallback `rows` extraction.
- Gateway scope is retrieval only; index generation and data writes remain external pipeline responsibilities.

## Consequences

- Agents interact through one stable retrieval API (`gateway.retrieve(...)`).
- Environment-driven configuration improves deployment flexibility without code changes.
- Clear source boundaries reduce accidental cross-source behavior.
- Additional response-shape handling increases adapter complexity, but it also improves runtime resilience.

## Alternatives Considered

- Separate gateway per source type: Simpler per adapter, but duplicates orchestration logic.
- Hard-code MCP tool names and payload schema: Lower flexibility across environments.
- Allow write/index operations in gateway: Increases coupling and operational risk in runtime path.

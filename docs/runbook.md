# Runbook

## Purpose

This runbook covers day-to-day operation of Agentic Application, including local execution, validation, packaging, and Databricks CI/CD rollout.

## Local Setup

```bash
uv sync
cp .env.example .env
```

Required local environment variable:

- ANTHROPIC_API_KEY

Optional runtime variables for MCP data retrieval:

- DATABRICKS_MCP_URL
- DATABRICKS_TOKEN
- DATABRICKS_MCP_UC_TOOL
- DATABRICKS_MCP_FEATURE_STORE_TOOL
- DATABRICKS_MCP_LAKEBASE_TOOL
- UC_CATALOG
- UC_SCHEMA
- UC_KB_TABLE
- UC_FEATURE_TABLE
- UC_FEATURE_TEXT_COLUMN
- UC_FEATURE_SCORE_COLUMN
- LAKEBASE_TABLE

## Common Commands

```bash
# run a task
uv run multi-ai-agent --task "build a RAG chatbot"

# include memory and message logs
uv run multi-ai-agent --task "build a churn model" --show-memory --show-messages

# reset state before run
uv run multi-ai-agent --task "redesign recommendation engine" --reset-memory
```

Make targets:

```bash
make sync
make init-env
make run TASK="build a user authentication system"
make run-quiet TASK="build a data pipeline"
make run-reset TASK="redesign the recommendation engine"
make build-wheel
make clean
```

## Validation Checklist

```bash
uv run python -m compileall src
uv run multi-ai-agent --help
make build-wheel
```

Expected artifact:

- dist/agentic_application-&lt;version&gt;-py3-none-any.whl

## CI/CD Workflow

Pipeline:

- .github/workflows/databricks-cicd.yml

Deploy helper:

- scripts/databricks_deploy.sh

Stages:

1. Build and validate wheel on Python 3.13.
2. Upload wheel artifact from dist/.
3. Deploy to staging Databricks App.
4. Optional production deploy via workflow_dispatch input deploy_prod=true.

## GitHub Environment Secrets

Required secrets in staging and production environments:

- DATABRICKS_HOST
- DATABRICKS_TOKEN
- DATABRICKS_APP_NAME
- DATABRICKS_VOLUME_PATH
- RUNTIME_ENV_B64

RUNTIME_ENV_B64 generation:

```bash
cat .env.runtime | base64
```

DATABRICKS_VOLUME_PATH format:

```text
<catalog>/<schema>/<volume>
```

## Deployment and Rollout Behavior

scripts/databricks_deploy.sh performs:

1. Validation of required Databricks variables.
2. Upload of wheel artifact to:
  dbfs:/Volumes/&lt;catalog&gt;/&lt;schema&gt;/&lt;volume&gt;/releases/&lt;commit_sha&gt;/
3. Databricks App deploy from generated bundle at .databricks/app_bundle.
4. App start and status retrieval for rollout visibility.

## Troubleshooting

- Build fails on compileall:
  - Run uv sync --frozen and re-run compile checks.
- Wheel missing in dist:
  - Run uv build --wheel and check pyproject metadata.
- Databricks deploy command fails:
  - Verify databricks CLI version and workspace app support.
  - Validate DATABRICKS_HOST, DATABRICKS_TOKEN, and DATABRICKS_APP_NAME.
- Runtime config not applied:
  - Recreate RUNTIME_ENV_B64 from the correct .env.runtime content.

## Operational Notes

- Shared state files are .agent_memory.json and .agent_messages.json in the project output root.
- Use --reset-memory for clean reruns to avoid stale coordination context.
- For production rollout, require manual workflow dispatch with deploy_prod=true.

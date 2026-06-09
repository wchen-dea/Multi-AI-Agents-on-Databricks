#!/usr/bin/env bash
set -euo pipefail

APP_ENV="${1:-}"
WHEEL_PATH="${2:-}"

if [[ -z "$APP_ENV" ]]; then
  echo "Usage: scripts/databricks_deploy.sh <environment> <wheel_path>"
  exit 1
fi

if [[ -z "$WHEEL_PATH" || ! -f "$WHEEL_PATH" ]]; then
  echo "ERROR: wheel path is required and must exist."
  exit 1
fi

: "${DATABRICKS_HOST:?Missing DATABRICKS_HOST}"
: "${DATABRICKS_TOKEN:?Missing DATABRICKS_TOKEN}"
: "${DATABRICKS_APP_NAME:?Missing DATABRICKS_APP_NAME}"
: "${DATABRICKS_VOLUME_PATH:?Missing DATABRICKS_VOLUME_PATH}"

if ! command -v databricks >/dev/null 2>&1; then
  echo "ERROR: databricks CLI is not installed in this runner."
  exit 1
fi

RELEASE_ID="${GITHUB_SHA:-local}"
WHEEL_NAME="$(basename "$WHEEL_PATH")"
WHEEL_DIR_URI="dbfs:/Volumes/${DATABRICKS_VOLUME_PATH}/releases/${RELEASE_ID}"
WHEEL_URI="${WHEEL_DIR_URI}/${WHEEL_NAME}"

mkdir -p .databricks/app_bundle/dist
cp "$WHEEL_PATH" ".databricks/app_bundle/dist/${WHEEL_NAME}"

if [[ -n "${RUNTIME_ENV_B64:-}" ]]; then
  echo "$RUNTIME_ENV_B64" | base64 --decode > .databricks/app_bundle/.env.runtime
fi

cat > .databricks/app_bundle/deploy-manifest.json <<EOF
{
  "app_name": "${DATABRICKS_APP_NAME}",
  "environment": "${APP_ENV}",
  "release_id": "${RELEASE_ID}",
  "wheel_uri": "${WHEEL_URI}",
  "wheel_name": "${WHEEL_NAME}"
}
EOF

# Upload wheel artifact to Unity Catalog Volume path for traceability.
databricks fs mkdirs "$WHEEL_DIR_URI"
databricks fs cp "$WHEEL_PATH" "$WHEEL_URI" --overwrite

# Deploy Databricks app source bundle for this release.
# Note: this expects Databricks Apps support in your workspace and CLI version.
databricks apps deploy "$DATABRICKS_APP_NAME" --source-code-path .databricks/app_bundle

# Apply rollout by starting/restarting the app on the target environment.
databricks apps start "$DATABRICKS_APP_NAME"

# Emit deployment status for pipeline logs.
databricks apps get "$DATABRICKS_APP_NAME"

echo "Deployment completed for ${APP_ENV}: ${DATABRICKS_APP_NAME} (${RELEASE_ID})"

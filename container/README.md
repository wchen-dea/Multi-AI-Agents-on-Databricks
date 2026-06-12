# Container Setup

This folder provides Docker Compose orchestration for:

- `mongodb`: MongoDB backend for shared memory.
- `rabbitmq`: RabbitMQ message bus for inter-agent communication.
- `app`: Agent application container.

## Prerequisites

- Docker Desktop or Docker Engine with Compose V2.
- ANTHROPIC_API_KEY exported in your shell, or provided via Compose environment.

## Run

From repository root:

```bash
export ANTHROPIC_API_KEY=your_anthropic_api_key_here
docker compose -f container/docker-compose.yml up --build
```

By default, Compose configures:

- MONGODB_URI as mongodb://mongodb:27017
- RABBITMQ_URL as `amqp://USERNAME:PASSWORD@rabbitmq:5672/`
- AI_APP_IMPLEMENTATION as classic (unless overridden)
- SUPERVISOR_MAX_WORKERS as 4 (unless overridden)

Optional task overrides:

```bash
APP_TASK="build a churn prediction model" \
APP_PROJECT="/workspace/output" \
APP_WORKERS=4 \
AI_APP_IMPLEMENTATION=langgraph \
docker compose -f container/docker-compose.yml up --build
```

If MongoDB or RabbitMQ is temporarily unavailable, the app can still run using in-memory fallback collaboration backends.

RabbitMQ management UI:

- <http://localhost:15672> (guest/guest by default)

## Stop and cleanup

```bash
docker compose -f container/docker-compose.yml down
```

Remove MongoDB persisted data too:

```bash
docker compose -f container/docker-compose.yml down -v
```

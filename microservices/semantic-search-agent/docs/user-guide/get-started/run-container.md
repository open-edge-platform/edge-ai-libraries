# Run With Docker Compose Tool

Use this path to run the Semantic Search Agent in a container. The REST API is exposed on host port `8080`, and Prometheus metrics on port `9090`.

## Before You Start

- Copy and configure the environment file:
  ```bash
  cp .env.example .env
  ```
- Edit `.env` to set `DEFAULT_MATCHING_STRATEGY` and the appropriate VLM backend variables. For exact-only matching, no VLM variables are needed.
- Review `config/inventory.json` and `config/orders.json`, and update them to match your data. These files are mounted read-only into the container.
- An optional `redis` service is included in the Compose file. It starts alongside the main service but is only used when `CACHE_BACKEND=redis`.

## Start the Service

From the `microservices/semantic-search-agent/` directory:

```bash
# Build the Docker image
make docker-build

# Start containers in detached mode
make docker-up
```

The Makefile selects the `.env` file in the project root automatically. To run Compose directly, pass the file explicitly from the `docker/` directory, because Compose does not read the parent directory by itself:

```bash
cd docker
docker compose --env-file ../.env build
docker compose --env-file ../.env up -d
```

Every variable in the `.env` file is passed to the container. The container listens on fixed ports `8080` and `9090`; `API_PORT` and `METRICS_PORT` change only the host ports.

### Run without a GPU

The Compose file maps the host GPU device `/dev/dri` into the container. If the host has no `/dev/dri` (for example, when using `exact` matching or a remote backend), remove the `devices` and `group_add` entries from `docker/docker-compose.yml` before starting the containers.

## Check Status

```bash
# Verify process status
docker compose -f docker/docker-compose.yml ps

# Hit health check
curl http://localhost:8080/api/v1/health
```

### Follow Logs

To tail the logs of the running service:

```bash
make docker-logs
```

Or directly with Docker Compose tool:

```bash
docker compose -f docker/docker-compose.yml logs -f semantic-service
```

### Restart after Configuration Updates

If you only modify `config/inventory.json` or `config/orders.json`, restart the container:

```bash
docker compose -f docker/docker-compose.yml restart semantic-service
```

If you modify the environment variables in `.env`, recreate the containers:

```bash
make docker-down
make docker-up
```

### Stop the Service

```bash
make docker-down
```

## Prometheus Metrics

When the service is running, Prometheus metrics are available at:

```bash
curl http://localhost:9090/metrics
```

## API Documentation

The service exposes the interactive Swagger UI documentation while running:

```
http://localhost:8080/docs
```

## API Use Cases and Examples

For API use cases, request examples, and endpoint details, see the [API Reference](../api-reference.md).

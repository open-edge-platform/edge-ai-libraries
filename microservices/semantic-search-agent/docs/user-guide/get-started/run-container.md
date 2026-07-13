# Run With Docker Compose

Use this path to run the Semantic Search Agent inside a container. The REST API is exposed on host port `8080` and Prometheus metrics on port `9090`.

## Before You Start

- Copy and configure the environment file:
  ```bash
  cp .env.example .env
  ```
- Edit `.env` to set `DEFAULT_MATCHING_STRATEGY` and the appropriate VLM backend variables. For exact-only matching, no VLM variables are needed.
- Review `config/inventory.json` and `config/orders.json` and update them to match your data. These files are mounted read-only into the container.
- An optional `redis` service is included in the Compose file. It is started alongside the main service but is only used when `CACHE_BACKEND=redis`.

## Start the Service

From the `semantic-search-agent/` directory:

```bash
# Build the Docker image
cd docker
docker compose build

# Start containers in detached mode
docker compose up -d
```

Or using the Makefile from the project root:

```bash
make docker-build
make docker-up
```

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

Or directly with Docker Compose:

```bash
docker compose -f docker/docker-compose.yml logs -f semantic-service
```

### Restart after configuration updates

If you only change `config/inventory.json` or `config/orders.json`, restart the container:

```bash
docker compose -f docker/docker-compose.yml restart semantic-service
```

If you modify environment variables in `.env`, recreate the containers:

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

The service exposes interactive Swagger UI documentation while running:

```
http://localhost:8080/docs
```

## API Use Cases and Examples

For API use cases, request examples, and endpoint details, see the [API Reference](../api-reference.md).

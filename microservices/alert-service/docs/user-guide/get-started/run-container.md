# Run With Docker Compose

Use this path to run the Alert Service inside a container. The REST API is exposed on host port `8000`.

## Before You Start

- Edit `config/config.yaml` with the subscriptions, deduplication strategies, and delivery channels you want. See [configuration.md](configuration.md) for detailed descriptions.
- Initialize your local environment file using `make init-env` to create a `.env` file from `.env.example`.
- In embedded MQTT mode (`MQTT_MODE=embedded`), Docker Compose starts a Mosquitto broker container (`mqtt`) alongside the alert service on port `1883` (and port `9001` for WebSockets).
- If you use an external MQTT broker, configure `MQTT_MODE=external` and provide host details in `.env`.

## Start the Service

From the `alert-service/` directory:

```bash
# Initialize .env (if not done already)
make init-env

# Build the docker container
make build

# Start the services in detached mode
make up
```

## Check Status

```bash
# Verify process status
docker compose -f docker/docker-compose.yml ps

# Hit health check
curl http://localhost:8000/api/v1/health
```

### Follow Logs

To tail the logs of the running service:

```bash
make logs
```

### Restart after configuration updates

If you only change `config/config.yaml`, you can restart the container:

```bash
docker compose -f docker/docker-compose.yml restart alert-service
```

If you modify environment variables in `.env`, recreate the containers:

```bash
make up
```

### Stop the Service

```bash
make down
```

## API Use Cases and Examples

For API use cases, request examples, and endpoint details, see the [API Reference](../api-reference.md).

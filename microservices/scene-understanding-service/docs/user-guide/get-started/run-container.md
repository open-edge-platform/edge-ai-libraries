# Run With Docker Compose

Use this path to run the service in a container. The API is exposed on port
`8082`. To rebuild the image from source, see
[build-from-source.md](build-from-source.md).

## Before You Start

- Prepare your `scene-config.yaml` and `rules.yaml` in a local `./configs`
  directory. For configuration details, see [configuration.md](configuration.md).
- Make sure a SceneScape deployment (MQTT broker + REST API) is reachable from
  the container, and that the `mqtt` / `scenescape_api` blocks in
  `scene-config.yaml` point at it.
- If `mqtt.use_tls: true`, mount your SceneScape CA cert at `/app/secrets`.

## Minimal Compose Service

```yaml
services:
  scene-understanding-service:
    image: intel/scene-understanding-service:latest
    ports:
      - "8082:8082"
    environment:
      STORE_ID: my_store_01
      SCENESCAPE_API_USER: admin
      SCENESCAPE_API_PASSWORD: ${SCENESCAPE_API_PASSWORD}
    volumes:
      - ./configs:/app/configs:ro          # scene-config.yaml + rules.yaml (required)
      - ./results:/app/results             # optional: persisted results/evidence
    restart: unless-stopped
```

For tighter isolation you can mount only the two files the service reads:

```yaml
    volumes:
      - ./configs/scene-config.yaml:/app/configs/scene-config.yaml:ro
      - ./configs/rules.yaml:/app/configs/rules.yaml:ro
```

## Full Integration

When your stack includes a SeaweedFS frame store, a behavioral-analysis
worker, and an alert-service, add the `seaweedfs` and `alert_service` blocks
to `scene-config.yaml` and place the services on a shared Docker network so
they resolve each other by container name. Behavioral analysis is integrated
over MQTT (topics `ba/requests` / `ba/results`) — no direct URL wiring is
needed.

## Start

```bash
docker compose up -d
```

## Check Status

```bash
docker compose ps
curl --noproxy '*' http://127.0.0.1:8082/health
curl --noproxy '*' http://127.0.0.1:8082/api/v1/lp/status
```

### Follow Logs

```bash
docker compose logs -f scene-understanding-service
```

### Restart

If you changed only the config files:

```bash
docker compose restart scene-understanding-service
```

For a clean restart:

```bash
docker compose down
docker compose up -d
```

### Stop

```bash
docker compose down
```

## API Use Cases and Examples

For endpoint details and examples, see the [API Reference](../api-reference.md).

## Notes

- Container host port: `8082`; API base path: `/api/v1/lp`.
- The service reads `scene-config.yaml` and `rules.yaml` from `/app/configs`
  (override with `CONFIG_DIR`). A mounted `./configs` volume overrides the
  bundled samples.
- There is no hard startup dependency on SceneScape — the service starts and
  retries the MQTT connection in the background.
- Use `GET /api/v1/lp/status` (or `GET /health`) for readiness gating in
  `depends_on`.

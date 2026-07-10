# Troubleshooting

## Service Will Not Start

- Confirm port `8082` is not already in use:

  ```bash
  ss -ltnp | grep 8082
  ```

- Confirm both config files exist and are valid YAML. The service loads
  `scene-config.yaml` and `rules.yaml` from `/app/configs` (or `CONFIG_DIR`,
  or the `configs/` directory next to the source in standalone runs).

## No Sessions / No Alerts Appear

This usually means the service is running but not receiving SceneScape events.

- Verify the MQTT broker is reachable and that `mqtt.host` / `mqtt.port` in
  `scene-config.yaml` are correct.
- Check the logs for connection retries:

  ```bash
  docker compose logs -f scene-understanding-service
  ```

- Confirm the SceneScape topic patterns in `scene-config.yaml` match your
  SceneScape deployment.
- Confirm the configured `cameras` match the camera names SceneScape
  publishes — persons seen only on non-configured cameras are not tracked.

## Zones Not Resolving

Zone auto-discovery runs at startup against the SceneScape REST API.

- Confirm `scenescape_api.base_url` is correct and reachable.
- Provide `SCENESCAPE_API_USER` / `SCENESCAPE_API_PASSWORD`.
- The zone **names** in `scene-config.yaml` must match the SceneScape region
  names exactly.
- Re-trigger discovery without restarting:

  ```bash
  curl --noproxy '*' -X POST http://127.0.0.1:8082/api/v1/lp/zones/discover
  ```

## MQTT TLS Connection Fails

- TLS is used only when `mqtt.use_tls: true`. When off, `mqtt.ca_cert_path` is
  ignored.
- When on, the CA cert is resolved relative to `/app`
  (e.g. `secrets/certs/scenescape-ca.pem` → `/app/secrets/certs/scenescape-ca.pem`).
- The cert is not in the image — mount it via a volume
  (e.g. `./secrets:/app/secrets:ro`). If the resolved path does not exist, the
  connection fails at startup.

## `health` Endpoint Fails

- For Docker: check `docker compose ps` and
  `docker compose logs -f scene-understanding-service`.
- For standalone: confirm the process is running and bound to the expected
  host/port (defaults `0.0.0.0:8082`).
- If you are behind a corporate proxy, pass `--noproxy '*'` to `curl` when
  hitting `127.0.0.1`.

## Alerts Not Delivered

- Alerts are forwarded to the alert-service at `ALERT_SERVICE_URL` (or
  `alert_service.base_url`). Confirm that service is reachable.
- If `alert_service.enabled` is `false`, alerts are generated but not
  forwarded. The `/api/v1/lp/alerts` endpoints will then return empty.

## Behavioral Analysis Not Triggering

- A `rules.yaml` rule must contain an `escalate` action targeting
  `behavioral_analysis`. Without it, no `ba/requests` are published.
- The `seaweedfs` block must be present so evidence frames can be captured.
- The behavioral-analysis worker must share the same MQTT broker
  (`ba/requests` / `ba/results`).

## Supporting Resources

- [Configuration Guide](./get-started/configuration.md)
- [API Reference](./api-reference.md)
- [System Requirements](./get-started/system-requirements.md)

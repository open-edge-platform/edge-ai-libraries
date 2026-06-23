# Troubleshooting

## Service Will Not Start

- **Port Conflict**: Confirm that port `8000` (FastAPI) or `1883` (Mosquitto) is not already in use by other processes:
  ```bash
  # Check port 8000
  ss -ltnp | grep 8000
  
  # Check port 1883
  ss -ltnp | grep 1883
  ```
- **Invalid YAML**: Ensure `config/config.yaml` is valid YAML. Syntactical errors will prevent the config loader from initializing subscriptions and starting the service.

## Health Endpoint Fails

- **Docker runs**: Run `docker compose -f docker/docker-compose.yml ps` and `make logs` to inspect startup errors.
- **Proxy blocks**: If you are behind a corporate proxy, `curl` commands hitting `localhost` or `127.0.0.1` might be blocked. Add `--noproxy '*'` to your command:
  ```bash
  curl --noproxy '*' http://localhost:8000/api/v1/health
  ```

## Deduplication Not Suppressing Alerts

- **Case Sensitivity**: Subscription matching is case-sensitive. If an incoming payload specifies `alert_type: "concealment"` but your `config.yaml` defines `alert_type: CONCEALMENT`, the alert will not match the subscription rule.
- **Field Matching Paths**: Ensure the list under `dedup.fields` matches the nesting hierarchy in the payload using dot-notation. For example, if you send `{"metadata": {"poi_id": "123"}}`, the config path must be `metadata.poi_id`.
- **Missing Fields**: If a field is missing and `dedup.on_missing` is set to `skip`, deduplication is skipped entirely and the alert will always be delivered. Check application logs for warning lines like:
  `Dedup field '...' missing for alert_type=..., skipping dedup`.

## MQTT Broker Failures

- **Wrong Mode**: Ensure `MQTT_MODE` in `.env` is set correctly:
  - Use `embedded` when running Mosquitto via Docker Compose (the alert service connects to it using the service name `mqtt`).
  - Use `external` when running Mosquitto on the host or connecting to a remote host.
- **Auth Errors**: If connecting to an external broker, ensure `MQTT_USERNAME` and `MQTT_PASSWORD` are defined correctly in `.env`.

## Webhook Failures

- Check logs using `make logs` to locate delivery warning or error entries:
  `Delivery failed: type=webhook alert_type=... attempt=1/3`
- Ensure the destination Webhook URL is accessible from inside the container network.

## Supporting Resources

- [Configuration Guide](./get-started/configuration.md)
- [API Reference](./api-reference.md)
- [System Requirements](./get-started/system-requirements.md)

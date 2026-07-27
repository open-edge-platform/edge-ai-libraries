# Troubleshooting

This guide covers common runtime failures observed from the source code, Docker configuration, and service startup logic.

---

## Service Fails to Start — SeaweedFS Not Ready

**Symptom:**
```
SeaweedFS not ready, retrying in 2s (attempt 1): ...
Failed to ensure bucket after retries: ...
```

**Cause:** The service attempts to create/verify the SeaweedFS bucket on startup and retries up to 5 times. If SeaweedFS is still initializing or unreachable, startup will fail after all retries.

**Resolution:**
- Ensure the SeaweedFS service is running and healthy before starting the behavioral-analysis service.
- In Docker Compose, the `depends_on: seaweedfs: condition: service_healthy` setting handles this automatically — verify the SeaweedFS healthcheck is passing.
- Check `SEAWEEDFS_ENDPOINT` is correct and reachable from within the container (e.g. `http://seaweedfs:8333`).

```bash
# Verify SeaweedFS is reachable
curl http://seaweedfs:8333
```

---

## Service Fails to Start — YOLO Model Not Found

**Symptom:**
```
ValueError: Expected .xml model path, got: /models/yolo_models/yolo26n-pose/yolo26n-pose.xml
FileNotFoundError: Model file not found
```

**Cause:** The YOLO-Pose OpenVINO IR model (`.xml` + `.bin`) is not present at the path specified by `YOLO_POSE_MODEL`.

**Resolution:**
- Download the model and place it at `./models/yolo_models/yolo26n-pose/yolo26n-pose.xml` (and `.bin`).
- Ensure the volume mount in Docker Compose is correct: `${DOWNLOADED_MODEL_PATH:-./models}:/models:ro`.
- The model path inside the container is `/models/yolo_models/yolo26n-pose/yolo26n-pose.xml`.

```bash
# Verify model file exists on the host
ls -la ./models/yolo_models/yolo26n-pose/
```

---

## Service Health and Connectivity

**Symptom:** Service starts but doesn't process requests.

**Cause:** SeaweedFS bucket is unavailable or MQTT connection failed.

**Resolution:**
- Verify SeaweedFS is running: `curl http://seaweedfs:8333`.
- Check `SEAWEEDFS_ENDPOINT` and `SEAWEEDFS_BUCKET` environment variables.
- Verify the MQTT broker is running and accessible.
- Check `MQTT_HOST` and `MQTT_PORT` environment variables.
- Review logs: `docker logs behavioral-analysis` or application stdout.

---

## VLM Analysis Not Running / `vlm_confirmed` Always `null`

**Symptom:** `vlm_confirmed` is always `null` in responses.

**Cause:** VLM is disabled, or the OVMS endpoint is unreachable.

**Resolution:**
- Check `VLM_ENABLED=true` is set.
- Verify `vlm_enabled: true` in `config/patterns.yaml` under `vlm_settings` and for the specific pattern.
- Confirm the OVMS service is running and responding: `curl http://ovms-vlm:8001/v2/health/ready`.
- Check `VLM_ENDPOINT` points to the correct host and port.
- In Docker Compose, `depends_on: ovms-vlm: condition: service_healthy` ensures OVMS is ready before the service starts.

---

## VLM Circuit Breaker Open

**Symptom in logs:**
```
VLM circuit breaker open — skipping analysis (cooldown: 30s remaining)
```

**Cause:** The VLM client encountered 3 or more consecutive failures and opened the circuit breaker. Requests are not sent to OVMS for the 30-second cooldown period.

**Resolution:**
- Check OVMS health: `curl http://ovms-vlm:8001/v2/health/ready`.
- Verify the model is loaded: `curl http://ovms-vlm:8001/v2/models`.
- Once OVMS recovers, the circuit breaker will auto-probe after 30 seconds.

---

## MQTT Consumer Not Receiving Messages

**Symptom:** Service starts but no analyses are triggered from `ba/requests`.

**Cause:** MQTT connection failure or incorrect topic configuration.

**Resolution:**
- Check logs for: `BA queue consumer connected, subscribed to ba/requests`.
- If you see `BA queue consumer MQTT connect failed, rc=...`, the broker is unreachable.
- Verify `MQTT_HOST` and `MQTT_PORT` environment variables.
- Confirm the MQTT broker is running and accessible from the container.
- Verify the upstream service is publishing to the same topic (`ba/requests` or the value of `BA_REQUEST_TOPIC`).

```bash
# Test broker reachability (from inside container)
python3 -c "import socket; s=socket.create_connection(('broker.scenescape.intel.com', 1883), timeout=5); print('OK')"
```

---

## Container Exits Immediately After Starting

**Symptom:** Container exits with code 1 shortly after launch.

**Resolution:**
- Inspect logs: `docker logs <container-name>`.
- Common causes:
  - Missing `SEAWEEDFS_ENDPOINT` environment variable.
  - YOLO model file missing at the mounted path.
  - Python import error (missing dependency — rebuild the image).

```bash
docker logs behavioral-analysis --tail 50
```

---

## Log Locations

| Context | Location |
|---|---|
| Docker Compose | `docker compose logs behavioral-analysis -f` |
| Running container | `docker logs <container-id> -f` |
| Standalone | Standard output (stdout); redirect with `> app.log 2>&1` |

---

## Debugging Steps

1. Check the health endpoint: `curl http://localhost:8085/health`.
2. Check service logs for startup errors (model loading, bucket creation, MQTT connection).
3. Verify all required services are running: SeaweedFS, OVMS (if VLM enabled), MQTT broker.
4. Confirm all environment variables are set (see [Configuration](get-started/configuration.md)).
5. Confirm the YOLO model files exist at the configured path.
6. Enable debug logging: set `LOG_LEVEL=DEBUG` and restart.
7. Use `POST /api/v1/analyze` with a known entity to isolate whether the issue is frame storage, pose extraction, or VLM.

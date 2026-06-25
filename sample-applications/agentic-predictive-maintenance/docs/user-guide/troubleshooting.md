# Troubleshooting

## Containers started but detections are not appearing

**Symptom**: The dashboard shows no detection events and `GET /detections/summary` returns zero totals.

**Steps to diagnose:**

1. Check that the DL Streamer container is running and processing the video:

   ```bash
   docker logs -f apm-dlstreamer
   ```

   Look for log lines showing inference results. If the container exited, the video file may be missing.

2. Confirm that `sample.mp4` exists in the expected location:

   ```bash
   ls apps/pipeline-defect-detection/resources/videos/
   ```

   If the file is missing, run the data preparation script described in [Get Started](./get-started.md#step-3--prepare-sample-data).

3. Check that MQTT messages are flowing from DL Streamer to the broker:

   ```bash
   docker exec apm-mqtt-broker mosquitto_sub -t 'dlstreamer/detections'
   ```

   If no messages appear, the DL Streamer pipeline may not have been triggered. Start it manually:

   ```bash
   curl -X POST http://localhost:8554/pipelines/user_defined_pipelines/pipeline_defect_detection \
     -H "Content-Type: application/json" -d '{}'
   ```

## Agent run stays in `in_progress` and never completes

**Symptom**: A run triggered via `POST /api/agents/runs` shows `status: in_progress` indefinitely.

**Steps to diagnose:**

1. Check the agent service logs:

   ```bash
   docker logs apm-agent
   ```

2. If `LLM_MODE=llm`, check that the VLM service is healthy:

   ```bash
   curl http://localhost:8010/health
   ```

   If the VLM service is unhealthy or still loading the model, wait for it to finish. The first startup can take several minutes while the model is downloaded and converted.

3. To test the pipeline without the VLM service, switch to fallback mode:

   ```bash
   ./setup.sh --stop
   LLM_MODE=fallback ./setup.sh --use-case pipeline-defect-detection
   ```

## Dashboard shows no runs or returns an error

**Symptom**: The UI displays no run history or `GET /api/agents/runs` returns an error.

**Check**: Verify that Nginx is routing requests correctly:

```bash
curl http://localhost:8080/api/agents/runs
```

If that fails, check the Nginx container:

```bash
docker logs apm-nginx
```

Also confirm that the agent service itself is healthy:

```bash
curl http://localhost:5002/health
```

## VLM service is unhealthy after startup

**Symptom**: `apm-vlm` shows as unhealthy in `docker ps` even after several minutes.

**Cause**: Model download and conversion on first startup can take 10–30 minutes depending on model size, hardware, and network speed.

**Steps:**

1. Check progress in the VLM logs:

   ```bash
   docker logs -f apm-vlm
   ```

2. If you need to run quickly without waiting, use fallback mode:

   ```bash
   ./setup.sh --stop
   LLM_MODE=fallback ./setup.sh --use-case pipeline-defect-detection
   ```

3. If you see permission errors related to `/app/ov-model`, remove the model cache volume and restart:

   ```bash
   ./setup.sh --stop
   docker volume rm apm_model_cache
   ./setup.sh --use-case pipeline-defect-detection
   ```

## Storage service is unhealthy

**Symptom**: `apm-storage` shows as unhealthy and detections are not being persisted.

**Check the storage service logs:**

```bash
docker logs apm-storage
```

Common causes:
- Port 5001 is already in use on the host — change `STORAGE_PORT` in the `.env` file.
- The `apm_sqlite_data` volume has a permission issue. Remove the volume and restart:

  ```bash
  ./setup.sh --clean-data
  ./setup.sh --use-case pipeline-defect-detection
  ```

## Quick Verification Checklist

Run these commands in order after startup to verify each stage of the pipeline:

```bash
# 1. All containers healthy?
docker ps --format "table {{.Names}}\t{{.Status}}"

# 2. Detections stored?
curl http://localhost:8080/api/storage/detections/summary

# 3. Agent service reachable?
curl http://localhost:8080/api/agents/runs

# 4. Trigger one agent run manually
RUN_ID=$(curl -s -X POST http://localhost:8080/api/agents/runs \
  -H "Content-Type: application/json" -d '{}' | python3 -c "import sys,json; print(json.load(sys.stdin)['run_id'])")
echo "Run ID: $RUN_ID"

# 5. Wait for completion and check result
sleep 15
curl http://localhost:8080/api/agents/runs/$RUN_ID | python3 -m json.tool
```

## Common Error Summary

| Symptom | Likely Cause | Action |
|---------|-------------|--------|
| No detections in storage | `sample.mp4` missing or pipeline not triggered | Prepare data and trigger DL Streamer pipeline |
| Agent run stuck in `in_progress` | VLM service unhealthy or still loading | Check `docker logs apm-vlm` or switch to fallback mode |
| UI shows no runs | Nginx proxy issue or agent service down | Check `docker logs apm-nginx` and `docker logs apm-agent` |
| `apm-storage` unhealthy | Port conflict or volume permission issue | Check port 5001 or run `./setup.sh --clean-data` |
| VLM container restarts repeatedly | GPU out of memory or unsupported model | Switch to CPU inference or use a smaller model |

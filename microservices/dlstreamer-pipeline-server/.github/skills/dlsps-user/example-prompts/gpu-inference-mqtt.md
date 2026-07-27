# Example: GPU-Accelerated Inference with MQTT Publishing

**Configure environment:**
```bash
cd edge-ai-libraries/microservices/dlstreamer-pipeline-server/docker
export RENDER_GID=$(stat -c "%g" /dev/dri/render* | head -1)
export MQTT_HOST=<MQTT_BROKER_IP>
export MQTT_PORT=1883
```

**Mount GPU config** in `docker-compose.yml`:
```yaml
volumes:
  - "../configs/sample_gpu_decode_and_inference/config.json:/home/pipeline-server/config.json"
```

GPU pipeline uses: `vah264dec ! vapostproc ! video/x-raw(memory:VAMemory) ! gvadetect device=GPU pre-process-backend=va-surface-sharing ... vapostproc ! video/x-raw ! appsink`

> **Important:** `vapostproc ! video/x-raw` before `appsink` is required for RTSP/MQTT compatibility with GPU pipelines.

**Start service:**
```bash
docker compose up
```

**Launch pipeline (GPU + MQTT):**
```bash
curl http://localhost:8080/pipelines/user_defined_pipelines/pallet_defect_detection \
  -X POST -H 'Content-Type: application/json' \
  -d '{"source":{"uri":"file:///home/pipeline-server/resources/videos/warehouse.avi","type":"uri"},"destination":{"metadata":{"type":"mqtt","topic":"detections","publish_frame":true},"frame":{"type":"rtsp","path":"gpu-det"}}}'
```

Note: `device=GPU` is already set in the pipeline config, so it's omitted from the request body.

Returns instance ID, e.g. `"b7e89335fadd11ec9f360242c0a86003"`.

**View RTSP stream:** `rtsp://localhost:8554/gpu-det` (open with ffplay or VLC)

**Check status:** `curl http://localhost:8080/pipelines/status`

**Stop:** `curl -X DELETE http://localhost:8080/pipelines/<instance_id>`

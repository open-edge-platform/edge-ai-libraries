# Example: Object Detection on Video File (CPU + RTSP)

**Start service:**
```bash
cd edge-ai-libraries/microservices/dlstreamer-pipeline-server/docker
docker compose up
```

**Launch pipeline:**
```bash
curl http://localhost:8080/pipelines/user_defined_pipelines/pallet_defect_detection \
  -X POST -H 'Content-Type: application/json' \
  -d '{"source":{"uri":"file:///home/pipeline-server/resources/videos/warehouse.avi","type":"uri"},"destination":{"frame":{"type":"rtsp","path":"det"}},"parameters":{"detection-properties":{"device":"CPU"}}}'
```

Returns instance ID, e.g. `"a6d67224eacc11ec9f360242c0a86003"`.

**View RTSP stream:** `rtsp://localhost:8554/det` (open with ffplay or VLC)

**Check status:** `curl http://localhost:8080/pipelines/status`

**Stop:** `curl -X DELETE http://localhost:8080/pipelines/<instance_id>`

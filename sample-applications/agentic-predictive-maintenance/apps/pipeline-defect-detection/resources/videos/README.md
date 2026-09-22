# Sample Video Resources

Place your sample video file here as `sample.mp4`.

The DL Streamer pipeline uses:
```
location=/home/pipeline-server/resources/videos/sample.mp4
```

## Obtaining a Sample Video

- Use any MP4 video showing pipeline/tube infrastructure for testing.
- For weld defect detection: use video showing weld seams or joints.
- For solar panel inspection: use aerial or ground-level panel imagery.

## RTSP Camera Input

To use a live RTSP camera instead of a video file, start the desired pipeline
via the DL Streamer REST API with `{auto_source}` resolved to your RTSP URL:

```bash
curl -X POST http://localhost:8080/pipelines/pipeline_defect_detection_gpu \
  -H "Content-Type: application/json" \
  -d '{"source": {"uri": "rtsp://camera-ip:554/stream", "type": "uri"}}'
```

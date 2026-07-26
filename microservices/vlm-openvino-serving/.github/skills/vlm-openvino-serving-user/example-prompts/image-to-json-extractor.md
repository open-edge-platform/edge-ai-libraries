Build an image-to-JSON extractor that converts a visual scene into structured data using the VLM service.

- Bring the VLM service up if it isn't already (prebuilt image, CPU is fine); wait for /health.
- Send each image with a prompt demanding strict JSON only: {"objects": [{"name": ..., "count": ...}], "visible_text": [...], "risks": [...]} — empty arrays when nothing applies.
- Parse the response; on a JSON parse failure retry once with "Return only valid JSON."; append each record to scene.json.

Validate the application using:
- Model Qwen/Qwen2.5-VL-3B-Instruct on http://localhost:9764/v1.
- Frames extracted with ffmpeg from person-bicycle-car-detection.mp4 in Intel's sample-videos repo (download: https://github.com/intel-iot-devkit/sample-videos/raw/refs/heads/master/<name>.mp4) — pick frames where the pedestrian, the cyclist, and the car each appear.

Expected results:
- Every frame yields parseable JSON; objects include person/bicycle/car with plausible counts in the frames where they appear.
- Fields with nothing to report are empty arrays (e.g. visible_text), not invented values.

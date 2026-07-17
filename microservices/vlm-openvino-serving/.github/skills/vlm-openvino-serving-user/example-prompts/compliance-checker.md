Build a compliance checker that grades an image against a fixed checklist using the VLM service.

- Bring the VLM service up if it isn't already (prebuilt image, CPU is fine); wait for /health.
- Send the image with the checklist and demand strict JSON only: {"checks": [{"item": ..., "pass": true|false, "evidence": ...}], "overall_pass": ...} — one entry per checklist item, evidence describing what is visible.
- Parse the response; on a JSON parse failure retry once with "Return only valid JSON.", then pretty-print the verdict.

Validate the application using:
- Model Qwen/Qwen2.5-VL-3B-Instruct on http://localhost:9764/v1.
- A frame extracted from worker-zone-detection.mp4 in Intel's sample-videos repo (download: https://github.com/intel-iot-devkit/sample-videos/raw/refs/heads/master/<name>.mp4).
- Checklist: "worker wears a hard hat", "worker wears a hi-vis vest", "no person lying on the ground".

Expected results:
- Valid JSON with exactly the three checklist entries; pass values consistent with what the frame actually shows, each with evidence describing the visible worker.
- overall_pass is the logical AND of the per-item verdicts.

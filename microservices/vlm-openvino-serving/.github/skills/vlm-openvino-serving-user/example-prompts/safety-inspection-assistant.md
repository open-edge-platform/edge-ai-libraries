Build a safety inspection assistant that checks camera frames for PPE and unsafe scenes using the VLM service.

- Bring the VLM service up if it isn't already (prebuilt image, CPU is fine); wait for /health before sending.
- For each frame, send one chat completion with an image part plus a rules prompt, e.g.: "You are a safety inspector. Rules: (1) every person must wear a hard hat, (2) every person must wear a hi-vis vest, (3) walkways and exits must be clear. List visible violations as bullets citing the rule number. If there are none, reply exactly: No violations."
- Print one report per frame.

Validate the application using:
- Model Qwen/Qwen2.5-VL-3B-Instruct on http://localhost:9764/v1.
- Frames extracted with ffmpeg (e.g. one every 5 s) from worker-zone-detection.mp4 in Intel's sample-videos repo (download: https://github.com/intel-iot-devkit/sample-videos/raw/refs/heads/master/<name>.mp4).

Expected results:
- /health returns 200 and model matches GET /v1/models before the first request.
- Each report cites only the numbered rules and correctly states whether the worker's hard hat and vest are actually visible in that frame; frames with no people yield exactly "No violations".
- The assistant does not invent people, PPE, or hazards that are not in the frame.

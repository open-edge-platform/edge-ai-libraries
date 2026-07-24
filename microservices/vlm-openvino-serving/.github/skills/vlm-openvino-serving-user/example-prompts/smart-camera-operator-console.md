Build a smart camera operator console: an operator asks natural-language questions about the latest frame of a (simulated) live camera, answered by the VLM service.

- Bring the VLM service up if it isn't already (prebuilt image, CPU is fine); wait for /health.
- Simulate the camera by extracting one frame every N seconds from a looping video file; keep only the newest frame with its timestamp (the VLM has no memory — each answer comes from the frame you send).
- On each operator question ("Is the loading bay clear?", "How many people are visible?"), send the newest frame plus the question as one chat completion and print the answer tagged with the frame timestamp.

Validate the application using:
- Model Qwen/Qwen2.5-VL-3B-Instruct on http://localhost:9764/v1.
- one-by-one-person-detection.mp4 from Intel's sample-videos repo (download: https://github.com/intel-iot-devkit/sample-videos/raw/refs/heads/master/<name>.mp4) as the simulated feed — people enter the area one at a time.

Expected results:
- Repeatedly asking "Is the area clear of people?" flips between yes and no as the sampled frame changes with people entering and leaving.
- Every answer is tagged with the timestamp of the frame it was computed from; stale frames are never sent.

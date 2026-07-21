Build a retail shelf assistant that reads shelf/aisle images and reports stock issues using the VLM service.

- Bring the VLM service up if it isn't already (prebuilt image, CPU is fine); wait for /health.
- Send each aisle image with the prompt: "You are a store-shelf auditor. Report: (1) visibly empty or sparsely stocked shelf sections, (2) misplaced or fallen items, (3) overall tidiness. Answer in three short sections; say 'none observed' where nothing applies."
- Print the audit per image.

Validate the application using:
- Model Qwen/Qwen2.5-VL-3B-Instruct on http://localhost:9764/v1.
- Frames extracted with ffmpeg from store-aisle-detection.mp4 (and optionally fruit-and-vegetable-detection.mp4) in Intel's sample-videos repo (download: https://github.com/intel-iot-devkit/sample-videos/raw/refs/heads/master/<name>.mp4).

Expected results:
- A three-section audit per frame that only describes shelves, products, and people actually visible in the overhead aisle view.
- Sections with nothing to report say "none observed" instead of inventing issues.
- Rerunning on the same frame gives substantively consistent findings.

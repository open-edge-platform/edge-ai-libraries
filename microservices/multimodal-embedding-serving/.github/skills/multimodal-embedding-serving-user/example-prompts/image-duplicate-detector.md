Build an image duplicate / near-duplicate detector using the multimodal embedding service (embeddings only — no LLM). It scans a folder of product images, CCTV frames, or documents and flags pairs with high similarity — useful for media cleanup, quality control, and dataset deduplication.

- Bring the embedding service up if it isn't already (prebuilt image, CPU is fine).
- Embed every image in the folder via POST /embeddings (input.type = image_base64 for local files, image_url for hosted ones), one request per image.
- Compute pairwise cosine similarity across all image vectors.
- Flag pairs above a similarity threshold — e.g. ≥ 0.99 exact/re-encoded duplicate, ≥ 0.95 near-duplicate (resized, cropped, watermarked, re-compressed); make both thresholds configurable.
- Group flagged pairs into clusters and write duplicates.json: one entry per cluster with a kept file and its duplicates [{filename, similarity}], plus a list of unique images.

Validate the application using:
- Model CLIP/clip-vit-b-32 on http://localhost:9777.
- A folder built from Intel's sample videos (download: https://github.com/intel-iot-devkit/sample-videos/raw/refs/heads/master/<name>.mp4): extract one frame each (ffmpeg) from 5–6 different videos (e.g. bottle-detection, store-aisle-detection, person-bicycle-car-detection, worker-zone-detection, classroom), then add an exact copy of one frame and a resized/re-compressed copy of another.

Expected results:
- The exact copy and the re-encoded copy are each paired with their original above the threshold; frames from different videos are not paired.
- duplicates.json groups them into clusters with one keeper each and per-pair similarity scores.
- All embeddings are 512-dim vectors and model in each request matches the loaded model.

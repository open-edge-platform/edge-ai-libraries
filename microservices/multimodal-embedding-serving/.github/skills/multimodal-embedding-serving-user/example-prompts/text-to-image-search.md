Build a text-to-image search demo — "Google Lens for a local folder" — using the multimodal embedding service (embeddings only — no LLM). The user types a phrase like "person wearing a red helmet" and gets the matching images back.

- Bring the embedding service up if it isn't already (prebuilt image, CPU is fine); the model must be multimodal — confirm image support via GET /model/capabilities (QwenText models are text-only).
- Embed every image in the folder once via POST /embeddings (input.type = image_base64 for local files) and keep {filename, vector} in an in-memory index — the service does not store vectors; add a local vector DB in the app layer if persistence is needed.
- Embed each text query with the same model (input.type = text) and rank images by cosine similarity — CLIP text and image vectors share one embedding space.
- Print the top-3 filenames with scores for each query.

Validate the application using:
- Model CLIP/clip-vit-b-32 on http://localhost:9777.
- An image folder built from Intel's sample videos (download: https://github.com/intel-iot-devkit/sample-videos/raw/refs/heads/master/<name>.mp4): ~5 frames each (ffmpeg) from person-bicycle-car-detection.mp4, store-aisle-detection.mp4, and fruit-and-vegetable-detection.mp4.
- Queries: "a person riding a bicycle on a street", "shelves in a store aisle", "fresh fruit and vegetables".

Expected results:
- Each query's top hits come from the matching video's frames (the bicycle query ranks person-bicycle-car frames first, and so on).
- Text and image embeddings are both 512-dim and produced by the same loaded model; the script errors out rather than mixing models between corpus and query.

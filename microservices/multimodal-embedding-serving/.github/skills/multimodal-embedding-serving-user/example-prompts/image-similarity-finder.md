Build an image similarity finder using the multimodal embedding service (embeddings only — no LLM). Given a query image, it returns the most similar images from a local folder — catalogs, factory datasets, retail imagery, or surveillance snapshots.

- Bring the embedding service up if it isn't already (prebuilt image, CPU is fine).
- Embed every image in the folder via POST /embeddings (input.type = image_base64 for local files, image_url for hosted ones), one request per image, and keep {filename, vector} in an in-memory index — the service does not store vectors; add a local vector DB in the app layer if persistence is needed.
- Embed the query image the same way and rank the folder by cosine similarity.
- Print the top-5 matches with their scores.

Validate the application using:
- Model CLIP/clip-vit-b-32 on http://localhost:9777.
- An image folder built from Intel's sample videos (download: https://github.com/intel-iot-devkit/sample-videos/raw/refs/heads/master/<name>.mp4): extract ~5 frames each (ffmpeg, e.g. -vf fps=1/3) from store-aisle-detection.mp4, person-bicycle-car-detection.mp4, and fruit-and-vegetable-detection.mp4.
- One extracted store-aisle frame as the query image.

Expected results:
- The top matches for the store-aisle query are the other store-aisle frames, scoring clearly above frames from the other two videos.
- All embeddings are 512-dim flat vectors and model in each request matches the loaded model.

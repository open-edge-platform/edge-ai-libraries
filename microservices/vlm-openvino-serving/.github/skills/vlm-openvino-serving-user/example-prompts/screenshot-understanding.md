Build a document/screenshot understanding helper that answers questions about UI screenshots, forms, charts, or dashboards using the VLM service.

- Bring the VLM service up if it isn't already (prebuilt image, CPU is fine); wait for /health.
- Send the screenshot as an image part plus the user's question in one chat completion; support structured follow-ups like "list every button with its label" or "read the table values as JSON".
- Print the answer.

Validate the application using:
- Model Qwen/Qwen2.5-VL-3B-Instruct on http://localhost:9764/v1.
- A screenshot of the service's own Swagger UI — open http://localhost:9764/docs in a browser and capture it (the sample-videos repo has no document footage, so the service documents itself).

Expected results:
- Asked "which API endpoints are listed?", the answer names only endpoints actually visible in the screenshot (e.g. /v1/chat/completions, /health) and invents none.
- "Return the visible endpoints as a JSON array" yields parseable JSON matching the screenshot.

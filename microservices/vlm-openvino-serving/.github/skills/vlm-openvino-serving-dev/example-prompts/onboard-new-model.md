Onboard a new vision-language model family so it can be served with the correct prompt formatting and capabilities.

- Add a dispatch branch for the family's prompt formatting (dispatch is substring-based in src/utils/common.py, routed through src/app.py).
- Add a src/config/model_config.yaml entry with the model's pixel limits and, if applicable, add it to the video_supported_models list.
- Guard telemetry code paths if the backend has no PerfMetrics (as with SmolVLM/optimum-intel). Add the SPDX header to any new file.

Validate the change using:
- Set VLM_MODEL_NAME to the new model and confirm it appears in GET /v1/models on http://localhost:9764.
- Send one text+image chat completion and confirm it routes to the new prompt path.
- Run the test suite with model interactions mocked (no real download).

Expected results:
- The new model is selectable, dispatched correctly, and reports the right image/video capabilities.
- Tests pass offline with initialize_model mocked — no multi-GB download is triggered.

# Pytest Notes (Internal)

> Internal-only test notes for maintainers. Do not expose this as user-facing documentation.

**Work folder:** `edge-ai-libraries/microservices/multilevel-video-understanding`

## 1) Environment setup (Poetry style, no fixed venv path)

Use steps aligned with [docs/user-guide/get-started.md](../docs/user-guide/get-started.md) -> `Manual Host Setup using Poetry`:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install poetry==1.8.3
poetry lock --no-update
poetry install
# Install video-chunking-utils from OEP/EAL source
pip install ../../libraries/video-chunking-utils/
```

## 2) Test strategy

- Default mode: **mock-based API tests** under `tests/test_api`.
  - No external VLM/LLM serving dependency.
  - Fast and stable for CI.
- Optional mode: **external-serving integration test** under `tests/test_integration`.
  - Requires real VLM/LLM endpoints.
  - Use for end-to-end validation.

## 3) Run tests

Run API tests (default):

```bash
source .venv/bin/activate
pytest -q tests/test_api
```

Run integration test with external serving (optional):

```bash
source .venv/bin/activate
export ENABLE_EXTERNAL_SERVING_TESTS=1
export VLM_BASE_URL="http://localhost:41091/v1"
export LLM_BASE_URL="http://localhost:41091/v1"
export VLM_MODEL_NAME=Qwen/Qwen3.5-35B-A3B
export LLM_MODEL_NAME=Qwen/Qwen3.5-35B-A3B
pytest -q tests/test_integration/test_summary_external_serving.py
```

## 4) Test plan & new-feature cases (2026.2)

- Source of truth: `tests/resources/Multilevel-Video-Understanding-Testplan.xlsx` (tab `testplan-rc2`),
  exported to `tests/resources/Multilevel-Video-Understanding-Testplan-rc2.csv`.
- New-feature cases appended in the same style: `Multi-vs-13..20`
  (caption-only, Chinese built-in task, prompt-task discovery / registration /
  fallbacks / autogen / lifecycle, and summarize-with-a-registered-task).
- Only the subset runnable directly against external serving is automated in
  `tests/test_integration/test_summary_external_serving.py`:
  - `SUMMARY_CASES` params `Multi-vs-13_caption_only_summary`, `Multi-vs-14_chinese_builtin_task`.
  - `test_register_minimal_task_autofills_optional_sections` (Multi-vs-17 fallback slice).
  - `test_summary_with_registered_dynamic_task` (Multi-vs-16 + Multi-vs-20 end-to-end).
- Prompt content used for `/v1/tasks` registration lives as text next to the tests:
  `tests/resources/task_playground_safety.txt` (full 4-anchor) and
  `tests/resources/task_minimal_report.txt` (GLOBAL + LOCAL only → exercises auto-fill).
  Registry-only behavior (conflicts, immutability, literal braces, hints) is covered
  fast/mocked in `tests/test_api/test_tasks.py`.

## 5) Notes

- Keep unit/API tests independent from network and external model serving whenever possible.
- Keep integration tests opt-in and environment-gated (`ENABLE_EXTERNAL_SERVING_TESTS=1`).

# Pytest Notes (Internal)

> Internal-only test notes for maintainers.

**Work folder:** `edge-ai-libraries/libraries/video-chunking-utils`

## 1) Virtual environment

Create and activate a local virtual environment in project root:

```bash
cd ./video-chunking-utils
python3 -m venv .venv
source .venv/bin/activate
```

## 2) Environment variables

Optional decoder-related environment variables:

```bash
export FORCE_CHUNKING_VIDEO_READER=decord
export DECORD_NUM_THREADS=0
```

Notes:

- `FORCE_CHUNKING_VIDEO_READER` supports `decord` or `ffmpeg`.
- If not set, backend is auto-selected.

## 3) Install python module

Install this package into current virtual environment:

```bash
pip install -e .
pip install pytest
```

## 4) Run tests

Run unit tests from the project root:

```bash
pytest -q
```

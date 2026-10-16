# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
"""Request model artifacts from the shared model-download service."""

import json
import base64
import os
import re
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import ProxyHandler, Request, build_opener

from utils.config_loader import config


_MODEL_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*/[A-Za-z0-9][A-Za-z0-9._-]*\Z")
_JOB_ID = re.compile(r"[a-f0-9-]{36}\Z")
_OPENER = build_opener(ProxyHandler({}))


def _request_json(url: str, payload: dict | None = None) -> dict:
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    request = Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"} if data is not None else {},
    )
    try:
        with _OPENER.open(request, timeout=15) as response:
            body = response.read(65537)
        if len(body) > 65536:
            raise RuntimeError("Model download service response exceeds 64 KiB")
        result = json.loads(body)
    except (HTTPError, URLError, TimeoutError, OSError, ValueError) as exc:
        raise RuntimeError(
            f"Model download service request failed (HTTP {exc.code})"
            if isinstance(exc, HTTPError)
            else "Model download service is unreachable or returned invalid JSON"
        ) from exc
    if not isinstance(result, dict):
        raise RuntimeError("Unexpected model download service response")
    return result


def get_model_from_service(
    model: str,
    revision: str | None = None,
    *,
    hub: str = "modelscope",
    download_path: str = "funasr",
    files: list[str] | None = None,
    required_files: list[str] | None = None,
    hf_token: str | None = None,
    models_base_path: str | None = None,
) -> str:
    if hub not in {"modelscope", "huggingface", "openai-whisper"}:
        raise ValueError(f"Unsupported model source: {hub}")
    if not _MODEL_ID.fullmatch(model) and not (hub == "openai-whisper" and model in {"tiny", "base", "small", "medium", "large-v3"}):
        raise ValueError(f"Invalid {hub} model identifier: {model!r}")
    if download_path not in {"funasr", "whisper-source", "diarization"}:
        raise ValueError(f"Invalid model download destination: {download_path}")

    base_url = os.environ.get("AUDIO_ANALYZER_MODEL_DOWNLOAD_URL", "").rstrip("/")
    parsed = urlsplit(base_url)
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.path
        or parsed.query
        or parsed.fragment
    ):
        raise RuntimeError(
            "Set AUDIO_ANALYZER_MODEL_DOWNLOAD_URL to the model-download service "
            "base URL (for example http://model-downloader:8000)"
        )

    model_dir = Path(models_base_path or config.models.asr.models_base_path) / download_path / hub / model.replace("/", "_")
    endpoint = f"{base_url}/models/download?{urlencode({'download_path': download_path})}"
    entry = {"name": model, "hub": hub}
    if revision is not None:
        entry["revision"] = revision
    if files is not None:
        entry["config"] = {"files": files}
    if hf_token:
        if hub != "huggingface":
            raise ValueError("HF_TOKEN overrides are only supported for Hugging Face")
        entry["override_credentials"] = {
            "HF_TOKEN": base64.b64encode(hf_token.encode("utf-8")).decode("ascii")
        }
    response = _request_json(
        endpoint,
        {"models": [entry]},
    )
    job_ids = response.get("job_ids")
    if (
        not isinstance(job_ids, list)
        or len(job_ids) != 1
        or not isinstance(job_ids[0], str)
        or not _JOB_ID.fullmatch(job_ids[0])
    ):
        raise RuntimeError(f"Model download service did not return one job for {model}")

    deadline = time.monotonic() + 1800
    while time.monotonic() < deadline:
        job = _request_json(f"{base_url}/jobs/{job_ids[0]}")
        if job.get("status") == "completed":
            result = job.get("result")
            if not isinstance(result, dict) or result.get("source") != hub or result.get("model_name") != model:
                raise RuntimeError(f"Unexpected completed {hub} job for {model}")
            if not model_dir.is_dir() or not any(model_dir.iterdir()) or any(
                not (model_dir / filename).is_file() for filename in (required_files or [])
            ):
                raise RuntimeError(
                    f"{hub} job completed but required files at {model_dir} are not on the shared models volume"
                )
            return str(model_dir.resolve())
        if job.get("status") in {"failed", "canceled"}:
            raise RuntimeError(f"{hub} download of {model} {job['status']}: {job.get('error', 'no details')}")
        if job.get("status") not in {"queued", "downloading"}:
            raise RuntimeError(f"Unexpected {hub} job status for {model}: {job.get('status')}")
        time.sleep(2)
    raise TimeoutError(f"Timed out waiting for {hub} download of {model}")

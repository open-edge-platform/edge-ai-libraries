# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
"""Resolve snapshots prepared by the one-shot Model Download job."""

import json
import re
from pathlib import Path

from utils.config_loader import config


MODEL_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*/[A-Za-z0-9][A-Za-z0-9._-]*\Z")
COMPLETION_FILE = ".audio-analyzer-model.json"
MAX_METADATA_BYTES = 1024 * 1024
FUNASR_MODEL_MAP = {
    "paraformer-zh": "funasr/paraformer-zh",
    "paraformer-en": "funasr/paraformer-en",
    "paraformer-online": "funasr/paraformer-zh-streaming",
}
FUNASR_MODEL_REVISIONS = {
    "funasr/paraformer-zh": "d7811ee3ac581fbcfdeb37c98c6ba674028433dc",
    "funasr/paraformer-en": "2bad1d78c117f38172165dccbc4575df6277ee0a",
    "funasr/paraformer-zh-streaming": "fd2af606b37d7fb8b3b8a218c5be5b07b53ef6ba",
    "funasr/fsmn-vad": "df20e6b30c653645fa4ff125cacfcabd1020a669",
    "funasr/ct-punc": "d0e55e2b8722a78b63705ff443d09c4f86e5d750",
}


def model_directory(model: str, download_path: str, models_base_path: str) -> Path:
    if not MODEL_ID.fullmatch(model):
        raise ValueError(f"Invalid Hugging Face model identifier: {model!r}")
    if download_path not in {"funasr", "whisper-source", "diarization"}:
        raise ValueError(f"Invalid model download destination: {download_path}")
    base = Path(models_base_path)
    directory = base / download_path / "huggingface" / model.replace("/", "_")
    if directory.is_symlink() or not directory.resolve().is_relative_to(base.resolve()):
        raise ValueError("Snapshot directory must remain inside the configured models volume")
    return directory


def get_local_model(
    model: str,
    revision: str | None = None,
    *,
    download_path: str = "funasr",
    required_files: list[str] | None = None,
    models_base_path: str | None = None,
) -> str:
    model_dir = model_directory(
        model, download_path, models_base_path or config.models.asr.models_base_path,
    )
    try:
        with (model_dir / COMPLETION_FILE).open("rb") as stream:
            raw = stream.read(MAX_METADATA_BYTES + 1)
        if len(raw) > MAX_METADATA_BYTES:
            raise ValueError("snapshot metadata exceeds 1 MiB")
        metadata = json.loads(raw)
        if (
            not isinstance(metadata, dict)
            or metadata.get("model") != model
            or metadata.get("revision") != revision
            or not isinstance(metadata.get("files"), dict)
            or not metadata["files"]
            or any(name not in metadata["files"] for name in (required_files or []))
            or any(
                not (model_dir / filename).is_file()
                or (model_dir / filename).stat().st_size == 0
                for filename in (required_files or [])
            )
        ):
            raise ValueError("incomplete snapshot or mismatched model revision")
        for filename, size in metadata["files"].items():
            path = model_dir / filename
            if (
                not path.resolve().is_relative_to(model_dir.resolve())
                or not isinstance(size, int)
                or isinstance(size, bool)
                or size < 0
                or not path.is_file()
                or path.stat().st_size != size
            ):
                raise ValueError("snapshot file is missing, changed, or outside the model directory")
    except (OSError, ValueError) as exc:
        raise RuntimeError(
            f"Model {model!r} is not provisioned correctly at {model_dir}. "
            "Run the model-downloader provisioning job successfully before starting Audio Analyzer."
        ) from exc
    return str(model_dir.resolve())

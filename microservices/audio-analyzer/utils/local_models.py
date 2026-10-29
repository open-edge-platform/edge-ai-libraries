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
    "paraformer-zh": "iic/speech_paraformer-large-vad-punc_asr_nat-zh-cn-16k-common-vocab8404-pytorch",
    "paraformer-en": "iic/speech_paraformer-large-vad-punc_asr_nat-en-16k-common-vocab10020",
    "paraformer-online": "iic/speech_paraformer-large_asr_nat-zh-cn-16k-common-vocab8404-online",
}
FUNASR_VAD_MODEL = "iic/speech_fsmn_vad_zh-cn-16k-common-pytorch"
FUNASR_PUNC_MODEL = "iic/punc_ct-transformer_zh-cn-common-vocab272727-pytorch"
FUNASR_MODEL_REVISIONS = {
    model: "v2.0.4"
    for model in (*FUNASR_MODEL_MAP.values(), FUNASR_VAD_MODEL, FUNASR_PUNC_MODEL)
}


def model_directory(
    model: str, download_path: str, models_base_path: str, *, hub: str = "huggingface",
) -> Path:
    if not MODEL_ID.fullmatch(model):
        raise ValueError(f"Invalid model identifier: {model!r}")
    if hub not in {"huggingface", "modelscope"}:
        raise ValueError(f"Invalid model hub: {hub}")
    if download_path not in {"funasr", "whisper-source", "diarization"}:
        raise ValueError(f"Invalid model download destination: {download_path}")
    base = Path(models_base_path)
    directory = base / download_path / hub / model.replace("/", "_")
    if directory.is_symlink() or not directory.resolve().is_relative_to(base.resolve()):
        raise ValueError("Snapshot directory must remain inside the configured models volume")
    return directory


def get_local_model(
    model: str,
    revision: str | None = None,
    *,
    hub: str = "huggingface",
    download_path: str = "funasr",
    required_files: list[str] | None = None,
    models_base_path: str | None = None,
) -> str:
    model_dir = model_directory(
        model, download_path, models_base_path or config.models.asr.models_base_path,
        hub=hub,
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

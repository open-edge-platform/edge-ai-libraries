# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
"""Derive and prepare the model snapshots Audio Analyzer needs.

`provision_models()` maps the Audio Analyzer configuration to hub download
requests. The actual transfer is delegated to a `fetch` callable so the same
plan works against a shared Model Download REST service
(`utils.model_download_client.fetch_from_service`) or by downloading directly
from the hub inside Audio Analyzer (`fetch_direct` below). Both leave an
identical, manifest-certified snapshot on disk.
"""

import asyncio
import base64
import json
import logging
import os
import shutil
import tempfile
from collections.abc import Awaitable, Callable
from pathlib import Path

import yaml

from utils.config_loader import config
from utils.ensure_model import (
    HF_PYTORCH_WEIGHTS_NAME,
    _resolve_hf_token,
    get_whispercpp_model_filename,
)
from utils.local_models import (
    COMPLETION_FILE,
    FUNASR_MODEL_MAP,
    FUNASR_MODEL_REVISIONS,
    FUNASR_PUNC_MODEL,
    FUNASR_VAD_MODEL,
    MAX_METADATA_BYTES,
    get_local_model,
    model_directory,
)

logger = logging.getLogger(__name__)


async def provision_models(fetch: Callable[..., Awaitable[str]]) -> None:
    """Derive downloads from the same configuration used by Audio Analyzer."""
    asr = config.models.asr
    if asr.provider == "openvino":
        # Mirror ensure_model(): full repo ids ("distil-whisper/...") pass through.
        hf_model_id = asr.name if "/" in asr.name else f"openai/{asr.name}"
        await fetch(
            hf_model_id, download_path="whisper-source",
            required_files=["config.json"],
        )
    elif asr.provider == "whispercpp":
        filename = get_whispercpp_model_filename(asr.name, getattr(asr, "weight_format", None))
        await fetch(
            "ggerganov/whisper.cpp", download_path="whisper-source",
            files=[filename], required_files=[filename],
        )
    elif asr.provider == "funasr":
        if asr.name not in FUNASR_MODEL_MAP:
            raise ValueError(f"Unsupported FunASR model: {asr.name}")
        for model in (
            FUNASR_MODEL_MAP[asr.name],
            getattr(asr, "vad_model", None) or FUNASR_VAD_MODEL,
            getattr(asr, "punc_model", None) or FUNASR_PUNC_MODEL,
        ):
            await fetch(
                model, FUNASR_MODEL_REVISIONS.get(model),
                hub="modelscope", download_path="funasr",
                required_files=["config.yaml", "model.pt"],
            )
    elif asr.provider != "openai":
        raise ValueError(f"Unsupported ASR provider: {asr.provider}")

    if not getattr(asr, "diarization", False):
        return
    diar = config.models.diarization
    if diar.provider != "huggingface":
        raise ValueError(f"Unsupported diarization provider: {diar.provider}")
    token = _resolve_hf_token()
    pipeline_dir = Path(await fetch(
        diar.name, download_path="diarization",
        required_files=["config.yaml"], hf_token=token,
    ))
    with (pipeline_dir / "config.yaml").open(encoding="utf-8") as stream:
        pipeline = yaml.safe_load(stream)
    params = pipeline["pipeline"]["params"]
    for key in ("segmentation", "embedding", "plda"):
        model = params.get(key)
        if not isinstance(model, str) or "/" not in model:
            continue
        if model.startswith("$model/"):
            bundled = pipeline_dir / model[len("$model/"):]
            if (
                not bundled.resolve().is_relative_to(pipeline_dir.resolve())
                or not bundled.is_dir()
                or not any(path.is_file() and path.stat().st_size > 0 for path in bundled.rglob("*"))
            ):
                raise RuntimeError(f"Bundled diarization dependency is missing or invalid: {key}")
            if key in {"segmentation", "embedding"}:
                weights = bundled / HF_PYTORCH_WEIGHTS_NAME
                if not weights.is_file() or weights.stat().st_size == 0:
                    raise RuntimeError(f"Bundled diarization weights are missing: {key}")
        else:
            await fetch(
                model, download_path="diarization",
                required_files=[HF_PYTORCH_WEIGHTS_NAME, "config.yaml"], hf_token=token,
            )


def record_snapshot(model: str, revision: str | None, directory: Path) -> None:
    files = {
        path.relative_to(directory).as_posix(): path.stat().st_size
        for path in directory.rglob("*")
        if path.is_file()
        and ".cache" not in path.relative_to(directory).parts
        and path.name not in {COMPLETION_FILE, "config.local.yaml"}
    }
    data = json.dumps({"model": model, "revision": revision, "files": files})
    if len(data.encode("utf-8")) > MAX_METADATA_BYTES:
        raise RuntimeError(f"Snapshot inventory for {model} exceeds 1 MiB")
    with tempfile.NamedTemporaryFile(mode="w", dir=directory, delete=False, encoding="utf-8") as stream:
        temporary = Path(stream.name)
        try:
            stream.write(data)
            stream.flush()
            os.replace(temporary, directory / COMPLETION_FILE)
        finally:
            temporary.unlink(missing_ok=True)


def build_request_entry(
    model: str,
    revision: str | None,
    *,
    hub: str,
    files: list[str] | None = None,
    hf_token: str | None = None,
) -> dict[str, object]:
    """Build one Model Download `ModelRequest` payload (API and REST share this schema)."""
    entry: dict[str, object] = {"name": model, "hub": hub, "revision": revision}
    if files:
        entry["config"] = {"files": files}
    if hf_token:
        entry["override_credentials"] = {
            "HF_TOKEN": base64.b64encode(hf_token.encode("utf-8")).decode("ascii"),
        }
    return entry


async def prepare_snapshot(
    model: str,
    revision: str | None,
    *,
    hub: str,
    download_path: str,
    required_files: list[str],
    models_dir: str,
    download: Callable[[Path], Awaitable[None]],
) -> str:
    """Reuse a valid snapshot or rebuild it via `download`, then certify it.

    `download(directory)` must leave the model files in `directory`; this helper
    owns the skip/rebuild decision, the completion inventory, and re-validation.
    """
    directory = model_directory(model, download_path, models_dir, hub=hub)
    try:
        return get_local_model(
            model, revision, download_path=download_path,
            required_files=required_files, models_base_path=models_dir, hub=hub,
        )
    except RuntimeError:
        logger.info("Preparing missing or changed snapshot: %s", model)
    if directory.is_symlink() or not directory.resolve().is_relative_to(Path(models_dir).resolve()):
        raise RuntimeError(f"Unsafe snapshot location for {model}")
    if directory.exists():
        # Rebuild only this invalid snapshot: stale hub metadata and files from
        # another revision must not be certified as the requested revision.
        shutil.rmtree(directory)
    directory.mkdir(parents=True, exist_ok=True)
    await download(directory)
    record_snapshot(model, revision, directory)
    try:
        return get_local_model(
            model, revision, download_path=download_path,
            required_files=required_files, models_base_path=models_dir, hub=hub,
        )
    except RuntimeError:
        (directory / COMPLETION_FILE).unlink(missing_ok=True)
        raise


def download_from_hub(
    directory: Path,
    model: str,
    revision: str | None,
    *,
    hub: str,
    files: list[str] | None = None,
    hf_token: str | None = None,
) -> None:
    """Fetch a snapshot straight from the hub into `directory` (same calls the
    Model Download huggingface/modelscope plugins make)."""
    if hub == "huggingface":
        from huggingface_hub import snapshot_download

        kwargs: dict[str, object] = {
            "repo_id": model, "local_dir": str(directory), "revision": revision, "token": hf_token,
        }
        if files:
            kwargs["allow_patterns"] = files
        snapshot_download(**kwargs)
    elif hub == "modelscope":
        try:
            from modelscope.hub.snapshot_download import snapshot_download
        except ImportError as exc:
            raise RuntimeError(
                "modelscope is not installed. Install the optional Chinese-ASR dependencies "
                "(pip install -r requirements-cjk.txt or build with INSTALL_CJK=true)."
            ) from exc
        snapshot_download(model, revision=revision, local_dir=str(directory))
    else:
        raise ValueError(f"Unsupported model hub: {hub}")


async def fetch_direct(
    model: str,
    revision: str | None = None,
    *,
    hub: str = "huggingface",
    download_path: str,
    required_files: list[str],
    files: list[str] | None = None,
    hf_token: str | None = None,
    models_base_path: str | None = None,
) -> str:
    """`fetch` implementation that downloads inside Audio Analyzer."""
    models_dir = models_base_path or config.models.asr.models_base_path

    async def download(directory: Path) -> None:
        logger.info("Downloading %s from %s into %s", model, hub, directory)
        await asyncio.to_thread(
            download_from_hub, directory, model, revision, hub=hub, files=files, hf_token=hf_token,
        )

    return await prepare_snapshot(
        model, revision, hub=hub, download_path=download_path,
        required_files=required_files, models_dir=models_dir, download=download,
    )
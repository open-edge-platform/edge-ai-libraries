# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
"""Prepare configured snapshots inside the ephemeral Model Download container."""

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
        await fetch(
            f"openai/{asr.name}", download_path="whisper-source",
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


async def main() -> None:
    # These packages belong to the Model Download image, not Audio Analyzer.
    from src.api.models import ModelDownloadRequest, ModelRequest
    from src.core.model_manager import ModelManager
    from src.core.model_submission import submit_models
    from src.core.plugin_registry import PluginRegistry
    import src.plugins as plugins

    registry = PluginRegistry()
    registry.discover_plugins(plugins)
    models_dir = os.environ.get("MODELS_DIR", "/opt/models")
    manager = ModelManager(registry, default_dir=models_dir)
    tasks: set[asyncio.Task] = set()

    async def fetch(
        model: str,
        revision: str | None = None,
        *,
        hub: str = "huggingface",
        download_path: str,
        required_files: list[str],
        files: list[str] | None = None,
        hf_token: str | None = None,
    ) -> str:
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
        entry: dict[str, object] = {"name": model, "hub": hub, "revision": revision}
        if files:
            entry["config"] = {"files": files}
        if hf_token:
            entry["override_credentials"] = {
                "HF_TOKEN": base64.b64encode(hf_token.encode("utf-8")).decode("ascii"),
            }
        jobs = await submit_models(
            ModelDownloadRequest(models=[ModelRequest.model_validate(entry)]),
            download_path, plugin_registry=registry, model_manager=manager,
            models_dir=models_dir, background_tasks=tasks,
        )
        await asyncio.gather(*tasks)
        if not jobs or any(
            (manager.get_job_status(job) or {}).get("status") != "completed"
            for job in jobs
        ):
            raise RuntimeError(f"Model provisioning failed for {model}; inspect Model Download job logs")
        record_snapshot(model, revision, directory)
        try:
            return get_local_model(
                model, revision, download_path=download_path,
                required_files=required_files, models_base_path=models_dir, hub=hub,
            )
        except RuntimeError:
            (directory / COMPLETION_FILE).unlink(missing_ok=True)
            raise

    await provision_models(fetch)
    logger.info("All configured Model Download snapshots are ready")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())

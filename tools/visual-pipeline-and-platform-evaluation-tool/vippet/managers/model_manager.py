"""
ModelManager: single source of truth for model listing, downloading and
uploading inside vippet-app.

Responsibilities:

* Read the model catalog (canonical models + variants, install status)
  from the `models`/`model_variants` DB tables, seeded at startup from
  ``vippet/models/*.yaml`` (see ``db_seed.py``).
* Resolve which predefined pipelines reference each model
  (``used_by_pipelines``).
* Start asynchronous download jobs:
    - For ``omz`` source: run ``omz_downloader``/``omz_converter`` in a
      worker thread (model-download has no OMZ plugin yet).
    - For every other supported source: forward the
      ``download_request`` body to the ``/models/download`` endpoint of
      the model-download microservice and poll its ``/jobs/{job_id}``
      endpoint until completion.
* Proxy multipart uploads to the model-download microservice
  (``/models/upload``) and register the resulting model in the DB so it
  shows up in ``GET /models`` immediately.

On every successful download/upload, the DB is updated and
``SupportedModelsManager`` (the in-memory cache used by pipeline
building/execution code) is explicitly refreshed so the new install
state is visible immediately without waiting for a restart.

Threading model mirrors :class:`OptimizationManager`:
* one background ``threading.Thread`` per job,
* jobs stored in-memory in a singleton (lost on restart; install state
  itself is durable in the DB),
* no cancellation.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import os
import shutil
import subprocess
import tempfile
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, BinaryIO

import httpx

from internal_types import (
    InternalModelCategory,
    InternalModelDownloadJobState,
    InternalModelDownloadJobStatus,
    InternalModelDownloadJobSummary,
    InternalModelInstallStatus,
    InternalModelPrecision,
    InternalModelSource,
    InternalModelUploadSpec,
    InternalModelVariant,
    InternalSupportedModel,
)
from managers.pipeline_manager import PipelineManager
from models import GENAI_SENTINEL_FILE, MODELS_PATH, SupportedModelsManager

logger = logging.getLogger("model_manager")

# ----------------------------------------------------------------------
# Configuration (env-overridable)
# ----------------------------------------------------------------------

# Base URL of the model-download microservice (no trailing slash).
MODEL_DOWNLOAD_URL: str = os.environ.get(
    "MODEL_DOWNLOAD_URL", "http://model-download:8000"
).rstrip("/")
# API root used by model-download.
MODEL_DOWNLOAD_API_PREFIX: str = "/api/v1"

# Polling configuration for remote model-download jobs.
DOWNLOAD_POLL_INTERVAL_S: float = float(
    os.environ.get("MODEL_DOWNLOAD_POLL_INTERVAL_S", "2")
)
DOWNLOAD_TIMEOUT_S: float = float(
    os.environ.get("MODEL_DOWNLOAD_TIMEOUT_S", str(24 * 3600))
)

# HTTP request timeout when talking to model-download (per request).
HTTP_REQUEST_TIMEOUT_S: float = float(
    os.environ.get("MODEL_DOWNLOAD_HTTP_TIMEOUT_S", "60")
)

# Upload streaming chunk size.
UPLOAD_CHUNK_SIZE: int = 8 * 1024 * 1024  # 8 MiB


def _precision_is_complete(category: str | None, model_path: str) -> bool:
    """Return True only when the model files at *model_path* are complete.

    For GenAI models the path points at a directory.  Checking that the
    directory exists is not enough — the download process creates it before
    any weights are written, so a failed download (e.g. due to a missing or
    invalid HF_TOKEN) can leave an empty or partially-populated directory
    that still passes an ``os.path.exists`` check.

    For all other model types the path points directly at the ``.xml``
    artefact, so a plain existence check is sufficient.
    """
    if category == "vision_language_models":
        return os.path.isfile(os.path.join(model_path, GENAI_SENTINEL_FILE))
    return os.path.exists(model_path)


# ----------------------------------------------------------------------
# OMZ post-processing assets shipped with DLStreamer
# ----------------------------------------------------------------------

DLSTREAMER_MODEL_PROC_DIR: str = os.environ.get(
    "DLSTREAMER_MODEL_PROC_DIR",
    "/opt/intel/dlstreamer/samples/gstreamer/model_proc",
)
DLSTREAMER_LABELS_DIR: str = os.environ.get(
    "DLSTREAMER_LABELS_DIR",
    "/opt/intel/dlstreamer/samples/labels",
)

# Path of the dedicated venv where ``openvino-dev[onnx]==2024.6.0`` (and
# the matching legacy ``openvino==2024.6.0``) live, isolated from the
# main runtime which uses ``openvino==2026.x``. Built in the Dockerfile;
# the env var lets local development override it.
OMZ_VENV_DIR: str = os.environ.get("OMZ_VIRTUAL_ENV", "/home/dlstreamer/.omz-venv")
OMZ_DOWNLOADER_BIN: str = os.environ.get(
    "OMZ_DOWNLOADER_BIN", os.path.join(OMZ_VENV_DIR, "bin", "omz_downloader")
)
OMZ_CONVERTER_BIN: str = os.environ.get(
    "OMZ_CONVERTER_BIN", os.path.join(OMZ_VENV_DIR, "bin", "omz_converter")
)


# Per-model custom post-processing for OMZ downloads. Each entry describes
# the OMZ category prefix produced by ``omz_downloader`` (``intel`` or
# ``public``) and an optional ``model_proc`` file to copy into the final
# model directory under a specific destination filename.
#
# Used by the OMZ fallback path for the subset of OMZ models still listed
# in ``supported_models.yaml`` that model-download does not handle yet.
_OMZ_MODEL_RULES: dict[str, dict[str, str]] = {
    "mobilenet-v2-pytorch": {
        "category": "public",
        "model_proc_src": os.path.join(
            DLSTREAMER_MODEL_PROC_DIR, "public", "preproc-aspect-ratio.json"
        ),
        "model_proc_dst": "mobilenet-v2.json",
        "labels_src": os.path.join(DLSTREAMER_LABELS_DIR, "imagenet_2012.txt"),
    },
    "age-gender-recognition-retail-0013": {
        "category": "intel",
        "model_proc_src": os.path.join(
            DLSTREAMER_MODEL_PROC_DIR,
            "intel",
            "age-gender-recognition-retail-0013.json",
        ),
        "model_proc_dst": "age-gender-recognition-retail-0013.json",
    },
    "face-detection-retail-0004": {
        "category": "intel",
        "model_proc_src": os.path.join(
            DLSTREAMER_MODEL_PROC_DIR, "intel", "face-detection-retail-0004.json"
        ),
        "model_proc_dst": "face-detection-retail-0004.json",
    },
}


# ----------------------------------------------------------------------
# Manager singleton
# ----------------------------------------------------------------------


class ModelManager:
    """Thread-safe singleton coordinating model state and downloads."""

    _instance: "ModelManager | None" = None
    _singleton_lock = threading.Lock()

    def __new__(cls) -> "ModelManager":
        if cls._instance is None:
            with cls._singleton_lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self) -> None:
        if hasattr(self, "_initialized"):
            return
        self._initialized = True

        # Job bookkeeping
        self._jobs: dict[str, InternalModelDownloadJobStatus] = {}
        self._jobs_lock = threading.Lock()

        # Re-sync the model cache (already warmed once in the FastAPI
        # lifespan before PipelineManager loaded predefined pipelines).
        # Idempotent and cheap; mainly guards against ModelManager ever
        # being constructed standalone (e.g. in isolated tests).
        SupportedModelsManager().reload()

    # ------------------------------------------------------------------
    # Helpers: type conversion
    # ------------------------------------------------------------------

    @staticmethod
    def _to_internal_source(raw: str) -> InternalModelSource:
        """Map a raw ``hub``/``source`` string to :class:`InternalModelSource`.

        Falls back to ``CUSTOM`` for unknown values so the API never
        breaks because of an unexpected entry in the YAML.
        """
        try:
            return InternalModelSource(raw)
        except ValueError:
            return InternalModelSource.CUSTOM

    @staticmethod
    def _to_internal_category(raw: str | None) -> InternalModelCategory | None:
        if not raw:
            return None
        try:
            return InternalModelCategory(raw)
        except ValueError:
            return None

    # ------------------------------------------------------------------
    # Public: model listing
    # ------------------------------------------------------------------

    async def list_models(self) -> list[InternalSupportedModel]:
        """Return every model known to vippet-app as internal records.

        Reads the `models`/`model_variants` DB tables directly (both
        YAML-catalog and custom-uploaded models live in the same
        `models` table, distinguished by `is_custom`). `install_status`
        is the DB's code-managed value merged with any active in-memory
        download job (RUNNING/FAILED overlays the DB's resting state so
        an in-flight download shows up immediately).
        """
        from sqlalchemy import select

        from database import async_session_maker
        from orm_models import Model, ModelVariant

        used_by_display = PipelineManager().get_model_display_names_used_by_pipelines()
        active_jobs = self._active_jobs_by_model()

        result: list[InternalSupportedModel] = []
        if async_session_maker is None:
            logger.warning("Database not initialized yet; returning no models")
            return result

        async with async_session_maker() as session:
            db_models = (await session.execute(select(Model))).scalars().all()
            for db_model in db_models:
                db_variants = (
                    (
                        await session.execute(
                            select(ModelVariant).where(
                                ModelVariant.model_id == db_model.id
                            )
                        )
                    )
                    .scalars()
                    .all()
                )

                precisions = self._collect_precisions(db_variants)
                variants = self._collect_variants(db_variants)
                install_status = self._compute_install_status(
                    name=db_model.name,
                    db_model=db_model,
                    active_jobs=active_jobs,
                )
                used_by = sorted(
                    {
                        pipeline_id
                        for v in db_variants
                        for pipeline_id in used_by_display.get(v.display_name, [])
                    }
                )

                result.append(
                    InternalSupportedModel(
                        name=db_model.name,
                        display_name=db_model.display_name,
                        category=self._to_internal_category(db_model.category),
                        source=self._to_internal_source(db_model.hub),
                        precisions=precisions,
                        variants=variants,
                        install_status=install_status,
                        used_by_pipelines=used_by,
                        default=bool(used_by),
                        unsupported_devices=db_model.unsupported_devices,
                        download_request=db_model.download_request,
                        description=db_model.description,
                    )
                )

        return result

    @staticmethod
    def _strip_precision_suffix(display_name: str) -> str:
        """Remove the trailing ``(PRECISION)`` suffix added by SupportedModelsManager.

        Returns the input unchanged if no precision suffix is detected.
        """
        if display_name.endswith(")") and " (" in display_name:
            return display_name.rsplit(" (", 1)[0]
        return display_name

    @staticmethod
    def _collect_precisions(db_variants: list[Any]) -> list[InternalModelPrecision]:
        """Build a unique list of precision variants for a canonical model."""
        seen: set[str] = set()
        precisions: list[InternalModelPrecision] = []
        for v in db_variants:
            if not v.precision or v.precision in seen:
                continue
            seen.add(v.precision)
            precisions.append(
                InternalModelPrecision(
                    precision=v.precision,
                    model_path=os.path.join(MODELS_PATH, v.model_path),
                )
            )
        return precisions

    @staticmethod
    def _collect_variants(db_variants: list[Any]) -> list[InternalModelVariant]:
        """Build the API-facing variant list for a canonical model.

        Emits one ``InternalModelVariant`` per `ModelVariant` row (one
        per precision and per model-proc alias). ``installed`` is the
        DB's code-managed flag, never a live disk check.
        """
        variants: list[InternalModelVariant] = []
        seen: set[str] = set()
        for v in db_variants:
            if v.display_name in seen:
                continue
            seen.add(v.display_name)
            variants.append(
                InternalModelVariant(
                    name=v.name,
                    display_name=v.display_name,
                    precision=v.precision or "",
                    installed=v.installed,
                )
            )
        return variants

    @staticmethod
    def _compute_install_status(
        name: str,
        db_model: Any,
        active_jobs: dict[str, InternalModelDownloadJobStatus],
    ) -> InternalModelInstallStatus:
        """Overlay an active in-memory job on top of the DB's resting install_status.

        Order of precedence:
        1. There is an active job for this model → INSTALLING/FAILED, so an
           in-flight or just-failed download shows up without a DB write.
        2. Otherwise, the DB's own `install_status` column.
        """
        job = active_jobs.get(name)
        if job is not None:
            if job.state == InternalModelDownloadJobState.RUNNING:
                return InternalModelInstallStatus.INSTALLING
            if job.state == InternalModelDownloadJobState.FAILED:
                return InternalModelInstallStatus.FAILED

        return InternalModelInstallStatus(db_model.install_status)

    def _active_jobs_by_model(
        self,
    ) -> dict[str, InternalModelDownloadJobStatus]:
        """Latest job per model name, used to compute install_status."""
        with self._jobs_lock:
            latest: dict[str, InternalModelDownloadJobStatus] = {}
            for job in self._jobs.values():
                current = latest.get(job.model_name)
                if current is None or job.start_time > current.start_time:
                    latest[job.model_name] = job
            return latest

    # ------------------------------------------------------------------
    # Public: jobs
    # ------------------------------------------------------------------

    def get_all_jobs(self) -> list[InternalModelDownloadJobStatus]:
        with self._jobs_lock:
            return list(self._jobs.values())

    def get_job(self, job_id: str) -> InternalModelDownloadJobStatus | None:
        with self._jobs_lock:
            return self._jobs.get(job_id)

    def get_job_summary(self, job_id: str) -> InternalModelDownloadJobSummary | None:
        with self._jobs_lock:
            job = self._jobs.get(job_id)
            if job is None:
                return None
            return InternalModelDownloadJobSummary(
                id=job.id, model_name=job.model_name, source=job.source
            )

    # ------------------------------------------------------------------
    # Public: download
    # ------------------------------------------------------------------

    async def start_download(self, model_name: str) -> tuple[str | None, int, str]:
        """Start a download job for the given supported model.

        Returns a tuple ``(job_id, http_status, message)`` where
        ``job_id`` is ``None`` for error responses. ``http_status`` is
        the HTTP code that the route layer should return.
        """
        from sqlalchemy import select

        from database import async_session_maker
        from orm_models import Model

        if async_session_maker is None:
            return None, 500, "Database not initialized yet"

        async with async_session_maker() as session:
            db_model = await session.scalar(
                select(Model).where(Model.name == model_name)
            )
        if db_model is None:
            return None, 404, f"Model '{model_name}' is not supported"

        source = self._to_internal_source(db_model.hub)
        download_request = db_model.download_request

        # Idempotency: reject if installed or already running.
        if db_model.install_status == InternalModelInstallStatus.INSTALLED.value:
            return None, 409, f"Model '{model_name}' is already installed"

        with self._jobs_lock:
            running = next(
                (
                    j
                    for j in self._jobs.values()
                    if j.model_name == model_name
                    and j.state == InternalModelDownloadJobState.RUNNING
                ),
                None,
            )
        if running is not None:
            return (
                None,
                409,
                f"Download for model '{model_name}' is already running (job {running.id})",
            )

        if source != InternalModelSource.OMZ and not download_request:
            return (
                None,
                400,
                f"Model '{model_name}' has no download_request configured",
            )

        # Create job record
        job_id = uuid.uuid1().hex
        job = InternalModelDownloadJobStatus(
            id=job_id,
            model_name=model_name,
            source=source,
            state=InternalModelDownloadJobState.RUNNING,
            start_time=int(time.time() * 1000),
            details=[f"Starting download of '{model_name}'"],
        )
        with self._jobs_lock:
            self._jobs[job_id] = job

        # Pick worker
        if source == InternalModelSource.OMZ:
            target = self._execute_omz_download
            args: tuple[Any, ...] = (job_id, model_name)
        else:
            assert download_request is not None
            target = self._execute_remote_download
            args = (job_id, model_name, download_request)

        threading.Thread(
            target=target,
            args=args,
            name=f"model-download-{job_id}",
            daemon=True,
        ).start()

        return job_id, 202, f"Download started (job {job_id})"

    # ------------------------------------------------------------------
    # Worker: remote download (model-download microservice)
    # ------------------------------------------------------------------

    def _execute_remote_download(
        self,
        job_id: str,
        model_name: str,
        download_request: dict[str, Any],
    ) -> None:
        """Run a download via the model-download microservice."""
        try:
            download_path = self._resolve_download_path()
            url = f"{MODEL_DOWNLOAD_URL}{MODEL_DOWNLOAD_API_PREFIX}/models/download"
            body = {"models": [download_request]}

            self._append_detail(
                job_id,
                f"POST {url}?download_path={download_path} body={body}",
            )

            with httpx.Client(timeout=HTTP_REQUEST_TIMEOUT_S) as client:
                response = client.post(
                    url, params={"download_path": download_path}, json=body
                )
                response.raise_for_status()
                payload = response.json()

            external_ids: list[str] = list(payload.get("job_ids") or [])
            if not external_ids:
                self._fail_job(job_id, "model-download returned no job ids")
                return

            with self._jobs_lock:
                job = self._jobs.get(job_id)
                if job is not None:
                    job.external_job_ids = list(external_ids)
                    job.progress_message = payload.get("status")

            # Poll until every external job reports completed/failed.
            deadline = time.monotonic() + DOWNLOAD_TIMEOUT_S
            with httpx.Client(timeout=HTTP_REQUEST_TIMEOUT_S) as client:
                while time.monotonic() < deadline:
                    statuses = []
                    for ext_id in external_ids:
                        r = client.get(
                            f"{MODEL_DOWNLOAD_URL}{MODEL_DOWNLOAD_API_PREFIX}/jobs/{ext_id}"
                        )
                        if r.status_code == 404:
                            statuses.append(("failed", f"job {ext_id} not found"))
                            continue
                        r.raise_for_status()
                        data = r.json()
                        statuses.append(
                            (
                                data.get("status", "processing"),
                                data.get("error"),
                            )
                        )

                    progress = ", ".join(s for s, _ in statuses)
                    with self._jobs_lock:
                        job = self._jobs.get(job_id)
                        if job is not None:
                            job.progress_message = progress

                    if all(s in ("completed", "failed") for s, _ in statuses):
                        if all(s == "completed" for s, _ in statuses):
                            self._finalize_success(job_id, model_name)
                            return
                        # At least one failed and none is still processing —
                        # aggregate every failure reason into a single message
                        # so callers see all root causes at once.
                        errors = [
                            err or "model-download reported a failed job"
                            for s, err in statuses
                            if s == "failed"
                        ]
                        self._fail_job(job_id, "; ".join(errors))
                        return

                    time.sleep(DOWNLOAD_POLL_INTERVAL_S)

            self._fail_job(
                job_id, f"Download timed out after {DOWNLOAD_TIMEOUT_S:.0f}s"
            )
        except httpx.HTTPError as exc:
            logger.error(
                "HTTP error while downloading %s in job %s",
                model_name,
                job_id,
                exc_info=True,
            )
            self._fail_job(job_id, f"HTTP error: {exc}")
        except Exception as exc:  # pragma: no cover - defensive
            logger.error(
                "Unexpected error while downloading %s in job %s",
                model_name,
                job_id,
                exc_info=True,
            )
            self._fail_job(job_id, f"Unexpected error: {exc}")

    @staticmethod
    def _resolve_download_path() -> str:
        """Pick the ``download_path`` query value passed to model-download.

        We always pass ``.`` (i.e. the MODELS_PATH root). The model-download
        plugins themselves prepend their own ``<hub>/`` subdirectory to
        ``output_dir`` (e.g. ``ultralytics/``, ``huggingface/``), and the
        download scripts they invoke further nest the files under
        ``<source>/<model_name>/<precision>/...``. ``supported_models.yaml``
        ``model_path`` entries must therefore include the full
        ``<hub>/<source>/<model_name>/<precision>/<file>`` prefix.
        """
        return "."

    # ------------------------------------------------------------------
    # Worker: OMZ download (handled locally by vippet-app)
    # ------------------------------------------------------------------

    def _execute_omz_download(self, job_id: str, model_name: str) -> None:
        """Download/convert an OMZ model using ``openvino-dev`` CLIs.

        model-download has no OMZ plugin yet, so we keep this fallback in
        vippet-app itself.

        Downloads and converts in a private temp dir, then moves the
        artefacts into ``MODELS_PATH/omz/<model_name>/`` and applies any
        per-model post-processing (copy ``model_proc`` JSON, inject
        ImageNet labels for ``mobilenet-v2-pytorch``, ...).
        """
        tmp_dir: str | None = None
        try:
            target_dir = os.path.join(MODELS_PATH, "omz", model_name)
            os.makedirs(os.path.dirname(target_dir), exist_ok=True)

            # Use a private scratch directory for omz_downloader/omz_converter
            # so partial artefacts never pollute the final layout.
            tmp_dir = tempfile.mkdtemp(prefix=f"vippet-omz-{model_name}-")

            self._append_detail(
                job_id,
                f"{OMZ_DOWNLOADER_BIN} --name {model_name} --output_dir {tmp_dir}",
            )
            self._run_subprocess(
                job_id,
                [
                    OMZ_DOWNLOADER_BIN,
                    "--name",
                    model_name,
                    "--output_dir",
                    tmp_dir,
                ],
            )

            self._append_detail(
                job_id,
                f"{OMZ_CONVERTER_BIN} --name {model_name} --download_dir {tmp_dir} "
                f"--output_dir {tmp_dir}",
            )
            self._run_subprocess(
                job_id,
                [
                    OMZ_CONVERTER_BIN,
                    "--name",
                    model_name,
                    "--download_dir",
                    tmp_dir,
                    "--output_dir",
                    tmp_dir,
                ],
            )

            self._materialize_omz_artifacts(
                job_id=job_id,
                model_name=model_name,
                tmp_dir=tmp_dir,
                target_dir=target_dir,
            )

            self._finalize_success(job_id, model_name)
        except subprocess.CalledProcessError as exc:
            stderr = (exc.stderr or "").strip() if isinstance(exc.stderr, str) else ""
            logger.error(
                "OMZ tool failed for %s (job %s): %s\nstderr:\n%s",
                model_name,
                job_id,
                exc,
                stderr or "<empty>",
                exc_info=True,
            )
            short = f"OMZ command failed: {' '.join(exc.cmd)} (rc={exc.returncode})"
            details = [short]
            if stderr:
                details.append("stderr:")
                details.extend(stderr.splitlines())
            self._fail_job(job_id, short, details=details)
        except FileNotFoundError as exc:
            logger.error(
                "OMZ tooling missing for job %s: %s", job_id, exc, exc_info=True
            )
            self._fail_job(
                job_id,
                "openvino-dev tools (omz_downloader/omz_converter) are not installed",
            )
        except Exception as exc:  # pragma: no cover - defensive
            logger.error(
                "Unexpected error in OMZ download job %s", job_id, exc_info=True
            )
            self._fail_job(job_id, f"Unexpected error: {exc}")
        finally:
            if tmp_dir:
                shutil.rmtree(tmp_dir, ignore_errors=True)

    def _materialize_omz_artifacts(
        self,
        job_id: str,
        model_name: str,
        tmp_dir: str,
        target_dir: str,
    ) -> None:
        """Move converted OMZ artefacts and apply per-model post-processing.

        Handles the per-model quirks (model-proc JSON copy, ImageNet
        label injection, ...) for OMZ models still listed in
        ``supported_models.yaml`` (``mobilenet-v2-pytorch``,
        ``age-gender-recognition-retail-0013``,
        ``face-detection-retail-0004``).
        """
        rule = _OMZ_MODEL_RULES.get(model_name)
        # Default OMZ category: ``intel`` (Intel-hosted, most retail models).
        category = (rule or {}).get("category", "intel")
        source_dir = os.path.join(tmp_dir, category, model_name)
        if not os.path.isdir(source_dir):
            # Fallback: scan ``intel`` and ``public`` for the model dir.
            for candidate in ("intel", "public"):
                alt = os.path.join(tmp_dir, candidate, model_name)
                if os.path.isdir(alt):
                    source_dir = alt
                    category = candidate
                    break
        if not os.path.isdir(source_dir):
            raise FileNotFoundError(
                f"omz_converter produced no output for '{model_name}' "
                f"(looked under {tmp_dir}/intel and {tmp_dir}/public)"
            )

        # Move everything into the target dir. ``shutil.move`` cannot
        # merge into an existing directory, so we move children one by
        # one after ensuring the target exists.
        os.makedirs(target_dir, exist_ok=True)
        for entry in os.listdir(source_dir):
            src = os.path.join(source_dir, entry)
            dst = os.path.join(target_dir, entry)
            if os.path.exists(dst):
                # Replace any partial leftover from a previous run.
                if os.path.isdir(dst):
                    shutil.rmtree(dst)
                else:
                    os.remove(dst)
            shutil.move(src, dst)
        self._append_detail(
            job_id,
            f"Moved OMZ artefacts from {source_dir} to {target_dir}",
        )

        if rule is None:
            return

        # Copy the bundled model_proc JSON (if shipped with DLStreamer).
        proc_src = rule.get("model_proc_src")
        proc_dst_name = rule.get("model_proc_dst")
        proc_dst_path: str | None = None
        if proc_src and proc_dst_name:
            if not os.path.isfile(proc_src):
                logger.warning(
                    "model_proc source not found for %s: %s", model_name, proc_src
                )
            else:
                proc_dst_path = os.path.join(target_dir, proc_dst_name)
                shutil.copyfile(proc_src, proc_dst_path)
                self._append_detail(
                    job_id, f"Copied model_proc {proc_src} -> {proc_dst_path}"
                )

        # mobilenet-v2-pytorch: inject ImageNet labels into the JSON.
        labels_src = rule.get("labels_src")
        if labels_src and proc_dst_path:
            self._inject_imagenet_labels(
                job_id=job_id,
                model_name=model_name,
                labels_path=labels_src,
                json_path=proc_dst_path,
            )

    @staticmethod
    def _inject_imagenet_labels(
        job_id: str, model_name: str, labels_path: str, json_path: str
    ) -> None:
        """Replicate the ``mobilenet-v2-pytorch`` label injection from the shell script.

        Reads ``imagenet_2012.txt`` (one ``<id> <label>`` per line) and
        writes the labels into ``output_postproc[0].labels`` of
        ``json_path``. Silently logs and skips on missing files/keys.
        """
        if not os.path.isfile(labels_path):
            logger.warning(
                "ImageNet labels file missing for %s: %s", model_name, labels_path
            )
            return
        if not os.path.isfile(json_path):
            logger.warning("model_proc JSON missing for %s: %s", model_name, json_path)
            return
        try:
            labels: list[str] = []
            with open(labels_path) as f:
                for raw_line in f:
                    line = raw_line.strip()
                    if not line:
                        continue
                    parts = line.split(" ", 1)
                    labels.append(parts[1] if len(parts) == 2 else parts[0])

            with open(json_path) as f:
                data = json.load(f)
            postproc = data.get("output_postproc")
            if isinstance(postproc, list) and postproc:
                postproc[0]["labels"] = labels
                with open(json_path, "w") as f:
                    json.dump(data, f, indent=4)
                logger.info(
                    "[job %s] Injected %d ImageNet labels into %s",
                    job_id,
                    len(labels),
                    json_path,
                )
            else:
                logger.warning(
                    "%s lacks output_postproc[0]; skipping label injection",
                    json_path,
                )
        except Exception:
            logger.error(
                "Failed to inject ImageNet labels into %s", json_path, exc_info=True
            )

    def _run_subprocess(self, job_id: str, command: list[str]) -> None:
        """Run an OMZ tool as a subprocess and stream stdout into job details.

        ``stderr`` is captured separately and attached to
        :class:`subprocess.CalledProcessError` when the command fails so
        the caller can log meaningful diagnostics (the OMZ CLIs send
        most error messages to stderr).

        The OMZ venv's ``bin/`` directory is prepended to ``PATH`` so
        helper CLIs that ``omz_converter`` invokes by name (notably
        ``mo`` from openvino-dev 2024.6) are resolved from the same
        isolated environment.
        """
        env = os.environ.copy()
        omz_bin_dir = os.path.join(OMZ_VENV_DIR, "bin")
        if os.path.isdir(omz_bin_dir):
            env["PATH"] = omz_bin_dir + os.pathsep + env.get("PATH", "")

        proc = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
            env=env,
        )
        assert proc.stdout is not None
        assert proc.stderr is not None

        stderr_lines: list[str] = []

        def _drain_stderr() -> None:
            assert proc.stderr is not None
            for line in proc.stderr:
                stripped = line.rstrip()
                stderr_lines.append(stripped)
                if stripped:
                    logger.debug("[job %s] [stderr] %s", job_id, stripped)

        stderr_thread = threading.Thread(
            target=_drain_stderr, name=f"omz-stderr-{job_id}", daemon=True
        )
        stderr_thread.start()

        for line in proc.stdout:
            line = line.rstrip()
            if not line:
                continue
            with self._jobs_lock:
                job = self._jobs.get(job_id)
                if job is not None:
                    job.progress_message = line

        rc = proc.wait()
        stderr_thread.join(timeout=5)
        stderr = "\n".join(stderr_lines).strip()
        if rc != 0:
            raise subprocess.CalledProcessError(rc, command, output=None, stderr=stderr)

    # ------------------------------------------------------------------
    # Job state transitions
    # ------------------------------------------------------------------

    def _append_detail(self, job_id: str, message: str) -> None:
        with self._jobs_lock:
            job = self._jobs.get(job_id)
            if job is not None:
                job.details.append(message)
        logger.info("[job %s] %s", job_id, message)

    def _fail_job(
        self,
        job_id: str,
        message: str,
        details: list[str] | None = None,
    ) -> None:
        """Mark a job as FAILED.

        No DB write is needed: the DB's resting `install_status` (never
        touched by a failed attempt) stays authoritative, and `GET
        /models` overlays this in-memory FAILED state on top of it (see
        `_compute_install_status`).

        Args:
            job_id: id of the job to update.
            message: short, one-line failure summary used for the
                application log.
            details: optional richer payload (for example captured
                stderr) attached to ``job.details`` so it surfaces in
                the API/UI without polluting the application log.
        """
        with self._jobs_lock:
            job = self._jobs.get(job_id)
            if job is None:
                return
            job.state = InternalModelDownloadJobState.FAILED
            job.end_time = int(time.time() * 1000)
            job.details = details if details else [message]
        logger.error("Model download job %s failed: %s", job_id, message)

    def _finalize_success(self, job_id: str, model_name: str) -> None:
        """Mark the job as COMPLETED and persist the new install state to the DB.

        Verifies that the expected model files are present on disk before
        trusting the model-download service's "completed" status.  The
        service can report success while leaving only partial artefacts —
        for example when a gated HuggingFace model is requested without a
        valid HF_TOKEN, the service may download config/metadata files and
        then exit cleanly, never writing the actual model weights.  In that
        case the job is re-classified as FAILED with an informative message.

        This is the ONLY place install_status/installed are ever derived
        from a filesystem check post-seed: it is tied to this specific
        download-completion event, not a periodic rescan.
        """
        installed, model_path = asyncio.run(self._persist_download_result(model_name))

        if not installed:
            logger.warning(
                "model-download reported success for '%s' (job %s) but the "
                "expected model files are not present on disk — reclassifying "
                "as FAILED.  If this is a gated model, ensure HF_TOKEN is set "
                "correctly before retrying.",
                model_name,
                job_id,
            )
            self._fail_job(
                job_id,
                "Model was not successfully installed. "
                "Check your Hugging Face access token and accept model license if needed. ",
            )
            return

        with self._jobs_lock:
            job = self._jobs.get(job_id)
            if job is None:
                return
            job.state = InternalModelDownloadJobState.COMPLETED
            job.end_time = int(time.time() * 1000)
            job.details = [f"Model '{model_name}' installed successfully"]
            job.model_path = model_path

        logger.info("Model download job %s completed", job_id)

    @staticmethod
    async def _persist_download_result(model_name: str) -> tuple[bool, str | None]:
        """Check disk for each variant's artefact and persist the result.

        Called exactly once, right after model-download/OMZ reports
        success. Also refreshes ``SupportedModelsManager`` so pipeline
        building sees the new install state immediately.
        """
        from sqlalchemy import select

        from database import async_session_maker
        from orm_models import Model, ModelVariant

        if async_session_maker is None:
            return False, None

        async with async_session_maker() as session:
            db_model = await session.scalar(
                select(Model).where(Model.name == model_name)
            )
            if db_model is None:
                return False, None
            variants = (
                (
                    await session.execute(
                        select(ModelVariant).where(
                            ModelVariant.model_id == db_model.id
                        )
                    )
                )
                .scalars()
                .all()
            )

            now = datetime.now(timezone.utc)
            any_installed = False
            model_path: str | None = None
            for variant in variants:
                full_path = os.path.join(MODELS_PATH, variant.model_path)
                is_installed = _precision_is_complete(db_model.category, full_path)
                variant.installed = is_installed
                variant.installed_at = now if is_installed else None
                if is_installed:
                    any_installed = True
                    if model_path is None:
                        model_path = full_path

            db_model.install_status = (
                InternalModelInstallStatus.INSTALLED.value
                if any_installed
                else InternalModelInstallStatus.NOT_INSTALLED.value
            )
            db_model.installed_at = now if any_installed else None
            await session.commit()

        if any_installed:
            await SupportedModelsManager().reload_async()

        return any_installed, model_path

    # ------------------------------------------------------------------
    # Public: upload
    # ------------------------------------------------------------------

    async def upload_model(
        self, spec: InternalModelUploadSpec
    ) -> tuple[InternalSupportedModel | None, int, str]:
        """Forward a model upload to model-download and register it in the DB.

        Returns ``(model, http_status, message)``. On success ``model``
        is the freshly registered :class:`InternalSupportedModel`.
        """
        url = f"{MODEL_DOWNLOAD_URL}{MODEL_DOWNLOAD_API_PREFIX}/models/upload"

        try:
            with open(spec.file_path, "rb") as fh:
                files = {
                    "file": (
                        spec.original_filename or os.path.basename(spec.file_path),
                        fh,
                        "application/zip",
                    )
                }
                data = {"model_name": spec.model_name}
                with httpx.Client(timeout=DOWNLOAD_TIMEOUT_S) as client:
                    response = client.post(url, data=data, files=files)
        except httpx.HTTPError as exc:
            logger.error("HTTP error while uploading model: %s", exc, exc_info=True)
            return None, 502, f"Upload failed: {exc}"
        except Exception as exc:  # pragma: no cover - defensive
            logger.error("Unexpected upload error", exc_info=True)
            return None, 500, f"Unexpected upload error: {exc}"

        if response.status_code >= 400:
            # Mirror model-download's status code so the UI can react.
            detail = self._extract_detail(response)
            return None, response.status_code, detail or "Upload failed"

        payload: dict[str, Any] = {}
        try:
            payload = response.json()
        except Exception:
            logger.debug("Upload response had no JSON body", exc_info=True)

        # Resolve installed model path. model-download replies include
        # ``output_dir`` (best-effort across versions).
        output_dir = str(
            payload.get("output_dir")
            or payload.get("model_path")
            or os.path.join(MODELS_PATH, "custom_uploaded_models", spec.model_name)
        )

        # Resolve the actual ``.xml`` artefact when model-download returns a
        # directory (custom ZIPs only contain ``.xml``/``.bin``). GenAI-style
        # uploads keep the directory itself, matching the sentinel-file check.
        resolved_path = output_dir
        if (
            spec.category != InternalModelCategory.VISION_LANGUAGE_MODELS
            and os.path.isdir(output_dir)
        ):
            try:
                xml_files = sorted(
                    f for f in os.listdir(output_dir) if f.endswith(".xml")
                )
            except OSError:
                xml_files = []
            if xml_files:
                resolved_path = os.path.join(output_dir, xml_files[0])

        # Store relative to MODELS_PATH so this row is indistinguishable
        # from a catalog-seeded row when SupportedModelsManager rebuilds
        # its cache (no special "uploaded model" adapter needed).
        relative_path = os.path.relpath(resolved_path, MODELS_PATH)

        from sqlalchemy import select
        from sqlalchemy.exc import IntegrityError

        from database import async_session_maker
        from orm_models import Model, ModelVariant

        if async_session_maker is None:
            return None, 500, "Database not initialized yet"

        now = datetime.now(timezone.utc)
        async with async_session_maker() as session:
            existing = await session.scalar(
                select(Model).where(Model.name == spec.model_name)
            )
            if existing is not None:
                return None, 409, f"Model '{spec.model_name}' already exists"

            db_model = Model(
                name=spec.model_name,
                display_name=spec.model_name,
                description=spec.description,
                category=spec.category.value,
                source=InternalModelSource.CUSTOM.value,
                hub=InternalModelSource.CUSTOM.value,
                unsupported_devices=None,
                is_custom=True,
                install_status=InternalModelInstallStatus.INSTALLED.value,
                installed_at=now,
                download_request=None,
                created_at=now,
            )
            session.add(db_model)
            try:
                await session.flush()
            except IntegrityError:
                await session.rollback()
                return None, 409, f"Model '{spec.model_name}' already exists"

            session.add(
                ModelVariant(
                    model_id=db_model.id,
                    name=spec.model_name,
                    display_name=spec.model_name,
                    precision="",
                    model_path=relative_path,
                    model_proc=None,
                    installed=True,
                    installed_at=now,
                )
            )
            await session.commit()

        await SupportedModelsManager().reload_async()

        model = InternalSupportedModel(
            name=spec.model_name,
            display_name=spec.model_name,
            category=spec.category,
            source=InternalModelSource.CUSTOM,
            precisions=[
                InternalModelPrecision(precision="", model_path=resolved_path)
            ],
            variants=[
                InternalModelVariant(
                    name=spec.model_name,
                    display_name=spec.model_name,
                    precision="",
                    installed=True,
                )
            ],
            install_status=InternalModelInstallStatus.INSTALLED,
            used_by_pipelines=[],
            default=False,
            unsupported_devices=None,
            download_request=None,
            description=spec.description,
        )
        return model, 201, "Model uploaded successfully"

    @staticmethod
    def _extract_detail(response: httpx.Response) -> str | None:
        try:
            body = response.json()
        except Exception:
            return response.text or None
        if isinstance(body, dict):
            detail = body.get("detail")
            if isinstance(detail, str):
                return detail
            if isinstance(detail, list) and detail:
                # FastAPI validation error array
                return "; ".join(str(item.get("msg", item)) for item in detail if item)
        return None

    # ------------------------------------------------------------------
    # Public: helper for streaming uploads to a temp file
    # ------------------------------------------------------------------

    @staticmethod
    def write_upload_to_tempfile(upload: BinaryIO, original_filename: str) -> str:
        """Stream an upload to a temporary file and return its absolute path.

        Caller is responsible for deleting the file after use
        (see :meth:`cleanup_tempfile`).
        """
        suffix = Path(original_filename).suffix or ".zip"
        fd, path = tempfile.mkstemp(prefix="vippet-upload-", suffix=suffix)
        try:
            with os.fdopen(fd, "wb") as out:
                shutil.copyfileobj(upload, out, length=UPLOAD_CHUNK_SIZE)
        except Exception:
            with contextlib.suppress(Exception):
                os.unlink(path)
            raise
        return path

    @staticmethod
    def cleanup_tempfile(path: str | None) -> None:
        if not path:
            return
        try:
            os.unlink(path)
        except FileNotFoundError:
            pass
        except Exception:  # pragma: no cover - defensive
            logger.debug("Failed to remove temp upload %s", path, exc_info=True)

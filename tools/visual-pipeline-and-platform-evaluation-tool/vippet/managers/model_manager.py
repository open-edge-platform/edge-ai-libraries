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
        - Forward the ``download_request`` body to the ``/models/download``
            endpoint of the model-download microservice and poll its
            ``/jobs/{job_id}`` endpoint until completion.
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
import logging
import os
import re
import shutil
import tempfile
import threading
import time
import uuid
from collections.abc import Callable, Sequence
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

# Ultralytics hub installs: model-download writes artefacts to
# ``<MODELS_PATH>/ultralytics/public/<name>/<PRECISION>/<name>.xml``.
ULTRALYTICS_SOURCE_DIR: str = "public"
_PRECISION_DIR_RE = re.compile(r"^(FP|INT)\d+$")
_ULTRALYTICS_CATEGORY_SUFFIXES: dict[str, InternalModelCategory] = {
    "-seg": InternalModelCategory.IMAGE_SEGMENTATION,
    "-cls": InternalModelCategory.IMAGE_CLASSIFICATION,
    "-pose": InternalModelCategory.POSE_ESTIMATION,
    "-obb": InternalModelCategory.OBJECT_DETECTION,
}


def ultralytics_category(name: str) -> InternalModelCategory:
    """Derive the model category from an Ultralytics model name suffix."""
    for suffix, category in _ULTRALYTICS_CATEGORY_SUFFIXES.items():
        if name.endswith(suffix):
            return category
    return InternalModelCategory.OBJECT_DETECTION


def scan_ultralytics_variants(name: str) -> list[tuple[str, str]]:
    """Find installed precisions of an Ultralytics model on disk.

    Args:
        name: Ultralytics model name (directory name under ``public/``).

    Returns:
        list[tuple[str, str]]: ``(precision, model_path)`` pairs sorted by
        precision, where ``model_path`` is relative to ``MODELS_PATH``.
    """
    rel_root = os.path.join("ultralytics", ULTRALYTICS_SOURCE_DIR, name)
    abs_root = os.path.join(MODELS_PATH, rel_root)
    if not os.path.isdir(abs_root):
        return []

    variants: list[tuple[str, str]] = []
    for precision in sorted(os.listdir(abs_root)):
        prec_dir = os.path.join(abs_root, precision)
        if not _PRECISION_DIR_RE.match(precision) or not os.path.isdir(prec_dir):
            continue
        xml_files = sorted(f for f in os.listdir(prec_dir) if f.endswith(".xml"))
        if not xml_files:
            continue
        xml_file = f"{name}.xml" if f"{name}.xml" in xml_files else xml_files[0]
        variants.append((precision, os.path.join(rel_root, precision, xml_file)))
    return variants


# HuggingFace hub installs: model-download writes a full repo snapshot to
# ``<MODELS_PATH>/huggingface/<name with "/" -> "_">/`` (no precision
# subfolders, unlike Ultralytics); only a single variant is derived.
_HF_PRECISION_RE = re.compile(r"(?i)(int4|int8|fp16|fp32)")
_GENAI_STYLE_CATEGORIES = {
    InternalModelCategory.VISION_LANGUAGE_MODELS,
    InternalModelCategory.LARGE_LANGUAGE_MODELS,
    InternalModelCategory.AUTOMATIC_SPEECH_RECOGNITION,
    InternalModelCategory.TEXT_TO_SPEECH,
}


def _guess_precision_from_name(name: str) -> str:
    """Best-effort precision guess from naming conventions like `-int8-ov`."""
    match = _HF_PRECISION_RE.search(name)
    return match.group(1).upper() if match else ""


def _strip_org_prefix(name: str) -> str:
    """Drop a hub repo id's ``owner/`` prefix (e.g. ``OpenVINO/gemma-4`` -> ``gemma-4``)."""
    return name.rsplit("/", 1)[-1]


def _find_genai_model_dir(abs_root: str) -> str | None:
    """Find the directory containing the GenAI sentinel file under *abs_root*.

    HuggingFace snapshots sometimes nest the model under a subdirectory,
    so both *abs_root* itself and its immediate children are checked.
    """
    if os.path.isfile(os.path.join(abs_root, GENAI_SENTINEL_FILE)):
        return abs_root
    if not os.path.isdir(abs_root):
        return None
    for entry in sorted(os.listdir(abs_root)):
        candidate = os.path.join(abs_root, entry)
        if os.path.isdir(candidate) and os.path.isfile(
            os.path.join(candidate, GENAI_SENTINEL_FILE)
        ):
            return candidate
    return None


def _find_first_xml(abs_root: str) -> str | None:
    """Recursively find the first non-tokenizer ``.xml`` file under *abs_root*."""
    for dirpath, _dirnames, filenames in os.walk(abs_root):
        for filename in sorted(filenames):
            if filename.endswith(".xml") and "tokenizer" not in filename.lower():
                return os.path.join(dirpath, filename)
    return None


def scan_huggingface_variant(
    name: str, category: InternalModelCategory
) -> tuple[str, str] | None:
    """Find the installed artefact of a HuggingFace hub model on disk.

    Returns a single ``(precision, model_path)`` pair (HuggingFace hub
    downloads are not split into precision subfolders like Ultralytics),
    where ``model_path`` is relative to ``MODELS_PATH``, or ``None`` when
    nothing usable was found.
    """
    rel_root = os.path.join("huggingface", name.replace("/", "_"))
    abs_root = os.path.join(MODELS_PATH, rel_root)
    if not os.path.isdir(abs_root):
        return None

    precision = _guess_precision_from_name(name)

    if category in _GENAI_STYLE_CATEGORIES:
        if category == InternalModelCategory.VISION_LANGUAGE_MODELS:
            genai_dir = _find_genai_model_dir(abs_root)
            return (
                None
                if genai_dir is None
                else (precision, os.path.relpath(genai_dir, MODELS_PATH))
            )
        # LLM/ASR/TTS have no established sentinel-file convention yet;
        # accept any non-empty download as a pragmatic fallback.
        return (precision, rel_root) if any(os.scandir(abs_root)) else None

    xml_path = _find_first_xml(abs_root)
    return (
        None
        if xml_path is None
        else (precision, os.path.relpath(xml_path, MODELS_PATH))
    )


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

    async def list_hub_models(self, request: dict[str, Any]) -> dict[str, Any]:
        """Proxy a model-catalog listing request to model-download."""
        url = f"{MODEL_DOWNLOAD_URL}{MODEL_DOWNLOAD_API_PREFIX}/models/list"
        async with httpx.AsyncClient(timeout=HTTP_REQUEST_TIMEOUT_S) as client:
            response = await client.post(url, json=request)
            response.raise_for_status()
            return response.json()

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
    def _collect_precisions(
        db_variants: Sequence[Any],
    ) -> list[InternalModelPrecision]:
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
    def _collect_variants(db_variants: Sequence[Any]) -> list[InternalModelVariant]:
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

    async def start_download(
        self,
        model_name: str,
        hub: str | None = None,
        category: InternalModelCategory | None = None,
    ) -> tuple[str | None, int, str]:
        """Start a download job for the given supported model.

        When ``hub`` is given and ``model_name`` is not in the catalog, the
        model is downloaded from that hub and registered on success.
        ``category`` is required for hubs that have no naming convention to
        derive it from (currently: ``huggingface``); it is ignored for
        ``ultralytics`` (derived from the name suffix instead).

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
            if hub is not None:
                return self._start_hub_download(hub, model_name, category)
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

        if not download_request:
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

        # Note: we intentionally do not insert a registry record here.
        # The registry only tracks successfully installed models; the
        # INSTALLING/FAILED states are derived from the in-memory job
        # (see ``_compute_install_status``).

        assert download_request is not None

        threading.Thread(
            target=self._execute_remote_download,
            args=(job_id, model_name, download_request),
            name=f"model-download-{job_id}",
            daemon=True,
        ).start()

        return job_id, 202, f"Download started (job {job_id})"

    def _start_hub_download(
        self,
        hub: str,
        name: str,
        category: InternalModelCategory | None,
    ) -> tuple[str | None, int, str]:
        """Start a download of a non-catalog model picked from a hub listing.

        On success the model and its installed precisions are registered
        in the DB.

        Args:
            hub: Upstream hub name (``ultralytics`` or ``huggingface``).
            name: Model name as returned by the hub listing.
            category: Required for ``huggingface`` (no naming convention to
                derive it from); ignored for ``ultralytics``.

        Returns:
            tuple[str | None, int, str]: ``(job_id, http_status, message)``.
        """
        if hub == InternalModelSource.ULTRALYTICS.value:
            resolved_category = ultralytics_category(name)
            source = InternalModelSource.ULTRALYTICS
            finalize = self._finalize_ultralytics_install
        elif hub == InternalModelSource.HUGGINGFACE.value:
            if category is None:
                return (
                    None,
                    400,
                    "A 'category' is required to install a model from hub 'huggingface'",
                )
            resolved_category = category
            source = InternalModelSource.HUGGINGFACE
            finalize = self._finalize_huggingface_install
        else:
            return None, 400, f"Installing models from hub '{hub}' is not supported"

        with self._jobs_lock:
            running = next(
                (
                    j
                    for j in self._jobs.values()
                    if j.model_name == name
                    and j.state == InternalModelDownloadJobState.RUNNING
                ),
                None,
            )
        if running is not None:
            return (
                None,
                409,
                f"Download for model '{name}' is already running (job {running.id})",
            )

        download_request: dict[str, Any] = {"hub": hub, "name": name}

        job_id = uuid.uuid1().hex
        job = InternalModelDownloadJobStatus(
            id=job_id,
            model_name=name,
            source=source,
            state=InternalModelDownloadJobState.RUNNING,
            start_time=int(time.time() * 1000),
            details=[f"Starting download of '{name}'"],
        )
        with self._jobs_lock:
            self._jobs[job_id] = job

        def on_success(job_id: str, model_name: str) -> None:
            finalize(job_id, model_name, resolved_category, download_request)

        threading.Thread(
            target=self._execute_remote_download,
            args=(job_id, name, download_request, on_success),
            name=f"model-download-{job_id}",
            daemon=True,
        ).start()

        return job_id, 202, f"Download started (job {job_id})"

    def _finalize_ultralytics_install(
        self,
        job_id: str,
        model_name: str,
        category: InternalModelCategory,
        download_request: dict[str, Any],
    ) -> None:
        """Register a freshly downloaded Ultralytics model in the DB."""
        variants = scan_ultralytics_variants(model_name)
        if not variants:
            self._fail_job(
                job_id,
                f"No installed precisions found for '{model_name}' after download",
            )
            return

        self._persist_and_complete_hub_job(
            job_id,
            model_name,
            category,
            download_request,
            variants,
            InternalModelSource.ULTRALYTICS,
            ULTRALYTICS_SOURCE_DIR,
        )

    def _finalize_huggingface_install(
        self,
        job_id: str,
        model_name: str,
        category: InternalModelCategory,
        download_request: dict[str, Any],
    ) -> None:
        """Register a freshly downloaded HuggingFace hub model in the DB."""
        variant = scan_huggingface_variant(model_name, category)
        if variant is None:
            self._fail_job(
                job_id,
                f"No installed artefacts found for '{model_name}' after download",
            )
            return

        self._persist_and_complete_hub_job(
            job_id,
            model_name,
            category,
            download_request,
            [variant],
            InternalModelSource.HUGGINGFACE,
            "huggingface",
        )

    def _persist_and_complete_hub_job(
        self,
        job_id: str,
        model_name: str,
        category: InternalModelCategory,
        download_request: dict[str, Any],
        variants: list[tuple[str, str]],
        hub: InternalModelSource,
        source: str,
    ) -> None:
        """Persist a hub-installed model's variants and complete its job."""
        try:
            asyncio.run(
                self._persist_hub_model(
                    model_name, category, download_request, variants, hub, source
                )
            )
        except Exception as exc:
            logger.error(
                "Failed to register model %s in job %s",
                model_name,
                job_id,
                exc_info=True,
            )
            self._fail_job(job_id, f"Failed to register model: {exc}")
            return

        with self._jobs_lock:
            job = self._jobs.get(job_id)
            if job is None:
                return
            job.state = InternalModelDownloadJobState.COMPLETED
            job.end_time = int(time.time() * 1000)
            job.details = [
                f"Model '{model_name}' installed successfully "
                f"({', '.join(p for p, _ in variants if p)})"
            ]
            job.model_path = os.path.join(MODELS_PATH, variants[0][1])

        logger.info("Model hub install job %s completed", job_id)

    @staticmethod
    async def _persist_hub_model(
        model_name: str,
        category: InternalModelCategory,
        download_request: dict[str, Any],
        variants: list[tuple[str, str]],
        hub: InternalModelSource,
        source: str,
    ) -> None:
        """Insert a hub-installed model and its precisions into the DB."""
        from database import async_session_maker
        from orm_models import Model, ModelVariant

        if async_session_maker is None:
            raise RuntimeError("Database not initialized yet")

        now = datetime.now(timezone.utc)
        display_base = _strip_org_prefix(model_name)
        async with async_session_maker() as session:
            db_model = Model(
                name=model_name,
                display_name=display_base,
                description=None,
                category=category.value,
                source=source,
                hub=hub.value,
                unsupported_devices=None,
                is_custom=False,
                install_status=InternalModelInstallStatus.INSTALLED.value,
                installed_at=now,
                download_request=download_request,
                created_at=now,
            )
            session.add(db_model)
            await session.flush()
            for precision, model_path in variants:
                display_name = (
                    f"{display_base} ({precision})" if precision else display_base
                )
                session.add(
                    ModelVariant(
                        model_id=db_model.id,
                        name=model_name,
                        display_name=display_name,
                        precision=precision,
                        model_path=model_path,
                        model_proc="",
                        installed=True,
                        installed_at=now,
                    )
                )
            await session.commit()

        await SupportedModelsManager().reload_async()

    # ------------------------------------------------------------------
    # Worker: remote download (model-download microservice)
    # ------------------------------------------------------------------

    def _execute_remote_download(
        self,
        job_id: str,
        model_name: str,
        download_request: dict[str, Any],
        on_success: Callable[[str, str], None] | None = None,
    ) -> None:
        """Run a download via the model-download microservice.

        ``on_success`` replaces :meth:`_finalize_success` when given.
        """
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
                            (on_success or self._finalize_success)(job_id, model_name)
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
        ``<source>/<model_name>/<precision>/...``. Model catalog entries'
        ``model_path`` entries must therefore include the full
        ``<hub>/<source>/<model_name>/<precision>/<file>`` prefix.
        """
        return "."

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
                        select(ModelVariant).where(ModelVariant.model_id == db_model.id)
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
            precisions=[InternalModelPrecision(precision="", model_path=resolved_path)],
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

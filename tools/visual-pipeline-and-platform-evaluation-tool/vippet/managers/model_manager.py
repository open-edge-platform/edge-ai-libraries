"""
ModelManager: single source of truth for model listing, downloading and
uploading inside vippet-app.

Responsibilities:

* Aggregate models known from ``supported_models.yaml`` and previously
  installed/uploaded ones (the latter persisted in
  ``installed_models.json`` next to the model files).
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
  (``/models/upload``) and register the resulting model locally so it
  shows up in ``GET /models`` immediately.

Threading model mirrors :class:`OptimizationManager`:
* one background ``threading.Thread`` per job,
* jobs stored in-memory in a singleton (lost on restart, but the
  installed-model registry survives via ``installed_models.json``),
* no cancellation.
"""

from __future__ import annotations

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
from dataclasses import dataclass, field
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
from models import MODELS_PATH, SupportedModel, SupportedModelsManager

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

# Path of the JSON registry tracking installed/uploaded models.
# Defaults to ``<MODELS_PATH>/installed_models.json`` so the file lives
# alongside the downloaded model artefacts inside the mounted
# ``shared/models/output/`` volume.
INSTALLED_MODELS_REGISTRY: str = os.environ.get(
    "INSTALLED_MODELS_REGISTRY",
    os.path.join(MODELS_PATH, "installed_models.json"),
)

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
# In-memory installed-model registry entry
# ----------------------------------------------------------------------


@dataclass
class _InstalledModelRecord:
    """Persisted record describing a model that lives on disk.

    Records are only created on successful download/upload and are
    removed (in-memory + on disk) at startup when the referenced files
    no longer exist. Implicit invariant: every record in the registry
    is currently ``INSTALLED``.
    """

    name: str
    display_name: str
    source: InternalModelSource
    category: InternalModelCategory | None
    precisions: list[InternalModelPrecision] = field(default_factory=list)


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

        # Installed-models registry (custom uploaded + completed downloads)
        self._registry: dict[str, _InstalledModelRecord] = {}
        self._registry_lock = threading.Lock()
        self._load_registry()

        # Pre-warm SupportedModelsManager so we fail fast if the YAML is broken.
        SupportedModelsManager()

    # ------------------------------------------------------------------
    # Registry persistence
    # ------------------------------------------------------------------

    def _load_registry(self) -> None:
        """Load the installed-models registry from disk if present.

        Stale entries (whose ``precisions[*].model_path`` no longer exist
        on disk) are pruned and the file is rewritten so the registry
        always reflects on-disk reality. The legacy ``install_status``
        field is ignored: presence in the registry implies ``INSTALLED``.
        """
        path = INSTALLED_MODELS_REGISTRY
        if not os.path.isfile(path):
            logger.debug("Installed-models registry not found at %s", path)
            return
        try:
            with open(path) as f:
                raw = json.load(f)
            if not isinstance(raw, list):
                logger.warning(
                    "Installed-models registry %s has unexpected shape, ignoring", path
                )
                return
            pruned = 0
            for entry in raw:
                try:
                    name = entry["name"]
                    precisions = [
                        InternalModelPrecision(
                            precision=p.get("precision", ""),
                            model_path=p["model_path"],
                        )
                        for p in entry.get("precisions", [])
                        if "model_path" in p
                    ]
                    # Prune entries whose files no longer exist on disk.
                    if not precisions or not any(
                        os.path.exists(p.model_path) for p in precisions
                    ):
                        logger.info(
                            "Pruning stale registry entry '%s' (files missing)", name
                        )
                        pruned += 1
                        continue
                    self._registry[name] = _InstalledModelRecord(
                        name=name,
                        display_name=entry.get("display_name", name),
                        source=InternalModelSource(entry.get("source", "custom")),
                        category=(
                            InternalModelCategory(entry["category"])
                            if entry.get("category")
                            else None
                        ),
                        precisions=precisions,
                    )
                except Exception:
                    logger.warning(
                        "Skipping malformed registry entry: %s", entry, exc_info=True
                    )
                    pruned += 1
            if pruned:
                # Persist the cleaned-up registry so the file stays in sync.
                with self._registry_lock:
                    self._save_registry_locked()
        except Exception:
            logger.error(
                "Failed to load installed-models registry from %s",
                path,
                exc_info=True,
            )

    def _save_registry_locked(self) -> None:
        """Persist the registry to disk. Caller must hold ``_registry_lock``."""
        path = INSTALLED_MODELS_REGISTRY
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            payload = [
                {
                    "name": r.name,
                    "display_name": r.display_name,
                    "source": r.source.value,
                    "category": r.category.value if r.category else None,
                    "precisions": [
                        {"precision": p.precision, "model_path": p.model_path}
                        for p in r.precisions
                    ],
                }
                for r in self._registry.values()
            ]
            tmp = f"{path}.tmp"
            with open(tmp, "w") as f:
                json.dump(payload, f, indent=2)
            os.replace(tmp, path)
        except Exception:
            logger.error(
                "Failed to persist installed-models registry to %s",
                path,
                exc_info=True,
            )

    def _upsert_registry_record(self, record: _InstalledModelRecord) -> None:
        with self._registry_lock:
            self._registry[record.name] = record
            self._save_registry_locked()

    def _remove_registry_record(self, model_name: str) -> None:
        """Drop ``model_name`` from the registry if present and persist."""
        with self._registry_lock:
            if self._registry.pop(model_name, None) is not None:
                self._save_registry_locked()

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

    def list_models(self) -> list[InternalSupportedModel]:
        """Return every model known to vippet-app as internal records.

        Combines:
        * entries from ``supported_models.yaml`` (grouped per canonical name),
        * uploaded/custom models stored in the registry that are not also
          listed in the YAML.

        The ``install_status`` and ``used_by_pipelines`` fields are
        computed at call time so that subsequent ``GET /models`` calls
        always reflect on-disk reality.
        """
        # Build display_name -> pipeline_ids map. PipelineManager exposes display
        # names because pipeline graphs store display names (see graph.py).
        used_by_display = PipelineManager().get_model_display_names_used_by_pipelines()

        supported = SupportedModelsManager().get_all_supported_models()

        # Group YAML entries by canonical name. A single canonical model
        # may appear multiple times: once per precision and once per
        # ``extra_model_procs`` variant. The API exposes the collapsed
        # canonical view (one installable model); fine-grained variants
        # remain visible to the PipelineBuilder via ``SupportedModel``.
        grouped: dict[str, list[SupportedModel]] = {}
        for m in supported:
            grouped.setdefault(m.canonical_name, []).append(m)

        result: list[InternalSupportedModel] = []
        active_jobs = self._active_jobs_by_model()

        # 1) Models from supported_models.yaml
        for name, entries in grouped.items():
            # Choose representative entry for display metadata.
            head = entries[0]

            precisions = self._collect_precisions(entries)
            variants = self._collect_variants(entries)
            install_status = self._compute_install_status(
                name=name,
                entries=entries,
                active_jobs=active_jobs,
            )

            display_name = self._strip_precision_suffix(head.canonical_display_name)
            used_by = sorted(
                {
                    pipeline_id
                    for e in entries
                    for pipeline_id in used_by_display.get(e.display_name, [])
                }
            )

            result.append(
                InternalSupportedModel(
                    name=name,
                    display_name=display_name,
                    category=self._to_internal_category(head.model_type),
                    source=self._to_internal_source(head.hub),
                    precisions=precisions,
                    variants=variants,
                    install_status=install_status,
                    used_by_pipelines=used_by,
                    default=head.default,
                    unsupported_devices=head.unsupported_devices or None,
                    download_request=self._lookup_download_request(name),
                )
            )

        # 2) Uploaded/custom models recorded in the registry only.
        yaml_names = set(grouped.keys())
        with self._registry_lock:
            extra_records = [
                r for r in self._registry.values() if r.name not in yaml_names
            ]
        for record in extra_records:
            result.append(
                InternalSupportedModel(
                    name=record.name,
                    display_name=record.display_name,
                    category=record.category,
                    source=record.source,
                    precisions=list(record.precisions),
                    variants=self._variants_from_record(record),
                    install_status=self._registry_install_status(record),
                    used_by_pipelines=[],
                    default=False,
                    unsupported_devices=None,
                    download_request=None,
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

    def _collect_precisions(
        self, entries: list[SupportedModel]
    ) -> list[InternalModelPrecision]:
        """Build a unique list of precision variants for a canonical model."""
        seen: set[str] = set()
        precisions: list[InternalModelPrecision] = []
        for e in entries:
            if not e.precision or e.precision in seen:
                continue
            seen.add(e.precision)
            precisions.append(
                InternalModelPrecision(
                    precision=e.precision, model_path=e.model_path_full
                )
            )
        return precisions

    @staticmethod
    def _collect_variants(
        entries: list[SupportedModel],
    ) -> list[InternalModelVariant]:
        """Build the API-facing variant list for a canonical model.

        Emits one ``InternalModelVariant`` per ``SupportedModel`` entry
        (one per precision and per ``extra_model_procs`` alias). Order
        follows the YAML definition so the dropdown stays predictable.
        Filesystem paths are intentionally excluded — variants are
        identified by ``name`` and matched to artefacts by the backend
        when ingesting / running a pipeline graph.

        ``SupportedModel.name`` is shared across precisions for a
        single canonical model (only ``extra_model_procs`` aliases
        suffix it), so deduplication must use the per-precision
        ``display_name`` which is always unique.

        ``installed`` reflects the on-disk presence of this exact
        variant so the pipeline builder can filter its dropdown to
        ready-to-use entries.
        """
        variants: list[InternalModelVariant] = []
        seen: set[str] = set()
        for e in entries:
            if e.display_name in seen:
                continue
            seen.add(e.display_name)
            variants.append(
                InternalModelVariant(
                    name=e.name,
                    display_name=e.display_name,
                    precision=e.precision or "",
                    installed=e.exists_on_disk(),
                )
            )
        return variants

    @staticmethod
    def _variants_from_record(
        record: "_InstalledModelRecord",
    ) -> list[InternalModelVariant]:
        """Build a single-variant list for a registry-only (uploaded) model.

        Custom uploads always carry exactly one entry today, so this
        keeps the schema consistent with YAML-backed models without
        inventing model-proc aliases. Registry records exist only for
        models that were successfully installed, so ``installed`` is
        always ``True`` here.
        """
        precision = record.precisions[0].precision if record.precisions else ""
        suffix = f" ({precision})" if precision else ""
        return [
            InternalModelVariant(
                name=record.name,
                display_name=f"{record.display_name}{suffix}",
                precision=precision,
                installed=True,
            )
        ]

    def _compute_install_status(
        self,
        name: str,
        entries: list[SupportedModel],
        active_jobs: dict[str, InternalModelDownloadJobStatus],
    ) -> InternalModelInstallStatus:
        """Decide install status using on-disk presence + active jobs + registry.

        Order of precedence:
        1. Files present on disk under any YAML precision → INSTALLED.
        2. Model is in the registry (only added on successful install) → INSTALLED.
        3. There is an active job for this model → INSTALLING/FAILED depending on state.
        4. Otherwise NOT_INSTALLED.
        """
        if any(e.exists_on_disk() for e in entries):
            return InternalModelInstallStatus.INSTALLED

        with self._registry_lock:
            if name in self._registry:
                return InternalModelInstallStatus.INSTALLED

        job = active_jobs.get(name)
        if job is not None:
            if job.state == InternalModelDownloadJobState.RUNNING:
                return InternalModelInstallStatus.INSTALLING
            if job.state == InternalModelDownloadJobState.FAILED:
                return InternalModelInstallStatus.FAILED

        return InternalModelInstallStatus.NOT_INSTALLED

    def _registry_install_status(
        self, record: _InstalledModelRecord
    ) -> InternalModelInstallStatus:
        """Install status for a registry-only model (no YAML entry).

        Records only exist in the registry when the underlying files
        were verified at startup or just after a successful job/upload,
        so this is always ``INSTALLED``.
        """
        del record
        return InternalModelInstallStatus.INSTALLED

    def _lookup_download_request(self, name: str) -> dict[str, Any] | None:
        """Return the raw ``download_request`` body from supported_models.yaml.

        We re-read the YAML here only for the supported model entry,
        falling back to ``None`` when not specified. The YAML payload
        is loaded once by SupportedModelsManager but ``download_request``
        is not exposed there yet; cache it lazily.
        """
        return _DownloadRequestCache.get(name)

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

    def start_download(self, model_name: str) -> tuple[str | None, int, str]:
        """Start a download job for the given supported model.

        Returns a tuple ``(job_id, http_status, message)`` where
        ``job_id`` is ``None`` for error responses. ``http_status`` is
        the HTTP code that the route layer should return.
        """
        # Resolve supported model entry
        entries = [
            m
            for m in SupportedModelsManager().get_all_supported_models()
            if m.canonical_name == model_name
        ]
        if not entries:
            return None, 404, f"Model '{model_name}' is not supported"

        head = entries[0]
        source = self._to_internal_source(head.hub)
        download_request = _DownloadRequestCache.get(model_name)

        # Idempotency: reject if installed or already running.
        if any(e.exists_on_disk() for e in entries):
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

        # Note: we intentionally do not insert a registry record here.
        # The registry only tracks successfully installed models; the
        # INSTALLING/FAILED states are derived from the in-memory job
        # (see ``_compute_install_status``).

        # Pick worker
        if source == InternalModelSource.OMZ:
            target = self._execute_omz_download
            args: tuple[Any, ...] = (job_id, model_name, head)
        else:
            assert download_request is not None
            target = self._execute_remote_download
            args = (job_id, model_name, head, download_request)

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
        head: SupportedModel,
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
                            self._finalize_success(job_id, model_name, head)
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

    def _execute_omz_download(
        self, job_id: str, model_name: str, head: SupportedModel
    ) -> None:
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

            self._finalize_success(job_id, model_name, head)
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
            model_name = job.model_name

        # The registry only tracks installed models. If a previous
        # install succeeded and a re-install fails, the on-disk files
        # may now be partial/missing — drop the stale record so the
        # API reports the failed state (derived from the job).
        with self._registry_lock:
            record = self._registry.get(model_name)
            if record is not None and not any(
                os.path.exists(p.model_path) for p in record.precisions
            ):
                self._registry.pop(model_name, None)
                self._save_registry_locked()
        logger.error("Model download job %s failed: %s", job_id, message)

    def _finalize_success(
        self, job_id: str, model_name: str, head: SupportedModel
    ) -> None:
        """Mark the job as COMPLETED and update the registry."""
        # Refresh on-disk precision list from supported_models.yaml entries.
        entries = [
            m
            for m in SupportedModelsManager().get_all_supported_models()
            if m.canonical_name == model_name
        ]
        precisions = self._collect_precisions(entries)
        model_path = precisions[0].model_path if precisions else None

        with self._jobs_lock:
            job = self._jobs.get(job_id)
            if job is None:
                return
            job.state = InternalModelDownloadJobState.COMPLETED
            job.end_time = int(time.time() * 1000)
            job.details = [f"Model '{model_name}' installed successfully"]
            job.model_path = model_path

        self._upsert_registry_record(
            _InstalledModelRecord(
                name=model_name,
                display_name=self._strip_precision_suffix(head.canonical_display_name),
                source=self._to_internal_source(head.hub),
                category=self._to_internal_category(head.model_type),
                precisions=precisions,
            )
        )
        logger.info("Model download job %s completed", job_id)

    # ------------------------------------------------------------------
    # Public: upload
    # ------------------------------------------------------------------

    def upload_model(
        self, spec: InternalModelUploadSpec
    ) -> tuple[InternalSupportedModel | None, int, str]:
        """Forward a model upload to model-download and register it locally.

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
        model_path = (
            payload.get("output_dir")
            or payload.get("model_path")
            or os.path.join(MODELS_PATH, "custom_uploaded_models", spec.model_name)
        )

        precisions = [InternalModelPrecision(precision="", model_path=str(model_path))]
        record = _InstalledModelRecord(
            name=spec.model_name,
            display_name=spec.model_name,
            source=InternalModelSource.CUSTOM,
            category=spec.category,
            precisions=precisions,
        )
        self._upsert_registry_record(record)

        model = InternalSupportedModel(
            name=record.name,
            display_name=record.display_name,
            category=record.category,
            source=record.source,
            precisions=list(record.precisions),
            variants=self._variants_from_record(record),
            install_status=InternalModelInstallStatus.INSTALLED,
            used_by_pipelines=[],
            default=False,
            unsupported_devices=None,
            download_request=None,
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


# ----------------------------------------------------------------------
# Helpers shared across the manager
# ----------------------------------------------------------------------


class _DownloadRequestCache:
    """Lazy cache for ``download_request`` fragments from ``supported_models.yaml``.

    We re-parse the YAML only the first time we need it: this keeps
    SupportedModelsManager untouched while still exposing the data the
    manager needs.
    """

    _data: dict[str, dict[str, Any] | None] | None = None
    _lock = threading.Lock()

    @classmethod
    def get(cls, model_name: str) -> dict[str, Any] | None:
        cls._load()
        assert cls._data is not None
        return cls._data.get(model_name)

    @classmethod
    def _load(cls) -> None:
        if cls._data is not None:
            return
        with cls._lock:
            if cls._data is not None:
                return
            import yaml

            from models import SUPPORTED_MODELS_FILE

            cls._data = {}
            try:
                with open(SUPPORTED_MODELS_FILE) as f:
                    raw = yaml.safe_load(f) or []
                for entry in raw:
                    if not isinstance(entry, dict):
                        continue
                    name = entry.get("name")
                    if not isinstance(name, str):
                        continue
                    dr = entry.get("download_request")
                    cls._data[name] = dr if isinstance(dr, dict) else None
            except Exception:
                logger.error(
                    "Failed to load download_request entries from %s",
                    SUPPORTED_MODELS_FILE,
                    exc_info=True,
                )

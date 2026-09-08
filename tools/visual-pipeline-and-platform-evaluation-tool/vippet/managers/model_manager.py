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
        - Forward the ``download_request`` body to the ``/models/download``
            endpoint of the model-download microservice and poll its
            ``/jobs/{job_id}`` endpoint until completion.
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
from models import (
    GENAI_SENTINEL_FILE,
    MODELS_PATH,
    SupportedModel,
    SupportedModelsManager,
)

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
    if category == "genai":
        return os.path.isfile(os.path.join(model_path, GENAI_SENTINEL_FILE))
    return os.path.exists(model_path)


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
# Adapter exposing uploaded models through the SupportedModel interface
# ----------------------------------------------------------------------


class _UploadedSupportedModel(SupportedModel):
    """``SupportedModel`` view over an uploaded model registry record.

    The registry stores absolute on-disk paths (e.g.
    ``<MODELS_PATH>/custom_uploaded_models/<name>/``), while
    ``SupportedModel`` normally joins relative ``model_path`` with
    ``MODELS_PATH``. This adapter bypasses that join and additionally
    resolves a single ``.xml`` artefact when the record points at a
    directory, so the resulting ``model_path_full`` is directly usable
    by GStreamer.

    Uploaded models never carry a model-proc file (custom ZIPs only
    contain ``.xml``/``.bin``), so ``model_proc_full`` stays empty.
    """

    def __init__(
        self,
        record: "_InstalledModelRecord",
        precision: "InternalModelPrecision",
    ) -> None:
        # Initialise the base with a sentinel relative path; we override
        # ``model_path_full`` below so the join with MODELS_PATH is moot.
        super().__init__(
            name=record.name,
            display_name=record.display_name,
            source=record.source.value,
            model_type=(record.category.value if record.category else ""),
            model_path=precision.model_path,
            model_proc=None,
            unsupported_devices=None,
            precision=precision.precision or None,
            default=False,
            hub=record.source.value,
            canonical_name=record.name,
            canonical_display_name=record.display_name,
        )
        # Treat the registry path as absolute and resolve the actual
        # ``.xml`` artefact when the record points at a directory.
        absolute_path = precision.model_path
        if os.path.isdir(absolute_path):
            try:
                xml_files = sorted(
                    f for f in os.listdir(absolute_path) if f.endswith(".xml")
                )
            except OSError:
                xml_files = []
            if xml_files:
                absolute_path = os.path.join(absolute_path, xml_files[0])
        self.model_path_full = absolute_path
        # Uploaded models never carry a model-proc.
        self.model_proc_full = ""

    def exists_on_disk(self) -> bool:  # pragma: no cover - thin wrapper
        # Either the resolved ``.xml`` exists, or (genai-style) the
        # registry path is a populated directory.
        path = self.model_path_full
        if os.path.isfile(path):
            return True
        return os.path.isdir(path)


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
                    category_raw: str | None = entry.get("category")
                    # Prune entries whose files no longer exist on disk or are
                    # incomplete (e.g. a GenAI directory without the sentinel
                    # model file, left behind by a failed/interrupted download).
                    if not precisions or not any(
                        _precision_is_complete(category_raw, p.model_path)
                        for p in precisions
                    ):
                        logger.info(
                            "Pruning stale registry entry '%s' (files missing or incomplete)",
                            name,
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
    # Public lookups for uploaded models (graph.py fallback)
    # ------------------------------------------------------------------

    def find_installed_uploaded_model_by_display_name(
        self, display_name: str
    ) -> SupportedModel | None:
        """Return a ``SupportedModel`` view for an uploaded model.

        Used by ``graph.py`` as a fallback when ``SupportedModelsManager``
        does not know the display name. Uploaded models are registered
        under ``self._registry`` and live outside the YAML catalogue.

        Args:
            display_name: Display name as shown in the UI dropdown.
                Uploaded models use ``model_name`` as their display name.

        Returns:
            A ``_UploadedSupportedModel`` view of the first precision
            entry, or ``None`` when no matching record exists or the
            on-disk files are missing.
        """
        with self._registry_lock:
            record = next(
                (
                    r
                    for r in self._registry.values()
                    if r.display_name == display_name or r.name == display_name
                ),
                None,
            )
        if record is None or not record.precisions:
            return None
        adapter = _UploadedSupportedModel(record, record.precisions[0])
        if not adapter.exists_on_disk():
            return None
        return adapter

    def find_uploaded_model_by_path(
        self,
        model_path: str,
        model_proc_path: str | None = None,  # noqa: ARG002 - uploads have no model-proc
    ) -> SupportedModel | None:
        """Return a ``SupportedModel`` view for an uploaded model by path.

        Mirrors ``SupportedModelsManager.find_model_by_model_and_proc_path``
        for uploaded models. Matching prefers exact path equality and
        falls back to filename + parent-dir equality so existing
        pipelines referencing absolute paths can still be resolved.

        Args:
            model_path: Path written in the pipeline string. May be the
                model directory or an ``.xml`` artefact inside it.
            model_proc_path: Ignored. Uploaded models do not carry a
                model-proc file (kept for signature symmetry with
                ``SupportedModelsManager``).

        Returns:
            A ``_UploadedSupportedModel`` view of the matching record,
            or ``None`` when no record matches.
        """
        normalized = os.path.normpath(model_path)
        with self._registry_lock:
            records = list(self._registry.values())
        for record in records:
            for precision in record.precisions:
                registry_path = os.path.normpath(precision.model_path)
                if registry_path == normalized:
                    return _UploadedSupportedModel(record, precision)
                # Allow the pipeline string to point at the resolved
                # ``.xml`` artefact when the registry stores a directory.
                if (
                    os.path.isdir(registry_path)
                    and os.path.dirname(normalized) == registry_path
                ):
                    return _UploadedSupportedModel(record, precision)
        return None

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
                    default=bool(used_by),
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
            args=(job_id, model_name, head, download_request),
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
            if record is not None:
                category_raw = record.category.value if record.category else None
                if not any(
                    _precision_is_complete(category_raw, p.model_path)
                    for p in record.precisions
                ):
                    self._registry.pop(model_name, None)
                    self._save_registry_locked()
        logger.error("Model download job %s failed: %s", job_id, message)

    def _finalize_success(
        self, job_id: str, model_name: str, head: SupportedModel
    ) -> None:
        """Mark the job as COMPLETED and update the registry.

        Verifies that the expected model files are present on disk before
        trusting the model-download service's "completed" status.  The
        service can report success while leaving only partial artefacts —
        for example when a gated HuggingFace model is requested without a
        valid HF_TOKEN, the service may download config/metadata files and
        then exit cleanly, never writing the actual model weights.  In that
        case the job is re-classified as FAILED with an informative message.
        """
        # Refresh on-disk precision list from supported_models.yaml entries.
        entries = [
            m
            for m in SupportedModelsManager().get_all_supported_models()
            if m.canonical_name == model_name
        ]
        precisions = self._collect_precisions(entries)
        model_path = precisions[0].model_path if precisions else None

        # Verify the expected files are actually on disk before registering.
        if not any(e.exists_on_disk() for e in entries):
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

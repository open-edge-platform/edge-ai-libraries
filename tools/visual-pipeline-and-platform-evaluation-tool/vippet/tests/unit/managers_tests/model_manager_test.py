# SPDX-License-Identifier: Apache-2.0
"""Unit tests for ``managers.model_manager.ModelManager``.

The manager is a thread-safe singleton with three main concerns:

* Aggregating models from ``supported_models.yaml`` and the installed-
  models registry into a single API-facing list.
* Driving background download jobs (either OMZ subprocess or HTTP calls
  to the model-download microservice) and tracking their state.
* Forwarding multipart model uploads to model-download and registering
  the resulting model locally.

These tests avoid touching the real filesystem / network: every external
dependency (``SupportedModelsManager``, ``PipelineManager``,
``threading.Thread``, ``httpx``, ``subprocess``, ``os.path.*``) is
patched. The singleton state is reset between tests so that ``_jobs``
and ``_registry`` always start empty.
"""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
import time
import unittest
from typing import Any
from unittest.mock import MagicMock, mock_open, patch

import managers.model_manager as mm_module
from internal_types import (
    InternalModelCategory,
    InternalModelDownloadJobState,
    InternalModelDownloadJobStatus,
    InternalModelInstallStatus,
    InternalModelPrecision,
    InternalModelSource,
    InternalModelUploadSpec,
)
from managers.model_manager import (
    ModelManager,
    _DownloadRequestCache,
    _InstalledModelRecord,
)


# ----------------------------------------------------------------------
# Test helpers
# ----------------------------------------------------------------------


def _reset_manager() -> None:
    """Drop the ``ModelManager`` singleton so each test starts from a clean slate.

    The class uses an ``_initialized`` guard inside ``__init__`` so we
    cannot just create a new instance — we have to drop ``_instance``
    too, otherwise ``__new__`` returns the previous one.
    """
    ModelManager._instance = None
    # ``_DownloadRequestCache`` is a class-level lazy cache. Drop it so
    # tests that patch the YAML loader observe a fresh load.
    _DownloadRequestCache._data = None


def _make_supported_model(
    *,
    name: str = "yolo11n",
    display_name: str | None = None,
    canonical_name: str | None = None,
    canonical_display_name: str | None = None,
    hub: str = "ultralytics",
    model_type: str = "detection",
    precision: str | None = "FP16",
    model_path_full: str = "/models/output/ultralytics/yolo11n/FP16/model.xml",
    default: bool = False,
    unsupported_devices: str | None = None,
    exists_on_disk: bool = False,
) -> MagicMock:
    """Build a ``SupportedModel``-shaped mock.

    The manager only touches a small subset of attributes/methods, so we
    do not instantiate the real class (which would resolve ``MODELS_PATH``
    and normalize paths). All attributes the manager reads are wired up
    here.
    """
    sm = MagicMock(name=f"SupportedModel({name})")
    sm.name = name
    sm.display_name = display_name or f"{name} ({precision})" if precision else name
    sm.canonical_name = canonical_name or name
    sm.canonical_display_name = canonical_display_name or (
        f"{name} ({precision})" if precision else name
    )
    sm.hub = hub
    sm.model_type = model_type
    sm.precision = precision
    sm.model_path_full = model_path_full
    sm.default = default
    sm.unsupported_devices = unsupported_devices
    sm.exists_on_disk.return_value = exists_on_disk
    return sm


def _make_running_job(
    *, job_id: str = "job-1", model_name: str = "yolo11n"
) -> InternalModelDownloadJobStatus:
    """Build a RUNNING ``InternalModelDownloadJobStatus`` for direct insertion."""
    return InternalModelDownloadJobStatus(
        id=job_id,
        model_name=model_name,
        source=InternalModelSource.ULTRALYTICS,
        state=InternalModelDownloadJobState.RUNNING,
        start_time=int(time.time() * 1000),
        details=["starting"],
    )


# ----------------------------------------------------------------------
# Static helpers and tiny pure-function utilities
# ----------------------------------------------------------------------


class TestStaticHelpers(unittest.TestCase):
    """Unit tests for the small pure helpers on ``ModelManager``."""

    def test_to_internal_source_maps_known_values(self) -> None:
        self.assertEqual(
            ModelManager._to_internal_source("ultralytics"),
            InternalModelSource.ULTRALYTICS,
        )
        self.assertEqual(
            ModelManager._to_internal_source("omz"), InternalModelSource.OMZ
        )

    def test_to_internal_source_falls_back_to_custom_for_unknown(self) -> None:
        """Unknown hub values default to CUSTOM — never raise."""
        self.assertEqual(
            ModelManager._to_internal_source("something-new"),
            InternalModelSource.CUSTOM,
        )

    def test_to_internal_category_returns_none_for_empty(self) -> None:
        self.assertIsNone(ModelManager._to_internal_category(None))
        self.assertIsNone(ModelManager._to_internal_category(""))

    def test_to_internal_category_returns_none_for_unknown(self) -> None:
        self.assertIsNone(ModelManager._to_internal_category("weird"))

    def test_to_internal_category_maps_known(self) -> None:
        self.assertEqual(
            ModelManager._to_internal_category("detection"),
            InternalModelCategory.DETECTION,
        )

    def test_strip_precision_suffix_removes_trailing_paren(self) -> None:
        self.assertEqual(
            ModelManager._strip_precision_suffix("YOLO 11n (INT8)"),
            "YOLO 11n",
        )

    def test_strip_precision_suffix_keeps_input_without_suffix(self) -> None:
        self.assertEqual(
            ModelManager._strip_precision_suffix("YOLO 11n"),
            "YOLO 11n",
        )

    def test_collect_precisions_dedupes_and_preserves_order(self) -> None:
        a = _make_supported_model(precision="FP16", model_path_full="/p/a.xml")
        b = _make_supported_model(precision="INT8", model_path_full="/p/b.xml")
        # Second FP16 entry must be ignored (already seen).
        c = _make_supported_model(precision="FP16", model_path_full="/p/c.xml")
        d = _make_supported_model(precision=None, model_path_full="/p/d.xml")

        mgr = MagicMock(spec=ModelManager)
        precisions = ModelManager._collect_precisions(mgr, [a, b, c, d])

        self.assertEqual([p.precision for p in precisions], ["FP16", "INT8"])
        self.assertEqual(precisions[0].model_path, "/p/a.xml")

    def test_collect_variants_dedupes_by_display_name(self) -> None:
        """Variants are deduped by display_name so duplicate precisions collapse."""
        a = _make_supported_model(
            name="m_INT8", display_name="m (INT8)", precision="INT8"
        )
        b = _make_supported_model(
            name="m_INT8", display_name="m (INT8)", precision="INT8"
        )
        c = _make_supported_model(
            name="m_FP16", display_name="m (FP16)", precision="FP16"
        )
        a.exists_on_disk.return_value = True
        b.exists_on_disk.return_value = True
        c.exists_on_disk.return_value = False

        variants = ModelManager._collect_variants([a, b, c])

        self.assertEqual([v.display_name for v in variants], ["m (INT8)", "m (FP16)"])
        self.assertTrue(variants[0].installed)
        self.assertFalse(variants[1].installed)

    def test_variants_from_record_with_precision(self) -> None:
        record = _InstalledModelRecord(
            name="custom",
            display_name="My Custom Model",
            source=InternalModelSource.CUSTOM,
            category=InternalModelCategory.DETECTION,
            precisions=[
                InternalModelPrecision(precision="FP32", model_path="/p/x.xml")
            ],
        )
        variants = ModelManager._variants_from_record(record)
        self.assertEqual(len(variants), 1)
        self.assertEqual(variants[0].display_name, "My Custom Model (FP32)")
        self.assertEqual(variants[0].precision, "FP32")
        self.assertTrue(variants[0].installed)

    def test_variants_from_record_without_precision(self) -> None:
        """Records without a precision label still produce one valid variant."""
        record = _InstalledModelRecord(
            name="custom",
            display_name="My Custom",
            source=InternalModelSource.CUSTOM,
            category=None,
            precisions=[InternalModelPrecision(precision="", model_path="/p/x.xml")],
        )
        variants = ModelManager._variants_from_record(record)
        self.assertEqual(variants[0].display_name, "My Custom")
        self.assertEqual(variants[0].precision, "")


# ----------------------------------------------------------------------
# Install-status computation
# ----------------------------------------------------------------------


class TestComputeInstallStatus(unittest.TestCase):
    """Cover every branch of ``_compute_install_status``."""

    def setUp(self) -> None:
        _reset_manager()
        # Patch the YAML loader so ``__init__`` does not touch disk.
        self._supported_patcher = patch("managers.model_manager.SupportedModelsManager")
        self._supported_patcher.start()
        self.mgr = ModelManager()
        # Drop any pre-loaded registry state.
        self.mgr._registry = {}
        self.mgr._jobs = {}

    def tearDown(self) -> None:
        self._supported_patcher.stop()
        _reset_manager()

    def test_files_on_disk_short_circuits_to_installed(self) -> None:
        entry = _make_supported_model(exists_on_disk=True)
        status = self.mgr._compute_install_status(
            name="yolo11n", entries=[entry], active_jobs={}
        )
        self.assertEqual(status, InternalModelInstallStatus.INSTALLED)

    def test_registry_only_is_installed(self) -> None:
        self.mgr._registry["yolo11n"] = _InstalledModelRecord(
            name="yolo11n",
            display_name="x",
            source=InternalModelSource.ULTRALYTICS,
            category=None,
            precisions=[],
        )
        entry = _make_supported_model(exists_on_disk=False)
        status = self.mgr._compute_install_status(
            name="yolo11n", entries=[entry], active_jobs={}
        )
        self.assertEqual(status, InternalModelInstallStatus.INSTALLED)

    def test_running_job_yields_installing(self) -> None:
        entry = _make_supported_model(exists_on_disk=False)
        job = _make_running_job(model_name="yolo11n")
        status = self.mgr._compute_install_status(
            name="yolo11n", entries=[entry], active_jobs={"yolo11n": job}
        )
        self.assertEqual(status, InternalModelInstallStatus.INSTALLING)

    def test_failed_job_yields_failed(self) -> None:
        entry = _make_supported_model(exists_on_disk=False)
        job = _make_running_job(model_name="yolo11n")
        job.state = InternalModelDownloadJobState.FAILED
        status = self.mgr._compute_install_status(
            name="yolo11n", entries=[entry], active_jobs={"yolo11n": job}
        )
        self.assertEqual(status, InternalModelInstallStatus.FAILED)

    def test_completed_job_without_files_is_not_installed(self) -> None:
        """A COMPLETED job without on-disk files / registry entry must not
        be reported as INSTALLED — the registry update is the source of
        truth for "installed", not the job state."""
        entry = _make_supported_model(exists_on_disk=False)
        job = _make_running_job(model_name="yolo11n")
        job.state = InternalModelDownloadJobState.COMPLETED
        status = self.mgr._compute_install_status(
            name="yolo11n", entries=[entry], active_jobs={"yolo11n": job}
        )
        self.assertEqual(status, InternalModelInstallStatus.NOT_INSTALLED)

    def test_no_job_no_files_no_registry_is_not_installed(self) -> None:
        entry = _make_supported_model(exists_on_disk=False)
        status = self.mgr._compute_install_status(
            name="yolo11n", entries=[entry], active_jobs={}
        )
        self.assertEqual(status, InternalModelInstallStatus.NOT_INSTALLED)


# ----------------------------------------------------------------------
# Registry persistence
# ----------------------------------------------------------------------


class TestRegistryPersistence(unittest.TestCase):
    """Cover ``_load_registry`` / ``_save_registry_locked`` branches."""

    def setUp(self) -> None:
        _reset_manager()
        self._tmpdir = tempfile.mkdtemp(prefix="vippet-mm-registry-")
        self._registry_path = os.path.join(self._tmpdir, "installed_models.json")
        # Redirect the module-level constant for the duration of the test.
        self._orig_path = mm_module.INSTALLED_MODELS_REGISTRY
        mm_module.INSTALLED_MODELS_REGISTRY = self._registry_path
        # Avoid touching the real SupportedModelsManager.
        self._supported_patcher = patch("managers.model_manager.SupportedModelsManager")
        self._supported_patcher.start()

    def tearDown(self) -> None:
        self._supported_patcher.stop()
        mm_module.INSTALLED_MODELS_REGISTRY = self._orig_path
        import shutil

        shutil.rmtree(self._tmpdir, ignore_errors=True)
        _reset_manager()

    def test_load_registry_no_file_leaves_registry_empty(self) -> None:
        # File does not exist — manager should boot with an empty registry.
        mgr = ModelManager()
        self.assertEqual(mgr._registry, {})

    def test_load_registry_invalid_shape_is_ignored(self) -> None:
        with open(self._registry_path, "w") as f:
            json.dump({"not": "a list"}, f)
        mgr = ModelManager()
        self.assertEqual(mgr._registry, {})

    def test_load_registry_prunes_entries_with_missing_files(self) -> None:
        """Records whose ``model_path`` does not exist on disk are dropped
        and the file rewritten in sync."""
        with open(self._registry_path, "w") as f:
            json.dump(
                [
                    {
                        "name": "ghost",
                        "display_name": "Ghost",
                        "source": "custom",
                        "category": "detection",
                        "precisions": [
                            {"precision": "FP32", "model_path": "/does/not/exist"}
                        ],
                    }
                ],
                f,
            )
        mgr = ModelManager()
        self.assertNotIn("ghost", mgr._registry)
        # Registry file should now reflect the pruned state.
        with open(self._registry_path) as f:
            saved = json.load(f)
        self.assertEqual(saved, [])

    def test_load_registry_keeps_entry_with_existing_file(self) -> None:
        """An entry whose model file exists is loaded verbatim."""
        existing_file = os.path.join(self._tmpdir, "model.xml")
        open(existing_file, "w").close()
        with open(self._registry_path, "w") as f:
            json.dump(
                [
                    {
                        "name": "kept",
                        "display_name": "Kept",
                        "source": "custom",
                        "category": "classification",
                        "precisions": [
                            {"precision": "FP32", "model_path": existing_file}
                        ],
                    }
                ],
                f,
            )
        mgr = ModelManager()
        self.assertIn("kept", mgr._registry)
        record = mgr._registry["kept"]
        self.assertEqual(record.source, InternalModelSource.CUSTOM)
        self.assertEqual(record.category, InternalModelCategory.CLASSIFICATION)
        self.assertEqual(record.precisions[0].model_path, existing_file)

    def test_load_registry_skips_malformed_entries(self) -> None:
        """Entries without ``name`` or with broken precisions are skipped."""
        existing_file = os.path.join(self._tmpdir, "ok.xml")
        open(existing_file, "w").close()
        with open(self._registry_path, "w") as f:
            json.dump(
                [
                    {"display_name": "no-name"},  # missing name
                    {
                        "name": "no-precisions",
                        "precisions": [],  # pruned by ``not precisions`` guard
                    },
                    {
                        "name": "ok",
                        "display_name": "OK",
                        "source": "custom",
                        "category": "detection",
                        "precisions": [
                            {"precision": "FP32", "model_path": existing_file}
                        ],
                    },
                ],
                f,
            )
        mgr = ModelManager()
        self.assertEqual(set(mgr._registry.keys()), {"ok"})

    def test_upsert_and_remove_persist_to_disk(self) -> None:
        mgr = ModelManager()
        existing_file = os.path.join(self._tmpdir, "live.xml")
        open(existing_file, "w").close()

        mgr._upsert_registry_record(
            _InstalledModelRecord(
                name="live",
                display_name="Live",
                source=InternalModelSource.CUSTOM,
                category=None,
                precisions=[
                    InternalModelPrecision(precision="", model_path=existing_file)
                ],
            )
        )
        with open(self._registry_path) as f:
            saved = json.load(f)
        self.assertEqual(saved[0]["name"], "live")

        mgr._remove_registry_record("live")
        with open(self._registry_path) as f:
            saved = json.load(f)
        self.assertEqual(saved, [])

    def test_remove_registry_record_missing_name_is_noop(self) -> None:
        """Removing a name that is not in the registry must not write to disk."""
        mgr = ModelManager()
        # File does not exist yet.
        mgr._remove_registry_record("never-existed")
        self.assertFalse(os.path.exists(self._registry_path))


# ----------------------------------------------------------------------
# list_models — aggregation of YAML + registry
# ----------------------------------------------------------------------


class TestListModels(unittest.TestCase):
    """Cover ``list_models`` aggregation paths."""

    def setUp(self) -> None:
        _reset_manager()
        self._tmpdir = tempfile.mkdtemp(prefix="vippet-mm-list-")
        self._orig_path = mm_module.INSTALLED_MODELS_REGISTRY
        mm_module.INSTALLED_MODELS_REGISTRY = os.path.join(
            self._tmpdir, "installed_models.json"
        )
        # Patch the YAML loader and the pipeline manager. We patch both
        # the type and its singleton accessor pattern by returning the
        # same mock instance on each call.
        self._supported_patcher = patch("managers.model_manager.SupportedModelsManager")
        self._pipeline_patcher = patch("managers.model_manager.PipelineManager")
        self._supported_cls = self._supported_patcher.start()
        self._pipeline_cls = self._pipeline_patcher.start()
        self._supported_cls.return_value.get_all_supported_models.return_value = []
        self._pipeline_cls.return_value.get_model_display_names_used_by_pipelines.return_value = {}
        # Patch the download_request cache to a fixed value.
        _DownloadRequestCache._data = {}

    def tearDown(self) -> None:
        self._supported_patcher.stop()
        self._pipeline_patcher.stop()
        mm_module.INSTALLED_MODELS_REGISTRY = self._orig_path
        import shutil

        shutil.rmtree(self._tmpdir, ignore_errors=True)
        _reset_manager()

    def test_list_models_yaml_entry_not_installed(self) -> None:
        entry = _make_supported_model(
            name="yolo11n",
            display_name="YOLO 11n (FP16)",
            canonical_name="yolo11n",
            canonical_display_name="YOLO 11n (FP16)",
            precision="FP16",
            exists_on_disk=False,
        )
        self._supported_cls.return_value.get_all_supported_models.return_value = [entry]

        mgr = ModelManager()
        models = mgr.list_models()

        self.assertEqual(len(models), 1)
        m = models[0]
        self.assertEqual(m.name, "yolo11n")
        # Trailing ``(FP16)`` suffix is stripped from the canonical name.
        self.assertEqual(m.display_name, "YOLO 11n")
        self.assertEqual(m.source, InternalModelSource.ULTRALYTICS)
        self.assertEqual(m.install_status, InternalModelInstallStatus.NOT_INSTALLED)
        self.assertEqual([v.precision for v in m.variants], ["FP16"])

    def test_list_models_marks_installed_when_files_present(self) -> None:
        entry = _make_supported_model(
            name="yolo11n",
            canonical_name="yolo11n",
            precision="FP16",
            exists_on_disk=True,
        )
        self._supported_cls.return_value.get_all_supported_models.return_value = [entry]

        mgr = ModelManager()
        models = mgr.list_models()
        self.assertEqual(models[0].install_status, InternalModelInstallStatus.INSTALLED)

    def test_list_models_groups_multiple_precisions(self) -> None:
        """Two YAML entries with the same canonical name collapse into one Model."""
        a = _make_supported_model(
            name="yolo11n_FP16",
            canonical_name="yolo11n",
            canonical_display_name="YOLO 11n (FP16)",
            display_name="YOLO 11n (FP16)",
            precision="FP16",
        )
        b = _make_supported_model(
            name="yolo11n_INT8",
            canonical_name="yolo11n",
            canonical_display_name="YOLO 11n (INT8)",
            display_name="YOLO 11n (INT8)",
            precision="INT8",
        )
        self._supported_cls.return_value.get_all_supported_models.return_value = [a, b]

        mgr = ModelManager()
        models = mgr.list_models()
        self.assertEqual(len(models), 1)
        self.assertEqual([p.precision for p in models[0].precisions], ["FP16", "INT8"])

    def test_list_models_includes_registry_only_custom_models(self) -> None:
        """Custom uploaded models are listed even with no YAML entry."""
        existing_file = os.path.join(self._tmpdir, "custom.xml")
        open(existing_file, "w").close()

        mgr = ModelManager()
        mgr._registry["my-custom"] = _InstalledModelRecord(
            name="my-custom",
            display_name="My Custom",
            source=InternalModelSource.CUSTOM,
            category=InternalModelCategory.DETECTION,
            precisions=[
                InternalModelPrecision(precision="FP32", model_path=existing_file)
            ],
        )

        models = mgr.list_models()
        self.assertEqual(len(models), 1)
        self.assertEqual(models[0].name, "my-custom")
        self.assertEqual(models[0].source, InternalModelSource.CUSTOM)
        self.assertEqual(models[0].install_status, InternalModelInstallStatus.INSTALLED)

    def test_list_models_skips_registry_entries_already_in_yaml(self) -> None:
        """Registry entries matching a YAML canonical name are not duplicated."""
        entry = _make_supported_model(name="yolo11n", canonical_name="yolo11n")
        self._supported_cls.return_value.get_all_supported_models.return_value = [entry]
        mgr = ModelManager()
        mgr._registry["yolo11n"] = _InstalledModelRecord(
            name="yolo11n",
            display_name="Y",
            source=InternalModelSource.ULTRALYTICS,
            category=None,
            precisions=[],
        )
        models = mgr.list_models()
        names = [m.name for m in models]
        self.assertEqual(names.count("yolo11n"), 1)

    def test_list_models_used_by_pipelines_is_populated(self) -> None:
        entry = _make_supported_model(
            name="yolo11n",
            canonical_name="yolo11n",
            display_name="YOLO 11n (FP16)",
            precision="FP16",
        )
        self._supported_cls.return_value.get_all_supported_models.return_value = [entry]
        self._pipeline_cls.return_value.get_model_display_names_used_by_pipelines.return_value = {
            "YOLO 11n (FP16)": ["smart-nvr", "goods-detection"]
        }

        mgr = ModelManager()
        models = mgr.list_models()
        self.assertEqual(
            sorted(models[0].used_by_pipelines), ["goods-detection", "smart-nvr"]
        )


# ----------------------------------------------------------------------
# start_download — entry-point that picks the right worker
# ----------------------------------------------------------------------


class TestStartDownload(unittest.TestCase):
    """``start_download`` validation and worker dispatch."""

    def setUp(self) -> None:
        _reset_manager()
        self._supported_patcher = patch("managers.model_manager.SupportedModelsManager")
        self._supported_cls = self._supported_patcher.start()
        self._supported_cls.return_value.get_all_supported_models.return_value = []
        _DownloadRequestCache._data = {}

    def tearDown(self) -> None:
        self._supported_patcher.stop()
        _reset_manager()

    def test_returns_404_for_unknown_model(self) -> None:
        mgr = ModelManager()
        job_id, status, msg = mgr.start_download("nope")
        self.assertIsNone(job_id)
        self.assertEqual(status, 404)
        self.assertIn("not supported", msg)

    def test_returns_409_when_files_already_on_disk(self) -> None:
        entry = _make_supported_model(canonical_name="yolo11n", exists_on_disk=True)
        self._supported_cls.return_value.get_all_supported_models.return_value = [entry]
        _DownloadRequestCache._data = {"yolo11n": {"model_id": "yolo11n"}}

        mgr = ModelManager()
        job_id, status, msg = mgr.start_download("yolo11n")
        self.assertIsNone(job_id)
        self.assertEqual(status, 409)
        self.assertIn("already installed", msg)

    def test_returns_409_when_a_job_is_already_running(self) -> None:
        entry = _make_supported_model(canonical_name="yolo11n", exists_on_disk=False)
        self._supported_cls.return_value.get_all_supported_models.return_value = [entry]
        _DownloadRequestCache._data = {"yolo11n": {"model_id": "yolo11n"}}

        mgr = ModelManager()
        running = _make_running_job(job_id="existing", model_name="yolo11n")
        mgr._jobs["existing"] = running

        job_id, status, msg = mgr.start_download("yolo11n")
        self.assertIsNone(job_id)
        self.assertEqual(status, 409)
        self.assertIn("already running", msg)

    def test_returns_400_when_remote_model_has_no_download_request(self) -> None:
        entry = _make_supported_model(
            canonical_name="yolo11n", hub="ultralytics", exists_on_disk=False
        )
        self._supported_cls.return_value.get_all_supported_models.return_value = [entry]
        _DownloadRequestCache._data = {}  # No download_request configured.

        mgr = ModelManager()
        job_id, status, msg = mgr.start_download("yolo11n")
        self.assertIsNone(job_id)
        self.assertEqual(status, 400)
        self.assertIn("download_request", msg)

    @patch("managers.model_manager.threading.Thread")
    def test_returns_202_and_spawns_remote_worker(self, mock_thread_cls) -> None:
        """Accepted remote download: a worker thread is started and the job is recorded."""
        entry = _make_supported_model(
            canonical_name="yolo11n", hub="ultralytics", exists_on_disk=False
        )
        self._supported_cls.return_value.get_all_supported_models.return_value = [entry]
        _DownloadRequestCache._data = {"yolo11n": {"model_id": "yolo11n"}}

        mgr = ModelManager()
        job_id, status, msg = mgr.start_download("yolo11n")

        self.assertEqual(status, 202)
        self.assertIsNotNone(job_id)
        self.assertIn(job_id, mgr._jobs)
        # The worker thread was created and started exactly once.
        mock_thread_cls.assert_called_once()
        mock_thread_cls.return_value.start.assert_called_once()
        # Dispatched to the remote worker (not the OMZ one).
        target = mock_thread_cls.call_args.kwargs["target"]
        self.assertEqual(target, mgr._execute_remote_download)

    @patch("managers.model_manager.threading.Thread")
    def test_returns_202_for_omz_without_download_request(
        self, mock_thread_cls
    ) -> None:
        """OMZ source is allowed to start a download with no ``download_request``."""
        entry = _make_supported_model(
            canonical_name="age-gender-recognition-retail-0013",
            hub="omz",
            exists_on_disk=False,
        )
        self._supported_cls.return_value.get_all_supported_models.return_value = [entry]
        _DownloadRequestCache._data = {}  # OMZ does not need a download_request.

        mgr = ModelManager()
        job_id, status, _msg = mgr.start_download("age-gender-recognition-retail-0013")

        self.assertEqual(status, 202)
        target = mock_thread_cls.call_args.kwargs["target"]
        self.assertEqual(target, mgr._execute_omz_download)


# ----------------------------------------------------------------------
# Remote download worker — happy path / failures / timeout
# ----------------------------------------------------------------------


class _FakeResponse:
    """Minimal stand-in for ``httpx.Response`` used by the remote worker tests."""

    def __init__(self, *, status_code: int = 200, json_body: Any = None) -> None:
        self.status_code = status_code
        self._json = json_body if json_body is not None else {}

    def json(self) -> Any:
        return self._json

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            import httpx

            raise httpx.HTTPStatusError(
                "http error", request=MagicMock(), response=MagicMock()
            )


class _FakeHttpxClient:
    """Context-manager stub returning canned responses for POST/GET."""

    def __init__(
        self,
        *,
        post_response: _FakeResponse | None = None,
        get_responses: list[_FakeResponse] | None = None,
        raise_on: str | None = None,
    ) -> None:
        self._post_response = post_response or _FakeResponse()
        self._get_queue = list(get_responses or [])
        self._raise_on = raise_on
        self.posts: list[tuple[str, dict[str, Any]]] = []
        self.gets: list[str] = []

    def __enter__(self) -> "_FakeHttpxClient":
        return self

    def __exit__(self, *exc_info: Any) -> None:
        return None

    def post(self, url: str, **kwargs: Any) -> _FakeResponse:
        import httpx

        if self._raise_on == "post":
            raise httpx.HTTPError("simulated network error")
        self.posts.append((url, kwargs))
        return self._post_response

    def get(self, url: str, **_kwargs: Any) -> _FakeResponse:
        import httpx

        if self._raise_on == "get":
            raise httpx.HTTPError("simulated network error during poll")
        self.gets.append(url)
        if not self._get_queue:
            # Tests that don't seed enough responses are typically
            # exercising the timeout path: keep replying ``processing``
            # so the polling loop only exits via the deadline.
            return _FakeResponse(json_body={"status": "processing"})
        return self._get_queue.pop(0)


class TestExecuteRemoteDownload(unittest.TestCase):
    """Cover the remote download worker — happy path, failures, timeout."""

    def setUp(self) -> None:
        _reset_manager()
        self._tmpdir = tempfile.mkdtemp(prefix="vippet-mm-remote-")
        self._orig_path = mm_module.INSTALLED_MODELS_REGISTRY
        mm_module.INSTALLED_MODELS_REGISTRY = os.path.join(
            self._tmpdir, "installed_models.json"
        )
        self._supported_patcher = patch("managers.model_manager.SupportedModelsManager")
        self._supported_cls = self._supported_patcher.start()
        self._supported_cls.return_value.get_all_supported_models.return_value = []
        # Speed up the polling loop and timeout for tests.
        self._orig_poll = mm_module.DOWNLOAD_POLL_INTERVAL_S
        self._orig_timeout = mm_module.DOWNLOAD_TIMEOUT_S
        mm_module.DOWNLOAD_POLL_INTERVAL_S = 0
        mm_module.DOWNLOAD_TIMEOUT_S = 5
        self.mgr = ModelManager()
        self.head = _make_supported_model(canonical_name="yolo11n")

    def tearDown(self) -> None:
        self._supported_patcher.stop()
        mm_module.DOWNLOAD_POLL_INTERVAL_S = self._orig_poll
        mm_module.DOWNLOAD_TIMEOUT_S = self._orig_timeout
        mm_module.INSTALLED_MODELS_REGISTRY = self._orig_path
        import shutil

        shutil.rmtree(self._tmpdir, ignore_errors=True)
        _reset_manager()

    def _seed_job(self, job_id: str = "job-1") -> None:
        self.mgr._jobs[job_id] = _make_running_job(job_id=job_id, model_name="yolo11n")

    def test_completes_when_all_external_jobs_succeed(self) -> None:
        self._seed_job()
        client = _FakeHttpxClient(
            post_response=_FakeResponse(json_body={"job_ids": ["ext-1"]}),
            get_responses=[_FakeResponse(json_body={"status": "completed"})],
        )
        with (
            patch("managers.model_manager.httpx.Client", return_value=client),
            patch.object(self.mgr, "_finalize_success") as fin,
        ):
            self.mgr._execute_remote_download(
                "job-1", "yolo11n", self.head, {"model_id": "yolo11n"}
            )
        fin.assert_called_once_with("job-1", "yolo11n", self.head)

    def test_fails_when_post_returns_no_job_ids(self) -> None:
        self._seed_job()
        client = _FakeHttpxClient(
            post_response=_FakeResponse(json_body={"job_ids": []})
        )
        with patch("managers.model_manager.httpx.Client", return_value=client):
            self.mgr._execute_remote_download(
                "job-1", "yolo11n", self.head, {"model_id": "yolo11n"}
            )
        job = self.mgr._jobs["job-1"]
        self.assertEqual(job.state, InternalModelDownloadJobState.FAILED)
        self.assertIn("no job ids", job.details[0])

    def test_aggregates_errors_when_polling_reports_failed(self) -> None:
        self._seed_job()
        client = _FakeHttpxClient(
            post_response=_FakeResponse(
                json_body={"job_ids": ["ext-1", "ext-2"], "status": "queued"}
            ),
            get_responses=[
                _FakeResponse(json_body={"status": "failed", "error": "boom-1"}),
                _FakeResponse(json_body={"status": "completed"}),
            ],
        )
        with patch("managers.model_manager.httpx.Client", return_value=client):
            self.mgr._execute_remote_download(
                "job-1", "yolo11n", self.head, {"model_id": "yolo11n"}
            )
        job = self.mgr._jobs["job-1"]
        self.assertEqual(job.state, InternalModelDownloadJobState.FAILED)
        self.assertIn("boom-1", job.details[0])

    def test_treats_404_from_external_job_as_failure(self) -> None:
        self._seed_job()
        client = _FakeHttpxClient(
            post_response=_FakeResponse(json_body={"job_ids": ["ext-1"]}),
            get_responses=[_FakeResponse(status_code=404)],
        )
        with patch("managers.model_manager.httpx.Client", return_value=client):
            self.mgr._execute_remote_download(
                "job-1", "yolo11n", self.head, {"model_id": "yolo11n"}
            )
        job = self.mgr._jobs["job-1"]
        self.assertEqual(job.state, InternalModelDownloadJobState.FAILED)
        self.assertIn("not found", job.details[0])

    def test_post_http_error_marks_job_failed(self) -> None:
        self._seed_job()
        client = _FakeHttpxClient(raise_on="post")
        with patch("managers.model_manager.httpx.Client", return_value=client):
            self.mgr._execute_remote_download(
                "job-1", "yolo11n", self.head, {"model_id": "yolo11n"}
            )
        job = self.mgr._jobs["job-1"]
        self.assertEqual(job.state, InternalModelDownloadJobState.FAILED)
        self.assertIn("HTTP error", job.details[0])

    def test_polling_timeout_marks_job_failed(self) -> None:
        """When external jobs never reach a terminal state the worker times out."""
        self._seed_job()
        # Force the polling loop to run at least once, then expire the deadline.
        mm_module.DOWNLOAD_TIMEOUT_S = 0.05
        client = _FakeHttpxClient(
            post_response=_FakeResponse(json_body={"job_ids": ["ext-1"]}),
            # Always returns ``processing`` so the loop never finishes.
            get_responses=[
                _FakeResponse(json_body={"status": "processing"}) for _ in range(50)
            ],
        )
        with patch("managers.model_manager.httpx.Client", return_value=client):
            self.mgr._execute_remote_download(
                "job-1", "yolo11n", self.head, {"model_id": "yolo11n"}
            )
        job = self.mgr._jobs["job-1"]
        self.assertEqual(job.state, InternalModelDownloadJobState.FAILED)
        self.assertIn("timed out", job.details[0])


# ----------------------------------------------------------------------
# OMZ worker — only the very-light branches
# ----------------------------------------------------------------------


class TestExecuteOmzDownload(unittest.TestCase):
    """Light tests for the OMZ worker — we mock subprocess + filesystem."""

    def setUp(self) -> None:
        _reset_manager()
        self._supported_patcher = patch("managers.model_manager.SupportedModelsManager")
        self._supported_cls = self._supported_patcher.start()
        self._supported_cls.return_value.get_all_supported_models.return_value = []
        self.mgr = ModelManager()
        self.head = _make_supported_model(
            canonical_name="age-gender-recognition-retail-0013", hub="omz"
        )

    def tearDown(self) -> None:
        self._supported_patcher.stop()
        _reset_manager()

    def _seed_job(self, job_id: str = "job-1") -> None:
        self.mgr._jobs[job_id] = _make_running_job(
            job_id=job_id, model_name="age-gender-recognition-retail-0013"
        )
        self.mgr._jobs[job_id].source = InternalModelSource.OMZ

    @patch("managers.model_manager.shutil.rmtree")
    @patch("managers.model_manager.tempfile.mkdtemp", return_value="/tmp/scratch")
    @patch("managers.model_manager.os.makedirs")
    def test_happy_path_calls_finalize_success(self, _md, _mk, _rm) -> None:
        self._seed_job()
        with (
            patch.object(self.mgr, "_run_subprocess") as run,
            patch.object(self.mgr, "_materialize_omz_artifacts") as mat,
            patch.object(self.mgr, "_finalize_success") as fin,
        ):
            self.mgr._execute_omz_download(
                "job-1", "age-gender-recognition-retail-0013", self.head
            )
        self.assertEqual(run.call_count, 2)  # downloader + converter
        mat.assert_called_once()
        fin.assert_called_once_with(
            "job-1", "age-gender-recognition-retail-0013", self.head
        )

    @patch("managers.model_manager.shutil.rmtree")
    @patch("managers.model_manager.tempfile.mkdtemp", return_value="/tmp/scratch")
    @patch("managers.model_manager.os.makedirs")
    def test_called_process_error_marks_job_failed(self, _md, _mk, _rm) -> None:
        self._seed_job()
        err = subprocess.CalledProcessError(
            returncode=2,
            cmd=["omz_downloader", "--name", "x"],
            output=None,
            stderr="boom",
        )
        with patch.object(self.mgr, "_run_subprocess", side_effect=err):
            self.mgr._execute_omz_download(
                "job-1", "age-gender-recognition-retail-0013", self.head
            )
        job = self.mgr._jobs["job-1"]
        self.assertEqual(job.state, InternalModelDownloadJobState.FAILED)
        # ``details`` carries both the summary and the captured stderr.
        joined = "\n".join(job.details)
        self.assertIn("OMZ command failed", joined)
        self.assertIn("boom", joined)

    @patch("managers.model_manager.shutil.rmtree")
    @patch("managers.model_manager.tempfile.mkdtemp", return_value="/tmp/scratch")
    @patch("managers.model_manager.os.makedirs")
    def test_missing_omz_binaries_marks_job_failed(self, _md, _mk, _rm) -> None:
        self._seed_job()
        with patch.object(
            self.mgr,
            "_run_subprocess",
            side_effect=FileNotFoundError("omz_downloader"),
        ):
            self.mgr._execute_omz_download(
                "job-1", "age-gender-recognition-retail-0013", self.head
            )
        job = self.mgr._jobs["job-1"]
        self.assertEqual(job.state, InternalModelDownloadJobState.FAILED)
        self.assertIn("openvino-dev", job.details[0])


# ----------------------------------------------------------------------
# upload_model — proxy to model-download
# ----------------------------------------------------------------------


class TestUploadModel(unittest.TestCase):
    """Cover the ``upload_model`` proxy path."""

    def setUp(self) -> None:
        _reset_manager()
        self._tmpdir = tempfile.mkdtemp(prefix="vippet-mm-upload-")
        self._orig_path = mm_module.INSTALLED_MODELS_REGISTRY
        mm_module.INSTALLED_MODELS_REGISTRY = os.path.join(
            self._tmpdir, "installed_models.json"
        )
        self._supported_patcher = patch("managers.model_manager.SupportedModelsManager")
        self._supported_patcher.start()
        # A real, readable file is needed because ``upload_model`` opens it.
        self._payload = os.path.join(self._tmpdir, "model.zip")
        with open(self._payload, "wb") as f:
            f.write(b"PK\x03\x04 fake zip")
        self.mgr = ModelManager()
        self.spec = InternalModelUploadSpec(
            model_name="my-detector",
            category=InternalModelCategory.DETECTION,
            file_path=self._payload,
            original_filename="my-detector.zip",
        )

    def tearDown(self) -> None:
        self._supported_patcher.stop()
        mm_module.INSTALLED_MODELS_REGISTRY = self._orig_path
        import shutil

        shutil.rmtree(self._tmpdir, ignore_errors=True)
        _reset_manager()

    def test_upload_success_registers_model_and_returns_201(self) -> None:
        client = _FakeHttpxClient(
            post_response=_FakeResponse(
                status_code=201,
                json_body={"output_dir": "/models/output/custom/my-detector"},
            )
        )
        with patch("managers.model_manager.httpx.Client", return_value=client):
            model, status, msg = self.mgr.upload_model(self.spec)

        self.assertEqual(status, 201)
        assert model is not None
        self.assertEqual(model.name, "my-detector")
        self.assertEqual(model.source, InternalModelSource.CUSTOM)
        self.assertEqual(model.install_status, InternalModelInstallStatus.INSTALLED)
        self.assertIn("my-detector", self.mgr._registry)
        self.assertEqual(
            self.mgr._registry["my-detector"].precisions[0].model_path,
            "/models/output/custom/my-detector",
        )
        self.assertIn("uploaded successfully", msg)

    def test_upload_success_without_output_dir_uses_fallback_path(self) -> None:
        """When model-download omits ``output_dir`` the manager falls back to MODELS_PATH."""
        client = _FakeHttpxClient(
            post_response=_FakeResponse(status_code=201, json_body={})
        )
        with patch("managers.model_manager.httpx.Client", return_value=client):
            model, status, _msg = self.mgr.upload_model(self.spec)
        self.assertEqual(status, 201)
        assert model is not None
        # Path is composed from MODELS_PATH + ``custom_uploaded_models``.
        self.assertTrue(model.precisions[0].model_path.endswith("/my-detector"))

    def test_upload_returns_502_on_http_error(self) -> None:
        client = _FakeHttpxClient(raise_on="post")
        with patch("managers.model_manager.httpx.Client", return_value=client):
            model, status, msg = self.mgr.upload_model(self.spec)
        self.assertIsNone(model)
        self.assertEqual(status, 502)
        self.assertIn("Upload failed", msg)

    def test_upload_propagates_upstream_status_and_detail(self) -> None:
        """A 4xx response from model-download is mirrored to the caller."""
        client = _FakeHttpxClient(
            post_response=_FakeResponse(
                status_code=409,
                json_body={"detail": "Model already exists"},
            )
        )
        with patch("managers.model_manager.httpx.Client", return_value=client):
            model, status, msg = self.mgr.upload_model(self.spec)
        self.assertIsNone(model)
        self.assertEqual(status, 409)
        self.assertEqual(msg, "Model already exists")

    def test_upload_extracts_detail_from_fastapi_validation_array(self) -> None:
        """FastAPI-style ``detail: [{msg, ...}]`` payloads are summarised."""
        client = _FakeHttpxClient(
            post_response=_FakeResponse(
                status_code=400,
                json_body={
                    "detail": [
                        {"msg": "field required"},
                        {"msg": "value error"},
                    ]
                },
            )
        )
        with patch("managers.model_manager.httpx.Client", return_value=client):
            _model, status, msg = self.mgr.upload_model(self.spec)
        self.assertEqual(status, 400)
        self.assertIn("field required", msg)
        self.assertIn("value error", msg)


# ----------------------------------------------------------------------
# Temp-file helpers
# ----------------------------------------------------------------------


class TestTempfileHelpers(unittest.TestCase):
    """Cover ``write_upload_to_tempfile`` and ``cleanup_tempfile``."""

    def test_write_upload_to_tempfile_streams_and_returns_path(self) -> None:
        import io

        payload = b"hello world" * 100
        upload = io.BytesIO(payload)
        path = ModelManager.write_upload_to_tempfile(upload, "x.zip")
        try:
            self.assertTrue(os.path.isfile(path))
            self.assertTrue(path.endswith(".zip"))
            with open(path, "rb") as f:
                self.assertEqual(f.read(), payload)
        finally:
            os.unlink(path)

    def test_write_upload_to_tempfile_cleans_up_on_error(self) -> None:
        """If copying fails the temp file is removed before re-raising."""

        class BoomBinary:
            def read(self, *_args: Any, **_kwargs: Any) -> bytes:
                raise RuntimeError("boom")

        path_holder: list[str] = []
        real_mkstemp = tempfile.mkstemp

        def _spy_mkstemp(*args: Any, **kwargs: Any) -> tuple[int, str]:
            fd, p = real_mkstemp(*args, **kwargs)
            path_holder.append(p)
            return fd, p

        with patch("managers.model_manager.tempfile.mkstemp", side_effect=_spy_mkstemp):
            with self.assertRaises(RuntimeError):
                ModelManager.write_upload_to_tempfile(BoomBinary(), "x.zip")  # type: ignore[arg-type]

        self.assertTrue(path_holder, "spy must have captured the temp path")
        self.assertFalse(
            os.path.exists(path_holder[0]),
            "temp file must be deleted on copy failure",
        )

    def test_cleanup_tempfile_handles_none_and_missing(self) -> None:
        # Both paths are silent no-ops.
        ModelManager.cleanup_tempfile(None)
        ModelManager.cleanup_tempfile("/does/not/exist")

    def test_cleanup_tempfile_removes_existing_file(self) -> None:
        fd, path = tempfile.mkstemp(prefix="vippet-cleanup-")
        os.close(fd)
        self.assertTrue(os.path.isfile(path))
        ModelManager.cleanup_tempfile(path)
        self.assertFalse(os.path.exists(path))


# ----------------------------------------------------------------------
# Lifecycle helpers — _fail_job / _finalize_success
# ----------------------------------------------------------------------


class TestJobLifecycle(unittest.TestCase):
    """Direct unit tests for ``_fail_job`` and ``_finalize_success``."""

    def setUp(self) -> None:
        _reset_manager()
        self._tmpdir = tempfile.mkdtemp(prefix="vippet-mm-lifecycle-")
        self._orig_path = mm_module.INSTALLED_MODELS_REGISTRY
        mm_module.INSTALLED_MODELS_REGISTRY = os.path.join(
            self._tmpdir, "installed_models.json"
        )
        self._supported_patcher = patch("managers.model_manager.SupportedModelsManager")
        self._supported_cls = self._supported_patcher.start()
        self._supported_cls.return_value.get_all_supported_models.return_value = []
        self.mgr = ModelManager()

    def tearDown(self) -> None:
        self._supported_patcher.stop()
        mm_module.INSTALLED_MODELS_REGISTRY = self._orig_path
        import shutil

        shutil.rmtree(self._tmpdir, ignore_errors=True)
        _reset_manager()

    def test_fail_job_records_state_and_end_time(self) -> None:
        job = _make_running_job(job_id="job-1", model_name="x")
        self.mgr._jobs["job-1"] = job
        self.mgr._fail_job("job-1", "stuff went wrong")
        self.assertEqual(job.state, InternalModelDownloadJobState.FAILED)
        self.assertIsNotNone(job.end_time)
        self.assertEqual(job.details, ["stuff went wrong"])

    def test_fail_job_with_custom_details_preserves_them(self) -> None:
        job = _make_running_job(job_id="job-1")
        self.mgr._jobs["job-1"] = job
        self.mgr._fail_job("job-1", "short", details=["a", "b", "c"])
        self.assertEqual(job.details, ["a", "b", "c"])

    def test_fail_job_unknown_id_is_silent(self) -> None:
        """Calling _fail_job for an unknown id is a no-op (not an error)."""
        self.mgr._fail_job("ghost", "x")  # must not raise

    def test_fail_job_drops_registry_entry_when_files_missing(self) -> None:
        """A failed install with no on-disk files drops the stale record."""
        self.mgr._registry["yolo11n"] = _InstalledModelRecord(
            name="yolo11n",
            display_name="x",
            source=InternalModelSource.ULTRALYTICS,
            category=None,
            precisions=[
                InternalModelPrecision(precision="FP16", model_path="/missing.xml")
            ],
        )
        job = _make_running_job(job_id="job-1", model_name="yolo11n")
        self.mgr._jobs["job-1"] = job
        self.mgr._fail_job("job-1", "nope")
        self.assertNotIn("yolo11n", self.mgr._registry)

    def test_finalize_success_records_state_and_registry(self) -> None:
        entry = _make_supported_model(
            canonical_name="yolo11n",
            canonical_display_name="YOLO 11n (FP16)",
            precision="FP16",
            model_path_full="/models/output/yolo11n/FP16/model.xml",
        )
        self._supported_cls.return_value.get_all_supported_models.return_value = [entry]
        job = _make_running_job(job_id="job-1", model_name="yolo11n")
        self.mgr._jobs["job-1"] = job

        self.mgr._finalize_success("job-1", "yolo11n", entry)

        self.assertEqual(job.state, InternalModelDownloadJobState.COMPLETED)
        self.assertEqual(job.model_path, entry.model_path_full)
        self.assertIn("yolo11n", self.mgr._registry)
        # Display name has the precision suffix stripped.
        self.assertEqual(self.mgr._registry["yolo11n"].display_name, "YOLO 11n")


# ----------------------------------------------------------------------
# DownloadRequestCache — lazy load + malformed YAML
# ----------------------------------------------------------------------


class TestDownloadRequestCache(unittest.TestCase):
    """The cache is read-once; tests assert ``get`` semantics."""

    def setUp(self) -> None:
        _DownloadRequestCache._data = None

    def tearDown(self) -> None:
        _DownloadRequestCache._data = None

    def test_get_returns_dict_for_known_name(self) -> None:
        yaml_payload = (
            "- name: yolo11n\n"
            "  download_request:\n"
            "    model_id: yolo11n\n"
            "- name: weird\n"
        )
        with patch("builtins.open", mock_open(read_data=yaml_payload)):
            value = _DownloadRequestCache.get("yolo11n")
        self.assertEqual(value, {"model_id": "yolo11n"})

    def test_get_returns_none_for_missing(self) -> None:
        with patch("builtins.open", mock_open(read_data="- name: x\n")):
            self.assertIsNone(_DownloadRequestCache.get("nope"))

    def test_get_returns_none_for_entry_without_download_request(self) -> None:
        with patch("builtins.open", mock_open(read_data="- name: x\n")):
            self.assertIsNone(_DownloadRequestCache.get("x"))

    def test_get_handles_yaml_load_error(self) -> None:
        """A broken YAML must not raise — cache stays empty and lookups return None."""
        with patch("builtins.open", side_effect=OSError("no such file")):
            self.assertIsNone(_DownloadRequestCache.get("yolo11n"))
        # Second call must not retry the broken open.
        self.assertEqual(_DownloadRequestCache._data, {})

    def test_get_caches_after_first_call(self) -> None:
        yaml_payload = "- name: yolo11n\n  download_request: {model_id: yolo11n}\n"
        with patch("builtins.open", mock_open(read_data=yaml_payload)) as m:
            _DownloadRequestCache.get("yolo11n")
            _DownloadRequestCache.get("yolo11n")
        # Only the first call opened the YAML.
        self.assertEqual(m.call_count, 1)


# ----------------------------------------------------------------------
# Singleton + simple accessors
# ----------------------------------------------------------------------


class TestSingletonAndJobAccessors(unittest.TestCase):
    """Cover the trivial accessors and singleton identity."""

    def setUp(self) -> None:
        _reset_manager()
        self._supported_patcher = patch("managers.model_manager.SupportedModelsManager")
        self._supported_patcher.start()

    def tearDown(self) -> None:
        self._supported_patcher.stop()
        _reset_manager()

    def test_singleton_returns_same_instance(self) -> None:
        a = ModelManager()
        b = ModelManager()
        self.assertIs(a, b)

    def test_get_all_jobs_returns_snapshot(self) -> None:
        mgr = ModelManager()
        job = _make_running_job(job_id="job-1")
        mgr._jobs["job-1"] = job
        jobs = mgr.get_all_jobs()
        self.assertEqual([j.id for j in jobs], ["job-1"])

    def test_get_job_returns_none_for_unknown(self) -> None:
        mgr = ModelManager()
        self.assertIsNone(mgr.get_job("nope"))

    def test_get_job_summary_returns_none_for_unknown(self) -> None:
        mgr = ModelManager()
        self.assertIsNone(mgr.get_job_summary("nope"))

    def test_get_job_summary_returns_summary(self) -> None:
        mgr = ModelManager()
        job = _make_running_job(job_id="job-1", model_name="yolo11n")
        mgr._jobs["job-1"] = job
        summary = mgr.get_job_summary("job-1")
        assert summary is not None
        self.assertEqual(summary.id, "job-1")
        self.assertEqual(summary.model_name, "yolo11n")
        self.assertEqual(summary.source, InternalModelSource.ULTRALYTICS)


# ----------------------------------------------------------------------
# _materialize_omz_artifacts — file-system layout normalisation
# ----------------------------------------------------------------------


class TestMaterializeOmzArtifacts(unittest.TestCase):
    """End-to-end test for OMZ artefact placement using a temp scratch tree.

    We build the directory layout that ``omz_converter`` is expected to
    produce, then assert the manager moves the files to the canonical
    ``MODELS_PATH/omz/<name>`` location and applies the per-model rule.
    """

    def setUp(self) -> None:
        _reset_manager()
        self._tmpdir = tempfile.mkdtemp(prefix="vippet-mm-omz-")
        self._supported_patcher = patch("managers.model_manager.SupportedModelsManager")
        self._supported_patcher.start()
        self.mgr = ModelManager()
        self.mgr._jobs["job-1"] = _make_running_job(
            job_id="job-1", model_name="face-detection-retail-0004"
        )

    def tearDown(self) -> None:
        self._supported_patcher.stop()
        import shutil

        shutil.rmtree(self._tmpdir, ignore_errors=True)
        _reset_manager()

    def test_moves_artifacts_and_applies_rule_when_proc_missing(self) -> None:
        """Files are moved verbatim; missing model_proc source is logged + ignored."""
        scratch = os.path.join(self._tmpdir, "scratch")
        target = os.path.join(self._tmpdir, "target")
        # ``intel/<model>/FP32/`` layout produced by omz_converter.
        src_dir = os.path.join(scratch, "intel", "face-detection-retail-0004")
        os.makedirs(src_dir)
        with open(os.path.join(src_dir, "model.xml"), "w") as f:
            f.write("<xml/>")

        # The rule references a model_proc source that does not exist in
        # our scratch tree — manager must log a warning and continue.
        self.mgr._materialize_omz_artifacts(
            job_id="job-1",
            model_name="face-detection-retail-0004",
            tmp_dir=scratch,
            target_dir=target,
        )

        self.assertTrue(
            os.path.isfile(os.path.join(target, "model.xml")),
            "model.xml should have been moved to the target dir",
        )

    def test_raises_when_no_output_directory_exists(self) -> None:
        scratch = os.path.join(self._tmpdir, "scratch")
        target = os.path.join(self._tmpdir, "target")
        os.makedirs(scratch)  # empty — no intel/ or public/ children
        with self.assertRaises(FileNotFoundError):
            self.mgr._materialize_omz_artifacts(
                job_id="job-1",
                model_name="face-detection-retail-0004",
                tmp_dir=scratch,
                target_dir=target,
            )

    def test_falls_back_to_public_when_intel_missing(self) -> None:
        """For ``mobilenet-v2-pytorch`` the manager scans ``public/`` first."""
        scratch = os.path.join(self._tmpdir, "scratch")
        target = os.path.join(self._tmpdir, "target")
        src_dir = os.path.join(scratch, "public", "mobilenet-v2-pytorch")
        os.makedirs(src_dir)
        with open(os.path.join(src_dir, "model.xml"), "w") as f:
            f.write("<xml/>")

        self.mgr._materialize_omz_artifacts(
            job_id="job-1",
            model_name="mobilenet-v2-pytorch",
            tmp_dir=scratch,
            target_dir=target,
        )
        self.assertTrue(os.path.isfile(os.path.join(target, "model.xml")))


# ----------------------------------------------------------------------
# _inject_imagenet_labels — happy path + missing files
# ----------------------------------------------------------------------


class TestInjectImagenetLabels(unittest.TestCase):
    """Light tests for ImageNet label injection used by ``mobilenet-v2-pytorch``."""

    def setUp(self) -> None:
        self._tmpdir = tempfile.mkdtemp(prefix="vippet-mm-labels-")

    def tearDown(self) -> None:
        import shutil

        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def test_happy_path_writes_labels_into_postproc(self) -> None:
        labels_path = os.path.join(self._tmpdir, "labels.txt")
        json_path = os.path.join(self._tmpdir, "proc.json")
        with open(labels_path, "w") as f:
            f.write("0 tench\n1 goldfish\n2 great_white_shark\n\n")
        with open(json_path, "w") as f:
            json.dump({"output_postproc": [{"labels": []}]}, f)

        ModelManager._inject_imagenet_labels(
            job_id="job-1",
            model_name="mobilenet-v2-pytorch",
            labels_path=labels_path,
            json_path=json_path,
        )
        with open(json_path) as f:
            data = json.load(f)
        self.assertEqual(
            data["output_postproc"][0]["labels"],
            ["tench", "goldfish", "great_white_shark"],
        )

    def test_missing_labels_file_is_silent_noop(self) -> None:
        json_path = os.path.join(self._tmpdir, "proc.json")
        with open(json_path, "w") as f:
            json.dump({"output_postproc": [{"labels": []}]}, f)
        # Must not raise even though the labels file does not exist.
        ModelManager._inject_imagenet_labels(
            job_id="job-1",
            model_name="mobilenet-v2-pytorch",
            labels_path="/does/not/exist",
            json_path=json_path,
        )
        # File untouched.
        with open(json_path) as f:
            data = json.load(f)
        self.assertEqual(data["output_postproc"][0]["labels"], [])

    def test_json_without_postproc_is_silent_noop(self) -> None:
        labels_path = os.path.join(self._tmpdir, "labels.txt")
        json_path = os.path.join(self._tmpdir, "proc.json")
        with open(labels_path, "w") as f:
            f.write("0 a\n1 b\n")
        with open(json_path, "w") as f:
            json.dump({}, f)
        ModelManager._inject_imagenet_labels(
            job_id="job-1",
            model_name="mobilenet-v2-pytorch",
            labels_path=labels_path,
            json_path=json_path,
        )
        with open(json_path) as f:
            data = json.load(f)
        # No mutation of an empty payload.
        self.assertEqual(data, {})


# ----------------------------------------------------------------------
# _run_subprocess — one success path, one failure path
# ----------------------------------------------------------------------


class _FakeProc:
    """Minimal ``subprocess.Popen`` stand-in with controllable rc/stdout/stderr."""

    def __init__(
        self,
        *,
        rc: int = 0,
        stdout_lines: list[str] | None = None,
        stderr_lines: list[str] | None = None,
    ) -> None:
        import io

        self.returncode = rc
        self.stdout = io.StringIO("\n".join(stdout_lines or []) + "\n")
        self.stderr = io.StringIO("\n".join(stderr_lines or []) + "\n")
        self._rc = rc

    def wait(self) -> int:
        return self._rc


class TestRunSubprocess(unittest.TestCase):
    """Lightweight tests for the subprocess helper used by the OMZ worker."""

    def setUp(self) -> None:
        _reset_manager()
        self._supported_patcher = patch("managers.model_manager.SupportedModelsManager")
        self._supported_patcher.start()
        self.mgr = ModelManager()
        self.mgr._jobs["job-1"] = _make_running_job(job_id="job-1")

    def tearDown(self) -> None:
        self._supported_patcher.stop()
        _reset_manager()

    def test_success_streams_stdout_into_progress_message(self) -> None:
        fake = _FakeProc(
            rc=0,
            stdout_lines=["Downloading...", "Done"],
            stderr_lines=[],
        )
        with patch("managers.model_manager.subprocess.Popen", return_value=fake):
            self.mgr._run_subprocess("job-1", ["omz_downloader", "--name", "x"])
        # Last non-empty stdout line was attached as progress_message.
        self.assertEqual(self.mgr._jobs["job-1"].progress_message, "Done")

    def test_nonzero_exit_raises_called_process_error(self) -> None:
        fake = _FakeProc(rc=1, stdout_lines=["ok"], stderr_lines=["boom"])
        with patch("managers.model_manager.subprocess.Popen", return_value=fake):
            with self.assertRaises(subprocess.CalledProcessError) as cm:
                self.mgr._run_subprocess("job-1", ["omz_downloader", "--name", "x"])
        # stderr is forwarded so the caller can attach it to job details.
        self.assertIn("boom", cm.exception.stderr or "")


# ----------------------------------------------------------------------
# Uploaded-model fallback (used by graph.py to resolve custom models)
# ----------------------------------------------------------------------


class TestUploadedModelLookups(unittest.TestCase):
    """Tests for ``find_installed_uploaded_model_by_display_name`` and
    ``find_uploaded_model_by_path`` — the helpers consumed by
    ``graph.py`` when a model is not in ``supported_models.yaml``.
    """

    def setUp(self) -> None:
        _reset_manager()
        # Skip the registry file load: tests seed records directly.
        with patch.object(ModelManager, "_load_registry", lambda self: None):
            self.mgr = ModelManager()
        # A temp directory acts as the "uploaded model" output dir.
        self._tmp = tempfile.TemporaryDirectory()
        self.upload_dir = self._tmp.name
        self.xml_path = os.path.join(self.upload_dir, "custom.xml")
        with open(self.xml_path, "w") as f:
            f.write("<net/>")
        with open(os.path.join(self.upload_dir, "custom.bin"), "wb") as f:
            f.write(b"\x00")

    def tearDown(self) -> None:
        self._tmp.cleanup()
        _reset_manager()

    def _seed_record(
        self,
        *,
        name: str = "my-custom",
        display_name: str | None = None,
        path: str | None = None,
    ) -> _InstalledModelRecord:
        record = _InstalledModelRecord(
            name=name,
            display_name=display_name or name,
            source=InternalModelSource.CUSTOM,
            category=InternalModelCategory.DETECTION,
            precisions=[
                InternalModelPrecision(precision="", model_path=path or self.upload_dir)
            ],
        )
        self.mgr._registry[record.name] = record
        return record

    # --- find_installed_uploaded_model_by_display_name --------------

    def test_find_by_display_name_returns_adapter_for_directory(self) -> None:
        self._seed_record(display_name="My Custom Model")
        result = self.mgr.find_installed_uploaded_model_by_display_name(
            "My Custom Model"
        )
        assert result is not None
        # The adapter resolves the directory to the inner ``.xml``.
        self.assertEqual(result.model_path_full, self.xml_path)
        # Uploaded models never carry a model-proc.
        self.assertEqual(result.model_proc_full, "")

    def test_find_by_display_name_matches_by_name_too(self) -> None:
        # The UI uses ``model_name`` as the dropdown value; uploaded
        # records use the same string for ``name`` and ``display_name``.
        self._seed_record(name="raw-name", display_name="raw-name")
        result = self.mgr.find_installed_uploaded_model_by_display_name("raw-name")
        self.assertIsNotNone(result)

    def test_find_by_display_name_unknown_returns_none(self) -> None:
        self._seed_record(display_name="Known")
        self.assertIsNone(
            self.mgr.find_installed_uploaded_model_by_display_name("Unknown")
        )

    def test_find_by_display_name_returns_none_when_files_missing(self) -> None:
        # Registry points at a path that no longer exists on disk.
        self._seed_record(display_name="Stale", path="/nonexistent/path/model_dir")
        self.assertIsNone(
            self.mgr.find_installed_uploaded_model_by_display_name("Stale")
        )

    def test_find_by_display_name_with_no_precisions_returns_none(self) -> None:
        record = self._seed_record(display_name="NoPrec")
        record.precisions = []
        self.assertIsNone(
            self.mgr.find_installed_uploaded_model_by_display_name("NoPrec")
        )

    # --- find_uploaded_model_by_path --------------------------------

    def test_find_by_path_matches_registry_directory(self) -> None:
        self._seed_record()
        result = self.mgr.find_uploaded_model_by_path(self.upload_dir)
        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result.name, "my-custom")

    def test_find_by_path_matches_inner_xml(self) -> None:
        # Pipeline strings reference the resolved ``.xml`` artefact, not
        # the directory. The lookup must still succeed.
        self._seed_record()
        result = self.mgr.find_uploaded_model_by_path(self.xml_path)
        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result.model_path_full, self.xml_path)

    def test_find_by_path_ignores_model_proc_argument(self) -> None:
        # Uploaded models have no model-proc; passing one must not break
        # resolution.
        self._seed_record()
        result = self.mgr.find_uploaded_model_by_path(
            self.xml_path, model_proc_path="/some/proc.json"
        )
        self.assertIsNotNone(result)

    def test_find_by_path_unknown_returns_none(self) -> None:
        self._seed_record()
        self.assertIsNone(
            self.mgr.find_uploaded_model_by_path("/totally/unrelated/path.xml")
        )

    def test_find_by_path_empty_registry_returns_none(self) -> None:
        self.assertIsNone(self.mgr.find_uploaded_model_by_path(self.xml_path))


if __name__ == "__main__":
    unittest.main()

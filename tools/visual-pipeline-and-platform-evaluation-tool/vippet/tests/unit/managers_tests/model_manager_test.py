# SPDX-License-Identifier: Apache-2.0
"""Unit tests for ``managers.model_manager.ModelManager``.

The manager is a thread-safe singleton with three main concerns:

* Reading the model catalog + install status from the `models`/
  `model_variants` DB tables (seeded from ``vippet/models/*.yaml``)
  and aggregating them into a single API-facing list.
* Driving background download jobs through the model-download
    microservice and tracking their state.
* Forwarding multipart model uploads to model-download and registering
  the resulting model directly in the DB.

These tests avoid touching the real filesystem / network: every external
dependency (``SupportedModelsManager``, ``PipelineManager``,
``threading.Thread``, ``httpx``, ``os.path.*``) is
patched. The singleton state is reset between tests so that ``_jobs``
always start empty.
"""

from __future__ import annotations

import asyncio
import os
import shutil
import tempfile
import time
import unittest
from datetime import datetime, timezone
from typing import Any
from unittest.mock import MagicMock, patch

import database
import managers.model_manager as mm_module
from internal_types import (
    InternalModelCategory,
    InternalModelDownloadJobState,
    InternalModelDownloadJobStatus,
    InternalModelInstallStatus,
    InternalModelSource,
    InternalModelUploadSpec,
)
from managers.model_manager import ModelManager
from models import SupportedModelsManager
from orm_models import Model, ModelVariant


# ----------------------------------------------------------------------
# Test helpers
# ----------------------------------------------------------------------


def _reset_manager() -> None:
    """Drop the ``ModelManager`` singleton so each test starts from a clean slate."""
    ModelManager._instance = None


def _reset_supported_models_manager() -> None:
    """Drop the ``SupportedModelsManager`` singleton (in-memory DB cache)."""
    SupportedModelsManager._instance = None


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


class _AsyncDBTestCase(unittest.IsolatedAsyncioTestCase):
    """Base class wiring a fresh temp-file SQLite database + MODELS_PATH per test."""

    async def asyncSetUp(self) -> None:
        self._tmpdir = tempfile.mkdtemp(prefix="vippet-mm-db-")
        self._db_path = os.path.join(self._tmpdir, "test.db")
        self._models_path = os.path.join(self._tmpdir, "models")
        os.makedirs(self._models_path, exist_ok=True)

        self._orig_database_url = database.DATABASE_URL
        database.DATABASE_URL = f"sqlite+aiosqlite:///{self._db_path}"
        self._orig_models_path_models = mm_module.MODELS_PATH
        mm_module.MODELS_PATH = self._models_path

        os.environ["DB_SEED_ON_STARTUP"] = "false"
        await database.init_db()

        _reset_manager()
        _reset_supported_models_manager()

    async def asyncTearDown(self) -> None:
        await database.close_db()
        database.DATABASE_URL = self._orig_database_url
        mm_module.MODELS_PATH = self._orig_models_path_models
        shutil.rmtree(self._tmpdir, ignore_errors=True)
        _reset_manager()
        _reset_supported_models_manager()

    async def _add_model(
        self,
        *,
        name: str = "yolo11n",
        display_name: str | None = None,
        category: str = "object_detection",
        source: str = "ultralytics",
        hub: str = "ultralytics",
        unsupported_devices: str | None = None,
        is_custom: bool = False,
        install_status: str = "not_installed",
        download_request: dict[str, Any] | None = None,
        variants: list[dict[str, Any]] | None = None,
    ) -> int:
        """Insert a ``Model`` + its ``ModelVariant`` rows, return the model id."""
        now = datetime.now(timezone.utc)
        async with database.async_session_maker() as session:
            model = Model(
                name=name,
                display_name=display_name or name,
                description=None,
                category=category,
                source=source,
                hub=hub,
                unsupported_devices=unsupported_devices,
                is_custom=is_custom,
                install_status=install_status,
                installed_at=now if install_status == "installed" else None,
                download_request=download_request,
                created_at=now,
            )
            session.add(model)
            await session.flush()
            for variant in variants or [
                {"precision": "FP16", "model_path": f"{name}/FP16/model.xml"}
            ]:
                session.add(
                    ModelVariant(
                        model_id=model.id,
                        name=variant.get("name", name),
                        display_name=variant.get(
                            "display_name",
                            f"{display_name or name} ({variant['precision']})",
                        ),
                        precision=variant["precision"],
                        model_path=variant["model_path"],
                        model_proc=variant.get("model_proc"),
                        installed=variant.get("installed", False),
                        installed_at=now if variant.get("installed", False) else None,
                    )
                )
            await session.commit()
            return model.id


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
            ModelManager._to_internal_category("object_detection"),
            InternalModelCategory.OBJECT_DETECTION,
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

    @staticmethod
    def _variant(
        *, precision: str, model_path: str, display_name: str, installed: bool = False
    ) -> MagicMock:
        """Build a ``ModelVariant``-shaped mock (only the read attributes)."""
        v = MagicMock()
        v.precision = precision
        v.model_path = model_path
        v.display_name = display_name
        v.installed = installed
        return v

    def test_collect_precisions_dedupes_and_preserves_order(self) -> None:
        a = self._variant(precision="FP16", model_path="a.xml", display_name="A (FP16)")
        b = self._variant(precision="INT8", model_path="b.xml", display_name="B (INT8)")
        # Second FP16 entry must be ignored (already seen).
        c = self._variant(precision="FP16", model_path="c.xml", display_name="C (FP16)")
        d = self._variant(precision="", model_path="d.xml", display_name="D")

        precisions = ModelManager._collect_precisions([a, b, c, d])

        self.assertEqual([p.precision for p in precisions], ["FP16", "INT8"])
        self.assertTrue(precisions[0].model_path.endswith("a.xml"))

    def test_collect_variants_dedupes_by_display_name(self) -> None:
        """Variants are deduped by display_name so duplicate precisions collapse."""
        a = self._variant(
            precision="INT8",
            model_path="m.xml",
            display_name="m (INT8)",
            installed=True,
        )
        b = self._variant(
            precision="INT8",
            model_path="m.xml",
            display_name="m (INT8)",
            installed=True,
        )
        c = self._variant(
            precision="FP16",
            model_path="m.xml",
            display_name="m (FP16)",
            installed=False,
        )
        a.name = b.name = "m_INT8"
        c.name = "m_FP16"

        variants = ModelManager._collect_variants([a, b, c])

        self.assertEqual([v.display_name for v in variants], ["m (INT8)", "m (FP16)"])
        self.assertTrue(variants[0].installed)
        self.assertFalse(variants[1].installed)


# ----------------------------------------------------------------------
# Install-status computation
# ----------------------------------------------------------------------


class TestComputeInstallStatus(unittest.TestCase):
    """Cover every branch of ``_compute_install_status``."""

    @staticmethod
    def _db_model(install_status: str = "not_installed") -> MagicMock:
        m = MagicMock()
        m.install_status = install_status
        return m

    def test_running_job_yields_installing(self) -> None:
        job = _make_running_job(model_name="yolo11n")
        status = ModelManager._compute_install_status(
            name="yolo11n",
            db_model=self._db_model("not_installed"),
            active_jobs={"yolo11n": job},
        )
        self.assertEqual(status, InternalModelInstallStatus.INSTALLING)

    def test_failed_job_yields_failed(self) -> None:
        job = _make_running_job(model_name="yolo11n")
        job.state = InternalModelDownloadJobState.FAILED
        status = ModelManager._compute_install_status(
            name="yolo11n",
            db_model=self._db_model("not_installed"),
            active_jobs={"yolo11n": job},
        )
        self.assertEqual(status, InternalModelInstallStatus.FAILED)

    def test_completed_job_defers_to_db_resting_state(self) -> None:
        """A COMPLETED job is not itself an overlay state — the DB's own
        install_status (already updated by _persist_download_result before
        the job is marked COMPLETED) is authoritative."""
        job = _make_running_job(model_name="yolo11n")
        job.state = InternalModelDownloadJobState.COMPLETED
        status = ModelManager._compute_install_status(
            name="yolo11n",
            db_model=self._db_model("installed"),
            active_jobs={"yolo11n": job},
        )
        self.assertEqual(status, InternalModelInstallStatus.INSTALLED)

    def test_no_active_job_uses_db_install_status(self) -> None:
        status = ModelManager._compute_install_status(
            name="yolo11n", db_model=self._db_model("installed"), active_jobs={}
        )
        self.assertEqual(status, InternalModelInstallStatus.INSTALLED)

    def test_no_active_job_and_not_installed_in_db(self) -> None:
        status = ModelManager._compute_install_status(
            name="yolo11n", db_model=self._db_model("not_installed"), active_jobs={}
        )
        self.assertEqual(status, InternalModelInstallStatus.NOT_INSTALLED)


# ----------------------------------------------------------------------
# list_models — aggregation of YAML + registry
# ----------------------------------------------------------------------


class TestListModels(_AsyncDBTestCase):
    """Cover ``list_models`` aggregation against a real DB."""

    async def asyncSetUp(self) -> None:
        await super().asyncSetUp()
        self._pipeline_patcher = patch("managers.model_manager.PipelineManager")
        self._pipeline_cls = self._pipeline_patcher.start()
        self._pipeline_cls.return_value.get_model_display_names_used_by_pipelines.return_value = {}
        self.mgr = ModelManager.__new__(ModelManager)
        self.mgr._jobs = {}
        import threading

        self.mgr._jobs_lock = threading.Lock()

    async def asyncTearDown(self) -> None:
        self._pipeline_patcher.stop()
        await super().asyncTearDown()

    async def test_list_models_not_installed(self) -> None:
        await self._add_model(
            name="yolo11n",
            display_name="YOLO 11n",
            variants=[
                {
                    "precision": "FP16",
                    "model_path": "yolo11n/FP16/model.xml",
                    "display_name": "YOLO 11n (FP16)",
                }
            ],
        )

        models = await self.mgr.list_models()

        self.assertEqual(len(models), 1)
        m = models[0]
        self.assertEqual(m.name, "yolo11n")
        self.assertEqual(m.source, InternalModelSource.ULTRALYTICS)
        self.assertEqual(m.install_status, InternalModelInstallStatus.NOT_INSTALLED)
        self.assertEqual([v.precision for v in m.variants], ["FP16"])

    async def test_list_models_reflects_installed_status_from_db(self) -> None:
        await self._add_model(name="yolo11n", install_status="installed")
        models = await self.mgr.list_models()
        self.assertEqual(models[0].install_status, InternalModelInstallStatus.INSTALLED)

    async def test_list_models_collapses_multiple_precisions(self) -> None:
        await self._add_model(
            name="yolo11n",
            display_name="YOLO 11n",
            variants=[
                {
                    "precision": "FP16",
                    "model_path": "yolo11n/FP16/model.xml",
                    "display_name": "YOLO 11n (FP16)",
                },
                {
                    "precision": "INT8",
                    "model_path": "yolo11n/INT8/model.xml",
                    "display_name": "YOLO 11n (INT8)",
                },
            ],
        )
        models = await self.mgr.list_models()
        self.assertEqual(len(models), 1)
        self.assertEqual([p.precision for p in models[0].precisions], ["FP16", "INT8"])

    async def test_list_models_includes_custom_models(self) -> None:
        """Custom uploaded models (is_custom=True) are listed just like catalog ones."""
        await self._add_model(
            name="my-custom",
            display_name="My Custom",
            source="custom",
            hub="custom",
            is_custom=True,
            install_status="installed",
            variants=[
                {
                    "precision": "",
                    "model_path": "custom_uploaded_models/my-custom/model.xml",
                    "display_name": "My Custom",
                    "installed": True,
                }
            ],
        )
        models = await self.mgr.list_models()
        self.assertEqual(len(models), 1)
        self.assertEqual(models[0].name, "my-custom")
        self.assertEqual(models[0].source, InternalModelSource.CUSTOM)
        self.assertEqual(models[0].install_status, InternalModelInstallStatus.INSTALLED)

    async def test_list_models_used_by_pipelines_is_populated(self) -> None:
        await self._add_model(
            name="yolo11n",
            display_name="YOLO 11n",
            variants=[
                {
                    "precision": "FP16",
                    "model_path": "yolo11n/FP16/model.xml",
                    "display_name": "YOLO 11n (FP16)",
                }
            ],
        )
        self._pipeline_cls.return_value.get_model_display_names_used_by_pipelines.return_value = {
            "YOLO 11n (FP16)": ["smart-nvr", "goods-detection"]
        }

        models = await self.mgr.list_models()
        self.assertEqual(
            sorted(models[0].used_by_pipelines), ["goods-detection", "smart-nvr"]
        )
        self.assertTrue(models[0].default)

    async def test_list_models_default_false_without_pipeline_usage(self) -> None:
        await self._add_model(name="yolo11n")
        models = await self.mgr.list_models()
        self.assertEqual(models[0].used_by_pipelines, [])
        self.assertFalse(models[0].default)

    async def test_list_models_running_job_overlays_installing(self) -> None:
        await self._add_model(name="yolo11n", install_status="not_installed")
        self.mgr._jobs["job-1"] = _make_running_job(model_name="yolo11n")
        models = await self.mgr.list_models()
        self.assertEqual(
            models[0].install_status, InternalModelInstallStatus.INSTALLING
        )


# ----------------------------------------------------------------------
# start_download — entry-point that picks the right worker
# ----------------------------------------------------------------------


class TestStartDownload(_AsyncDBTestCase):
    """``start_download`` validation and worker dispatch against a real DB."""

    async def asyncSetUp(self) -> None:
        await super().asyncSetUp()
        self.mgr = ModelManager.__new__(ModelManager)
        self.mgr._jobs = {}
        import threading

        self.mgr._jobs_lock = threading.Lock()

    async def test_returns_404_for_unknown_model(self) -> None:
        job_id, status, msg = await self.mgr.start_download("nope")
        self.assertIsNone(job_id)
        self.assertEqual(status, 404)
        self.assertIn("not supported", msg)

    async def test_returns_409_when_already_installed(self) -> None:
        await self._add_model(
            name="yolo11n",
            install_status="installed",
            download_request={"model_id": "yolo11n"},
        )
        job_id, status, msg = await self.mgr.start_download("yolo11n")
        self.assertIsNone(job_id)
        self.assertEqual(status, 409)
        self.assertIn("already installed", msg)

    async def test_returns_409_when_a_job_is_already_running(self) -> None:
        await self._add_model(name="yolo11n", download_request={"model_id": "yolo11n"})
        self.mgr._jobs["existing"] = _make_running_job(
            job_id="existing", model_name="yolo11n"
        )

        job_id, status, msg = await self.mgr.start_download("yolo11n")
        self.assertIsNone(job_id)
        self.assertEqual(status, 409)
        self.assertIn("already running", msg)

    async def test_returns_400_when_remote_model_has_no_download_request(self) -> None:
        await self._add_model(name="yolo11n", hub="ultralytics", download_request=None)
        job_id, status, msg = await self.mgr.start_download("yolo11n")
        self.assertIsNone(job_id)
        self.assertEqual(status, 400)
        self.assertIn("download_request", msg)

    @patch("managers.model_manager.threading.Thread")
    async def test_returns_202_and_spawns_remote_worker(self, mock_thread_cls) -> None:
        """Accepted remote download: a worker thread is started and the job is recorded."""
        await self._add_model(
            name="yolo11n", hub="ultralytics", download_request={"model_id": "yolo11n"}
        )

        job_id, status, msg = await self.mgr.start_download("yolo11n")

        self.assertEqual(status, 202)
        self.assertIsNotNone(job_id)
        self.assertIn(job_id, self.mgr._jobs)
        mock_thread_cls.assert_called_once()
        mock_thread_cls.return_value.start.assert_called_once()
        target = mock_thread_cls.call_args.kwargs["target"]
        self.assertEqual(target, self.mgr._execute_remote_download)

    @patch("managers.model_manager.threading.Thread")
    async def test_omz_dispatches_to_remote_worker(self, mock_thread_cls) -> None:
        """OMZ-sourced models go through the same remote worker as any other hub."""
        download_request = {
            "hub": "omz",
            "name": "age-gender-recognition-retail-0013",
        }
        await self._add_model(
            name="age-gender-recognition-retail-0013",
            hub="omz",
            download_request=download_request,
        )

        job_id, status, _msg = await self.mgr.start_download(
            "age-gender-recognition-retail-0013"
        )

        self.assertEqual(status, 202)
        thread_args = mock_thread_cls.call_args.kwargs
        self.assertEqual(thread_args["target"], self.mgr._execute_remote_download)
        self.assertEqual(
            thread_args["args"],
            (job_id, "age-gender-recognition-retail-0013", download_request),
        )


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
        self._supported_patcher = patch("managers.model_manager.SupportedModelsManager")
        self._supported_cls = self._supported_patcher.start()
        self._supported_cls.return_value.get_all_supported_models.return_value = []
        # Speed up the polling loop and timeout for tests.
        self._orig_poll = mm_module.DOWNLOAD_POLL_INTERVAL_S
        self._orig_timeout = mm_module.DOWNLOAD_TIMEOUT_S
        mm_module.DOWNLOAD_POLL_INTERVAL_S = 0
        mm_module.DOWNLOAD_TIMEOUT_S = 5
        self.mgr = ModelManager()

    def tearDown(self) -> None:
        self._supported_patcher.stop()
        mm_module.DOWNLOAD_POLL_INTERVAL_S = self._orig_poll
        mm_module.DOWNLOAD_TIMEOUT_S = self._orig_timeout
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
                "job-1", "yolo11n", {"model_id": "yolo11n"}
            )
        fin.assert_called_once_with("job-1", "yolo11n")

    def test_fails_when_post_returns_no_job_ids(self) -> None:
        self._seed_job()
        client = _FakeHttpxClient(
            post_response=_FakeResponse(json_body={"job_ids": []})
        )
        with patch("managers.model_manager.httpx.Client", return_value=client):
            self.mgr._execute_remote_download(
                "job-1", "yolo11n", {"model_id": "yolo11n"}
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
                "job-1", "yolo11n", {"model_id": "yolo11n"}
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
                "job-1", "yolo11n", {"model_id": "yolo11n"}
            )
        job = self.mgr._jobs["job-1"]
        self.assertEqual(job.state, InternalModelDownloadJobState.FAILED)
        self.assertIn("not found", job.details[0])

    def test_post_http_error_marks_job_failed(self) -> None:
        self._seed_job()
        client = _FakeHttpxClient(raise_on="post")
        with patch("managers.model_manager.httpx.Client", return_value=client):
            self.mgr._execute_remote_download(
                "job-1", "yolo11n", {"model_id": "yolo11n"}
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
                "job-1", "yolo11n", {"model_id": "yolo11n"}
            )
        job = self.mgr._jobs["job-1"]
        self.assertEqual(job.state, InternalModelDownloadJobState.FAILED)
        self.assertIn("timed out", job.details[0])


# ----------------------------------------------------------------------
# upload_model — proxy to model-download
# ----------------------------------------------------------------------


class TestUploadModel(_AsyncDBTestCase):
    """Cover the ``upload_model`` proxy path against a real DB."""

    async def asyncSetUp(self) -> None:
        await super().asyncSetUp()
        self.mgr = ModelManager.__new__(ModelManager)
        self.mgr._jobs = {}
        import threading

        self.mgr._jobs_lock = threading.Lock()
        self._payload = os.path.join(self._tmpdir, "model.zip")
        with open(self._payload, "wb") as f:
            f.write(b"PK\x03\x04 fake zip")
        self.spec = InternalModelUploadSpec(
            model_name="my-detector",
            category=InternalModelCategory.OBJECT_DETECTION,
            file_path=self._payload,
            original_filename="my-detector.zip",
            description="Detects vehicles",
        )

    async def test_upload_success_registers_model_in_db(self) -> None:
        client = _FakeHttpxClient(
            post_response=_FakeResponse(
                status_code=201,
                json_body={"output_dir": "/models/output/custom/my-detector"},
            )
        )
        with patch("managers.model_manager.httpx.Client", return_value=client):
            model, status, msg = await self.mgr.upload_model(self.spec)

        self.assertEqual(status, 201)
        assert model is not None
        self.assertEqual(model.name, "my-detector")
        self.assertEqual(model.source, InternalModelSource.CUSTOM)
        self.assertEqual(model.install_status, InternalModelInstallStatus.INSTALLED)
        self.assertEqual(model.description, "Detects vehicles")
        self.assertIn("uploaded successfully", msg)

        from sqlalchemy import select

        async with database.async_session_maker() as session:
            db_model = await session.scalar(
                select(Model).where(Model.name == "my-detector")
            )
            assert db_model is not None
            self.assertTrue(db_model.is_custom)
            self.assertEqual(db_model.install_status, "installed")

    async def test_upload_success_without_output_dir_uses_fallback_path(self) -> None:
        """When model-download omits ``output_dir`` the manager falls back to MODELS_PATH."""
        client = _FakeHttpxClient(
            post_response=_FakeResponse(status_code=201, json_body={})
        )
        with patch("managers.model_manager.httpx.Client", return_value=client):
            model, status, _msg = await self.mgr.upload_model(self.spec)
        self.assertEqual(status, 201)
        assert model is not None
        self.assertTrue(model.precisions[0].model_path.endswith("my-detector"))

    async def test_upload_returns_502_on_http_error(self) -> None:
        client = _FakeHttpxClient(raise_on="post")
        with patch("managers.model_manager.httpx.Client", return_value=client):
            model, status, msg = await self.mgr.upload_model(self.spec)
        self.assertIsNone(model)
        self.assertEqual(status, 502)
        self.assertIn("Upload failed", msg)

    async def test_upload_propagates_upstream_status_and_detail(self) -> None:
        """A 4xx response from model-download is mirrored to the caller."""
        client = _FakeHttpxClient(
            post_response=_FakeResponse(
                status_code=409,
                json_body={"detail": "Model already exists"},
            )
        )
        with patch("managers.model_manager.httpx.Client", return_value=client):
            model, status, msg = await self.mgr.upload_model(self.spec)
        self.assertIsNone(model)
        self.assertEqual(status, 409)
        self.assertEqual(msg, "Model already exists")

    async def test_upload_extracts_detail_from_fastapi_validation_array(self) -> None:
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
            _model, status, msg = await self.mgr.upload_model(self.spec)
        self.assertEqual(status, 400)
        self.assertIn("field required", msg)
        self.assertIn("value error", msg)

    async def test_upload_duplicate_name_returns_409(self) -> None:
        """A model already present in the DB rejects a same-named upload."""
        await self._add_model(name="my-detector")
        client = _FakeHttpxClient(
            post_response=_FakeResponse(status_code=201, json_body={"output_dir": "/x"})
        )
        with patch("managers.model_manager.httpx.Client", return_value=client):
            model, status, msg = await self.mgr.upload_model(self.spec)
        self.assertIsNone(model)
        self.assertEqual(status, 409)
        self.assertIn("already exists", msg)


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
    """Direct unit tests for ``_fail_job`` and ``_finalize_success``.

    Both are synchronous entry points invoked from download-worker
    threads: ``_finalize_success`` bridges into the DB via
    ``asyncio.run`` internally, so this test class stays a plain
    (non-async) ``TestCase`` and drives the DB setup/teardown with its
    own ``asyncio.run`` calls, exactly like the worker threads do.
    """

    def setUp(self) -> None:
        _reset_manager()
        _reset_supported_models_manager()
        self._tmpdir = tempfile.mkdtemp(prefix="vippet-mm-lifecycle-")
        self._db_path = os.path.join(self._tmpdir, "test.db")
        self._models_path = os.path.join(self._tmpdir, "models")
        os.makedirs(self._models_path, exist_ok=True)

        self._orig_database_url = database.DATABASE_URL
        database.DATABASE_URL = f"sqlite+aiosqlite:///{self._db_path}"
        self._orig_models_path = mm_module.MODELS_PATH
        mm_module.MODELS_PATH = self._models_path
        os.environ["DB_SEED_ON_STARTUP"] = "false"
        asyncio.run(database.init_db())

        self.mgr = ModelManager.__new__(ModelManager)
        self.mgr._jobs = {}
        import threading

        self.mgr._jobs_lock = threading.Lock()

    def tearDown(self) -> None:
        asyncio.run(database.close_db())
        database.DATABASE_URL = self._orig_database_url
        mm_module.MODELS_PATH = self._orig_models_path
        shutil.rmtree(self._tmpdir, ignore_errors=True)
        _reset_manager()
        _reset_supported_models_manager()

    def _add_model(self, **kwargs: Any) -> int:
        return asyncio.run(_AsyncDBTestCase._add_model(self, **kwargs))  # type: ignore[arg-type]

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

    def test_finalize_success_marks_completed_and_persists_db(self) -> None:
        self._add_model(
            name="yolo11n",
            display_name="YOLO 11n",
            variants=[
                {
                    "precision": "FP16",
                    "model_path": "yolo11n/FP16/model.xml",
                    "display_name": "YOLO 11n (FP16)",
                }
            ],
        )
        # Create the on-disk artefact so the post-download disk check succeeds.
        full_path = os.path.join(self._models_path, "yolo11n", "FP16", "model.xml")
        os.makedirs(os.path.dirname(full_path), exist_ok=True)
        open(full_path, "w").close()

        job = _make_running_job(job_id="job-1", model_name="yolo11n")
        self.mgr._jobs["job-1"] = job

        self.mgr._finalize_success("job-1", "yolo11n")

        self.assertEqual(job.state, InternalModelDownloadJobState.COMPLETED)
        self.assertEqual(job.model_path, full_path)

        from sqlalchemy import select

        async def _check() -> str:
            async with database.async_session_maker() as session:
                db_model = await session.scalar(
                    select(Model).where(Model.name == "yolo11n")
                )
                assert db_model is not None
                return db_model.install_status

        self.assertEqual(asyncio.run(_check()), "installed")

    def test_finalize_success_fails_when_files_missing(self) -> None:
        """If model-download reports success but files are not on disk the job
        must be reclassified as FAILED and the DB install_status must stay
        untouched. This guards against silent failures such as a missing
        HF_TOKEN that causes only metadata to be downloaded while the
        service still reports "completed"."""
        self._add_model(
            name="gemma3",
            display_name="Gemma 3",
            category="vision_language_models",
            hub="huggingface",
            source="huggingface",
            variants=[
                {
                    "precision": "INT4",
                    "model_path": "gemma3",
                    "display_name": "Gemma 3",
                }
            ],
        )
        job = _make_running_job(job_id="job-2", model_name="gemma3")
        self.mgr._jobs["job-2"] = job

        self.mgr._finalize_success("job-2", "gemma3")

        self.assertEqual(job.state, InternalModelDownloadJobState.FAILED)

        from sqlalchemy import select

        async def _check() -> str:
            async with database.async_session_maker() as session:
                db_model = await session.scalar(
                    select(Model).where(Model.name == "gemma3")
                )
                assert db_model is not None
                return db_model.install_status

        self.assertEqual(asyncio.run(_check()), "not_installed")


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


if __name__ == "__main__":
    unittest.main()

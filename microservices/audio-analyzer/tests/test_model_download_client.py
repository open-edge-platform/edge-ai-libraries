# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import asyncio
import base64
import itertools
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from utils import model_download_client as client
from utils import provision_models
from utils.local_models import COMPLETION_FILE, get_local_model, model_directory
from utils.provision_models import record_snapshot

JOB_ID = "e8f1892a-8c08-401f-a37a-d48957f206c1"
BASE_URL = "http://model-downloader:8000"


def _write_snapshot(directory: Path, names=("config.yaml", "model.pt")) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    for name in names:
        (directory / name).write_bytes(b"data")


class ServiceUrlTests(unittest.TestCase):
    def test_unset_means_disabled(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop(client.SERVICE_URL_ENV, None)
            self.assertIsNone(client.get_service_url())

    def test_trailing_slash_is_stripped(self):
        with patch.dict(os.environ, {client.SERVICE_URL_ENV: BASE_URL + "/"}):
            self.assertEqual(client.get_service_url(), BASE_URL)

    def test_rejects_non_http_credentials_or_query(self):
        for bad in ("ftp://host", "http://user:pw@host:8000", "http://host?x=1", "host:8000"):
            with self.subTest(url=bad), patch.dict(os.environ, {client.SERVICE_URL_ENV: bad}):
                with self.assertRaisesRegex(RuntimeError, client.SERVICE_URL_ENV):
                    client.get_service_url()

    def test_timeout_must_be_positive_number(self):
        with patch.dict(os.environ, {client.TIMEOUT_ENV: "abc"}):
            with self.assertRaisesRegex(RuntimeError, "number of seconds"):
                client._timeout_sec()
        with patch.dict(os.environ, {client.TIMEOUT_ENV: "0"}):
            with self.assertRaisesRegex(RuntimeError, "positive"):
                client._timeout_sec()
        with patch.dict(os.environ, {client.TIMEOUT_ENV: "30"}):
            self.assertEqual(client._timeout_sec(), 30.0)


class FetchFromServiceTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.base = tempfile.TemporaryDirectory()
        self.addCleanup(self.base.cleanup)
        self.env = patch.dict(os.environ, {client.SERVICE_URL_ENV: BASE_URL})
        self.env.start()
        self.addCleanup(self.env.stop)
        self.sleep = patch.object(client.asyncio, "sleep", AsyncMock())
        self.sleep.start()
        self.addCleanup(self.sleep.stop)

    def _directory(self, model="iic/example", hub="modelscope", download_path="funasr") -> Path:
        return model_directory(model, download_path, self.base.name, hub=hub)

    async def test_valid_snapshot_is_reused_without_contacting_service(self):
        directory = self._directory()
        _write_snapshot(directory)
        record_snapshot("iic/example", "v2.0.4", directory)
        with patch.object(client, "_request_json") as request:
            path = await client.fetch_from_service(
                "iic/example", "v2.0.4", hub="modelscope", download_path="funasr",
                required_files=["config.yaml", "model.pt"], models_base_path=self.base.name,
            )
        request.assert_not_called()
        self.assertEqual(path, str(directory.resolve()))

    async def test_submits_polls_and_certifies_snapshot(self):
        directory = self._directory()

        def fake_request(url, payload=None):
            if url.endswith("/models/download?download_path=funasr"):
                self.assertEqual(payload, {"models": [
                    {"name": "iic/example", "hub": "modelscope", "revision": "v2.0.4"},
                ]})
                return {"job_ids": [JOB_ID]}
            self.assertEqual(url, f"{BASE_URL}/jobs/{JOB_ID}")
            if fake_request.polls == 0:
                fake_request.polls += 1
                return {"status": "downloading"}
            _write_snapshot(directory)
            return {"status": "completed", "result": {"source": "modelscope", "model_name": "iic/example"}}

        fake_request.polls = 0
        with patch.object(client, "_request_json", side_effect=fake_request):
            path = await client.fetch_from_service(
                "iic/example", "v2.0.4", hub="modelscope", download_path="funasr",
                required_files=["config.yaml", "model.pt"], models_base_path=self.base.name,
            )
        self.assertEqual(path, str(directory.resolve()))
        self.assertTrue((directory / COMPLETION_FILE).is_file())
        self.assertEqual(get_local_model(
            "iic/example", "v2.0.4", hub="modelscope", download_path="funasr",
            required_files=["config.yaml", "model.pt"], models_base_path=self.base.name,
        ), str(directory.resolve()))

    async def test_stale_snapshot_is_rebuilt_and_files_and_token_are_forwarded(self):
        directory = self._directory("pyannote/example", "huggingface", "diarization")
        _write_snapshot(directory, ("stale.bin",))
        (directory / COMPLETION_FILE).write_text("{}")
        requests = []

        def fake_request(url, payload=None):
            requests.append((url, payload))
            if payload is not None:
                self.assertFalse((directory / "stale.bin").exists())
                return {"job_ids": [JOB_ID]}
            _write_snapshot(directory, ("config.yaml",))
            return {"status": "completed", "result": {"source": "huggingface", "model_name": "pyannote/example"}}

        with patch.object(client, "_request_json", side_effect=fake_request):
            await client.fetch_from_service(
                "pyannote/example", download_path="diarization", required_files=["config.yaml"],
                files=["config.yaml"], hf_token="hf_secret", models_base_path=self.base.name,
            )
        entry = requests[0][1]["models"][0]
        self.assertEqual(entry["config"], {"files": ["config.yaml"]})
        self.assertEqual(entry["override_credentials"], {"HF_TOKEN": base64.b64encode(b"hf_secret").decode("ascii")})
        self.assertIsNone(entry["revision"])

    async def test_failed_job_surfaces_error_and_leaves_no_inventory(self):
        directory = self._directory()
        with patch.object(client, "_request_json", side_effect=[
            {"job_ids": [JOB_ID]},
            {"status": "failed", "error": "plugin modelscope is not enabled"},
        ]):
            with self.assertRaisesRegex(RuntimeError, "plugin modelscope is not enabled"):
                await client.fetch_from_service(
                    "iic/example", "v2.0.4", hub="modelscope", download_path="funasr",
                    required_files=["config.yaml", "model.pt"], models_base_path=self.base.name,
                )
        self.assertFalse((directory / COMPLETION_FILE).exists())

    async def test_completed_job_without_required_files_is_not_certified(self):
        directory = self._directory()
        with patch.object(client, "_request_json", side_effect=[
            {"job_ids": [JOB_ID]},
            {"status": "completed", "result": {"source": "modelscope", "model_name": "iic/example"}},
        ]):
            with self.assertRaisesRegex(RuntimeError, "not provisioned correctly"):
                await client.fetch_from_service(
                    "iic/example", "v2.0.4", hub="modelscope", download_path="funasr",
                    required_files=["config.yaml", "model.pt"], models_base_path=self.base.name,
                )
        self.assertFalse((directory / COMPLETION_FILE).exists())

    async def test_unexpected_job_result_or_count_is_rejected(self):
        with patch.object(client, "_request_json", side_effect=[{"job_ids": [JOB_ID, JOB_ID]}]):
            with self.assertRaisesRegex(RuntimeError, "exactly one job"):
                await client.fetch_from_service(
                    "iic/example", hub="modelscope", download_path="funasr",
                    required_files=["config.yaml"], models_base_path=self.base.name,
                )
        with patch.object(client, "_request_json", side_effect=[
            {"job_ids": [JOB_ID]},
            {"status": "completed", "result": {"source": "huggingface", "model_name": "iic/example"}},
        ]):
            with self.assertRaisesRegex(RuntimeError, "unexpected result"):
                await client.fetch_from_service(
                    "iic/example", hub="modelscope", download_path="funasr",
                    required_files=["config.yaml"], models_base_path=self.base.name,
                )

    async def test_times_out_while_job_is_still_running(self):
        # Patch the module's `time` reference only; the event loop needs the real monotonic clock.
        clock = itertools.chain([0.0, 0.0], itertools.repeat(10.0))
        with patch.dict(os.environ, {client.TIMEOUT_ENV: "5"}), \
             patch.object(client, "time", SimpleNamespace(monotonic=lambda: next(clock))), \
             patch.object(client, "_request_json", side_effect=[
                 {"job_ids": [JOB_ID]}, {"status": "queued"}, {"status": "queued"},
             ]):
            with self.assertRaisesRegex(TimeoutError, "Timed out after 5s"):
                await client.fetch_from_service(
                    "iic/example", hub="modelscope", download_path="funasr",
                    required_files=["config.yaml"], models_base_path=self.base.name,
                )

    async def test_provision_from_service_uses_configuration_plan(self):
        cfg = SimpleNamespace(models=SimpleNamespace(
            asr=SimpleNamespace(provider="funasr", name="paraformer-zh", diarization=False),
        ))
        with patch.object(provision_models, "config", cfg), \
             patch.object(client, "fetch_from_service", AsyncMock(return_value="/x")) as fetch:
            await client.provision_from_service()
        self.assertEqual(fetch.await_count, 3)
        self.assertTrue(all(call.kwargs["hub"] == "modelscope" for call in fetch.await_args_list))


class SourceSelectionTests(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, {}, clear=False)
        self.env.start()
        self.addCleanup(self.env.stop)
        os.environ.pop(client.SERVICE_URL_ENV, None)
        os.environ.pop(client.DIRECT_DOWNLOAD_ENV, None)

    def test_defaults_to_direct_download_when_no_service_is_configured(self):
        self.assertIs(client.select_fetch(), client.fetch_direct)

    def test_uses_service_when_configured_and_reachable(self):
        os.environ[client.SERVICE_URL_ENV] = BASE_URL
        with patch.object(client, "_request_json", return_value={"status": "healthy"}) as request:
            self.assertIs(client.select_fetch(), client.fetch_from_service)
        request.assert_called_once_with(f"{BASE_URL}/health")

    def test_falls_back_to_direct_download_when_service_is_unreachable(self):
        os.environ[client.SERVICE_URL_ENV] = BASE_URL
        with patch.object(client, "_request_json", side_effect=RuntimeError("unreachable")):
            self.assertIs(client.select_fetch(), client.fetch_direct)

    def test_strict_mode_without_service_relies_on_existing_snapshots(self):
        os.environ[client.DIRECT_DOWNLOAD_ENV] = "false"
        self.assertIsNone(client.select_fetch())
        self.assertFalse(asyncio.run(client.provision_at_startup()))

    def test_strict_mode_with_unreachable_service_fails(self):
        os.environ[client.SERVICE_URL_ENV] = BASE_URL
        os.environ[client.DIRECT_DOWNLOAD_ENV] = "false"
        with patch.object(client, "_request_json", side_effect=RuntimeError("unreachable")):
            with self.assertRaisesRegex(RuntimeError, "unreachable"):
                client.select_fetch()

    def test_invalid_direct_download_flag_is_rejected(self):
        os.environ[client.DIRECT_DOWNLOAD_ENV] = "maybe"
        with self.assertRaisesRegex(RuntimeError, client.DIRECT_DOWNLOAD_ENV):
            client.direct_download_enabled()

    def test_provision_at_startup_runs_plan_with_selected_fetch(self):
        cfg = SimpleNamespace(models=SimpleNamespace(
            asr=SimpleNamespace(provider="openvino", name="whisper-base", diarization=False),
        ))
        with patch.object(provision_models, "config", cfg), \
             patch.object(client, "fetch_direct", AsyncMock(return_value="/x")) as fetch:
            self.assertTrue(asyncio.run(client.provision_at_startup()))
        fetch.assert_awaited_once()
        self.assertEqual(fetch.await_args.args[0], "openai/whisper-base")


class RequestJsonTests(unittest.TestCase):
    def test_http_error_includes_service_detail(self):
        from io import BytesIO
        from urllib.error import HTTPError

        error = HTTPError(BASE_URL, 400, "Bad Request", {}, BytesIO(b'{"detail":"hub not enabled"}'))
        with patch.object(client._OPENER, "open", side_effect=error):
            with self.assertRaisesRegex(RuntimeError, "HTTP 400.*hub not enabled"):
                client._request_json(BASE_URL + "/jobs/x")

    def test_unreachable_service_is_reported(self):
        from urllib.error import URLError

        with patch.object(client._OPENER, "open", side_effect=URLError("refused")):
            with self.assertRaisesRegex(RuntimeError, "unreachable"):
                client._request_json(BASE_URL + "/jobs/x")


if __name__ == "__main__":
    unittest.main()

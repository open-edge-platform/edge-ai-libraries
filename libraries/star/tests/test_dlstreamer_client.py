# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
File: tests/test_dlstreamer_client.py
Description: Unit tests for the DL Streamer Pipeline Server REST client that
replaces local YOLO inference in `Encoder.extract_objs` (see
semantic_img_comp/integration/dlstreamer_client.py). All HTTP calls are mocked
via httpx.MockTransport -- no real pipeline server or GStreamer runtime needed.
"""
from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest
from PIL import Image

from semantic_img_comp.integration.dlstreamer_client import (
    DLStreamerDetectionClient,
    DLStreamerDetectionError,
    _PIPELINE_SERVER_NAMESPACE,
    build_client_from_config,
    run_dlstreamer_detect,
)

PIPELINE_NAME = "user_defined_pipelines"
PIPELINE_VERSION = "star_image_object_detection"
INSTANCE_ID = "fixed-instance-id"


def _start_url(base_url: str) -> str:
    return f"{base_url}/pipelines/{PIPELINE_NAME}/{PIPELINE_VERSION}"


def _status_url(base_url: str, instance_id: str = INSTANCE_ID) -> str:
    return f"{base_url}/pipelines/{instance_id}/status"


def _delete_url(base_url: str, instance_id: str = INSTANCE_ID) -> str:
    return f"{base_url}/pipelines/{instance_id}"


class _ServerFixture:
    """Records requests and drives a scripted DL Streamer Pipeline Server response
    sequence: POST starts an instance (optionally writing metadata immediately, the
    way the real server's `gvametapublish` would while the pipeline runs), GET
    /status is answered from a caller-supplied sequence, DELETE is recorded."""

    def __init__(self, *, status_sequence=("COMPLETED",), start_status_code=200,
                 instance_id=INSTANCE_ID, write_metadata_on_start=None):
        self.status_sequence = list(status_sequence)
        self.start_status_code = start_status_code
        self.instance_id = instance_id
        self.write_metadata_on_start = write_metadata_on_start
        self.start_requests = []
        self.status_calls = 0
        self.delete_calls = 0

    def handler(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if request.method == "POST" and path.endswith(f"/pipelines/{PIPELINE_NAME}/{PIPELINE_VERSION}"):
            body = json.loads(request.content or b"{}")
            self.start_requests.append(body)
            if self.write_metadata_on_start is not None:
                file_path = Path(body["parameters"]["publish-properties"]["file-path"])
                file_path.parent.mkdir(parents=True, exist_ok=True)
                with open(file_path, "w", encoding="utf-8") as fh:
                    fh.write(json.dumps(self.write_metadata_on_start) + "\n")
            if self.start_status_code >= 400:
                return httpx.Response(self.start_status_code, text="boom")
            return httpx.Response(200, text=self.instance_id)

        if request.method == "GET" and path.endswith("/status"):
            self.status_calls += 1
            idx = min(self.status_calls - 1, len(self.status_sequence) - 1)
            state = self.status_sequence[idx]
            return httpx.Response(
                200,
                json={"id": 0, "state": state, "start_time": 1, "elapsed_time": self.status_calls},
            )

        if request.method == "DELETE":
            self.delete_calls += 1
            return httpx.Response(200, json={"id": 0, "state": "STOPPED"})

        raise AssertionError(f"Unexpected request: {request.method} {path}")


def _make_client(tmp_path, server: _ServerFixture, **overrides) -> DLStreamerDetectionClient:
    input_dir = tmp_path / "input"
    output_dir = tmp_path / "output"
    kwargs = dict(
        base_url="http://dlstreamer-pipeline-server:8080",
        pipeline_name=PIPELINE_NAME,
        pipeline_version=PIPELINE_VERSION,
        input_dir=input_dir,
        output_dir=output_dir,
        poll_interval_sec=0.01,
        timeout_sec=1.0,
        http_client=httpx.Client(transport=httpx.MockTransport(server.handler), trust_env=False),
    )
    kwargs.update(overrides)
    return DLStreamerDetectionClient(**kwargs)


def _record(objects):
    return {"objects": objects, "resolution": {"width": 640, "height": 480}, "timestamp": 0}


def _test_image() -> Image.Image:
    return Image.new("RGB", (640, 480), color=(10, 20, 30))


class TestDLStreamerDetectionClientDetect:
    def test_detect_returns_pixel_bounding_boxes(self, tmp_path):
        record = _record([
            {
                "detection": {"confidence": 0.87, "label": "Vehicle", "label_id": 1},
                "x": 10, "y": 20, "w": 100, "h": 50,
            }
        ])
        server = _ServerFixture(write_metadata_on_start=record)
        client = _make_client(tmp_path, server)

        dets = client.detect(_test_image())

        assert dets == [(10.0, 20.0, 110.0, 70.0, pytest.approx(0.87), 1)]
        client.close()

    def test_detect_denormalizes_bounding_box_when_pixel_rect_missing(self, tmp_path):
        record = _record([
            {
                "detection": {
                    "confidence": 0.5,
                    "label": "Person",
                    "label_id": 0,
                    "bounding_box": {"x_min": 0.25, "y_min": 0.5, "x_max": 0.75, "y_max": 1.0},
                },
            }
        ])
        server = _ServerFixture(write_metadata_on_start=record)
        client = _make_client(tmp_path, server)

        dets = client.detect(_test_image())

        assert dets == [(160.0, 240.0, 480.0, 480.0, pytest.approx(0.5), 0)]
        client.close()

    def test_detect_skips_objects_with_no_usable_bounding_box(self, tmp_path):
        record = _record([
            {"detection": {"confidence": 0.5, "label": "Person", "label_id": 0}},
        ])
        server = _ServerFixture(write_metadata_on_start=record)
        client = _make_client(tmp_path, server)

        dets = client.detect(_test_image())

        assert dets == []
        client.close()

    def test_detect_polls_status_until_completed(self, tmp_path):
        server = _ServerFixture(
            status_sequence=("RUNNING", "RUNNING", "COMPLETED"),
            write_metadata_on_start=_record([]),
        )
        client = _make_client(tmp_path, server)

        dets = client.detect(_test_image())

        assert dets == []
        assert server.status_calls == 3
        client.close()

    def test_detect_raises_on_error_state(self, tmp_path):
        server = _ServerFixture(status_sequence=("ERROR",), write_metadata_on_start=_record([]))
        client = _make_client(tmp_path, server)

        with pytest.raises(DLStreamerDetectionError, match="ERROR"):
            client.detect(_test_image())
        client.close()

    def test_detect_raises_on_timeout(self, tmp_path):
        server = _ServerFixture(status_sequence=("RUNNING",), write_metadata_on_start=_record([]))
        client = _make_client(tmp_path, server, timeout_sec=0.05, poll_interval_sec=0.01)

        with pytest.raises(DLStreamerDetectionError, match="Timed out"):
            client.detect(_test_image())
        client.close()

    def test_detect_raises_on_http_error_starting_pipeline(self, tmp_path):
        server = _ServerFixture(start_status_code=500)
        client = _make_client(tmp_path, server)

        with pytest.raises(DLStreamerDetectionError, match="Failed to start"):
            client.detect(_test_image())
        client.close()

    def test_detect_raises_on_empty_instance_id(self, tmp_path):
        server = _ServerFixture(instance_id="")
        client = _make_client(tmp_path, server)

        with pytest.raises(DLStreamerDetectionError, match="empty instance id"):
            client.detect(_test_image())
        client.close()

    def test_detect_raises_when_metadata_file_missing(self, tmp_path):
        # write_metadata_on_start=None: pipeline "completes" but never wrote a file.
        server = _ServerFixture(status_sequence=("COMPLETED",))
        client = _make_client(tmp_path, server)

        with pytest.raises(DLStreamerDetectionError, match="metadata file"):
            client.detect(_test_image())
        client.close()

    def test_detect_cleans_up_temp_input_and_output_files_on_success(self, tmp_path):
        server = _ServerFixture(write_metadata_on_start=_record([]))
        client = _make_client(tmp_path, server)

        client.detect(_test_image())

        assert list((tmp_path / "input").iterdir()) == []
        assert list((tmp_path / "output").iterdir()) == []
        client.close()

    def test_detect_cleans_up_temp_input_file_even_on_failure(self, tmp_path):
        server = _ServerFixture(status_sequence=("ERROR",), write_metadata_on_start=_record([]))
        client = _make_client(tmp_path, server)

        with pytest.raises(DLStreamerDetectionError):
            client.detect(_test_image())

        assert list((tmp_path / "input").iterdir()) == []
        assert list((tmp_path / "output").iterdir()) == []
        client.close()

    def test_detect_sends_confidence_threshold_as_detection_properties(self, tmp_path):
        server = _ServerFixture(write_metadata_on_start=_record([]))
        client = _make_client(tmp_path, server)

        client.detect(_test_image(), confidence_threshold=0.3)

        assert len(server.start_requests) == 1
        params = server.start_requests[0]["parameters"]
        assert params["detection-properties"] == {"threshold": 0.3}
        assert "file-path" in params["publish-properties"]
        client.close()

    def test_detect_omits_detection_properties_when_no_threshold_given(self, tmp_path):
        server = _ServerFixture(write_metadata_on_start=_record([]))
        client = _make_client(tmp_path, server)

        client.detect(_test_image())

        assert "detection-properties" not in server.start_requests[0]["parameters"]
        client.close()

    def test_detect_source_uri_uses_input_dir(self, tmp_path):
        server = _ServerFixture(write_metadata_on_start=_record([]))
        client = _make_client(tmp_path, server)

        client.detect(_test_image())

        uri = server.start_requests[0]["source"]["uri"]
        assert uri.startswith(f"file://{tmp_path / 'input'}/")
        assert uri.endswith(".jpg")
        client.close()

    def test_detect_stop_pipeline_failure_does_not_fail_detect(self, tmp_path):
        class _FailingDeleteServer(_ServerFixture):
            def handler(self, request: httpx.Request) -> httpx.Response:
                if request.method == "DELETE":
                    self.delete_calls += 1
                    return httpx.Response(500, text="stop failed")
                return super().handler(request)

        server = _FailingDeleteServer(write_metadata_on_start=_record([]))
        client = _make_client(tmp_path, server)

        dets = client.detect(_test_image())

        assert dets == []
        assert server.delete_calls == 1
        client.close()

    def test_detect_stops_pipeline_instance_after_completion(self, tmp_path):
        server = _ServerFixture(write_metadata_on_start=_record([]))
        client = _make_client(tmp_path, server)

        client.detect(_test_image())

        assert server.delete_calls == 1
        client.close()


class TestDLStreamerDetectionClientLifecycle:
    def test_close_does_not_close_externally_provided_http_client(self, tmp_path):
        server = _ServerFixture(write_metadata_on_start=_record([]))
        external_client = httpx.Client(transport=httpx.MockTransport(server.handler), trust_env=False)

        client = _make_client(tmp_path, server, http_client=external_client)
        client.detect(_test_image())
        client.close()

        assert external_client.is_closed is False
        external_client.close()

    def test_context_manager_closes_owned_http_client(self, tmp_path):
        input_dir = tmp_path / "input"
        output_dir = tmp_path / "output"

        # No `http_client` passed in: the client owns (and must close) its own
        # internally created httpx.Client -- unlike the externally-provided case
        # above, this one isn't the caller's responsibility.
        with DLStreamerDetectionClient(
            base_url="http://dlstreamer-pipeline-server:8080",
            pipeline_name=PIPELINE_NAME,
            pipeline_version=PIPELINE_VERSION,
            input_dir=input_dir,
            output_dir=output_dir,
        ) as client:
            owned_client = client._client
            assert client._owns_client is True

        assert owned_client.is_closed is True

    def test_constructor_creates_shared_directories(self, tmp_path):
        input_dir = tmp_path / "nested" / "input"
        output_dir = tmp_path / "nested" / "output"
        assert not input_dir.exists()

        client = DLStreamerDetectionClient(
            base_url="http://dlstreamer-pipeline-server:8080",
            pipeline_name=PIPELINE_NAME,
            pipeline_version=PIPELINE_VERSION,
            input_dir=input_dir,
            output_dir=output_dir,
        )

        assert input_dir.is_dir()
        assert output_dir.is_dir()
        client.close()


class TestBuildClientFromConfig:
    def test_build_client_from_config_uses_model_fields(self, tmp_path):
        model_cfg = SimpleNamespace(
            dlstreamer_base_url="http://dlstreamer-pipeline-server:8080",
            dlstreamer_pipeline_name=PIPELINE_VERSION,
            dlstreamer_exchange_input_dir=tmp_path / "input",
            dlstreamer_exchange_output_dir=tmp_path / "output",
            dlstreamer_poll_interval_sec=0.5,
            dlstreamer_timeout_sec=45.0,
        )
        cfg = SimpleNamespace(model=model_cfg)

        client = build_client_from_config(cfg)

        assert client.base_url == "http://dlstreamer-pipeline-server:8080"
        assert client.pipeline_name == _PIPELINE_SERVER_NAMESPACE
        assert client.pipeline_version == PIPELINE_VERSION
        assert client.input_dir == tmp_path / "input"
        assert client.output_dir == tmp_path / "output"
        assert client.poll_interval_sec == 0.5
        assert client.timeout_sec == 45.0
        client.close()


class TestRunDlstreamerDetect:
    def test_run_dlstreamer_detect_filters_by_valid_obj_categories(self, tmp_path):
        record = _record([
            {"detection": {"confidence": 0.9, "label": "Person", "label_id": 0}, "x": 0, "y": 0, "w": 10, "h": 10},
            {"detection": {"confidence": 0.8, "label": "Vehicle", "label_id": 1}, "x": 20, "y": 20, "w": 10, "h": 10},
        ])
        server = _ServerFixture(write_metadata_on_start=record)
        client = _make_client(tmp_path, server)

        cfg = SimpleNamespace(model=SimpleNamespace(pre_comp_conf=0.05, valid_obj_categories={0}))
        dets = run_dlstreamer_detect(_test_image(), cfg, client=client)

        assert len(dets) == 1
        assert dets[0][5] == 0
        client.close()

    def test_run_dlstreamer_detect_keeps_all_classes_when_unfiltered(self, tmp_path):
        record = _record([
            {"detection": {"confidence": 0.9, "label": "Person", "label_id": 0}, "x": 0, "y": 0, "w": 10, "h": 10},
            {"detection": {"confidence": 0.8, "label": "Vehicle", "label_id": 1}, "x": 20, "y": 20, "w": 10, "h": 10},
        ])
        server = _ServerFixture(write_metadata_on_start=record)
        client = _make_client(tmp_path, server)

        cfg = SimpleNamespace(model=SimpleNamespace(pre_comp_conf=0.05, valid_obj_categories=None))
        dets = run_dlstreamer_detect(_test_image(), cfg, client=client)

        assert len(dets) == 2
        client.close()

    def test_run_dlstreamer_detect_reuses_provided_client_without_closing(self):
        calls = SimpleNamespace(detect=0, close=0)

        class _FakeClient:
            def detect(self, pil_img, *, confidence_threshold=None):
                calls.detect += 1
                return []

            def close(self):
                calls.close += 1

        fake_client = _FakeClient()
        cfg = SimpleNamespace(model=SimpleNamespace(pre_comp_conf=0.05, valid_obj_categories=None))

        dets = run_dlstreamer_detect(_test_image(), cfg, client=fake_client)

        assert dets == []
        assert calls.detect == 1
        assert calls.close == 0

    def test_run_dlstreamer_detect_builds_and_closes_client_when_not_provided(self, monkeypatch):
        calls = SimpleNamespace(detect=0, close=0)

        class _FakeClient:
            def detect(self, pil_img, *, confidence_threshold=None):
                calls.detect += 1
                return []

            def close(self):
                calls.close += 1

        fake_client = _FakeClient()
        monkeypatch.setattr(
            "semantic_img_comp.integration.dlstreamer_client.build_client_from_config",
            lambda cfg: fake_client,
        )
        cfg = SimpleNamespace(model=SimpleNamespace(pre_comp_conf=0.05, valid_obj_categories=None))

        dets = run_dlstreamer_detect(_test_image(), cfg)

        assert dets == []
        assert calls.detect == 1
        assert calls.close == 1

    def test_run_dlstreamer_detect_closes_built_client_even_on_error(self, monkeypatch):
        calls = SimpleNamespace(close=0)

        class _FailingClient:
            def detect(self, pil_img, *, confidence_threshold=None):
                raise DLStreamerDetectionError("boom")

            def close(self):
                calls.close += 1

        monkeypatch.setattr(
            "semantic_img_comp.integration.dlstreamer_client.build_client_from_config",
            lambda cfg: _FailingClient(),
        )
        cfg = SimpleNamespace(model=SimpleNamespace(pre_comp_conf=0.05, valid_obj_categories=None))

        with pytest.raises(DLStreamerDetectionError):
            run_dlstreamer_detect(_test_image(), cfg)

        assert calls.close == 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

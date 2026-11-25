# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Tests for pipeline-case pytest parameter wrapping and input video checks."""

import unittest
from typing import Any
from unittest import mock

import requests
from _pytest.mark.structures import ParameterSet

from helpers.pipeline_case_helpers import (
    NO_INPUT_VIDEO,
    MissingVideos,
    PipelineCase,
    describe_missing_videos,
    discover_pipeline_cases_for_pytest,
    find_missing_videos,
    input_video_names,
    missing_videos_for_pipelines,
    wrap_cases_for_pytest,
)


def _node(node_type: str, **data: str) -> dict[str, Any]:
    return {"id": str(len(data)), "type": node_type, "data": data}


def _variant(variant_id: str, *nodes: dict[str, Any]) -> dict[str, Any]:
    return {"id": variant_id, "pipeline_graph": {"nodes": list(nodes), "edges": []}}


def _skip_reason(param: Any) -> str:
    assert isinstance(param, ParameterSet)
    (mark,) = [mark for mark in param.marks if mark.name == "skip"]
    return str(mark.kwargs["reason"])


class TestWrapCasesForPytest(unittest.TestCase):
    def setUp(self) -> None:
        self.case = PipelineCase(
            case_id="sample_cpu",
            pipeline_id="pipeline-1",
            variant_id="variant-1",
            device_family="CPU",
            pipeline_name="Sample",
        )
        self.missing_models = {"pipeline-1": {"Missing Model"}}

    def test_skip_missing_models_skips_case_with_reason(self) -> None:
        params, ids = wrap_cases_for_pytest(
            [self.case], self.missing_models, skip_missing_models=True
        )

        self.assertEqual(ids, ["sample_cpu"])
        param = params[0]
        assert isinstance(param, ParameterSet)
        self.assertEqual(param.values, (self.case,))
        skip_marks = [mark for mark in param.marks if mark.name == "skip"]
        self.assertEqual(len(skip_marks), 1)
        self.assertIn("Missing Model", str(skip_marks[0].kwargs["reason"]))

    def test_not_skipping_missing_models_schedules_case(self) -> None:
        params, ids = wrap_cases_for_pytest(
            [self.case], self.missing_models, skip_missing_models=False
        )

        self.assertEqual(ids, ["sample_cpu"])
        self.assertIs(params[0], self.case)


class TestWrapCasesForMissingVideos(unittest.TestCase):
    def setUp(self) -> None:
        self.case = PipelineCase(
            case_id="sample_cpu",
            pipeline_id="pipeline-1",
            variant_id="variant-1",
            device_family="CPU",
            pipeline_name="Sample",
        )

    def _wrap(self, names: list[str], downloadable: set[str]) -> Any:
        missing = MissingVideos(
            {("pipeline-1", "variant-1"): names}, frozenset(downloadable)
        )
        # Missing videos skip even when missing models are scheduled anyway.
        params, _ = wrap_cases_for_pytest(
            [self.case],
            {},
            skip_missing_models=False,
            missing_videos=missing,
            video_download_hint="HINT.",
        )
        return params[0]

    def test_sample_video_gets_the_download_hint(self) -> None:
        reason = _skip_reason(self._wrap(["people.mp4"], {"people.mp4"}))
        self.assertIn("not downloaded: ['people.mp4']. HINT.", reason)

    def test_other_video_must_be_uploaded(self) -> None:
        reason = _skip_reason(self._wrap(["mine.mp4"], set()))
        self.assertIn("['mine.mp4']", reason)
        self.assertIn("Upload them on the ViPPET UI Videos page", reason)
        self.assertNotIn("HINT", reason)

    def test_empty_location_means_no_video_selected(self) -> None:
        reason = _skip_reason(self._wrap([NO_INPUT_VIDEO], set()))
        self.assertIn("no input video selected", reason)
        self.assertIn("pipeline Input node", reason)

    def test_other_variants_are_not_skipped(self) -> None:
        missing = MissingVideos({("pipeline-1", "other"): ["a.mp4"]})
        params, _ = wrap_cases_for_pytest([self.case], {}, missing_videos=missing)
        self.assertIs(params[0], self.case)

    def test_describe_lists_each_kind_once(self) -> None:
        reason = describe_missing_videos(
            "P", ["b.mp4", "a.mp4", "", "a.mp4"], {"a.mp4"}, "HINT."
        )
        self.assertEqual(reason.count("a.mp4"), 1)
        self.assertEqual(reason.count("b.mp4"), 1)
        self.assertIn("no input video selected", reason)


class TestInputVideoNames(unittest.TestCase):
    def test_filesrc_and_video_source_nodes(self) -> None:
        variant = _variant(
            "v",
            _node("filesrc", location="people.mp4"),
            _node("source", kind="video", source="cars.mp4", location="x.mp4"),
            _node("source", kind="VIDEO", location="fallback.mp4"),
            _node("source", kind="camera", source="usb-0"),
            _node("gvadetect", model="m"),
        )
        self.assertEqual(
            input_video_names({"id": "p"}, variant),
            ["people.mp4", "cars.mp4", "fallback.mp4"],
        )

    def test_absolute_paths_are_ignored_and_names_kept_once(self) -> None:
        variant = _variant(
            "v",
            _node("filesrc", location="/videos/input/people.mp4"),
            _node("filesrc", location="a.mp4"),
            _node("filesrc", location="a.mp4"),
        )
        self.assertEqual(input_video_names({"id": "p"}, variant), ["a.mp4"])

    def test_empty_location_is_no_input_video(self) -> None:
        variant = _variant("v", _node("filesrc", location=" "))
        self.assertEqual(input_video_names({"id": "p"}, variant), [NO_INPUT_VIDEO])

    def test_time_series_and_graphless_variants_read_no_video(self) -> None:
        variant = _variant("v", _node("filesrc", location="a.mp4"))
        self.assertEqual(
            input_video_names({"id": "p", "tags": ["Time Series"]}, variant), []
        )
        self.assertEqual(input_video_names({"id": "p"}, {"id": "v"}), [])
        self.assertEqual(
            input_video_names({"id": "p"}, {"id": "v", "pipeline_graph": "bad"}), []
        )


class _Response:
    def __init__(self, status: int, payload: Any) -> None:
        self.status_code = status
        self._payload = payload

    def json(self) -> Any:
        return self._payload

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise requests.HTTPError(f"HTTP {self.status_code}")


class _Session:
    """Fake requests.Session for GET /videos and /videos/default-recordings."""

    def __init__(self, videos: list[str], samples: list[str] | None) -> None:
        self.videos = videos
        self.samples = samples
        self.paths: list[str] = []

    def get(self, url: str, timeout: float) -> _Response:
        path = url.split("/api/v1", 1)[-1]
        self.paths.append(path)
        if path == "/videos":
            return _Response(200, [{"filename": name} for name in self.videos])
        if path == "/videos/default-recordings":
            if self.samples is None:
                return _Response(404, {"detail": "Not Found"})
            return _Response(200, [{"filename": name} for name in self.samples])
        return _Response(404, {})


_VIDEO_PIPELINES = [
    {
        "id": "p1",
        "variants": [
            _variant("cpu", _node("filesrc", location="people.mp4")),
            _variant("gpu", _node("filesrc", location="cars.mp4")),
        ],
    },
    {"id": "p2", "variants": [_variant("cpu", _node("filesrc", location="mine.mp4"))]},
]


class TestMissingVideos(unittest.TestCase):
    def test_find_missing_videos_is_per_variant(self) -> None:
        self.assertEqual(
            find_missing_videos(_VIDEO_PIPELINES, ["cars.mp4"]),
            {("p1", "cpu"): ["people.mp4"], ("p2", "cpu"): ["mine.mp4"]},
        )

    def test_downloadable_are_the_listed_samples(self) -> None:
        session = _Session(["cars.mp4"], ["people.mp4", "bears.mp4"])
        missing = missing_videos_for_pipelines(session, _VIDEO_PIPELINES)  # type: ignore[arg-type]
        self.assertEqual(missing.get("p1", "cpu"), ["people.mp4"])
        self.assertEqual(missing.get("p1", "gpu"), [])
        self.assertEqual(missing.downloadable, frozenset({"people.mp4"}))

    def test_older_vippet_has_no_downloadable_videos(self) -> None:
        session = _Session([], None)
        missing = missing_videos_for_pipelines(session, _VIDEO_PIPELINES)  # type: ignore[arg-type]
        self.assertEqual(len(missing.by_variant), 3)
        self.assertEqual(missing.downloadable, frozenset())

    def test_no_video_pipelines_make_no_request(self) -> None:
        session = _Session([], [])
        pipelines = [{"id": "ts", "variants": [{"id": "cpu"}]}]
        missing = missing_videos_for_pipelines(session, pipelines)  # type: ignore[arg-type]
        self.assertEqual(missing, MissingVideos())
        self.assertEqual(session.paths, [])

    def test_nothing_missing_skips_the_sample_list(self) -> None:
        session = _Session(["people.mp4", "cars.mp4", "mine.mp4"], [])
        missing = missing_videos_for_pipelines(session, _VIDEO_PIPELINES)  # type: ignore[arg-type]
        self.assertEqual(missing, MissingVideos())
        self.assertEqual(session.paths, ["/videos"])


class _DiscoverySession(_Session):
    """Fake session for discover_pipeline_cases_for_pytest (one CPU case)."""

    def __init__(self, videos: list[str] | None) -> None:
        super().__init__(videos or [], [])
        self.videos_fail = videos is None
        self.headers: dict[str, str] = {}

    def __enter__(self) -> "_DiscoverySession":
        return self

    def __exit__(self, *_: object) -> None:
        return None

    def get(self, url: str, timeout: float) -> _Response:
        path = url.split("/api/v1", 1)[-1]
        if path == "/devices":
            self.paths.append(path)
            return _Response(200, [{"device_family": "CPU"}])
        if path == "/pipelines":
            self.paths.append(path)
            pipeline = {
                "id": "p1",
                "name": "People",
                "variants": [
                    dict(
                        _variant("cpu", _node("filesrc", location="people.mp4")),
                        name="CPU",
                    )
                ],
            }
            return _Response(200, [pipeline])
        if path == "/models":
            self.paths.append(path)
            return _Response(200, [])
        if path == "/videos" and self.videos_fail:
            self.paths.append(path)
            return _Response(500, {"detail": "boom"})
        return super().get(url, timeout)


def _discover(session: _DiscoverySession) -> tuple[list[Any], list[str]]:
    with mock.patch(
        "helpers.pipeline_case_helpers.requests.Session", return_value=session
    ):
        return discover_pipeline_cases_for_pytest()


class TestDiscoverPipelineCases(unittest.TestCase):
    def test_pipelines_are_fetched_once(self) -> None:
        session = _DiscoverySession(["people.mp4"])
        params, ids = _discover(session)
        self.assertEqual(ids, ["people_cpu"])
        self.assertIsInstance(params[0], PipelineCase)
        self.assertEqual(session.paths.count("/pipelines"), 1)

    def test_missing_video_skips_the_case(self) -> None:
        params, ids = _discover(_DiscoverySession([]))
        self.assertEqual(ids, ["people_cpu"])
        self.assertIn("people.mp4", _skip_reason(params[0]))

    def test_failed_video_lookup_runs_the_cases(self) -> None:
        with self.assertLogs("helpers.pipeline_case_helpers", "WARNING") as logs:
            params, ids = _discover(_DiscoverySession(None))
        self.assertEqual(ids, ["people_cpu"])
        self.assertIsInstance(params[0], PipelineCase)
        self.assertIn("Could not look up input videos", logs.output[0])

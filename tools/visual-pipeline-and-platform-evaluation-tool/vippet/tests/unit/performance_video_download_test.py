# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for perf_helpers.video_download (plan, prompt, download, outcome)."""

import json
import unittest
from typing import Any

import httpx

from api.api_schemas import DefaultVideoConversionState
from tests.performance.perf_helpers import video_download as vd
from tests.performance.perf_helpers.asset_download import OutcomeEnvError
from tests.performance.perf_helpers.matrix import MatrixFilters, build_matrix

_BASE = "http://vippet.test/api/v1"

_PIPELINES = [
    {
        "id": "smart-nvr",
        "name": "Smart NVR",
        "variants": [{"id": "1", "name": "CPU"}, {"id": "2", "name": "GPU"}],
    },
    {"id": "goods", "name": "Goods", "variants": [{"id": "3", "name": "CPU"}]},
    {"id": "npu-only", "name": "NPU only", "variants": [{"id": "4", "name": "NPU"}]},
]

_MISSING = {
    ("smart-nvr", "1"): ["people.mp4"],
    ("smart-nvr", "2"): ["people.mp4"],
    ("goods", "3"): ["warehouse.avi", "mine.mp4"],
    # Excluded variant (no NPU on the host): never planned.
    ("npu-only", "4"): ["bears.mp4"],
}


def _matrix(pipelines: Any = "*", streams: tuple[int, ...] = (1, 3)) -> Any:
    return build_matrix(
        _PIPELINES,
        [{"device_family": "CPU"}, {"device_family": "GPU"}],
        {},
        MatrixFilters(pipelines=pipelines, stream_counts=streams),
        missing_videos=_MISSING,
        downloadable_videos=["people.mp4", "warehouse.avi", "bears.mp4"],
    )


def _recording(
    filename: str,
    status: str = "available",
    conversion: str = "not_converted",
    source: str = "Pexels",
) -> dict[str, Any]:
    return {
        "filename": filename,
        "source": source,
        "status": status,
        "hevc_filename": filename.rsplit(".", 1)[0] + "_h265.mp4",
        "conversion_status": conversion,
    }


_RECORDINGS = [
    _recording("people.mp4"),
    _recording("warehouse.avi", source="OpenVINO"),
    _recording("bears.mp4"),
]


def _planned(name: str, *, downloading: bool = False) -> vd.PlannedVideo:
    return vd.PlannedVideo(
        filename=name,
        source="Pexels",
        pipelines=("smart-nvr",),
        runs=2,
        already_downloading=downloading,
    )


class _Clock:
    def __init__(self) -> None:
        self.now = 1000.0
        self.sleeps: list[float] = []

    def monotonic(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds


class _FakeApi:
    """MockTransport handler for the ViPPET sample video endpoints.

    Each ``GET /videos/default-recordings`` returns the next entry of
    *polls* (the last one repeats); an entry may be an exception to raise.
    """

    def __init__(
        self,
        polls: list[Any],
        *,
        post_status: dict[str, int] | None = None,
        post_error: Exception | None = None,
    ) -> None:
        self.polls = list(polls)
        self.post_status = post_status or {}
        self.post_error = post_error
        self.posts: list[str] = []
        self.gets = 0

    def __call__(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if request.method == "POST" and path.endswith("/videos/download-default"):
            if self.post_error is not None:
                raise self.post_error
            name = json.loads(request.content)["filename"]
            self.posts.append(name)
            status = self.post_status.get(name, 202)
            body = (
                {"filename": name, "status": "queued"}
                if status in (200, 202)
                else {"detail": f"cannot download {name}\x1b[31m"}
            )
            return httpx.Response(status, json=body)
        if path.endswith("/videos/default-recordings"):
            self.gets += 1
            poll = self.polls[0] if len(self.polls) == 1 else self.polls.pop(0)
            if isinstance(poll, Exception):
                raise poll
            return httpx.Response(200, json=poll)
        return httpx.Response(404, json={"detail": "not found"})


def _downloader(
    api: _FakeApi, clock: _Clock, timeout: float = 600
) -> tuple[vd.VideoDownloader, list[str]]:
    lines: list[str] = []
    client = httpx.Client(transport=httpx.MockTransport(api))
    downloader = vd.VideoDownloader(
        client=client,
        base_url=_BASE,
        poll_interval=5,
        timeout_seconds=timeout,
        request_timeout=30,
        report=lines.append,
        monotonic=clock.monotonic,
        sleep=clock.sleep,
    )
    return downloader, lines


# --------------------------------------------------------------------------- #
# Plan
# --------------------------------------------------------------------------- #


class TestBuildPlan(unittest.TestCase):
    def test_plans_sample_videos_of_included_runs(self) -> None:
        plan = vd.build_plan(_RECORDINGS, _matrix())
        self.assertEqual(
            [(v.filename, v.source, v.pipelines, v.runs) for v in plan.videos],
            [
                # Two variants x two stream counts.
                ("people.mp4", "Pexels", ("smart-nvr",), 4),
                ("warehouse.avi", "OpenVINO", ("goods",), 2),
            ],
        )
        # Not a sample video: must be uploaded.
        self.assertEqual(plan.unavailable, ("mine.mp4",))

    def test_only_selected_pipelines_count(self) -> None:
        plan = vd.build_plan(_RECORDINGS, _matrix(pipelines=["goods"], streams=(1,)))
        self.assertEqual(
            [(v.filename, v.runs) for v in plan.videos], [("warehouse.avi", 1)]
        )

    def test_in_progress_downloads_are_waited_for(self) -> None:
        recordings = [
            _recording("people.mp4", "downloading"),
            _recording("warehouse.avi"),
        ]
        plan = vd.build_plan(recordings, _matrix())
        self.assertEqual([v.filename for v in plan.already_downloading], ["people.mp4"])
        self.assertEqual([v.filename for v in plan.to_download], ["warehouse.avi"])

    def test_conflicting_name_cannot_be_downloaded(self) -> None:
        recordings = [_recording("people.mp4", "conflict"), _recording("warehouse.avi")]
        plan = vd.build_plan(recordings, _matrix())
        self.assertEqual([v.filename for v in plan.videos], ["warehouse.avi"])
        self.assertIn("people.mp4", plan.unavailable)

    def test_untrusted_text_is_cleaned(self) -> None:
        recordings = [_recording("people.mp4", source="Pex\x1b[2Jels\n")]
        plan = vd.build_plan(recordings, _matrix(pipelines=["smart-nvr"]))
        self.assertEqual(plan.videos[0].source, "Pexels")

    def test_no_missing_video_gives_empty_plan(self) -> None:
        matrix = build_matrix(
            _PIPELINES,
            [{"device_family": "CPU"}],
            {},
            MatrixFilters(pipelines="*", stream_counts=(1,)),
        )
        self.assertEqual(vd.build_plan(_RECORDINGS, matrix), vd.VideoPlan())


class TestFormatPlan(unittest.TestCase):
    def test_table_licenses_and_upload_note(self) -> None:
        text = vd.format_plan(vd.build_plan(_RECORDINGS, _matrix()))
        self.assertIn("2 sample video(s)", text)
        self.assertIn("people.mp4", text)
        self.assertIn("smart-nvr", text)
        self.assertIn(f"Pexels License: {vd.PEXELS_LICENSE_URL}", text)
        self.assertIn(f"Pexels Terms of Service: {vd.PEXELS_TERMS_URL}", text)
        self.assertIn("upload them on the ViPPET UI Videos page", text)
        self.assertIn("mine.mp4", text)
        self.assertTrue(text.endswith(vd.LICENSE_NOTE))

    def test_no_pexels_links_without_pexels_videos(self) -> None:
        plan = vd.VideoPlan((vd.PlannedVideo("a.mp4", "GitHub", ("p",), 1),))
        text = vd.format_plan(plan)
        self.assertNotIn("pexels.com", text)
        self.assertTrue(text.endswith(vd.LICENSE_NOTE))

    def test_waiting_videos_are_marked(self) -> None:
        plan = vd.VideoPlan((_planned("a.mp4", downloading=True),))
        self.assertIn("wait (already downloading)", vd.format_plan(plan))

    def test_present_empty_plan_is_one_line(self) -> None:
        lines: list[str] = []
        vd.present_plan(vd.VideoPlan(), lines.append)
        self.assertEqual(lines, [vd.NOTHING_TO_DOWNLOAD])

    def test_present_lists_videos_to_upload_without_header(self) -> None:
        lines: list[str] = []
        vd.present_plan(vd.VideoPlan(unavailable=("mine.mp4",)), lines.append)
        self.assertEqual(lines[0], vd.NOTHING_TO_DOWNLOAD)
        self.assertIn("mine.mp4", lines[1])
        self.assertNotIn(vd.SECTION_HEADER, lines)


class TestPrompt(unittest.TestCase):
    def test_prompt_text(self) -> None:
        self.assertEqual(
            vd.prompt_text(vd.VideoPlan((_planned("a"), _planned("b")))),
            "Download 2 video(s) now? [y/N] ",
        )
        self.assertEqual(
            vd.prompt_text(
                vd.VideoPlan((_planned("a"), _planned("b", downloading=True)))
            ),
            "Download 1 video(s) and wait for 1 already downloading now? [y/N] ",
        )
        self.assertEqual(
            vd.prompt_text(vd.VideoPlan((_planned("b", downloading=True),))),
            "Wait for 1 video(s) that are already downloading? [y/N] ",
        )

    def test_agree(self) -> None:
        plan = vd.VideoPlan((_planned("a"),))
        lines: list[str] = []
        for answer, expected in (("y", True), ("YES", True), ("", False), ("n", False)):
            with self.subTest(answer=answer):
                self.assertIs(
                    vd.agree_to_download(
                        plan,
                        ask=True,
                        input_fn=lambda _, a=answer: a,
                        report=lines.append,
                    ),
                    expected,
                )

    def test_eof_means_no(self) -> None:
        def eof(_: str) -> str:
            raise EOFError

        lines: list[str] = []
        self.assertFalse(
            vd.agree_to_download(
                vd.VideoPlan((_planned("a"),)),
                ask=True,
                input_fn=eof,
                report=lines.append,
            )
        )
        self.assertIn("Not downloading", lines[-1])

    def test_yes_never_prompts(self) -> None:
        def no_prompt(_: str) -> str:
            raise AssertionError("must not prompt")

        lines: list[str] = []
        self.assertTrue(
            vd.agree_to_download(
                vd.VideoPlan((_planned("a"),)),
                ask=False,
                input_fn=no_prompt,
                report=lines.append,
            )
        )
        self.assertIn("--download-missing-videos=yes", lines[0])

    def test_mode_effect(self) -> None:
        self.assertIn("without asking", vd.describe_mode_effect("yes", False))
        self.assertIn("asks before", vd.describe_mode_effect("ask", True))
        self.assertIn("stdin is not a terminal", vd.describe_mode_effect("ask", False))
        self.assertIn("does not download", vd.describe_mode_effect("no", True))


# --------------------------------------------------------------------------- #
# Outcome hand-off
# --------------------------------------------------------------------------- #


class TestOutcomeEnv(unittest.TestCase):
    def test_round_trip(self) -> None:
        outcomes = [
            vd.VideoOutcome("a.mp4", vd.Outcome.DOWNLOADED, "", "converted"),
            vd.VideoOutcome("b.mp4", vd.Outcome.TIMED_OUT, "slow", "converting"),
            vd.VideoOutcome("c.mp4", vd.Outcome.DECLINED, "declined at the prompt"),
        ]
        self.assertEqual(vd.decode_outcomes(vd.encode_outcomes(outcomes)), outcomes)

    def test_unset_is_none(self) -> None:
        self.assertIsNone(vd.decode_outcomes(None))
        self.assertIsNone(vd.decode_outcomes(""))

    def test_invalid_values_are_rejected(self) -> None:
        good = {
            "filename": "a.mp4",
            "outcome": "downloaded",
            "reason": "",
            "conversion_status": "",
        }
        for raw in (
            "not json",
            json.dumps({"filename": "a"}),
            json.dumps([dict(good, outcome="maybe")]),
            json.dumps([dict(good, filename="")]),
            json.dumps([dict(good, extra="x")]),
            json.dumps([{k: v for k, v in good.items() if k != "conversion_status"}]),
            json.dumps([dict(good, reason=1)]),
            json.dumps([good] * 1001),
            "[" + " " * (256 * 1024) + "]",
        ):
            with self.subTest(raw=raw[:40]):
                with self.assertRaises(OutcomeEnvError):
                    vd.decode_outcomes(raw)

    def test_text_is_cleaned_and_unknown_conversion_dropped(self) -> None:
        raw = json.dumps(
            [
                {
                    "filename": "a\x1b[2J.mp4",
                    "outcome": "failed",
                    "reason": "bad\nthing",
                    "conversion_status": "weird",
                }
            ]
        )
        (outcome,) = vd.decode_outcomes(raw) or []
        self.assertEqual(
            outcome, vd.VideoOutcome("a.mp4", vd.Outcome.FAILED, "bad thing", "")
        )


class TestDownloadProblem(unittest.TestCase):
    def test_failed_and_timed_out_are_errors(self) -> None:
        for outcome in (vd.Outcome.FAILED, vd.Outcome.TIMED_OUT):
            with self.subTest(outcome=outcome):
                problem = vd.download_problem(
                    ["a.mp4"], [vd.VideoOutcome("a.mp4", outcome, "offline")]
                )
                assert problem is not None
                self.assertEqual(problem.kind, "error")
                self.assertIn("'a.mp4' failed to download: offline", problem.reason)

    def test_interrupted_is_a_skip(self) -> None:
        problem = vd.download_problem(
            ["a.mp4"], [vd.VideoOutcome("a.mp4", vd.Outcome.INTERRUPTED)]
        )
        assert problem is not None
        self.assertEqual(problem.kind, "skip")
        self.assertIn("interrupted", problem.reason)

    def test_declined_or_unrelated_keeps_the_plain_skip(self) -> None:
        self.assertIsNone(
            vd.download_problem(
                ["a.mp4"], [vd.VideoOutcome("a.mp4", vd.Outcome.DECLINED)]
            )
        )
        self.assertIsNone(
            vd.download_problem(
                ["a.mp4"], [vd.VideoOutcome("b.mp4", vd.Outcome.FAILED)]
            )
        )
        self.assertIsNone(vd.download_problem(["a.mp4"], []))
        # No input video selected: nothing to download.
        self.assertIsNone(vd.download_problem([""], []))


class TestReporting(unittest.TestCase):
    def test_format_outcomes(self) -> None:
        text = vd.format_outcomes(
            [
                vd.VideoOutcome("a.mp4", vd.Outcome.DOWNLOADED, "", "converted"),
                vd.VideoOutcome("b.mp4", vd.Outcome.FAILED, "offline"),
            ]
        )
        self.assertTrue(text.startswith("Video download: 1 downloaded, 1 failed\n"))
        self.assertIn("converted", text)
        self.assertIn("offline", text)

    def test_conversion_failure_line(self) -> None:
        self.assertEqual(
            vd.conversion_failure_line(
                [
                    vd.VideoOutcome("a", vd.Outcome.DOWNLOADED, "", "failed"),
                    vd.VideoOutcome("b", vd.Outcome.DOWNLOADED, "", "conflict"),
                    vd.VideoOutcome("c", vd.Outcome.DOWNLOADED, "", "converted"),
                    vd.VideoOutcome("d", vd.Outcome.DOWNLOADED, "", "unsupported"),
                ]
            ),
            "HEVC conversion failed for 3 video(s); the benchmark is not affected",
        )
        self.assertEqual(vd.conversion_failure_line([]), "")

    def test_unsupported_conversion_is_labelled(self) -> None:
        outcome = vd.VideoOutcome("a.mp4", vd.Outcome.DOWNLOADED, "", "unsupported")
        self.assertEqual(vd.decode_outcomes(vd.encode_outcomes([outcome])), [outcome])
        self.assertIn("not converted (no HEVC encoder)", vd.format_outcomes([outcome]))

    def test_conversion_states_match_the_api(self) -> None:
        self.assertEqual(
            vd.CONVERSION_STATES, {s.value for s in DefaultVideoConversionState}
        )

    def test_skipped_hint(self) -> None:
        self.assertIn(
            "--download-missing-videos=yes", vd.describe_skipped_for_missing_videos(3)
        )
        declined = [vd.VideoOutcome("a", vd.Outcome.DECLINED)]
        self.assertIn(
            "you declined", vd.describe_skipped_for_missing_videos(3, declined)
        )


# --------------------------------------------------------------------------- #
# Downloader
# --------------------------------------------------------------------------- #


class TestVideoDownloader(unittest.TestCase):
    def test_downloads_and_waits_for_conversion(self) -> None:
        api = _FakeApi(
            [
                [_recording("a.mp4", "downloading")],
                [_recording("a.mp4", "downloading")],
                [_recording("a.mp4", "downloaded", "converting")],
                [_recording("a.mp4", "downloaded", "converted")],
            ]
        )
        downloader, lines = _downloader(api, _Clock())
        outcomes = downloader.download(vd.VideoPlan((_planned("a.mp4"),)))
        self.assertEqual(api.posts, ["a.mp4"])
        self.assertEqual(
            outcomes, [vd.VideoOutcome("a.mp4", vd.Outcome.DOWNLOADED, "", "converted")]
        )
        self.assertTrue(all(line.startswith("[video-download] ") for line in lines))
        # A state is printed once, when it changes.
        self.assertEqual(sum("a.mp4: downloading" in line for line in lines), 1)
        self.assertTrue(any("a.mp4: downloaded" in line for line in lines))
        self.assertTrue(any("HEVC copy ready" in line for line in lines))

    def test_waits_for_running_download_without_requesting_it(self) -> None:
        api = _FakeApi([[_recording("a.mp4", "downloaded", "converted")]])
        downloader, _ = _downloader(api, _Clock())
        outcomes = downloader.download(
            vd.VideoPlan((_planned("a.mp4", downloading=True),))
        )
        self.assertEqual(api.posts, [])
        self.assertEqual(outcomes[0].outcome, vd.Outcome.DOWNLOADED)

    def test_rejected_request_fails_only_that_video(self) -> None:
        for status in (404, 409):
            with self.subTest(status=status):
                api = _FakeApi(
                    [[_recording("b.mp4", "downloaded", "converted")]],
                    post_status={"a.mp4": status},
                )
                downloader, lines = _downloader(api, _Clock())
                outcomes = downloader.download(
                    vd.VideoPlan((_planned("a.mp4"), _planned("b.mp4")))
                )
                self.assertEqual(
                    [o.outcome for o in outcomes],
                    [vd.Outcome.FAILED, vd.Outcome.DOWNLOADED],
                )
                self.assertIn(f"HTTP {status}", outcomes[0].reason)
                # Server text is cleaned before it is shown.
                self.assertNotIn("\x1b", outcomes[0].reason)
                self.assertTrue(any("a.mp4: FAILED" in line for line in lines))

    def test_network_error_on_request_fails(self) -> None:
        api = _FakeApi([[]], post_error=httpx.ConnectError("refused"))
        downloader, _ = _downloader(api, _Clock())
        (outcome,) = downloader.download(vd.VideoPlan((_planned("a.mp4"),)))
        self.assertEqual(outcome.outcome, vd.Outcome.FAILED)
        self.assertIn("ConnectError", outcome.reason)

    def test_server_side_failure_and_conflict(self) -> None:
        for status, text in (
            ("failed", "could not download"),
            ("conflict", "filename"),
        ):
            with self.subTest(status=status):
                api = _FakeApi([[_recording("a.mp4", status)]])
                downloader, _ = _downloader(api, _Clock())
                (outcome,) = downloader.download(vd.VideoPlan((_planned("a.mp4"),)))
                self.assertEqual(outcome.outcome, vd.Outcome.FAILED)
                self.assertIn(text, outcome.reason)

    def test_back_to_available_means_the_download_was_lost(self) -> None:
        api = _FakeApi([[_recording("a.mp4", "available")]])
        downloader, _ = _downloader(api, _Clock())
        (outcome,) = downloader.download(vd.VideoPlan((_planned("a.mp4"),)))
        self.assertEqual(outcome.outcome, vd.Outcome.FAILED)
        self.assertIn("restarted", outcome.reason)

    def test_poll_errors_are_retried(self) -> None:
        api = _FakeApi(
            [
                httpx.ReadTimeout("slow"),
                [_recording("a.mp4", "downloaded", "converted")],
            ]
        )
        downloader, lines = _downloader(api, _Clock())
        (outcome,) = downloader.download(vd.VideoPlan((_planned("a.mp4"),)))
        self.assertEqual(outcome.outcome, vd.Outcome.DOWNLOADED)
        self.assertTrue(any("POLL FAILED" in line for line in lines))

    def test_timeout_marks_unfinished_downloads(self) -> None:
        api = _FakeApi([[_recording("a.mp4", "downloading")]])
        clock = _Clock()
        downloader, lines = _downloader(api, clock, timeout=60)
        (outcome,) = downloader.download(vd.VideoPlan((_planned("a.mp4"),)))
        self.assertEqual(outcome.outcome, vd.Outcome.TIMED_OUT)
        self.assertIn("--video-download-timeout", outcome.reason)
        self.assertLessEqual(clock.now - 1000.0, 60)
        self.assertTrue(any("TIMED OUT" in line for line in lines))

    def test_unfinished_conversion_at_timeout_does_not_fail_the_video(self) -> None:
        api = _FakeApi([[_recording("a.mp4", "downloaded", "converting")]])
        downloader, _ = _downloader(api, _Clock(), timeout=60)
        (outcome,) = downloader.download(vd.VideoPlan((_planned("a.mp4"),)))
        self.assertEqual(
            outcome, vd.VideoOutcome("a.mp4", vd.Outcome.DOWNLOADED, "", "converting")
        )

    def test_failed_conversions_are_one_summary_line(self) -> None:
        api = _FakeApi(
            [
                [
                    _recording("a.mp4", "downloaded", "failed"),
                    _recording("b.mp4", "downloaded", "failed"),
                ]
            ]
        )
        downloader, lines = _downloader(api, _Clock())
        outcomes = downloader.download(
            vd.VideoPlan((_planned("a.mp4"), _planned("b.mp4")))
        )
        self.assertEqual([o.outcome for o in outcomes], [vd.Outcome.DOWNLOADED] * 2)
        self.assertEqual([o.conversion_status for o in outcomes], ["failed"] * 2)
        failure_lines = [line for line in lines if "HEVC conversion" in line]
        self.assertEqual(
            failure_lines,
            [
                "[video-download] HEVC conversion failed for 2 video(s); the "
                "benchmark is not affected"
            ],
        )

    def test_ctrl_c_while_waiting_is_interrupted(self) -> None:
        api = _FakeApi(
            [
                [
                    _recording("a.mp4", "downloaded", "converted"),
                    _recording("b.mp4", "downloading"),
                ]
            ]
        )
        downloader, lines = _downloader(api, _Clock())

        def ctrl_c(_: float) -> None:
            raise KeyboardInterrupt

        downloader.sleep = ctrl_c
        outcomes = downloader.download(
            vd.VideoPlan((_planned("a.mp4"), _planned("b.mp4")))
        )
        self.assertEqual(
            [o.outcome for o in outcomes],
            [vd.Outcome.DOWNLOADED, vd.Outcome.INTERRUPTED],
        )
        self.assertTrue(any("Interrupted" in line for line in lines))

    def test_summary_is_printed_while_waiting(self) -> None:
        api = _FakeApi([[_recording("a.mp4", "downloading")]])
        downloader, lines = _downloader(api, _Clock(), timeout=300)
        downloader.summary_interval = 60
        downloader.download(vd.VideoPlan((_planned("a.mp4"),)))
        self.assertTrue(any("still downloading" in line for line in lines))


class TestFetchDefaultRecordings(unittest.TestCase):
    def _fetch(self, response: httpx.Response) -> Any:
        client = httpx.Client(transport=httpx.MockTransport(lambda _: response))
        return vd.fetch_default_recordings(client, _BASE, 5)

    def test_404_means_older_vippet(self) -> None:
        self.assertIsNone(self._fetch(httpx.Response(404)))

    def test_other_errors_raise(self) -> None:
        with self.assertRaises(httpx.HTTPStatusError):
            self._fetch(httpx.Response(500))
        with self.assertRaises(ValueError):
            self._fetch(httpx.Response(200, json={"not": "a list"}))

    def test_non_objects_are_dropped(self) -> None:
        self.assertEqual(
            self._fetch(httpx.Response(200, json=[_RECORDINGS[0], "x", 1])),
            [_RECORDINGS[0]],
        )


if __name__ == "__main__":
    unittest.main()

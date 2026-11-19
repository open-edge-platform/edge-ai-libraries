# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for perf_helpers.model_install (plan, prompt, install, outcome)."""

import json
import re
import unittest
from typing import Any

import httpx

from tests.performance.perf_helpers import model_install as mi
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
    {"id": "other", "name": "Other", "variants": [{"id": "5", "name": "CPU"}]},
]


def _matrix(pipelines: Any = "*", streams: tuple[int, ...] = (1, 3)) -> Any:
    return build_matrix(
        _PIPELINES,
        [{"device_family": "CPU"}, {"device_family": "GPU"}],
        {},
        MatrixFilters(pipelines=pipelines, stream_counts=streams),
    )


def _model(name: str, status: str = "not_installed", **extra: Any) -> dict[str, Any]:
    return {
        "name": name,
        "display_name": extra.pop("display_name", name.upper()),
        "source": extra.pop("source", "omz"),
        "install_status": status,
        "used_by_pipelines": extra.pop("used_by", ["smart-nvr"]),
        **extra,
    }


def _planned(name: str, *, installing: bool = False) -> mi.PlannedModel:
    return mi.PlannedModel(
        name=name,
        display_name=name.upper(),
        source="omz",
        gated="",
        link="",
        pipelines=("smart-nvr",),
        runs=2,
        already_installing=installing,
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
    """MockTransport handler for the ViPPET model endpoints."""

    def __init__(
        self,
        *,
        download_status: int = 202,
        download_body: Any = None,
        jobs_list: Any = (),
        job_states: dict[str, list[dict[str, Any]]] | None = None,
        models: Any = (),
        post_error: Exception | None = None,
    ) -> None:
        self.download_status = download_status
        self.download_body = download_body
        self.jobs_list = list(jobs_list)
        self.job_states = job_states or {}
        self.models = list(models)
        self.post_error = post_error
        self.requests: list[tuple[str, str, Any]] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path.removeprefix("/api/v1")
        body = json.loads(request.content) if request.content else None
        self.requests.append((request.method, path, body))
        if request.method == "POST" and path == "/models/download":
            if self.post_error is not None:
                raise self.post_error
            return httpx.Response(self.download_status, json=self.download_body)
        if path == "/jobs/models/status":
            return httpx.Response(200, json=self.jobs_list)
        if path == "/models":
            return httpx.Response(200, json=self.models)
        match = re.fullmatch(r"/jobs/models/([^/]+)/status", path)
        if match and match.group(1) in self.job_states:
            states = self.job_states[match.group(1)]
            state = states.pop(0) if len(states) > 1 else states[0]
            return httpx.Response(200, json=state)
        return httpx.Response(404, json={"message": "not found"})

    def client(self) -> httpx.Client:
        return httpx.Client(transport=httpx.MockTransport(self))

    def paths(self, method: str | None = None) -> list[str]:
        return [p for m, p, _ in self.requests if method is None or m == method]


def _job(state: str, **extra: Any) -> dict[str, Any]:
    return {"state": state, "details": extra.pop("details", []), **extra}


def _accepted(*names: str) -> dict[str, Any]:
    return {
        "jobs": {
            name: {
                "name": name,
                "job_id": f"job{n}",
                "status_code": 202,
                "message": "ok",
            }
            for n, name in enumerate(names)
        }
    }


class _InstallerMixin(unittest.TestCase):
    def setUp(self) -> None:
        self.clock = _Clock()
        self.lines: list[str] = []

    def install(
        self, api: _FakeApi, plan: mi.InstallPlan, timeout: float = 100.0
    ) -> list[mi.ModelOutcome]:
        with api.client() as client:
            installer = mi.ModelInstaller(
                client=client,
                base_url=_BASE,
                poll_interval=2.0,
                timeout_seconds=timeout,
                request_timeout=5.0,
                report=self.lines.append,
                monotonic=self.clock.monotonic,
                sleep=self.clock.sleep,
            )
            return installer.install(plan)

    def by_name(self, outcomes: list[mi.ModelOutcome]) -> dict[str, mi.ModelOutcome]:
        return {o.name: o for o in outcomes}

    @property
    def text(self) -> str:
        return "\n".join(self.lines)


# --------------------------------------------------------------------------- #
# Untrusted text
# --------------------------------------------------------------------------- #


class TestCleanText(unittest.TestCase):
    def test_strips_escape_sequences_and_control_characters(self) -> None:
        raw = "\x1b[31mred\x1b[0m\x07 \x1b]0;title\x07name\x00\u202e\nnext\tline"
        self.assertEqual(mi.clean_text(raw), "red name next line")

    def test_truncates_and_handles_none(self) -> None:
        self.assertEqual(mi.clean_text(None), "")
        self.assertEqual(mi.clean_text("x" * 20, max_length=10), "xxxxxxx...")

    def test_format_duration(self) -> None:
        self.assertEqual(mi.format_duration(5), "5s")
        self.assertEqual(mi.format_duration(65), "1m05s")
        self.assertEqual(mi.format_duration(3725), "1h02m05s")


# --------------------------------------------------------------------------- #
# Plan
# --------------------------------------------------------------------------- #


class TestBuildPlan(unittest.TestCase):
    def test_only_models_of_included_pipelines_that_are_not_installed(self) -> None:
        models = [
            _model("needed", used_by=["smart-nvr", "other"]),
            _model("retry", status="failed", used_by=["goods"]),
            _model("busy", status="installing", used_by=["goods"]),
            _model("done", status="installed"),
            # The NPU variant is excluded on this CPU/GPU host.
            _model("npu", used_by=["npu-only"]),
            _model("unused", used_by=[]),
            {
                "display_name": "No name",
                "install_status": "not_installed",
                "used_by_pipelines": ["goods"],
            },
        ]
        plan = mi.build_plan(models, _matrix())
        by_name = {m.name: m for m in plan.models}
        self.assertEqual(sorted(by_name), ["busy", "needed", "retry"])
        # smart-nvr: 2 variants x 2 streams, other: 1 x 2.
        self.assertEqual(by_name["needed"].runs, 6)
        self.assertEqual(by_name["needed"].pipelines, ("other", "smart-nvr"))
        self.assertTrue(by_name["busy"].already_installing)
        self.assertEqual([m.name for m in plan.to_download], ["needed", "retry"])
        self.assertEqual([m.name for m in plan.already_installing], ["busy"])

    def test_pipeline_filter_limits_the_plan(self) -> None:
        models = [_model("a", used_by=["smart-nvr"]), _model("b", used_by=["goods"])]
        plan = mi.build_plan(models, _matrix(pipelines=["goods"], streams=(1,)))
        self.assertEqual(
            [(m.name, m.pipelines, m.runs) for m in plan.models], [("b", ("goods",), 1)]
        )

    def test_untrusted_fields_are_cleaned(self) -> None:
        model = _model(
            "m",
            display_name="Evil\x1b[2J",
            gated="manual",
            link="javascript:alert(1)",
        )
        planned = mi.build_plan([model], _matrix()).models[0]
        self.assertEqual(planned.display_name, "Evil")
        self.assertEqual(planned.link, "")
        self.assertTrue(planned.is_gated)

    def test_empty_plan(self) -> None:
        plan = mi.build_plan([_model("done", status="installed")], _matrix())
        self.assertEqual(plan.models, ())
        self.assertEqual(
            mi.format_plan(plan), "Every model the selected runs need is installed."
        )


class TestFormatPlan(unittest.TestCase):
    def test_table_gated_note_and_license_footer(self) -> None:
        models = [
            _model("open", display_name="Open Model", gated="false"),
            _model(
                "gated",
                display_name="Gated Model",
                source="huggingface",
                gated="auto",
                link="https://huggingface.co/org/gated",
            ),
        ]
        text = mi.format_plan(mi.build_plan(models, _matrix()))
        self.assertIn("2 model(s) needed by the selected runs are not installed", text)
        for header in (
            "model",
            "source",
            "gated",
            "link",
            "pipelines in this run",
            "runs needing it",
        ):
            self.assertIn(header, text)
        self.assertIn(
            "Gated Model: accept the license at https://huggingface.co/org/gated", text
        )
        self.assertIn("HF_TOKEN", text)
        self.assertIn("docker compose up -d model-download", text)
        self.assertNotIn("Open Model: accept", text)
        self.assertTrue(
            text.endswith(
                "By installing you accept the license terms of each model's "
                "upstream source."
            )
        )

    def test_no_gated_note_without_gated_models(self) -> None:
        text = mi.format_plan(mi.build_plan([_model("m")], _matrix()))
        self.assertNotIn("HF_TOKEN", text)

    def test_prompt_text(self) -> None:
        self.assertEqual(
            mi.prompt_text(mi.InstallPlan((_planned("a"), _planned("b")))),
            "Install 2 model(s) now? [y/N] ",
        )
        self.assertIn(
            "wait for 1 already installing",
            mi.prompt_text(
                mi.InstallPlan((_planned("a"), _planned("b", installing=True)))
            ),
        )
        self.assertEqual(
            mi.prompt_text(mi.InstallPlan((_planned("b", installing=True),))),
            "Wait for 1 model(s) that are already installing? [y/N] ",
        )

    def test_describe_mode_effect(self) -> None:
        self.assertIn("without asking", mi.describe_mode_effect("yes", False))
        self.assertIn("does not install", mi.describe_mode_effect("no", True))
        self.assertIn("asks before", mi.describe_mode_effect("ask", True))
        no_tty = mi.describe_mode_effect("ask", False)
        self.assertIn("stdin is not a terminal", no_tty)
        self.assertIn("--install-missing-models=yes", no_tty)


# --------------------------------------------------------------------------- #
# Prompt
# --------------------------------------------------------------------------- #


class TestPrompt(unittest.TestCase):
    def test_confirm(self) -> None:
        for answer, expected in (
            ("y", True),
            (" YES ", True),
            ("n", False),
            ("", False),
            ("sure", False),
        ):
            with self.subTest(answer=answer):
                self.assertIs(mi.confirm("?", lambda _: answer), expected)

    def test_eof_means_no(self) -> None:
        def eof(_: str) -> str:
            raise EOFError

        self.assertFalse(mi.confirm("?", eof))

    def _offer(self, plan: mi.InstallPlan, ask: bool, answer: str = "") -> Any:
        prompts: list[str] = []
        installs: list[mi.InstallPlan] = []
        lines: list[str] = []

        def input_fn(text: str) -> str:
            prompts.append(text)
            return answer

        def install(p: mi.InstallPlan) -> list[mi.ModelOutcome]:
            installs.append(p)
            return [
                mi.ModelOutcome(m.name, m.display_name, mi.Outcome.INSTALLED)
                for m in p.models
            ]

        outcomes = mi.offer_and_install(
            plan, ask=ask, install=install, input_fn=input_fn, report=lines.append
        )
        return outcomes, prompts, installs, "\n".join(lines)

    def test_empty_plan_never_prompts(self) -> None:
        outcomes, prompts, installs, text = self._offer(mi.InstallPlan(), ask=True)
        self.assertEqual((outcomes, prompts, installs), ([], [], []))
        self.assertEqual(text, "Every model the selected runs need is installed.")

    def test_declining_installs_nothing(self) -> None:
        plan = mi.InstallPlan((_planned("a"),))
        outcomes, prompts, installs, text = self._offer(plan, ask=True, answer="n")
        self.assertEqual(prompts, ["Install 1 model(s) now? [y/N] "])
        self.assertEqual(installs, [])
        self.assertEqual([o.outcome for o in outcomes], [mi.Outcome.DECLINED])
        self.assertIn("Not installing", text)
        self.assertIn("--install-missing-models=yes", text)

    def test_accepting_installs(self) -> None:
        plan = mi.InstallPlan((_planned("a"),))
        outcomes, _, installs, text = self._offer(plan, ask=True, answer="y")
        self.assertEqual(installs, [plan])
        self.assertEqual([o.outcome for o in outcomes], [mi.Outcome.INSTALLED])
        self.assertIn("Model installation: 1 installed", text)

    def test_yes_installs_without_prompt(self) -> None:
        plan = mi.InstallPlan((_planned("a"),))
        _, prompts, installs, text = self._offer(plan, ask=False)
        self.assertEqual(prompts, [])
        self.assertEqual(installs, [plan])
        self.assertIn("Installing without asking", text)


# --------------------------------------------------------------------------- #
# Install and wait
# --------------------------------------------------------------------------- #


class TestInstaller(_InstallerMixin):
    def test_accepted_downloads_are_polled_until_completed(self) -> None:
        api = _FakeApi(
            download_body=_accepted("a", "b"),
            job_states={
                "job0": [
                    _job("RUNNING", progress_message="fetching"),
                    _job("COMPLETED"),
                ],
                "job1": [_job("COMPLETED")],
            },
        )
        plan = mi.InstallPlan((_planned("a"), _planned("b")))
        outcomes = self.by_name(self.install(api, plan))
        self.assertEqual(outcomes["a"].outcome, mi.Outcome.INSTALLED)
        self.assertEqual(outcomes["b"].outcome, mi.Outcome.INSTALLED)
        posts = [b for m, p, b in api.requests if m == "POST"]
        self.assertEqual(posts, [{"names": ["a", "b"]}])
        self.assertEqual(self.clock.sleeps, [2.0])
        self.assertIn("A: RUNNING - fetching (0s)", self.text)
        self.assertIn("A: installed (2s)", self.text)

    def test_failed_job_reports_only_the_last_detail(self) -> None:
        api = _FakeApi(
            download_body=_accepted("a"),
            job_states={
                "job0": [
                    _job(
                        "FAILED",
                        details=[
                            "POST http://model-download/internal body={...}",
                            "Model was not successfully installed. Check your "
                            "Hugging Face access token\x1b[0m",
                        ],
                    )
                ]
            },
        )
        outcome = self.install(api, mi.InstallPlan((_planned("a"),)))[0]
        self.assertEqual(outcome.outcome, mi.Outcome.FAILED)
        self.assertEqual(
            outcome.reason,
            "Model was not successfully installed. Check your Hugging Face access token",
        )
        self.assertNotIn("model-download/internal", self.text)

    def test_mixed_207_response(self) -> None:
        body = _accepted("a")
        body["jobs"]["unknown"] = {
            "name": "unknown",
            "job_id": None,
            "status_code": 404,
            "message": "Model 'unknown' is not supported",
        }
        body["jobs"]["nodl"] = {
            "name": "nodl",
            "job_id": None,
            "status_code": 400,
            "message": "Model 'nodl' has no download_request configured",
        }
        api = _FakeApi(
            download_status=207,
            download_body=body,
            job_states={"job0": [_job("COMPLETED")]},
        )
        plan = mi.InstallPlan((_planned("a"), _planned("unknown"), _planned("nodl")))
        outcomes = self.by_name(self.install(api, plan))
        self.assertEqual(outcomes["a"].outcome, mi.Outcome.INSTALLED)
        self.assertEqual(outcomes["unknown"].outcome, mi.Outcome.FAILED)
        self.assertIn("HTTP 404", outcomes["unknown"].reason)
        self.assertIn("is not supported", outcomes["unknown"].reason)
        self.assertIn("HTTP 400", outcomes["nodl"].reason)

    def test_409_running_job_is_polled(self) -> None:
        api = _FakeApi(
            download_status=409,
            download_body={
                "jobs": {
                    "a": {
                        "name": "a",
                        "job_id": None,
                        "status_code": 409,
                        "message": "Download for model 'a' is already running (job old)",
                    }
                }
            },
            jobs_list=[
                {"id": "old", "model_name": "a", "state": "FAILED", "start_time": 1},
                {"id": "run", "model_name": "a", "state": "RUNNING", "start_time": 2},
            ],
            job_states={"run": [_job("COMPLETED")]},
        )
        outcome = self.install(api, mi.InstallPlan((_planned("a"),)))[0]
        self.assertEqual(outcome.outcome, mi.Outcome.INSTALLED)
        self.assertIn("/jobs/models/run/status", api.paths("GET"))
        self.assertIn("A: already downloading", self.text)

    def test_409_without_running_job(self) -> None:
        body = {
            "jobs": {
                name: {"name": name, "job_id": None, "status_code": 409, "message": "x"}
                for name in ("done", "ghost")
            }
        }
        api = _FakeApi(
            download_status=409,
            download_body=body,
            models=[_model("done", status="installed"), _model("ghost")],
        )
        plan = mi.InstallPlan((_planned("done"), _planned("ghost")))
        outcomes = self.by_name(self.install(api, plan))
        self.assertEqual(outcomes["done"].outcome, mi.Outcome.INSTALLED)
        self.assertEqual(outcomes["done"].reason, "already installed")
        self.assertEqual(outcomes["ghost"].outcome, mi.Outcome.FAILED)
        self.assertIn("no running download was found", outcomes["ghost"].reason)

    def test_already_installing_models_are_waited_for_without_post(self) -> None:
        api = _FakeApi(
            jobs_list=[{"id": "j9", "model_name": "busy", "state": "RUNNING"}],
            job_states={"j9": [_job("COMPLETED")]},
        )
        outcome = self.install(
            api, mi.InstallPlan((_planned("busy", installing=True),))
        )[0]
        self.assertEqual(outcome.outcome, mi.Outcome.INSTALLED)
        self.assertEqual(api.paths("POST"), [])

    def test_rejected_envelope_fails_every_model(self) -> None:
        api = _FakeApi(download_status=422, download_body={"detail": "duplicate names"})
        outcomes = self.install(api, mi.InstallPlan((_planned("a"), _planned("b"))))
        self.assertEqual({o.outcome for o in outcomes}, {mi.Outcome.FAILED})
        self.assertIn("HTTP 422", outcomes[0].reason)
        self.assertIn("duplicate names", outcomes[0].reason)

    def test_post_transport_error_fails_every_model(self) -> None:
        api = _FakeApi(post_error=httpx.ConnectError("refused"))
        outcome = self.install(api, mi.InstallPlan((_planned("a"),)))[0]
        self.assertEqual(outcome.outcome, mi.Outcome.FAILED)
        self.assertIn("POST /models/download failed: ConnectError", outcome.reason)

    def test_unsafe_job_id_is_not_used_in_a_url(self) -> None:
        body = {"jobs": {"a": {"name": "a", "job_id": "../../x", "status_code": 202}}}
        api = _FakeApi(download_body=body)
        outcome = self.install(api, mi.InstallPlan((_planned("a"),)))[0]
        self.assertEqual(outcome.outcome, mi.Outcome.FAILED)
        self.assertFalse(any(".." in p for p in api.paths()))

    def test_vanished_job_fails(self) -> None:
        api = _FakeApi(download_body=_accepted("a"))  # job0 unknown -> 404
        outcome = self.install(api, mi.InstallPlan((_planned("a"),)))[0]
        self.assertEqual(outcome.outcome, mi.Outcome.FAILED)
        self.assertIn("disappeared", outcome.reason)

    def test_timeout_marks_running_models_timed_out(self) -> None:
        api = _FakeApi(
            download_body=_accepted("a", "b"),
            job_states={"job0": [_job("RUNNING")], "job1": [_job("COMPLETED")]},
        )
        plan = mi.InstallPlan((_planned("a"), _planned("b")))
        outcomes = self.by_name(self.install(api, plan, timeout=7))
        self.assertEqual(outcomes["a"].outcome, mi.Outcome.TIMED_OUT)
        self.assertIn("still installing after 7s", outcomes["a"].reason)
        self.assertIn("continues on the server", outcomes["a"].reason)
        self.assertEqual(outcomes["b"].outcome, mi.Outcome.INSTALLED)
        self.assertEqual(self.clock.sleeps, [2.0, 2.0, 2.0, 1.0])

    def test_progress_lines_only_on_change_plus_summary_every_60s(self) -> None:
        states = [_job("RUNNING", progress_message="downloading")] * 70
        api = _FakeApi(
            download_body=_accepted("a"),
            job_states={"job0": states + [_job("COMPLETED")]},
        )
        self.install(api, mi.InstallPlan((_planned("a"),)), timeout=1000)
        progress = [line for line in self.lines if "RUNNING" in line]
        summaries = [line for line in self.lines if "still installing (elapsed" in line]
        self.assertEqual(len(progress), 1)
        # 70 RUNNING polls 2 s apart (0..138 s): summaries at 60 s and 120 s.
        self.assertEqual(len(summaries), 2)
        self.assertIn(
            "0 installed, 0 failed, 1 still installing (elapsed 1m00s", summaries[0]
        )

    def test_transient_poll_error_keeps_waiting(self) -> None:
        calls = {"n": 0}

        def handler(request: httpx.Request) -> httpx.Response:
            if request.method == "POST":
                return httpx.Response(202, json=_accepted("a"))
            calls["n"] += 1
            if calls["n"] == 1:
                raise httpx.ReadTimeout("slow")
            return httpx.Response(200, json=_job("COMPLETED"))

        with httpx.Client(transport=httpx.MockTransport(handler)) as client:
            outcome = mi.ModelInstaller(
                client=client,
                base_url=_BASE,
                poll_interval=1,
                timeout_seconds=100,
                request_timeout=5,
                report=self.lines.append,
                monotonic=self.clock.monotonic,
                sleep=self.clock.sleep,
            ).install(mi.InstallPlan((_planned("a"),)))[0]
        self.assertEqual(outcome.outcome, mi.Outcome.INSTALLED)
        self.assertIn("POLL FAILED - ReadTimeout", self.text)

    def test_ctrl_c_stops_waiting_and_marks_pending_interrupted(self) -> None:
        api = _FakeApi(
            download_body=_accepted("a", "b"),
            job_states={"job0": [_job("COMPLETED")], "job1": [_job("RUNNING")]},
        )

        def interrupt(_: float) -> None:
            raise KeyboardInterrupt

        self.clock.sleep = interrupt  # type: ignore[method-assign]
        plan = mi.InstallPlan((_planned("a"), _planned("b")))
        outcomes = self.by_name(self.install(api, plan))
        self.assertEqual(outcomes["a"].outcome, mi.Outcome.INSTALLED)
        self.assertEqual(outcomes["b"].outcome, mi.Outcome.INTERRUPTED)
        self.assertIn(
            "Downloads that already started continue on the server", self.text
        )
        self.assertIn("press Ctrl-C again to abort", self.text)


# --------------------------------------------------------------------------- #
# Outcome hand-over and mapping to pytest results
# --------------------------------------------------------------------------- #


class TestOutcomeHandOver(unittest.TestCase):
    def test_round_trip(self) -> None:
        outcomes = [
            mi.ModelOutcome("a", "A", mi.Outcome.INSTALLED),
            mi.ModelOutcome("b", "B", mi.Outcome.FAILED, "no token"),
        ]
        self.assertEqual(mi.decode_outcomes(mi.encode_outcomes(outcomes)), outcomes)

    def test_unset_or_empty_is_none(self) -> None:
        self.assertIsNone(mi.decode_outcomes(None))
        self.assertIsNone(mi.decode_outcomes(""))
        self.assertEqual(mi.decode_outcomes("[]"), [])

    def test_invalid_values_are_rejected(self) -> None:
        valid = {"name": "a", "display_name": "A", "outcome": "failed", "reason": ""}
        for raw in (
            "{not json",
            "{}",
            json.dumps([{**valid, "outcome": "exploded"}]),
            json.dumps([{**valid, "extra": "x"}]),
            json.dumps([{**valid, "reason": 5}]),
            json.dumps([{**valid, "name": ""}]),
            "[" + " " * (300 * 1024) + "]",
        ):
            with self.subTest(raw=raw[:40]):
                with self.assertRaisesRegex(mi.ModelInstallError, "To fix: unset it"):
                    mi.decode_outcomes(raw)

    def test_decoded_text_is_cleaned_again(self) -> None:
        raw = json.dumps(
            [
                {
                    "name": "a",
                    "display_name": "A\x1b[2J",
                    "outcome": "failed",
                    "reason": "bad\x07",
                }
            ]
        )
        outcome = mi.decode_outcomes(raw)[0]  # type: ignore[index]
        self.assertEqual((outcome.display_name, outcome.reason), ("A", "bad"))


class TestInstallProblem(unittest.TestCase):
    def _outcomes(self) -> list[mi.ModelOutcome]:
        return [
            mi.ModelOutcome("f", "Failed", mi.Outcome.FAILED, "check HF token"),
            mi.ModelOutcome("t", "Slow", mi.Outcome.TIMED_OUT, "still installing"),
            mi.ModelOutcome("i", "Busy", mi.Outcome.INTERRUPTED, "x"),
            mi.ModelOutcome("d", "Declined", mi.Outcome.DECLINED, "x"),
            mi.ModelOutcome("ok", "Done", mi.Outcome.INSTALLED),
        ]

    def test_failed_and_timed_out_are_errors(self) -> None:
        kind, reason = mi.install_problem({"Failed", "Slow", "Busy"}, self._outcomes())  # type: ignore[misc]
        self.assertEqual(kind, "error")
        self.assertIn("model 'Failed' failed to install: check HF token", reason)
        self.assertIn("model 'Slow' failed to install: still installing", reason)

    def test_interrupted_is_skipped(self) -> None:
        kind, reason = mi.install_problem({"Busy", "Declined"}, self._outcomes())  # type: ignore[misc]
        self.assertEqual(kind, "skip")
        self.assertIn("'Busy'", reason)
        self.assertIn("continues on the server", reason)

    def test_declined_or_unknown_keep_the_default_skip(self) -> None:
        self.assertIsNone(mi.install_problem({"Declined"}, self._outcomes()))
        self.assertIsNone(mi.install_problem({"Never tried"}, self._outcomes()))
        self.assertIsNone(mi.install_problem({"Failed"}, []))

    def test_format_outcomes_and_hint(self) -> None:
        text = mi.format_outcomes(self._outcomes())
        self.assertIn(
            "1 installed, 1 failed, 1 timed_out, 1 declined, 1 interrupted", text
        )
        self.assertIn("check HF token", text)
        hint = mi.describe_skipped_for_missing_models(3)
        self.assertIn("3 run(s) were skipped", hint)
        self.assertIn('PERF_ARGS="--install-missing-models=yes"', hint)
        self.assertIn("a direct pytest run never does", hint)


if __name__ == "__main__":
    unittest.main()

# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Offer to install the models the selected benchmark runs need.

Used by the CLI (``python -m perf_helpers.cli``) before it starts pytest:

1. :func:`build_plan` picks the models that are not installed and are used
   by a pipeline in the benchmark matrix.
2. :func:`offer_and_install` prints the plan, asks (``ask``) or not
   (``yes``), and runs :class:`ModelInstaller`, which starts the downloads
   through ``POST /models/download`` and waits for their jobs.
3. The per-model outcome is handed to the pytest subprocess as JSON in
   :data:`ENV_MODEL_INSTALL` (see :func:`encode_outcomes` /
   :func:`decode_outcomes`). pytest turns runs whose model failed to install
   into errors (:func:`install_problem`) and reports the outcome.

pytest itself never prompts or installs. Every text that comes from the
server is passed through :func:`clean_text` before it is printed, because it
is untrusted (it could carry terminal escape sequences).

All HTTP goes through an injected ``httpx.Client``, and time, sleep, input
and output are injectable, so this module is unit-testable without a stack.
"""

import json
import re
import time
import unicodedata
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

import httpx

from .matrix import Matrix, format_table

# Set by the CLI for its pytest subprocess: JSON list of model outcomes.
ENV_MODEL_INSTALL: str = "PERF_MODEL_INSTALL_OUTCOME"
_MAX_OUTCOME_CHARS = 256 * 1024
_MAX_OUTCOME_MODELS = 1000

# pytest marker that turns a run into an ERROR (set at collection, raised by
# an autouse fixture during setup).
MODEL_INSTALL_ERROR_MARK: str = "perf_model_install_error"

SUMMARY_INTERVAL_SECONDS: float = 60.0

_INSTALLED = "installed"
_INSTALLING = "installing"
_GATED_VALUES: frozenset[str] = frozenset({"auto", "manual"})
# Job ids are put into a URL path; accept only plain identifiers.
_JOB_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,128}$")
_LOG_PREFIX = "[model-install]"

INSTALL_HINT: str = (
    'Install them with make test-performance PERF_ARGS="--install-missing-models=yes" '
    "(or python -m perf_helpers.cli --install-missing-models=yes), or on the "
    "ViPPET UI Models page"
)
SKIP_REASON_HINT: str = f"{INSTALL_HINT}, to enable this case."


class ModelInstallError(ValueError):
    """Raised when the outcome handed over by the CLI is not valid."""


class Outcome(StrEnum):
    INSTALLED = "installed"
    FAILED = "failed"
    TIMED_OUT = "timed_out"
    DECLINED = "declined"
    INTERRUPTED = "interrupted"


# Runs needing a model with one of these outcomes are reported as ERROR.
ERROR_OUTCOMES: frozenset[Outcome] = frozenset({Outcome.FAILED, Outcome.TIMED_OUT})


# --------------------------------------------------------------------------- #
# Untrusted text
# --------------------------------------------------------------------------- #

_ESCAPE_SEQUENCE_RE = re.compile(
    r"\x1b\[[0-?]*[ -/]*[@-~]"  # CSI, e.g. colours and cursor movement
    r"|\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)?"  # OSC, e.g. window title, hyperlinks
    r"|\x1b[@-_]"  # other two-character escapes
)


def clean_text(value: Any, max_length: int = 300) -> str:
    """Return *value* as one line of printable text.

    Removes terminal escape sequences and control/format characters, folds
    whitespace and truncates to *max_length* characters.
    """
    if value is None:
        return ""
    text = _ESCAPE_SEQUENCE_RE.sub("", str(value))
    chars = []
    for char in text:
        if char in "\t\n\r":
            chars.append(" ")
        elif not unicodedata.category(char).startswith("C"):
            chars.append(char)
    text = " ".join("".join(chars).split())
    if len(text) > max_length:
        text = text[: max_length - 3] + "..."
    return text


def _clean_link(value: Any) -> str:
    link = clean_text(value, max_length=500)
    return link if link.startswith(("https://", "http://")) else ""


def format_duration(seconds: float) -> str:
    seconds = max(0, int(seconds))
    if seconds < 60:
        return f"{seconds}s"
    minutes, seconds = divmod(seconds, 60)
    if minutes < 60:
        return f"{minutes}m{seconds:02d}s"
    hours, minutes = divmod(minutes, 60)
    return f"{hours}h{minutes:02d}m{seconds:02d}s"


# --------------------------------------------------------------------------- #
# Plan
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class PlannedModel:
    """One model the selected runs need and that is not installed."""

    name: str
    """Internal model name, used for ``POST /models/download``."""
    display_name: str
    """Name used by pipelines and in skip reasons."""
    source: str
    gated: str
    """``auto``/``manual`` for gated Hugging Face models, else ``""``."""
    link: str
    pipelines: tuple[str, ...]
    """Pipeline ids in this run that use the model."""
    runs: int
    """Number of matrix rows (pipeline x variant x streams) that need it."""
    already_installing: bool = False

    @property
    def is_gated(self) -> bool:
        return self.gated in _GATED_VALUES


@dataclass(frozen=True)
class InstallPlan:
    models: tuple[PlannedModel, ...] = ()

    @property
    def to_download(self) -> list[PlannedModel]:
        return [m for m in self.models if not m.already_installing]

    @property
    def already_installing(self) -> list[PlannedModel]:
        return [m for m in self.models if m.already_installing]


def _gated_value(value: Any) -> str:
    if value is True:
        return "auto"
    text = str(value or "").strip().lower()
    return text if text in _GATED_VALUES else ""


def build_plan(models: Iterable[Mapping[str, Any]], matrix: Matrix) -> InstallPlan:
    """Pick the models from ``GET /models`` that the matrix needs.

    A model is planned when it is not installed and at least one pipeline of
    ``matrix.included`` uses it (``used_by_pipelines``), so ``--pipelines``,
    ``--variants`` and the host's device families limit the plan. Models
    that are already ``installing`` are planned as "wait only".
    """
    runs_per_pipeline: dict[str, int] = {}
    streams = len(matrix.stream_counts) or 1
    for case in matrix.included:
        runs_per_pipeline[case.pipeline_id] = (
            runs_per_pipeline.get(case.pipeline_id, 0) + streams
        )

    planned: list[PlannedModel] = []
    seen: set[str] = set()
    for model in models:
        if not isinstance(model, Mapping):
            continue
        name = model.get("name")
        status = str(model.get("install_status") or "").lower()
        if not isinstance(name, str) or not name or status == _INSTALLED:
            continue
        used_by = model.get("used_by_pipelines") or []
        if not isinstance(used_by, list):
            continue
        pipelines = tuple(
            sorted({p for p in used_by if isinstance(p, str)} & set(runs_per_pipeline))
        )
        if not pipelines or name in seen:
            continue
        seen.add(name)
        planned.append(
            PlannedModel(
                name=name,
                display_name=clean_text(model.get("display_name")) or clean_text(name),
                source=clean_text(model.get("source"), max_length=40),
                gated=_gated_value(model.get("gated")),
                link=_clean_link(model.get("link")),
                pipelines=pipelines,
                runs=sum(runs_per_pipeline[p] for p in pipelines),
                already_installing=status == _INSTALLING,
            )
        )
    planned.sort(key=lambda m: (m.display_name.lower(), m.name))
    return InstallPlan(tuple(planned))


def format_plan(plan: InstallPlan) -> str:
    """Render the plan: table, notes for gated models and the license footer."""
    if not plan.models:
        return "Every model the selected runs need is installed."
    rows = [
        (
            m.display_name,
            m.source or "?",
            m.gated or "no",
            m.link or "-",
            ", ".join(m.pipelines),
            m.runs,
            "wait (already installing)" if m.already_installing else "install",
        )
        for m in plan.models
    ]
    lines = [
        f"{len(plan.models)} model(s) needed by the selected runs are not installed:",
        format_table(
            (
                "model",
                "source",
                "gated",
                "link",
                "pipelines in this run",
                "runs needing it",
                "action",
            ),
            rows,
        ),
    ]
    gated = [m for m in plan.models if m.is_gated]
    if gated:
        lines.append("")
        lines.append("Gated models need access granted on Hugging Face:")
        lines.extend(
            f"  - {m.display_name}: accept the license at {m.link or 'its model page'}"
            for m in gated
        )
        lines.append(
            "  Then set HF_TOKEN in the shell or .env used to start ViPPET and "
            "restart model-download (make run, or docker compose up -d "
            "model-download). This tool cannot check that HF_TOKEN is set."
        )
    lines.append("")
    lines.append(
        "By installing you accept the license terms of each model's upstream source."
    )
    return "\n".join(lines)


def prompt_text(plan: InstallPlan) -> str:
    download = len(plan.to_download)
    waiting = len(plan.already_installing)
    if download and waiting:
        return (
            f"Install {download} model(s) and wait for {waiting} already "
            "installing now? [y/N] "
        )
    if download:
        return f"Install {download} model(s) now? [y/N] "
    return f"Wait for {waiting} model(s) that are already installing? [y/N] "


def describe_mode_effect(mode: str, stdin_is_tty: bool) -> str:
    """What a benchmark run would do with the plan (for ``--dry-run``)."""
    if mode == "yes":
        return (
            "With --install-missing-models=yes a run installs these models "
            "without asking."
        )
    if mode == "no":
        return (
            "With --install-missing-models=no a run does not install them; "
            "the runs that need them are skipped."
        )
    if stdin_is_tty:
        return (
            "With --install-missing-models=ask (default) a run asks before "
            "installing these models."
        )
    return (
        "With --install-missing-models=ask (default) a run does not install "
        "them here, because stdin is not a terminal; pass "
        "--install-missing-models=yes to install them without asking."
    )


# --------------------------------------------------------------------------- #
# Outcome
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class ModelOutcome:
    name: str
    display_name: str
    outcome: Outcome
    reason: str = ""

    def to_dict(self) -> dict[str, str]:
        return {
            "name": self.name,
            "display_name": self.display_name,
            "outcome": self.outcome.value,
            "reason": self.reason,
        }


def declined(plan: InstallPlan) -> list[ModelOutcome]:
    return [
        ModelOutcome(m.name, m.display_name, Outcome.DECLINED, "declined at the prompt")
        for m in plan.models
    ]


def encode_outcomes(outcomes: Sequence[ModelOutcome]) -> str:
    return json.dumps([o.to_dict() for o in outcomes])


def decode_outcomes(raw: str | None) -> list[ModelOutcome] | None:
    """Parse :data:`ENV_MODEL_INSTALL`; ``None`` when it is unset or empty.

    The value is checked strictly (size, shape, outcome names) and its text
    is cleaned again, because the environment is not trusted either.
    """
    if not raw:
        return None
    problem = ModelInstallError(
        f"env {ENV_MODEL_INSTALL} is not a valid model install outcome. To fix: "
        "unset it; perf_helpers.cli sets it for its own pytest run."
    )
    if len(raw) > _MAX_OUTCOME_CHARS:
        raise problem
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise problem from exc
    if not isinstance(data, list) or len(data) > _MAX_OUTCOME_MODELS:
        raise problem
    outcomes: list[ModelOutcome] = []
    valid = {o.value for o in Outcome}
    for item in data:
        if not (
            isinstance(item, dict)
            and set(item) == {"name", "display_name", "outcome", "reason"}
            and all(isinstance(v, str) for v in item.values())
            and item["outcome"] in valid
            and item["name"]
        ):
            raise problem
        outcomes.append(
            ModelOutcome(
                name=clean_text(item["name"]),
                display_name=clean_text(item["display_name"]),
                outcome=Outcome(item["outcome"]),
                reason=clean_text(item["reason"], max_length=500),
            )
        )
    return outcomes


def install_problem(
    missing_display_names: Iterable[str], outcomes: Iterable[ModelOutcome]
) -> tuple[str, str] | None:
    """Decide what happens to a run whose models are missing.

    Returns ``("error", reason)`` when one of its models failed to install or
    timed out, ``("skip", reason)`` when waiting for one was interrupted, and
    ``None`` otherwise (declined, or no install attempted: today's skip).
    """
    by_display = {o.display_name: o for o in outcomes}
    relevant = [
        by_display[name] for name in sorted(missing_display_names) if name in by_display
    ]
    failed = [o for o in relevant if o.outcome in ERROR_OUTCOMES]
    if failed:
        return (
            "error",
            "; ".join(
                f"model {o.display_name!r} failed to install: {o.reason}"
                for o in failed
            ),
        )
    interrupted = [o for o in relevant if o.outcome == Outcome.INTERRUPTED]
    if interrupted:
        names = ", ".join(repr(o.display_name) for o in interrupted)
        return (
            "skip",
            f"model(s) {names} were still installing when waiting was "
            "interrupted (Ctrl-C); the download continues on the server. "
            "Rerun when it has finished.",
        )
    return None


def format_outcomes(outcomes: Sequence[ModelOutcome]) -> str:
    if not outcomes:
        return "No model installation was needed."
    counts = {o: sum(1 for x in outcomes if x.outcome == o) for o in Outcome}
    summary = ", ".join(f"{n} {o.value}" for o, n in counts.items() if n)
    table = format_table(
        ("model", "outcome", "reason"),
        [(o.display_name, o.outcome.value, o.reason or "-") for o in outcomes],
    )
    return f"Model installation: {summary}\n{table}"


def describe_skipped_for_missing_models(count: int) -> str:
    return (
        f"{count} run(s) were skipped because the models they need are not "
        f"installed. {INSTALL_HINT}. Only the CLI installs models; a direct "
        "pytest run never does."
    )


# --------------------------------------------------------------------------- #
# HTTP
# --------------------------------------------------------------------------- #


def fetch_models(
    client: httpx.Client, base_url: str, request_timeout: float
) -> list[dict[str, Any]]:
    """Return ``GET /models``. Raises ``httpx.HTTPError`` or ``ValueError``."""
    response = client.get(f"{base_url.rstrip('/')}/models", timeout=request_timeout)
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, list):
        raise ValueError(f"GET /models: expected a list, got {type(payload).__name__}")
    return [m for m in payload if isinstance(m, dict)]


def _response_message(response: httpx.Response) -> str:
    try:
        body = response.json()
    except ValueError:
        return clean_text(response.text) or "no message"
    if isinstance(body, dict):
        for key in ("message", "detail"):
            if body.get(key):
                return clean_text(body[key])
    return clean_text(body) or "no message"


@dataclass
class _Job:
    model: PlannedModel
    job_id: str | None = None
    state: str = ""
    progress: str = ""


@dataclass
class ModelInstaller:
    """Start the downloads of a plan and wait for them.

    ``install`` never raises for server or network problems: they become
    ``failed`` outcomes. The first Ctrl-C stops waiting; models without a
    result then get the outcome ``interrupted``.
    """

    client: httpx.Client
    base_url: str
    poll_interval: float
    timeout_seconds: float
    request_timeout: float
    report: Callable[[str], None] = print
    monotonic: Callable[[], float] = time.monotonic
    sleep: Callable[[float], None] = time.sleep
    summary_interval: float = SUMMARY_INTERVAL_SECONDS
    _start: float = field(default=0.0, init=False)

    @property
    def _api(self) -> str:
        return self.base_url.rstrip("/")

    def _elapsed(self) -> str:
        return format_duration(self.monotonic() - self._start)

    def _say(self, text: str) -> None:
        self.report(f"{_LOG_PREFIX} {text}")

    def install(self, plan: InstallPlan) -> list[ModelOutcome]:
        self._start = self.monotonic()
        outcomes: dict[str, ModelOutcome] = {}
        jobs: dict[str, _Job] = {}
        try:
            self._submit(plan, jobs, outcomes)
            self._attach_running_jobs(jobs, outcomes)
            self._wait(jobs, outcomes)
        except KeyboardInterrupt:
            for model in plan.models:
                if model.name not in outcomes:
                    outcomes[model.name] = ModelOutcome(
                        model.name,
                        model.display_name,
                        Outcome.INTERRUPTED,
                        "waiting was interrupted (Ctrl-C); the download may "
                        "still be running on the server",
                    )
            self._say(
                "Interrupted: stopped waiting. Downloads that already started "
                "continue on the server. Continuing with the models installed "
                "so far; press Ctrl-C again to abort the benchmark."
            )
        return [outcomes[m.name] for m in plan.models]

    # -- steps ---------------------------------------------------------------

    def _fail(
        self, outcomes: dict[str, ModelOutcome], model: PlannedModel, reason: str
    ) -> None:
        outcomes[model.name] = ModelOutcome(
            model.name, model.display_name, Outcome.FAILED, reason
        )
        self._say(f"{model.display_name}: FAILED: {reason}")

    def _submit(
        self,
        plan: InstallPlan,
        jobs: dict[str, _Job],
        outcomes: dict[str, ModelOutcome],
    ) -> None:
        for model in plan.already_installing:
            jobs[model.name] = _Job(model)
        to_download = plan.to_download
        if not to_download:
            return
        names = [m.name for m in to_download]
        try:
            response = self.client.post(
                f"{self._api}/models/download",
                json={"names": names},
                timeout=self.request_timeout,
            )
            body = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            reason = (
                f"POST /models/download failed: {type(exc).__name__}: {clean_text(exc)}"
            )
            for model in to_download:
                self._fail(outcomes, model, reason)
            return

        items = body.get("jobs") if isinstance(body, dict) else None
        if not isinstance(items, dict):
            reason = (
                f"ViPPET rejected the download request (HTTP "
                f"{response.status_code}): {_response_message(response)}"
            )
            for model in to_download:
                self._fail(outcomes, model, reason)
            return

        for model in to_download:
            item = items.get(model.name)
            if not isinstance(item, dict):
                self._fail(
                    outcomes,
                    model,
                    f"ViPPET returned no result for this model (HTTP "
                    f"{response.status_code})",
                )
                continue
            code = item.get("status_code")
            job_id = item.get("job_id")
            message = clean_text(item.get("message")) or "no message"
            if code == 202 and isinstance(job_id, str) and _JOB_ID_RE.match(job_id):
                jobs[model.name] = _Job(model, job_id)
                self._say(f"{model.display_name}: download started")
            elif code == 409:
                # Already installed or already downloading: resolved below.
                jobs[model.name] = _Job(model)
            else:
                self._fail(
                    outcomes,
                    model,
                    f"ViPPET rejected the download (HTTP {code}): {message}",
                )

    def _get_json(self, path: str) -> Any:
        response = self.client.get(f"{self._api}{path}", timeout=self.request_timeout)
        response.raise_for_status()
        return response.json()

    def _attach_running_jobs(
        self, jobs: dict[str, _Job], outcomes: dict[str, ModelOutcome]
    ) -> None:
        """Find the running job of every model that has no job id yet."""
        pending = [job for job in jobs.values() if job.job_id is None]
        if not pending:
            return
        try:
            listed = self._get_json("/jobs/models/status")
            if not isinstance(listed, list):
                raise ValueError("expected a list")
        except (httpx.HTTPError, ValueError) as exc:
            for job in pending:
                del jobs[job.model.name]
                self._fail(
                    outcomes,
                    job.model,
                    "cannot look up its running download (GET /jobs/models/status: "
                    f"{type(exc).__name__}: {clean_text(exc)})",
                )
            return

        running: dict[str, dict[str, Any]] = {}
        for entry in listed:
            if not (
                isinstance(entry, dict)
                and entry.get("state") == "RUNNING"
                and isinstance(entry.get("model_name"), str)
                and isinstance(entry.get("id"), str)
                and _JOB_ID_RE.match(entry["id"])
            ):
                continue
            current = running.get(entry["model_name"])
            start = entry.get("start_time")
            start = start if isinstance(start, (int, float)) else 0
            if current is None or start > current["_start"]:
                running[entry["model_name"]] = {"id": entry["id"], "_start": start}

        installed: set[str] | None = None
        for job in pending:
            found = running.get(job.model.name)
            if found is not None:
                job.job_id = found["id"]
                self._say(
                    f"{job.model.display_name}: already downloading, waiting for it"
                )
                continue
            if installed is None:
                installed = self._installed_names()
            del jobs[job.model.name]
            if job.model.name in installed:
                outcomes[job.model.name] = ModelOutcome(
                    job.model.name,
                    job.model.display_name,
                    Outcome.INSTALLED,
                    "already installed",
                )
                self._say(f"{job.model.display_name}: already installed")
            else:
                self._fail(
                    outcomes,
                    job.model,
                    "ViPPET reported it as already installed or downloading, but "
                    "it is not installed and no running download was found",
                )

    def _installed_names(self) -> set[str]:
        try:
            models = fetch_models(self.client, self.base_url, self.request_timeout)
        except (httpx.HTTPError, ValueError):
            return set()
        return {
            m["name"]
            for m in models
            if isinstance(m.get("name"), str)
            and str(m.get("install_status") or "").lower() == _INSTALLED
        }

    def _wait(self, jobs: dict[str, _Job], outcomes: dict[str, ModelOutcome]) -> None:
        if not jobs:
            return
        deadline = self._start + self.timeout_seconds
        last_summary = self.monotonic()
        while jobs:
            for name, job in list(jobs.items()):
                outcome = self._poll(job)
                if outcome is not None:
                    outcomes[name] = outcome
                    del jobs[name]
            if not jobs:
                return
            now = self.monotonic()
            if now >= deadline:
                reason = (
                    f"still installing after {format_duration(self.timeout_seconds)} "
                    "(--model-install-timeout); the download continues on the server"
                )
                for name, job in jobs.items():
                    outcomes[name] = ModelOutcome(
                        name, job.model.display_name, Outcome.TIMED_OUT, reason
                    )
                    self._say(f"{job.model.display_name}: TIMED OUT: {reason}")
                jobs.clear()
                return
            if now - last_summary >= self.summary_interval:
                last_summary = now
                self._say(self._summary(jobs, outcomes))
            self.sleep(min(self.poll_interval, deadline - now))

    def _summary(self, jobs: dict[str, _Job], outcomes: dict[str, ModelOutcome]) -> str:
        installed = sum(1 for o in outcomes.values() if o.outcome == Outcome.INSTALLED)
        failed = sum(1 for o in outcomes.values() if o.outcome != Outcome.INSTALLED)
        return (
            f"{installed} installed, {failed} failed, {len(jobs)} still installing "
            f"(elapsed {self._elapsed()} of {format_duration(self.timeout_seconds)})"
        )

    def _note(self, job: _Job, state: str, progress: str) -> None:
        """Print a line only when the model's state or progress changed."""
        if (state, progress) == (job.state, job.progress):
            return
        job.state, job.progress = state, progress
        detail = f" - {progress}" if progress else ""
        self._say(f"{job.model.display_name}: {state}{detail} ({self._elapsed()})")

    def _poll(self, job: _Job) -> ModelOutcome | None:
        model = job.model
        try:
            response = self.client.get(
                f"{self._api}/jobs/models/{job.job_id}/status",
                timeout=self.request_timeout,
            )
        except httpx.HTTPError as exc:
            # Transient: keep waiting until the overall timeout.
            self._note(job, "POLL FAILED", f"{type(exc).__name__}: {clean_text(exc)}")
            return None
        if response.status_code == 404:
            reason = "the download job disappeared from ViPPET (was ViPPET restarted?)"
            self._say(f"{model.display_name}: FAILED: {reason}")
            return ModelOutcome(model.name, model.display_name, Outcome.FAILED, reason)
        try:
            response.raise_for_status()
            payload = response.json()
            if not isinstance(payload, dict):
                raise ValueError("expected an object")
        except (httpx.HTTPError, ValueError) as exc:
            self._note(job, "POLL FAILED", f"{type(exc).__name__}: {clean_text(exc)}")
            return None

        state = clean_text(payload.get("state"), max_length=40)
        if state == "COMPLETED":
            self._say(f"{model.display_name}: installed ({self._elapsed()})")
            return ModelOutcome(model.name, model.display_name, Outcome.INSTALLED)
        if state == "FAILED":
            # Only the last entry: earlier RUNNING details hold internal
            # request URLs and bodies.
            details = payload.get("details")
            last = details[-1] if isinstance(details, list) and details else ""
            reason = clean_text(last, max_length=500) or "download failed (no details)"
            self._say(f"{model.display_name}: FAILED: {reason}")
            return ModelOutcome(model.name, model.display_name, Outcome.FAILED, reason)
        self._note(job, state or "UNKNOWN", clean_text(payload.get("progress_message")))
        return None


# --------------------------------------------------------------------------- #
# Prompt and orchestration
# --------------------------------------------------------------------------- #


def confirm(text: str, input_fn: Callable[[str], str] = input) -> bool:
    """Ask a yes/no question; anything but y/yes (or EOF) means no."""
    try:
        answer = input_fn(text)
    except EOFError:
        return False
    return answer.strip().lower() in {"y", "yes"}


def offer_and_install(
    plan: InstallPlan,
    *,
    ask: bool,
    install: Callable[[InstallPlan], list[ModelOutcome]],
    input_fn: Callable[[str], str] = input,
    report: Callable[[str], None] = print,
) -> list[ModelOutcome]:
    """Print the plan, ask if needed, install, and return the outcomes."""
    report(format_plan(plan))
    if not plan.models:
        return []
    if ask:
        if not confirm(prompt_text(plan), input_fn):
            report(
                "Not installing. The runs that need these models are skipped. "
                f"{INSTALL_HINT}."
            )
            return declined(plan)
    else:
        report("Installing without asking (--install-missing-models=yes).")
    outcomes = install(plan)
    report(format_outcomes(outcomes))
    return outcomes

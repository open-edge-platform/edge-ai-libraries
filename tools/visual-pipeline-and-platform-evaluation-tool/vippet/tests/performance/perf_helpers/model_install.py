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
The parts shared with :mod:`perf_helpers.video_download` live in
:mod:`perf_helpers.asset_download`.
"""

import json
import re
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, ClassVar

import httpx

from .asset_download import (
    AssetWaiter,
    WaitState,
    response_message,
    SETUP_ERROR_MARK,
    AssetProblem,
    DownloadAction,
    OutcomeEnvError,
    clean_link,
    clean_text,
    confirm,
    decode_outcome_env,
    download_action,
    format_duration,
)
from .matrix import Matrix, format_table
from .settings import InstallMode

# Set by the CLI for its pytest subprocess: JSON list of model outcomes.
ENV_MODEL_INSTALL: str = "PERF_MODEL_INSTALL_OUTCOME"
_OUTCOME_KEYS = ("name", "display_name", "outcome", "reason")

# Kept for callers of this module; the marker is shared with video downloads.
MODEL_INSTALL_ERROR_MARK: str = SETUP_ERROR_MARK
ModelInstallError = OutcomeEnvError
"""Raised when the outcome handed over by the CLI is not valid."""
InstallProblem = AssetProblem
InstallAction = DownloadAction
install_action = download_action

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
SECTION_HEADER: str = f"{'-' * 30} Model installation {'-' * 30}"
NOTHING_TO_INSTALL: str = (
    "Model installation: every model the selected runs need is installed."
)


class Outcome(StrEnum):
    INSTALLED = "installed"
    FAILED = "failed"
    TIMED_OUT = "timed_out"
    DECLINED = "declined"
    INTERRUPTED = "interrupted"


# Runs needing a model with one of these outcomes are reported as ERROR.
ERROR_OUTCOMES: frozenset[Outcome] = frozenset({Outcome.FAILED, Outcome.TIMED_OUT})


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
    text = str(value or "").strip().lower()
    return text if text in _GATED_VALUES else ""


def build_plan(models: Iterable[Mapping[str, Any]], matrix: Matrix) -> InstallPlan:
    """Pick the models from ``GET /models`` that the matrix needs.

    A model is planned when it is not installed and at least one pipeline of
    ``matrix.included`` uses it (``used_by_pipelines``), so ``--pipelines``,
    ``--variants`` and the host's device families limit the plan. Models
    that are already ``installing`` are planned as "wait only".

    Args:
        models: The ``GET /models`` payload (untrusted; text is cleaned).
        matrix: The benchmark matrix; only its included runs count.

    Returns:
        The plan, sorted by display name.
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
                link=clean_link(model.get("link")),
                pipelines=pipelines,
                runs=sum(runs_per_pipeline[p] for p in pipelines),
                already_installing=status == _INSTALLING,
            )
        )
    planned.sort(key=lambda m: (m.display_name.lower(), m.name))
    return InstallPlan(tuple(planned))


def format_plan(plan: InstallPlan) -> str:
    """Render the plan: table, notes for gated models and the license footer.

    Args:
        plan: The install plan.

    Returns:
        The rendered plan, or one sentence when the plan is empty.
    """
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
    """Return the yes/no question for a non-empty *plan*.

    Args:
        plan: The install plan.

    Returns:
        The question, ending in ``[y/N] ``.
    """
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


def describe_mode_effect(mode: InstallMode, stdin_is_tty: bool) -> str:
    """Describe what a benchmark run would do with the plan (for ``--dry-run``).

    Args:
        mode: The ``benchmark.models.install`` setting.
        stdin_is_tty: Whether stdin is a terminal.

    Returns:
        One sentence naming the setting and its effect on this terminal.
    """
    action = install_action(mode, stdin_is_tty)
    if action == "install":
        return (
            "With --install-missing-models=yes a run installs these models "
            "without asking."
        )
    if action == "prompt":
        return (
            "With --install-missing-models=ask (default) a run asks before "
            "installing these models."
        )
    if mode == "no":
        return (
            "With --install-missing-models=no a run does not install them; "
            "the runs that need them are skipped."
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
    """Return a ``declined`` outcome for every model of *plan*.

    Args:
        plan: The plan the user declined.

    Returns:
        One outcome per model, in plan order.
    """
    return [
        ModelOutcome(m.name, m.display_name, Outcome.DECLINED, "declined at the prompt")
        for m in plan.models
    ]


def encode_outcomes(outcomes: Sequence[ModelOutcome]) -> str:
    """Encode *outcomes* for :data:`ENV_MODEL_INSTALL`.

    Args:
        outcomes: The install outcomes.

    Returns:
        A JSON list that :func:`decode_outcomes` reads back.
    """
    return json.dumps([o.to_dict() for o in outcomes])


def decode_outcomes(raw: str | None) -> list[ModelOutcome] | None:
    """Parse the value of :data:`ENV_MODEL_INSTALL`.

    The value is checked strictly (size, shape, outcome names) and its text
    is cleaned again, because the environment is not trusted either.

    Args:
        raw: The env value, or ``None`` when it is unset.

    Returns:
        The outcomes, or ``None`` when the value is unset or empty.

    Raises:
        ModelInstallError: The value is not a valid outcome list.
    """
    items = decode_outcome_env(
        raw,
        env_name=ENV_MODEL_INSTALL,
        keys=_OUTCOME_KEYS,
        outcomes={o.value for o in Outcome},
    )
    if items is None:
        return None
    return [
        ModelOutcome(
            name=clean_text(item["name"]),
            display_name=clean_text(item["display_name"]),
            outcome=Outcome(item["outcome"]),
            reason=clean_text(item["reason"], max_length=500),
        )
        for item in items
    ]


def install_problem(
    missing_display_names: Iterable[str], outcomes: Iterable[ModelOutcome]
) -> InstallProblem | None:
    """Decide what happens to a run whose models are missing.

    Missing names come raw from ``GET /models``; the outcome names were
    cleaned by the CLI. Both sides are cleaned the same way before matching.

    Args:
        missing_display_names: Display names of the run's missing models.
        outcomes: Install outcomes handed over by the CLI.

    Returns:
        An ``error`` problem when one of the run's models failed to install or
        timed out, a ``skip`` problem when waiting for one was interrupted,
        and ``None`` otherwise (declined, or no install attempted: the
        default missing-models skip applies).
    """
    by_display = {o.display_name: o for o in outcomes}
    cleaned = sorted({clean_text(name) for name in missing_display_names})
    relevant = [by_display[name] for name in cleaned if name in by_display]
    failed = [o for o in relevant if o.outcome in ERROR_OUTCOMES]
    if failed:
        return InstallProblem(
            "error",
            "; ".join(
                f"model {o.display_name!r} failed to install: {o.reason}"
                for o in failed
            ),
        )
    interrupted = [o for o in relevant if o.outcome == Outcome.INTERRUPTED]
    if interrupted:
        names = ", ".join(repr(o.display_name) for o in interrupted)
        return InstallProblem(
            "skip",
            f"model(s) {names} were still installing when waiting was "
            "interrupted (Ctrl-C); the download continues on the server. "
            "Rerun when it has finished.",
        )
    return None


def format_outcomes(outcomes: Sequence[ModelOutcome]) -> str:
    """Render the install outcomes: a count per outcome and a table.

    Args:
        outcomes: The install outcomes.

    Returns:
        The rendered outcomes.
    """
    if not outcomes:
        return "No model installation was needed."
    counts = {o: sum(1 for x in outcomes if x.outcome == o) for o in Outcome}
    summary = ", ".join(f"{n} {o.value}" for o, n in counts.items() if n)
    table = format_table(
        ("model", "outcome", "reason"),
        [(o.display_name, o.outcome.value, o.reason or "-") for o in outcomes],
    )
    return f"Model installation: {summary}\n{table}"


def describe_skipped_for_missing_models(
    count: int, outcomes: Sequence[ModelOutcome] | None = None
) -> str:
    """Explain runs that were skipped because their models are not installed.

    Args:
        count: Number of runs skipped for missing models.
        outcomes: Install outcomes handed over by the CLI, or ``None`` when
            no install step ran.

    Returns:
        A hint that tells the user how to install the models. When the user
        declined at the prompt it says so instead of the generic hint.
    """
    if outcomes and any(o.outcome == Outcome.DECLINED for o in outcomes):
        return (
            f"{count} run(s) were skipped because you declined installing their "
            "models. Rerun with --install-missing-models=yes, or answer y."
        )
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
    """Read the model list.

    Args:
        client: HTTP client, owned by the caller.
        base_url: ViPPET API base URL.
        request_timeout: Timeout of the request, in seconds.

    Returns:
        The objects of ``GET /models``; other entries are dropped.

    Raises:
        httpx.HTTPError: The request failed or returned an error status.
        ValueError: The response is not a JSON list.
    """
    response = client.get(f"{base_url.rstrip('/')}/models", timeout=request_timeout)
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, list):
        raise ValueError(f"GET /models: expected a list, got {type(payload).__name__}")
    return [m for m in payload if isinstance(m, dict)]


@dataclass
class _Job:
    model: PlannedModel
    job_id: str | None = None
    state: str = ""
    progress: str = ""


@dataclass
class _InstallState(WaitState):
    """Progress of one :meth:`ModelInstaller.install` call."""

    jobs: dict[str, _Job] = field(default_factory=dict)
    """Models still being waited for, by model name."""
    outcomes: dict[str, ModelOutcome] = field(default_factory=dict)
    """Models with a final outcome, by model name."""

    def resolve(self, model: PlannedModel, outcome: Outcome, reason: str = "") -> None:
        """Record the final outcome of *model* and stop waiting for it."""
        self.jobs.pop(model.name, None)
        self.outcomes[model.name] = ModelOutcome(
            model.name, model.display_name, outcome, reason
        )

    def count(self, outcome: Outcome) -> int:
        return sum(1 for o in self.outcomes.values() if o.outcome == outcome)


@dataclass
class ModelInstaller(AssetWaiter):
    """Start the downloads of a plan and wait for them.

    ``install`` never raises for server or network problems: they become
    ``failed`` outcomes. The first Ctrl-C stops waiting; models without a
    result then get the outcome ``interrupted``.
    """

    log_prefix: ClassVar[str] = _LOG_PREFIX

    def _time_out(
        self, state: _InstallState, jobs: Iterable[_Job], reason: str
    ) -> None:
        for job in list(jobs):
            state.resolve(job.model, Outcome.TIMED_OUT, reason)
            self._say(f"{job.model.display_name}: TIMED OUT: {reason}")

    def install(self, plan: InstallPlan) -> list[ModelOutcome]:
        """Install the models of *plan* and wait until each has an outcome.

        Args:
            plan: The models to download, and those already installing that
                only need to be waited for.

        Returns:
            One outcome per model of the plan, in plan order.
        """
        state = _InstallState(start=self.monotonic())
        try:
            self._submit(plan, state)
            self._attach_running_jobs(state)
            self._wait(state)
        except KeyboardInterrupt:
            for model in plan.models:
                if model.name not in state.outcomes:
                    state.resolve(
                        model,
                        Outcome.INTERRUPTED,
                        "waiting was interrupted (Ctrl-C); the download may "
                        "still be running on the server",
                    )
            self._say(
                "Interrupted: stopped waiting. Downloads that already started "
                "continue on the server. Continuing with the models installed "
                "so far; press Ctrl-C again to abort the benchmark."
            )
        return [state.outcomes[m.name] for m in plan.models]

    # -- steps ---------------------------------------------------------------

    def _fail(self, state: _InstallState, model: PlannedModel, reason: str) -> None:
        state.resolve(model, Outcome.FAILED, reason)
        self._say(f"{model.display_name}: FAILED: {reason}")

    def _submit(self, plan: InstallPlan, state: _InstallState) -> None:
        for model in plan.already_installing:
            state.jobs[model.name] = _Job(model)
        to_download = plan.to_download
        if not to_download:
            return
        names = [m.name for m in to_download]
        try:
            response = self.client.post(
                f"{self._api}/models/download",
                json={"names": names},
                timeout=self._request_timeout(state),
            )
            body = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            reason = (
                f"POST /models/download failed: {type(exc).__name__}: {clean_text(exc)}"
            )
            if isinstance(exc, httpx.TimeoutException):
                reason += "; ViPPET may have started the download anyway"
            for model in to_download:
                self._fail(state, model, reason)
            return

        items = body.get("jobs") if isinstance(body, dict) else None
        if not isinstance(items, dict):
            reason = (
                f"ViPPET rejected the download request (HTTP "
                f"{response.status_code}): {response_message(response)}"
            )
            for model in to_download:
                self._fail(state, model, reason)
            return

        for model in to_download:
            item = items.get(model.name)
            if not isinstance(item, dict):
                self._fail(
                    state,
                    model,
                    f"ViPPET returned no result for this model (HTTP "
                    f"{response.status_code})",
                )
                continue
            code = item.get("status_code")
            job_id = item.get("job_id")
            message = clean_text(item.get("message")) or "no message"
            if code == 202 and isinstance(job_id, str) and _JOB_ID_RE.match(job_id):
                state.jobs[model.name] = _Job(model, job_id)
                self._say(f"{model.display_name}: download started")
            elif code == 409:
                # Already installed or already downloading: resolved below.
                state.jobs[model.name] = _Job(model)
            else:
                self._fail(
                    state,
                    model,
                    f"ViPPET rejected the download (HTTP {code}): {message}",
                )

    def _running_jobs(self, timeout: float) -> dict[str, str]:
        """Return the newest RUNNING job id per model name.

        Raises ``httpx.HTTPError`` or ``ValueError``.
        """
        response = self.client.get(f"{self._api}/jobs/models/status", timeout=timeout)
        response.raise_for_status()
        listed = response.json()
        if not isinstance(listed, list):
            raise ValueError("expected a list")
        newest: dict[str, tuple[float, str]] = {}
        for entry in listed:
            if not (
                isinstance(entry, dict)
                and entry.get("state") == "RUNNING"
                and isinstance(entry.get("model_name"), str)
                and isinstance(entry.get("id"), str)
                and _JOB_ID_RE.match(entry["id"])
            ):
                continue
            start = entry.get("start_time")
            start = start if isinstance(start, (int, float)) else 0
            current = newest.get(entry["model_name"])
            if current is None or start > current[0]:
                newest[entry["model_name"]] = (start, entry["id"])
        return {name: job_id for name, (_, job_id) in newest.items()}

    def _attach_running_jobs(self, state: _InstallState) -> None:
        """Find the running job of every model that has no job id yet."""
        pending = [job for job in state.jobs.values() if job.job_id is None]
        if not pending:
            return
        # A 409 means "installed or downloading"; which one is not known yet.
        unchecked = (
            f"the install timeout ({format_duration(self.timeout_seconds)}, "
            "--model-install-timeout) ran out before ViPPET could be asked "
            "whether it is installed or still downloading"
        )
        if self._remaining(state) <= 0:
            self._time_out(state, pending, unchecked)
            return
        try:
            running = self._running_jobs(self._request_timeout(state))
        except (httpx.HTTPError, ValueError) as exc:
            for job in pending:
                self._fail(
                    state,
                    job.model,
                    "cannot look up its running download (GET /jobs/models/status: "
                    f"{type(exc).__name__}: {clean_text(exc)})",
                )
            return

        unmatched: list[_Job] = []
        for job in pending:
            job_id = running.get(job.model.name)
            if job_id is None:
                unmatched.append(job)
                continue
            job.job_id = job_id
            self._say(f"{job.model.display_name}: already downloading, waiting for it")
        if not unmatched:
            return
        if self._remaining(state) <= 0:
            self._time_out(state, unmatched, unchecked)
            return

        lookup_error = ""
        try:
            installed = self._installed_names(self._request_timeout(state))
        except (httpx.HTTPError, ValueError) as exc:
            installed = set()
            lookup_error = f"{type(exc).__name__}: {clean_text(exc)}"
        for job in unmatched:
            if lookup_error:
                self._fail(
                    state,
                    job.model,
                    "ViPPET reported it as already installed or downloading, but "
                    "it has no running download, and this tool cannot check "
                    f"whether it is installed (GET /models: {lookup_error})",
                )
            elif job.model.name in installed:
                state.resolve(job.model, Outcome.INSTALLED, "already installed")
                self._say(f"{job.model.display_name}: already installed")
            else:
                self._fail(
                    state,
                    job.model,
                    "ViPPET reported it as already installed or downloading, but "
                    "it is not installed and no running download was found",
                )

    def _installed_names(self, timeout: float) -> set[str]:
        """Names ViPPET reports as installed. Raises on HTTP or JSON errors."""
        models = fetch_models(self.client, self.base_url, timeout)
        return {
            m["name"]
            for m in models
            if isinstance(m.get("name"), str)
            and str(m.get("install_status") or "").lower() == _INSTALLED
        }

    def _wait(self, state: _InstallState) -> None:
        def poll() -> None:
            for job in list(state.jobs.values()):
                if self._remaining(state) <= 0:
                    break
                self._poll(state, job)

        self._wait_until_done(
            state,
            pending=lambda: bool(state.jobs),
            poll=poll,
            time_out=lambda: self._time_out(
                state,
                state.jobs.values(),
                f"still installing after {format_duration(self.timeout_seconds)} "
                "(--model-install-timeout); the download continues on the server",
            ),
            summary=lambda: self._summary(state),
        )

    def _summary(self, state: _InstallState) -> str:
        installed = state.count(Outcome.INSTALLED)
        failed = len(state.outcomes) - installed
        return (
            f"{installed} installed, {failed} failed, {len(state.jobs)} still "
            f"installing (elapsed {self._elapsed(state)} of "
            f"{format_duration(self.timeout_seconds)})"
        )

    def _note(
        self, state: _InstallState, job: _Job, status: str, progress: str
    ) -> None:
        """Print a line only when the model's state or progress changed."""
        if (status, progress) == (job.state, job.progress):
            return
        job.state, job.progress = status, progress
        detail = f" - {progress}" if progress else ""
        self._say(
            f"{job.model.display_name}: {status}{detail} ({self._elapsed(state)})"
        )

    def _poll(self, state: _InstallState, job: _Job) -> None:
        """Poll *job* once; resolve its model when the job has finished."""
        model = job.model
        try:
            response = self.client.get(
                f"{self._api}/jobs/models/{job.job_id}/status",
                timeout=self._request_timeout(state),
            )
        except httpx.HTTPError as exc:
            # Transient: keep waiting until the overall timeout.
            self._note(
                state, job, "POLL FAILED", f"{type(exc).__name__}: {clean_text(exc)}"
            )
            return
        if response.status_code == 404:
            self._fail(
                state,
                model,
                "the download job disappeared from ViPPET (was ViPPET restarted?)",
            )
            return
        try:
            response.raise_for_status()
            payload = response.json()
            if not isinstance(payload, dict):
                raise ValueError("expected an object")
        except (httpx.HTTPError, ValueError) as exc:
            self._note(
                state, job, "POLL FAILED", f"{type(exc).__name__}: {clean_text(exc)}"
            )
            return

        status = clean_text(payload.get("state"), max_length=40)
        if status == "COMPLETED":
            state.resolve(model, Outcome.INSTALLED)
            self._say(f"{model.display_name}: installed ({self._elapsed(state)})")
            return
        if status == "FAILED":
            # Only the last entry: earlier RUNNING details hold internal
            # request URLs and bodies.
            details = payload.get("details")
            last = details[-1] if isinstance(details, list) and details else ""
            self._fail(
                state,
                model,
                clean_text(last, max_length=500) or "download failed (no details)",
            )
            return
        self._note(
            state,
            job,
            status or "UNKNOWN",
            clean_text(payload.get("progress_message")),
        )


# --------------------------------------------------------------------------- #
# Prompt and orchestration
# --------------------------------------------------------------------------- #


def present_plan(plan: InstallPlan, report: Callable[[str], None] = print) -> None:
    """Print the plan under the section header, or one line when it is empty."""
    if not plan.models:
        report(NOTHING_TO_INSTALL)
        return
    report(SECTION_HEADER)
    report(format_plan(plan))


def agree_to_install(
    plan: InstallPlan,
    *,
    ask: bool,
    input_fn: Callable[[str], str] = input,
    report: Callable[[str], None] = print,
) -> bool:
    """Ask whether to install a non-empty *plan* (or say it installs unasked).

    Returns:
        ``True`` to install; ``False`` when the user declined.
    """
    if not ask:
        report("Installing without asking (--install-missing-models=yes).")
        return True
    if confirm(prompt_text(plan), input_fn):
        return True
    report(
        f"Not installing. The runs that need these models are skipped. {INSTALL_HINT}."
    )
    return False


def offer_and_install(
    plan: InstallPlan,
    *,
    ask: bool,
    install: Callable[[InstallPlan], list[ModelOutcome]],
    input_fn: Callable[[str], str] = input,
    report: Callable[[str], None] = print,
) -> list[ModelOutcome]:
    """Print the plan, ask if needed, install, and return the outcomes.

    Args:
        plan: The install plan.
        ask: Prompt before installing; otherwise install without asking.
        install: Installs the plan (usually :meth:`ModelInstaller.install`).
        input_fn: Reads the answer to the prompt.
        report: Prints one line of output.

    Returns:
        One outcome per planned model; empty when nothing is missing (one
        line is printed then, with no section header).
    """
    present_plan(plan, report)
    if not plan.models:
        return []
    if not agree_to_install(plan, ask=ask, input_fn=input_fn, report=report):
        return declined(plan)
    outcomes = install(plan)
    report(format_outcomes(outcomes))
    return outcomes

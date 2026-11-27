# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Shared parts of getting the assets a benchmark needs before it runs.

The CLI downloads two kinds of assets before it starts pytest: models
(:mod:`perf_helpers.model_install`) and sample input videos
(:mod:`perf_helpers.video_download`). Both follow the same steps: plan what
the selected runs miss, ask (``ask``) or not (``yes``), start the downloads
and wait for them within a timeout, stop waiting on Ctrl-C, and hand the
per-asset outcome to pytest through an environment variable. This module
holds what the two share:

* :func:`download_action` - what a run does for an ``ask``/``yes``/``no``
  setting on this terminal, and :func:`describe_mode_effect` - the same as
  one sentence for ``--dry-run``;
* :func:`present_plan`, :func:`agree` and :func:`confirm` - the plan
  section and the yes/no prompt;
* :func:`clean_text` / :func:`clean_link` - untrusted server text made safe
  to print;
* :func:`decode_outcome_env` - strict parsing of an outcome handed to pytest;
* :class:`AssetProblem` and :data:`SETUP_ERROR_MARK` - how pytest reports a
  run whose asset failed;
* :class:`AssetWaiter` - the HTTP client, time budget, progress lines and
  poll loop that :class:`~perf_helpers.model_install.ModelInstaller` and
  :class:`~perf_helpers.video_download.VideoDownloader` share;
* :func:`run_concurrently` and :func:`interruptible_sleep` - model installs
  and video downloads wait at the same time, and one Ctrl-C stops both.
"""

import json
import re
import threading
import time
import unicodedata
from collections.abc import Callable, Collection, Sequence
from dataclasses import dataclass
from typing import Any, ClassVar, Literal, TypeVar

import httpx

from .settings import InstallMode

# pytest marker that turns a run into an ERROR (set at collection, raised by
# an autouse fixture during setup).
SETUP_ERROR_MARK: str = "perf_setup_error"

# How often a downloader prints a progress summary while it waits.
SUMMARY_INTERVAL_SECONDS: float = 60.0

_T = TypeVar("_T")


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

    Args:
        value: Untrusted value, usually text from the server; ``None`` gives
            an empty string.
        max_length: Longest result; longer text is cut and ends in ``...``.

    Returns:
        The text without terminal escape sequences and control/format
        characters, with whitespace folded to single spaces.
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


def clean_link(value: Any) -> str:
    """Return *value* as a cleaned ``http(s)`` link, or ``""`` if it is not one."""
    link = clean_text(value, max_length=500)
    return link if link.startswith(("https://", "http://")) else ""


def format_duration(seconds: float) -> str:
    """Format *seconds* compactly, e.g. ``5s``, ``1m05s`` or ``1h02m05s``.

    Args:
        seconds: Duration; fractions are dropped and negatives count as 0.

    Returns:
        The formatted duration.
    """
    seconds = max(0, int(seconds))
    if seconds < 60:
        return f"{seconds}s"
    minutes, seconds = divmod(seconds, 60)
    if minutes < 60:
        return f"{minutes}m{seconds:02d}s"
    hours, minutes = divmod(minutes, 60)
    return f"{hours}h{minutes:02d}m{seconds:02d}s"


# --------------------------------------------------------------------------- #
# Mode and prompt
# --------------------------------------------------------------------------- #

DownloadAction = Literal["prompt", "install", "skip"]


def download_action(mode: InstallMode, stdin_is_tty: bool) -> DownloadAction:
    """Decide what a benchmark run does with the assets it is missing.

    Args:
        mode: The ``ask``/``yes``/``no`` setting.
        stdin_is_tty: Whether stdin is a terminal the user can answer from.

    Returns:
        ``prompt`` (``ask`` on a terminal), ``install`` (``yes``) or ``skip``
        (``no``, or ``ask`` without a terminal, which must never block).
    """
    if mode == "yes":
        return "install"
    if mode == "ask" and stdin_is_tty:
        return "prompt"
    return "skip"


def confirm(text: str, input_fn: Callable[[str], str] = input) -> bool:
    """Ask a yes/no question.

    Args:
        text: The question.
        input_fn: Reads the answer.

    Returns:
        ``True`` for y/yes (any case); anything else, and EOF, means no.
    """
    try:
        answer = input_fn(text)
    except EOFError:
        return False
    return answer.strip().lower() in {"y", "yes"}


def describe_mode_effect(
    mode: InstallMode, stdin_is_tty: bool, *, flag: str, verb: str, noun: str
) -> str:
    """Describe what a benchmark run would do with a plan (for ``--dry-run``).

    Args:
        mode: The ``ask``/``yes``/``no`` setting.
        stdin_is_tty: Whether stdin is a terminal.
        flag: The CLI flag of the setting, e.g. ``--install-missing-models``.
        verb: What the run does, e.g. ``install`` (``installs``,
            ``installing`` are derived).
        noun: What it acts on, e.g. ``models``.

    Returns:
        One sentence naming the setting and its effect on this terminal.
    """
    action = download_action(mode, stdin_is_tty)
    if action == "install":
        return f"With {flag}=yes a run {verb}s these {noun} without asking."
    if action == "prompt":
        return f"With {flag}=ask (default) a run asks before {verb}ing these {noun}."
    if mode == "no":
        return (
            f"With {flag}=no a run does not {verb} them; the runs that need them "
            "are skipped."
        )
    return (
        f"With {flag}=ask (default) a run does not {verb} them here, because "
        f"stdin is not a terminal; pass {flag}=yes to {verb} them without asking."
    )


def present_plan(
    plan_text: str | None,
    *,
    header: str,
    nothing_missing: str,
    notes: Sequence[str] = (),
    report: Callable[[str], None] = print,
) -> None:
    """Print a plan under its section header, or one line when it is empty.

    Args:
        plan_text: The rendered plan, or ``None`` when nothing is missing.
        header: The section header printed above the plan.
        nothing_missing: The single line printed instead of an empty plan.
        notes: Lines printed after that line (only for an empty plan).
        report: Prints one line of output.
    """
    if plan_text is None:
        report(nothing_missing)
        for note in notes:
            report(note)
        return
    report(header)
    report(plan_text)


def agree(
    *,
    ask: bool,
    question: str,
    unasked: str,
    declined: str,
    input_fn: Callable[[str], str] = input,
    report: Callable[[str], None] = print,
) -> bool:
    """Ask whether to download a non-empty plan (or say it does so unasked).

    Args:
        ask: Prompt (``ask`` on a terminal); otherwise accept (``yes``).
        question: The ``[y/N]`` question.
        unasked: Printed when accepting without asking.
        declined: Printed when the user declined.
        input_fn: Reads the answer.
        report: Prints one line of output.

    Returns:
        ``True`` to download; ``False`` when the user declined.
    """
    if not ask:
        report(unasked)
        return True
    if confirm(question, input_fn):
        return True
    report(declined)
    return False


# --------------------------------------------------------------------------- #
# Outcome handed to pytest
# --------------------------------------------------------------------------- #


class OutcomeEnvError(ValueError):
    """Raised when an outcome handed over by the CLI is not valid."""


def decode_outcome_env(
    raw: str | None,
    *,
    env_name: str,
    keys: Collection[str],
    outcomes: Collection[str],
    max_chars: int = 256 * 1024,
    max_items: int = 1000,
) -> list[dict[str, str]] | None:
    """Parse a JSON outcome list the CLI handed to pytest in *env_name*.

    The value is checked strictly, because the environment is not trusted:
    its size, that it is a list of objects with exactly *keys* as string
    values, a non-empty first key, and an ``outcome`` in *outcomes*. Callers
    clean the text again before printing it.

    Args:
        raw: The env value, or ``None`` when it is unset.
        env_name: Name of the variable, for the error message.
        keys: The exact keys of every item; the first is the asset name.
        outcomes: The valid values of the ``outcome`` key.
        max_chars: Longest accepted value.
        max_items: Most accepted items.

    Returns:
        The items, or ``None`` when the value is unset or empty.

    Raises:
        OutcomeEnvError: The value is not a valid outcome list.
    """
    if not raw:
        return None
    problem = OutcomeEnvError(
        f"env {env_name} is not a valid outcome list. To fix: unset it; "
        "perf_helpers.cli sets it for its own pytest run."
    )
    if len(raw) > max_chars:
        raise problem
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise problem from exc
    if not isinstance(data, list) or len(data) > max_items:
        raise problem
    expected = set(keys)
    name_key = next(iter(keys))
    for item in data:
        if not (
            isinstance(item, dict)
            and set(item) == expected
            and all(isinstance(v, str) for v in item.values())
            and item["outcome"] in outcomes
            and item[name_key]
        ):
            raise problem
    return data


@dataclass(frozen=True)
class AssetProblem:
    """What happens to a run because of an asset's download outcome."""

    kind: Literal["error", "skip"]
    """``error``: report the run as ERROR; ``skip``: skip it."""
    reason: str


# --------------------------------------------------------------------------- #
# Waiting for several downloads at once
# --------------------------------------------------------------------------- #


def interruptible_sleep(
    stop: threading.Event, sleep: Callable[[float], None] | None = None
) -> Callable[[float], None]:
    """Return a sleep that raises ``KeyboardInterrupt`` once *stop* is set.

    Downloaders catch ``KeyboardInterrupt`` to stop waiting; a worker thread
    never gets the real one, so :func:`run_concurrently` sets *stop* and
    this sleep raises it in the worker instead.

    Args:
        stop: Set when the user pressed Ctrl-C.
        sleep: Waits; defaults to waiting on *stop*, which ends early once
            it is set. Tests inject a fake.
    """

    def wait(seconds: float) -> None:
        if stop.is_set():
            raise KeyboardInterrupt
        if sleep is None:
            stop.wait(seconds)
        else:
            sleep(seconds)
        if stop.is_set():
            raise KeyboardInterrupt

    return wait


def run_concurrently(
    tasks: Sequence[Callable[[], _T]],
    stop: threading.Event,
    join_interval: float = 0.2,
) -> list[_T]:
    """Run *tasks* at the same time and return their results in order.

    One task runs in the calling thread, so Ctrl-C reaches it directly.
    Several tasks run in daemon threads: the first Ctrl-C sets *stop*
    (their :func:`interruptible_sleep` then raises ``KeyboardInterrupt``,
    which each downloader handles), and this waits until they have
    returned. A second Ctrl-C propagates and aborts the benchmark.

    Args:
        tasks: Functions that never raise for server or network problems.
        stop: Set on the first Ctrl-C.
        join_interval: How often the calling thread checks for Ctrl-C.

    Returns:
        The result of each task, in order.

    Raises:
        KeyboardInterrupt: Ctrl-C while the tasks were stopping.
        BaseException: Re-raised from a task that failed unexpectedly.
    """
    if len(tasks) == 1:
        return [tasks[0]()]
    results: list[Any] = [None] * len(tasks)
    errors: list[BaseException | None] = [None] * len(tasks)

    def run(index: int) -> None:
        try:
            results[index] = tasks[index]()
        except BaseException as exc:  # handed to the calling thread below
            errors[index] = exc

    threads = [
        threading.Thread(target=run, args=(index,), daemon=True)
        for index in range(len(tasks))
    ]
    for thread in threads:
        thread.start()

    def join_all() -> None:
        for thread in threads:
            while thread.is_alive():
                thread.join(join_interval)

    try:
        join_all()
    except KeyboardInterrupt:
        stop.set()
        join_all()
    for error in errors:
        if error is not None:
            raise error
    return results


# --------------------------------------------------------------------------- #
# Waiting for downloads on the server
# --------------------------------------------------------------------------- #


def response_message(response: httpx.Response) -> str:
    """Return the cleaned ``message``/``detail`` of an error response."""
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
class WaitState:
    """When one download call started; downloaders add their progress."""

    start: float


@dataclass
class AssetWaiter:
    """What model installs and video downloads share while they wait.

    Holds the HTTP client and the timing (all injectable for tests), prints
    progress lines with :attr:`log_prefix`, caps each request by the time
    left, and runs the poll loop (:meth:`_wait_until_done`).
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

    log_prefix: ClassVar[str] = ""

    @property
    def _api(self) -> str:
        return self.base_url.rstrip("/")

    def _say(self, text: str) -> None:
        self.report(f"{self.log_prefix} {text}")

    def _elapsed(self, state: WaitState) -> str:
        return format_duration(self.monotonic() - state.start)

    def _remaining(self, state: WaitState) -> float:
        return state.start + self.timeout_seconds - self.monotonic()

    def _request_timeout(self, state: WaitState) -> float:
        """HTTP timeout of one request, capped by the remaining budget.

        The first request runs with the whole budget; every later request
        is only sent while budget is left. The floor only keeps httpx from
        getting a zero or negative timeout.
        """
        return max(0.001, min(self.request_timeout, self._remaining(state)))

    def _wait_until_done(
        self,
        state: WaitState,
        *,
        pending: Callable[[], bool],
        poll: Callable[[], None],
        time_out: Callable[[], None],
        summary: Callable[[], str],
    ) -> None:
        """Poll until nothing is *pending* or the budget is spent.

        Args:
            state: The call's start time.
            pending: Whether anything is still being waited for.
            poll: Checks the server once and resolves what has finished.
            time_out: Resolves what is still pending once the budget is spent.
            summary: The progress line printed every :attr:`summary_interval`.
        """
        last_summary = self.monotonic()
        while pending():
            if self._remaining(state) > 0:
                poll()
            if not pending():
                return
            remaining = self._remaining(state)
            if remaining <= 0:
                time_out()
                return
            now = self.monotonic()
            if now - last_summary >= self.summary_interval:
                last_summary = now
                self._say(summary())
            self.sleep(min(self.poll_interval, remaining))

# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Offer to download the sample input videos the selected benchmark runs need.

ViPPET downloads its sample videos on demand. A pipeline whose input video
is not downloaded cannot start, so the CLI (``python -m perf_helpers.cli``)
does this before it starts pytest, next to the model installation
(:mod:`perf_helpers.model_install`):

1. :func:`build_plan` picks the missing input videos of the runs in the
   benchmark matrix that ViPPET lists as sample videos
   (``GET /videos/default-recordings``). Other missing videos must be
   uploaded; the runs that need them are skipped.
2. The CLI prints the plan, asks (``ask``) or not (``yes``), and runs
   :class:`VideoDownloader`, which starts each download through
   ``POST /videos/download-default`` and polls the sample list until the
   video is downloaded and its HEVC copy is converted.
3. The per-video outcome is handed to the pytest subprocess as JSON in
   :data:`ENV_VIDEO_DOWNLOAD`. pytest turns runs whose video failed to
   download into errors (:func:`download_problem`) and reports the outcome.

pytest itself never prompts or downloads. Every text from the server is
passed through :func:`clean_text` before it is printed.
"""

import json
import time
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from enum import StrEnum
from typing import Any

import httpx

from .asset_download import (
    AssetProblem,
    clean_text,
    confirm,
    decode_outcome_env,
    format_duration,
)
from .matrix import Matrix, format_table
from .settings import InstallMode

# Set by the CLI for its pytest subprocess: JSON list of video outcomes.
ENV_VIDEO_DOWNLOAD: str = "PERF_VIDEO_DOWNLOAD_OUTCOME"
_OUTCOME_KEYS = ("filename", "outcome", "reason", "conversion_status")

SUMMARY_INTERVAL_SECONDS: float = 60.0
_LOG_PREFIX = "[video-download]"

# Download states of GET /videos/default-recordings.
_IN_PROGRESS: frozenset[str] = frozenset({"queued", "downloading"})
_DOWNLOADED = "downloaded"
_CONFLICT = "conflict"
# HEVC conversion states that are still running.
_CONVERTING: frozenset[str] = frozenset({"queued", "converting"})
CONVERSION_STATES: frozenset[str] = frozenset(
    {"not_converted", "queued", "converting", "converted", "failed", "conflict"}
)
PEXELS_LICENSE_URL = "https://www.pexels.com/license/"
PEXELS_TERMS_URL = "https://www.pexels.com/terms-of-service/"
# HEVC conversion states in which no HEVC copy was made.
CONVERSION_FAILED: frozenset[str] = frozenset({"failed", "conflict"})

DOWNLOAD_HINT: str = (
    'Download them with make test-performance PERF_ARGS="--download-missing-videos=yes" '
    "(or python -m perf_helpers.cli --download-missing-videos=yes), or on the "
    "ViPPET UI Videos page"
)
SKIP_REASON_HINT: str = f"{DOWNLOAD_HINT}, to enable this case."
SECTION_HEADER: str = f"{'-' * 30} Video download {'-' * 30}"
NOTHING_TO_DOWNLOAD: str = (
    "Video download: every sample video the selected runs need is downloaded."
)
LICENSE_NOTE: str = (
    "By downloading you accept the license terms of each video's source."
)


class Outcome(StrEnum):
    DOWNLOADED = "downloaded"
    FAILED = "failed"
    TIMED_OUT = "timed_out"
    DECLINED = "declined"
    INTERRUPTED = "interrupted"


# Runs needing a video with one of these outcomes are reported as ERROR.
ERROR_OUTCOMES: frozenset[Outcome] = frozenset({Outcome.FAILED, Outcome.TIMED_OUT})


# --------------------------------------------------------------------------- #
# Plan
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class PlannedVideo:
    """One sample video the selected runs need and that is not downloaded."""

    filename: str
    """Name used by pipelines and for ``POST /videos/download-default``."""
    source: str
    pipelines: tuple[str, ...]
    """Pipeline ids in this run that read the video."""
    runs: int
    """Number of matrix rows (pipeline x variant x streams) that need it."""
    already_downloading: bool = False

    @property
    def label(self) -> str:
        return clean_text(self.filename)

    @property
    def is_pexels(self) -> bool:
        return self.source.lower() == "pexels"


@dataclass(frozen=True)
class VideoPlan:
    videos: tuple[PlannedVideo, ...] = ()
    unavailable: tuple[str, ...] = ()
    """Missing videos that are not sample videos ViPPET can download."""

    @property
    def to_download(self) -> list[PlannedVideo]:
        return [v for v in self.videos if not v.already_downloading]

    @property
    def already_downloading(self) -> list[PlannedVideo]:
        return [v for v in self.videos if v.already_downloading]


def build_plan(recordings: Iterable[Mapping[str, Any]], matrix: Matrix) -> VideoPlan:
    """Pick the sample videos the matrix's included runs need.

    A video is planned when an included case reads it, ViPPET does not have
    it, and ``GET /videos/default-recordings`` lists it (and no other video
    has taken its name). Videos that are already downloading are planned as
    "wait only".

    Args:
        recordings: The ``GET /videos/default-recordings`` payload
            (untrusted; text is cleaned).
        matrix: The benchmark matrix; only its included runs count.

    Returns:
        The plan, sorted by filename.
    """
    streams = len(matrix.stream_counts) or 1
    runs: dict[str, int] = {}
    pipelines: dict[str, set[str]] = {}
    for case in matrix.included:
        for name in matrix.videos_missing_for(case):
            if name:
                runs[name] = runs.get(name, 0) + streams
                pipelines.setdefault(name, set()).add(case.pipeline_id)

    by_name = {
        r["filename"]: r
        for r in recordings
        if isinstance(r, Mapping) and isinstance(r.get("filename"), str)
    }
    planned: list[PlannedVideo] = []
    unavailable: list[str] = []
    for name in sorted(runs):
        recording = by_name.get(name)
        status = str((recording or {}).get("status") or "").lower()
        if recording is None or status == _CONFLICT:
            unavailable.append(clean_text(name))
            continue
        planned.append(
            PlannedVideo(
                filename=name,
                source=clean_text(recording.get("source"), max_length=40),
                pipelines=tuple(sorted(pipelines[name])),
                runs=runs[name],
                already_downloading=status in _IN_PROGRESS or status == _DOWNLOADED,
            )
        )
    return VideoPlan(tuple(planned), tuple(unavailable))


def _unavailable_note(plan: VideoPlan) -> str:
    return (
        "These missing videos are not sample videos ViPPET can download; "
        "upload them on the ViPPET UI Videos page (the runs that need them "
        f"are skipped): {', '.join(plan.unavailable)}"
    )


def format_plan(plan: VideoPlan) -> str:
    """Render the plan: table, the videos that must be uploaded, license note.

    Args:
        plan: The download plan.

    Returns:
        The rendered plan, or one sentence when nothing can be downloaded.
    """
    lines: list[str] = []
    if plan.videos:
        rows = [
            (
                v.label,
                v.source or "?",
                ", ".join(v.pipelines),
                v.runs,
                "wait (already downloading)" if v.already_downloading else "download",
            )
            for v in plan.videos
        ]
        lines += [
            f"{len(plan.videos)} sample video(s) needed by the selected runs are "
            "not downloaded:",
            format_table(
                (
                    "video",
                    "source",
                    "pipelines in this run",
                    "runs needing it",
                    "action",
                ),
                rows,
            ),
            "",
            "ViPPET also converts each downloaded video to HEVC (H.265); the "
            "wait includes that conversion.",
        ]
    else:
        lines.append("Every sample video the selected runs need is downloaded.")
    if plan.unavailable:
        lines += ["", _unavailable_note(plan)]
    if plan.videos:
        lines.append("")
        if any(v.is_pexels for v in plan.videos):
            lines += [
                f"Pexels License: {PEXELS_LICENSE_URL}",
                f"Pexels Terms of Service: {PEXELS_TERMS_URL}",
            ]
        lines.append(LICENSE_NOTE)
    return "\n".join(lines)


def prompt_text(plan: VideoPlan) -> str:
    """Return the yes/no question for a plan with videos.

    Args:
        plan: The download plan.

    Returns:
        The question, ending in ``[y/N] ``.
    """
    download = len(plan.to_download)
    waiting = len(plan.already_downloading)
    if download and waiting:
        return (
            f"Download {download} video(s) and wait for {waiting} already "
            "downloading now? [y/N] "
        )
    if download:
        return f"Download {download} video(s) now? [y/N] "
    return f"Wait for {waiting} video(s) that are already downloading? [y/N] "


def describe_mode_effect(mode: InstallMode, stdin_is_tty: bool) -> str:
    """Describe what a benchmark run would do with the plan (for ``--dry-run``).

    Args:
        mode: The ``benchmark.videos.download`` setting.
        stdin_is_tty: Whether stdin is a terminal.

    Returns:
        One sentence naming the setting and its effect on this terminal.
    """
    if mode == "yes":
        return (
            "With --download-missing-videos=yes a run downloads these videos "
            "without asking."
        )
    if mode == "ask" and stdin_is_tty:
        return (
            "With --download-missing-videos=ask (default) a run asks before "
            "downloading these videos."
        )
    if mode == "no":
        return (
            "With --download-missing-videos=no a run does not download them; "
            "the runs that need them are skipped."
        )
    return (
        "With --download-missing-videos=ask (default) a run does not download "
        "them here, because stdin is not a terminal; pass "
        "--download-missing-videos=yes to download them without asking."
    )


# --------------------------------------------------------------------------- #
# Outcome
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class VideoOutcome:
    filename: str
    outcome: Outcome
    reason: str = ""
    conversion_status: str = ""
    """State of the HEVC copy after a download (e.g. ``converted``), or ``""``."""

    def to_dict(self) -> dict[str, str]:
        return {
            "filename": self.filename,
            "outcome": self.outcome.value,
            "reason": self.reason,
            "conversion_status": self.conversion_status,
        }


def declined(plan: VideoPlan) -> list[VideoOutcome]:
    """Return a ``declined`` outcome for every video of *plan*."""
    return [
        VideoOutcome(v.label, Outcome.DECLINED, "declined at the prompt")
        for v in plan.videos
    ]


def encode_outcomes(outcomes: Sequence[VideoOutcome]) -> str:
    """Encode *outcomes* for :data:`ENV_VIDEO_DOWNLOAD`."""
    return json.dumps([o.to_dict() for o in outcomes])


def decode_outcomes(raw: str | None) -> list[VideoOutcome] | None:
    """Parse the value of :data:`ENV_VIDEO_DOWNLOAD`.

    Args:
        raw: The env value, or ``None`` when it is unset.

    Returns:
        The outcomes, or ``None`` when the value is unset or empty.

    Raises:
        OutcomeEnvError: The value is not a valid outcome list.
    """
    items = decode_outcome_env(
        raw,
        env_name=ENV_VIDEO_DOWNLOAD,
        keys=_OUTCOME_KEYS,
        outcomes={o.value for o in Outcome},
    )
    if items is None:
        return None
    return [
        VideoOutcome(
            filename=clean_text(item["filename"]),
            outcome=Outcome(item["outcome"]),
            reason=clean_text(item["reason"], max_length=500),
            conversion_status=item["conversion_status"]
            if item["conversion_status"] in CONVERSION_STATES
            else "",
        )
        for item in items
    ]


def download_problem(
    missing_names: Iterable[str], outcomes: Iterable[VideoOutcome]
) -> AssetProblem | None:
    """Decide what happens to a run whose input videos are missing.

    Args:
        missing_names: The run's missing videos (raw from ViPPET).
        outcomes: Download outcomes handed over by the CLI.

    Returns:
        An ``error`` problem when one of the run's videos failed to download
        or timed out, a ``skip`` problem when waiting for one was
        interrupted, and ``None`` otherwise (declined, not a sample video,
        or no download attempted: the default missing-videos skip applies).
    """
    by_name = {o.filename: o for o in outcomes}
    cleaned = sorted({clean_text(name) for name in missing_names if name})
    relevant = [by_name[name] for name in cleaned if name in by_name]
    failed = [o for o in relevant if o.outcome in ERROR_OUTCOMES]
    if failed:
        return AssetProblem(
            "error",
            "; ".join(
                f"input video {o.filename!r} failed to download: {o.reason}"
                for o in failed
            ),
        )
    interrupted = [o for o in relevant if o.outcome == Outcome.INTERRUPTED]
    if interrupted:
        names = ", ".join(repr(o.filename) for o in interrupted)
        return AssetProblem(
            "skip",
            f"input video(s) {names} were still downloading when waiting was "
            "interrupted (Ctrl-C); the download continues on the server. "
            "Rerun when it has finished.",
        )
    return None


_CONVERSION_LABELS: dict[str, str] = {
    "converted": "converted",
    "failed": "conversion failed",
    "conflict": "not converted (name taken)",
    "not_converted": "not converted",
    "queued": "still converting",
    "converting": "still converting",
}


def format_outcomes(outcomes: Sequence[VideoOutcome]) -> str:
    """Render the download outcomes: a count per outcome and a table."""
    if not outcomes:
        return "No video download was needed."
    counts = {o: sum(1 for x in outcomes if x.outcome == o) for o in Outcome}
    summary = ", ".join(f"{n} {o.value}" for o, n in counts.items() if n)
    table = format_table(
        ("video", "outcome", "HEVC copy", "reason"),
        [
            (
                o.filename,
                o.outcome.value,
                _CONVERSION_LABELS.get(o.conversion_status, "-"),
                o.reason or "-",
            )
            for o in outcomes
        ],
    )
    return f"Video download: {summary}\n{table}"


def conversion_failure_line(outcomes: Sequence[VideoOutcome]) -> str:
    """Return one line about failed HEVC conversions, or ``""`` if none failed.

    The benchmark reads the original (H.264) videos, so a failed conversion
    never affects a run.
    """
    failed = sum(1 for o in outcomes if o.conversion_status in CONVERSION_FAILED)
    if not failed:
        return ""
    return (
        f"HEVC conversion failed for {failed} video(s); the benchmark is not affected"
    )


def describe_skipped_for_missing_videos(
    count: int, outcomes: Sequence[VideoOutcome] | None = None
) -> str:
    """Explain runs that were skipped because their input videos are missing.

    Args:
        count: Number of runs skipped for missing videos.
        outcomes: Download outcomes handed over by the CLI, or ``None`` when
            no download step ran.

    Returns:
        A hint that tells the user how to get the videos. When the user
        declined at the prompt it says so instead of the generic hint.
    """
    if outcomes and any(o.outcome == Outcome.DECLINED for o in outcomes):
        return (
            f"{count} run(s) were skipped because you declined downloading "
            "their input videos. Rerun with --download-missing-videos=yes, or "
            "answer y."
        )
    return (
        f"{count} run(s) were skipped because their input videos are missing. "
        f"{DOWNLOAD_HINT}; upload videos that are not samples there too. Only "
        "the CLI downloads videos; a direct pytest run never does."
    )


# --------------------------------------------------------------------------- #
# HTTP
# --------------------------------------------------------------------------- #


def fetch_default_recordings(
    client: httpx.Client, base_url: str, request_timeout: float
) -> list[dict[str, Any]] | None:
    """Read the sample video list.

    Args:
        client: HTTP client, owned by the caller.
        base_url: ViPPET API base URL.
        request_timeout: Timeout of the request, in seconds.

    Returns:
        The objects of ``GET /videos/default-recordings``, or ``None`` when
        ViPPET has no such endpoint (HTTP 404; older releases download every
        sample video at startup).

    Raises:
        httpx.HTTPError: The request failed or returned another error status.
        ValueError: The response is not a JSON list.
    """
    response = client.get(
        f"{base_url.rstrip('/')}/videos/default-recordings", timeout=request_timeout
    )
    if response.status_code == 404:
        return None
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, list):
        raise ValueError(
            "GET /videos/default-recordings: expected a list, got "
            f"{type(payload).__name__}"
        )
    return [r for r in payload if isinstance(r, dict)]


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
class _Track:
    video: PlannedVideo
    state: str = ""
    detail: str = ""


@dataclass
class _DownloadState:
    """Progress of one :meth:`VideoDownloader.download` call."""

    start: float
    downloading: dict[str, _Track] = field(default_factory=dict)
    """Videos still being downloaded, by filename."""
    converting: dict[str, _Track] = field(default_factory=dict)
    """Downloaded videos whose HEVC conversion is still running."""
    outcomes: dict[str, VideoOutcome] = field(default_factory=dict)
    """Videos with a final download outcome, by filename."""

    def resolve(
        self,
        video: PlannedVideo,
        outcome: Outcome,
        reason: str = "",
        conversion: str = "",
    ) -> None:
        self.downloading.pop(video.filename, None)
        self.outcomes[video.filename] = VideoOutcome(
            video.label, outcome, reason, conversion
        )

    def set_conversion(self, video: PlannedVideo, conversion: str) -> None:
        self.converting.pop(video.filename, None)
        outcome = self.outcomes[video.filename]
        self.outcomes[video.filename] = replace(outcome, conversion_status=conversion)

    def count(self, outcome: Outcome) -> int:
        return sum(1 for o in self.outcomes.values() if o.outcome == outcome)


@dataclass
class VideoDownloader:
    """Start the downloads of a plan and wait for them and their conversion.

    ``download`` never raises for server or network problems: they become
    ``failed`` outcomes. The first Ctrl-C stops waiting; videos without a
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

    @property
    def _api(self) -> str:
        return self.base_url.rstrip("/")

    def _elapsed(self, state: _DownloadState) -> str:
        return format_duration(self.monotonic() - state.start)

    def _remaining(self, state: _DownloadState) -> float:
        return state.start + self.timeout_seconds - self.monotonic()

    def _request_timeout(self, state: _DownloadState) -> float:
        return max(0.001, min(self.request_timeout, self._remaining(state)))

    def _say(self, text: str) -> None:
        self.report(f"{_LOG_PREFIX} {text}")

    def download(self, plan: VideoPlan) -> list[VideoOutcome]:
        """Download the videos of *plan* and wait until each has an outcome.

        Args:
            plan: The videos to download, and those already downloading that
                only need to be waited for.

        Returns:
            One outcome per video of the plan, in plan order.
        """
        state = _DownloadState(start=self.monotonic())
        try:
            self._submit(plan, state)
            self._wait(state)
        except KeyboardInterrupt:
            for video in plan.videos:
                if video.filename not in state.outcomes:
                    state.resolve(
                        video,
                        Outcome.INTERRUPTED,
                        "waiting was interrupted (Ctrl-C); the download may "
                        "still be running on the server",
                    )
            for track in list(state.converting.values()):
                state.set_conversion(track.video, "converting")
            self._say(
                "Interrupted: stopped waiting. Downloads that already started "
                "continue on the server. Continuing with the videos downloaded "
                "so far; press Ctrl-C again to abort the benchmark."
            )
        outcomes = [state.outcomes[v.filename] for v in plan.videos]
        line = conversion_failure_line(outcomes)
        if line:
            self._say(line)
        return outcomes

    # -- steps ---------------------------------------------------------------

    def _fail(self, state: _DownloadState, video: PlannedVideo, reason: str) -> None:
        state.resolve(video, Outcome.FAILED, reason)
        self._say(f"{video.label}: FAILED: {reason}")

    def _submit(self, plan: VideoPlan, state: _DownloadState) -> None:
        for video in plan.already_downloading:
            state.downloading[video.filename] = _Track(video)
        for video in plan.to_download:
            try:
                response = self.client.post(
                    f"{self._api}/videos/download-default",
                    json={"filename": video.filename},
                    timeout=self._request_timeout(state),
                )
            except httpx.HTTPError as exc:
                reason = (
                    "POST /videos/download-default failed: "
                    f"{type(exc).__name__}: {clean_text(exc)}"
                )
                if isinstance(exc, httpx.TimeoutException):
                    reason += "; ViPPET may have started the download anyway"
                self._fail(state, video, reason)
                continue
            if response.status_code not in (200, 202):
                self._fail(
                    state,
                    video,
                    f"ViPPET rejected the download (HTTP {response.status_code}): "
                    f"{_response_message(response)}",
                )
                continue
            state.downloading[video.filename] = _Track(video)
            if response.status_code == 202:
                self._say(f"{video.label}: download started")

    def _wait(self, state: _DownloadState) -> None:
        last_summary = self.monotonic()
        while state.downloading or state.converting:
            if self._remaining(state) > 0:
                self._poll(state)
            if not (state.downloading or state.converting):
                return
            remaining = self._remaining(state)
            if remaining <= 0:
                self._time_out(state)
                return
            now = self.monotonic()
            if now - last_summary >= self.summary_interval:
                last_summary = now
                self._say(self._summary(state))
            self.sleep(min(self.poll_interval, remaining))

    def _time_out(self, state: _DownloadState) -> None:
        budget = format_duration(self.timeout_seconds)
        for track in list(state.downloading.values()):
            reason = (
                f"still downloading after {budget} (--video-download-timeout); "
                "the download continues on the server"
            )
            state.resolve(track.video, Outcome.TIMED_OUT, reason)
            self._say(f"{track.video.label}: TIMED OUT: {reason}")
        for track in list(state.converting.values()):
            state.set_conversion(track.video, "converting")
            self._say(
                f"{track.video.label}: HEVC conversion still running after "
                f"{budget}; continuing without it (the H.264 video is used)"
            )

    def _summary(self, state: _DownloadState) -> str:
        downloaded = state.count(Outcome.DOWNLOADED)
        failed = len(state.outcomes) - downloaded
        return (
            f"{downloaded} downloaded, {failed} failed, {len(state.downloading)} "
            f"still downloading, {len(state.converting)} converting (elapsed "
            f"{self._elapsed(state)} of {format_duration(self.timeout_seconds)})"
        )

    def _note(
        self, state: _DownloadState, track: _Track, status: str, detail: str = ""
    ) -> None:
        """Print a line only when the video's state changed."""
        if (status, detail) == (track.state, track.detail):
            return
        track.state, track.detail = status, detail
        suffix = f" - {detail}" if detail else ""
        self._say(f"{track.video.label}: {status}{suffix} ({self._elapsed(state)})")

    def _poll(self, state: _DownloadState) -> None:
        """Read the sample list once and resolve what has finished."""
        try:
            recordings = fetch_default_recordings(
                self.client, self.base_url, self._request_timeout(state)
            )
            if recordings is None:
                raise ValueError("GET /videos/default-recordings returned HTTP 404")
        except (httpx.HTTPError, ValueError) as exc:
            # Transient: keep waiting until the overall timeout.
            detail = f"{type(exc).__name__}: {clean_text(exc)}"
            for track in [*state.downloading.values(), *state.converting.values()]:
                self._note(state, track, "POLL FAILED", detail)
            return
        by_name = {r.get("filename"): r for r in recordings}
        for track in list(state.downloading.values()):
            self._check_download(state, track, by_name.get(track.video.filename))
        for track in list(state.converting.values()):
            self._check_conversion(state, track, by_name.get(track.video.filename))

    def _check_download(
        self, state: _DownloadState, track: _Track, recording: Mapping[str, Any] | None
    ) -> None:
        video = track.video
        if recording is None:
            self._fail(state, video, "ViPPET no longer lists it as a sample video")
            return
        status = clean_text(recording.get("status"), max_length=40).lower()
        if status == _DOWNLOADED:
            state.resolve(video, Outcome.DOWNLOADED)
            self._say(f"{video.label}: downloaded ({self._elapsed(state)})")
            state.converting[video.filename] = _Track(video)
            self._check_conversion(state, state.converting[video.filename], recording)
        elif status in _IN_PROGRESS:
            self._note(state, track, status)
        elif status == "failed":
            self._fail(
                state,
                video,
                "ViPPET could not download it; check the ViPPET logs (docker "
                "compose logs vippet) and the network or proxy settings, then rerun",
            )
        elif status == _CONFLICT:
            self._fail(
                state,
                video,
                "another video already has this filename; rename or delete it "
                "on the ViPPET UI Videos page, then rerun",
            )
        else:
            self._fail(
                state,
                video,
                "the download is no longer queued on ViPPET (was ViPPET restarted?)",
            )

    def _check_conversion(
        self, state: _DownloadState, track: _Track, recording: Mapping[str, Any] | None
    ) -> None:
        status = clean_text((recording or {}).get("conversion_status"), max_length=40)
        status = status.lower()
        if status in _CONVERTING:
            self._note(state, track, "converting to HEVC")
            return
        state.set_conversion(track.video, status if status in CONVERSION_STATES else "")
        if status == "converted":
            self._say(f"{track.video.label}: HEVC copy ready ({self._elapsed(state)})")
        # Failed conversions are summed up in one line by download().


# --------------------------------------------------------------------------- #
# Prompt
# --------------------------------------------------------------------------- #


def present_plan(plan: VideoPlan, report: Callable[[str], None] = print) -> None:
    """Print the plan under the section header, or one line when it has no
    video to download (plus the videos that must be uploaded, if any)."""
    if not plan.videos:
        report(NOTHING_TO_DOWNLOAD)
        if plan.unavailable:
            report(_unavailable_note(plan))
        return
    report(SECTION_HEADER)
    report(format_plan(plan))


def agree_to_download(
    plan: VideoPlan,
    *,
    ask: bool,
    input_fn: Callable[[str], str] = input,
    report: Callable[[str], None] = print,
) -> bool:
    """Ask whether to download a plan with videos (or say it downloads unasked).

    Returns:
        ``True`` to download; ``False`` when the user declined.
    """
    if not ask:
        report("Downloading without asking (--download-missing-videos=yes).")
        return True
    if confirm(prompt_text(plan), input_fn):
        return True
    report(
        "Not downloading. The runs that need these videos are skipped. "
        f"{DOWNLOAD_HINT}."
    )
    return False

# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Shared dependencies and helpers for the tool layer."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from fastmcp import Context
from mcp.types import ToolAnnotations

from ..clients import VssClient, VssError
from ..core import Settings
from ..features import ALL_FEATURES, Features
from ..projections import (
    caption_progress,
    is_final_summary_done,
    is_number,
    is_timeline_done,
    slim_video,
)

#: Frames sampled per chunk when the deployment allows it; the UI default.
PREFERRED_SAMPLING_FRAMES = 8

#: Chunk length in seconds; the UI default.
DEFAULT_CHUNK_DURATION = 8

#: MCP tool hints. Clients use ``readOnlyHint`` to run a tool without asking
#: for confirmation; everything talks only to this VSS deployment, so no tool
#: is open-world. Only removing a camera is destructive, and even that keeps
#: the camera's recorded media and embeddings.
READ_ONLY = ToolAnnotations(readOnlyHint=True, openWorldHint=False)
STARTS_WORK = ToolAnnotations(
    readOnlyHint=False, destructiveHint=False, openWorldHint=False
)
IDEMPOTENT_WORK = STARTS_WORK.model_copy(update={"idempotentHint": True})
DESTRUCTIVE = ToolAnnotations(
    readOnlyHint=False,
    destructiveHint=True,
    idempotentHint=True,
    openWorldHint=False,
)

#: EVAM pipeline preference: ``object_detection`` keeps labelled detections
#: alongside the chunks; ``video_ingestion`` is the fallback.
EVAM_PREFERENCE = ("object_detection", "video_ingestion")


@dataclass(frozen=True, slots=True)
class Deps:
    """Objects every tool needs.

    ``features`` is resolved once at startup and decides which tools are
    registered. It defaults to everything on for callers constructing this by
    hand; the server always passes the detected set.
    """

    client: VssClient
    settings: Settings
    features: Features = ALL_FEATURES


#: Watch auto-refresh interval assumed when the config gives none or cannot
#: be read; Pipeline Manager's own default.
DEFAULT_REFRESH_SECONDS = 10.0


async def read_refresh_config(deps: Deps) -> tuple[bool, float] | None:
    """Whether VSS auto-refreshes watched searches, and how often (seconds).

    The one reading of ``GET /search/refresh-config``: ``enabled`` defaults
    to true and a missing or non-positive ``intervalMs`` to
    :data:`DEFAULT_REFRESH_SECONDS`. ``None`` when the config cannot be read,
    leaving the caller to decide what an unknown setting means.
    """

    try:
        config = await deps.client.get_refresh_config()
    except VssError as exc:
        logging.getLogger(__name__).warning(
            "Could not read the watch refresh config: %s", exc
        )
        return None
    if not config:
        return None
    interval = config.get("intervalMs")
    seconds = (
        interval / 1000
        if is_number(interval) and interval > 0
        else DEFAULT_REFRESH_SECONDS
    )
    return config.get("enabled", True) is not False, seconds


async def require_video(deps: Deps, video_id: str) -> dict[str, Any]:
    """Return the video row for ``video_id``, or raise a usable error."""

    video = await deps.client.get_video(video_id)
    if not video:
        raise VssError(
            f"No video with id {video_id}. Use resolve_video or list_videos to "
            "find the right id."
        )
    return video


def _positive_int(name: str, value: Any, *, minimum: int) -> int:
    """Validate an integer option, so VSS is not handed one it rejects."""

    if not is_number(value) or value != int(value):
        raise VssError(f"{name} must be a whole number, got {value!r}.")
    if value < minimum:
        raise VssError(f"{name} must be at least {minimum}, got {value}.")
    return int(value)


def _choose_evam_pipeline(
    config: dict[str, Any], available: list[str], requested: str | None
) -> str:
    """Return the EVAM pipeline: ``requested`` if given, else the
    deployment's default, as the UI picks it."""

    if requested:
        if requested not in available:
            raise VssError(
                f"Unknown evam_pipeline {requested!r}; this deployment offers "
                f"{available}."
            )
        return requested
    default = config.get("evamPipeline")
    pipeline = (
        default
        if default in available
        else next(
            (name for name in EVAM_PREFERENCE if name in available),
            available[0] if available else None,
        )
    )
    if not pipeline:
        raise VssError(
            "This deployment advertises no EVAM pipeline, so summarization "
            "cannot be started."
        )
    return pipeline


def _choose_audio(
    meta: dict[str, Any],
    *,
    audio: bool,
    audio_model: str | None,
    full_transcript_summary: bool,
    final_summary: bool,
) -> dict[str, Any] | None:
    """Return the ``audio`` block, or ``None`` for no transcription.

    As in the UI, audio is on by default with the deployment's default model,
    and silently off when the deployment offers no audio model.
    """

    if not audio:
        return None
    models = [
        option.get("model_id")
        for option in meta.get("audioModels") or []
        if option.get("model_id")
    ]
    if audio_model:
        if models and audio_model not in models:
            raise VssError(
                f"Unknown audio_model {audio_model!r}; this deployment offers "
                f"{models}."
            )
        if not models and not meta.get("defaultAudioModel"):
            raise VssError(
                "This deployment offers no audio model, so audio_model "
                "cannot be used."
            )
        model = audio_model
    else:
        model = meta.get("defaultAudioModel")
    if not model:
        return None
    return {
        "audioModel": model,
        # Full-transcript summarization feeds the final summary, so it is
        # only meaningful alongside one -- the UI disables it otherwise.
        "useFullTranscriptSummary": bool(full_transcript_summary and final_summary),
    }


async def build_summary_body(
    client: VssClient,
    video: dict[str, Any],
    *,
    focus: str | None = None,
    final_summary: bool = True,
    chunk_duration: int | None = None,
    sampling_frames: int | None = None,
    frame_overlap: int | None = None,
    evam_pipeline: str | None = None,
    audio: bool = True,
    audio_model: str | None = None,
    audio_full_transcript_summary: bool = False,
) -> dict[str, Any]:
    """Construct a body that passes ``POST /summary``'s validation, filling
    omitted options with the VSS UI's defaults.

    ``GET /app/config`` supplies what would otherwise be a bare 400:
    ``multiFrame`` above the deployment's maximum, ``frameOverlap +
    samplingFrame != multiFrame``, or no EVAM pipeline named.

    Raises:
        VssError: If an option is invalid for this deployment, or it
            advertises no EVAM pipeline.
    """

    config = await client.get_app_config()
    meta = config.get("meta") or {}

    max_batch = int(config.get("multiFrame") or PREFERRED_SAMPLING_FRAMES)

    chunk_duration = _positive_int(
        "chunk_duration",
        DEFAULT_CHUNK_DURATION if chunk_duration is None else chunk_duration,
        minimum=1,
    )
    # Pipeline Manager ignores a frameOverlap of 0 and applies the
    # deployment's own, so that is the effective default -- but that also
    # means an explicit 0 cannot be told apart from "unset" there, so a
    # nonzero deployment default silently replaces it and then mismatches
    # the multiFrame computed below.
    deployment_overlap = int(config.get("frameOverlap") or 0)
    if frame_overlap == 0 and deployment_overlap:
        raise VssError(
            "frame_overlap=0 cannot be honored on this deployment: Pipeline "
            "Manager treats a zero frameOverlap as unset and applies its own "
            f"default ({deployment_overlap}) instead, which would then "
            "mismatch the multi-frame batch size requested here. Omit "
            "frame_overlap to use the deployment default, or pass a "
            "positive value."
        )
    overlap = _positive_int(
        "frame_overlap",
        deployment_overlap if frame_overlap is None else frame_overlap,
        minimum=0,
    )
    if sampling_frames is None:
        frames = max(1, min(PREFERRED_SAMPLING_FRAMES, max_batch - overlap))
    else:
        frames = _positive_int("sampling_frames", sampling_frames, minimum=1)
    if frames + overlap > max_batch:
        raise VssError(
            f"sampling_frames + frame_overlap is {frames + overlap}, but this "
            f"deployment processes at most {max_batch} frames per batch."
        )

    available = [
        option.get("value")
        for option in meta.get("evamPipelines") or []
        if option.get("value")
    ]
    pipeline = _choose_evam_pipeline(config, available, evam_pipeline)

    body: dict[str, Any] = {
        "videoId": video["videoId"],
        "title": slim_video(video)["name"] or video["videoId"],
        "sampling": {
            "chunkDuration": chunk_duration,
            "samplingFrame": frames,
            "frameOverlap": overlap,
            # frameOverlap + samplingFrame == multiFrame by construction.
            "multiFrame": frames + overlap,
        },
        "evam": {"evamPipeline": pipeline},
        "produceFinalSummary": bool(final_summary),
    }

    audio_block = _choose_audio(
        meta,
        audio=audio,
        audio_model=audio_model,
        full_transcript_summary=audio_full_transcript_summary,
        final_summary=final_summary,
    )
    if audio_block:
        body["audio"] = audio_block

    if focus:
        base_prompt = (config.get("framePrompt") or "").strip()
        instruction = (
            f"Pay particular attention to: {focus.strip()}. "
            "Describe it explicitly whenever it appears."
        )
        body["prompts"] = {"framePrompt": f"{base_prompt}\n\n{instruction}".strip()}

    return body


async def run_summary(
    deps: Deps,
    video: dict[str, Any],
    *,
    focus: str | None = None,
    final_summary: bool = True,
    wait_seconds: float | None = None,
    ctx: Context | None = None,
    **options: Any,
) -> tuple[str, dict[str, Any] | None, bool]:
    """Start a summary (``options`` go to :func:`build_summary_body`) and wait
    within the budget. Returns ``(state_id, last_state, completed)``.

    Without a final summary ``videoSummaryStatus`` never reaches
    ``complete``, so the timeline is the terminal signal. Progress goes to
    ``ctx`` as MCP notifications, which also keep long calls from timing out.
    """

    body = await build_summary_body(
        deps.client, video, focus=focus, final_summary=final_summary, **options
    )
    state_id = await deps.client.create_summary(body)

    async def report(state: dict[str, Any]) -> None:
        progress = caption_progress(state)
        await ctx.report_progress(
            progress["complete"],
            progress["total"] or None,
            f"Captioned {progress['complete']} of {progress['total']} chunks",
        )

    state, completed = await deps.client.poll_state(
        state_id,
        is_final_summary_done if final_summary else is_timeline_done,
        wait_seconds=(
            deps.settings.default_wait_seconds
            if wait_seconds is None
            else wait_seconds
        ),
        poll_interval_seconds=deps.settings.poll_interval_seconds,
        on_state=report if ctx else None,
    )
    return state_id, state, completed

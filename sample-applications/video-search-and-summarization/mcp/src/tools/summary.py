# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Summarization tools, and the ``POST /summary`` request they build."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from fastmcp import Context, FastMCP

from ..clients import VssClient, VssError
from ..projections import (
    caption_progress,
    is_final_summary_done,
    is_number,
    is_timeline_done,
    parse_iso_epoch,
    slim_summary,
    slim_video,
)
from ..schemas import Timeline, VideoSummary
from ._deps import READ_ONLY, STARTS_WORK, Deps, require_video

logger = logging.getLogger(__name__)

#: Frames sampled per chunk when the deployment allows it; the UI default.
PREFERRED_SAMPLING_FRAMES = 8

#: Chunk length in seconds; the UI default.
DEFAULT_CHUNK_DURATION = 8


def _positive_int(name: str, value: Any, *, minimum: int) -> int:
    """Validate an integer option; Pipeline Manager checks none of them."""

    if not is_number(value) or value != int(value):
        raise VssError(f"{name} must be a whole number, got {value!r}.")
    if value < minimum:
        raise VssError(f"{name} must be at least {minimum}, got {value}.")
    return int(value)


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
    and silently off when the deployment offers no audio model. Pipeline
    Manager transcribes only when a model is named.
    """

    if not audio:
        return None
    models = [
        option.get("model_id")
        for option in meta.get("audioModels") or []
        if option.get("model_id")
    ]
    if audio_model and audio_model not in models:
        raise VssError(
            f"Unknown audio_model {audio_model!r}; this deployment offers "
            f"{models or 'no audio model'}."
        )
    model = audio_model or meta.get("defaultAudioModel")
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
    ``multiFrame`` above the deployment's maximum, or ``frameOverlap +
    samplingFrame != multiFrame``.

    Raises:
        VssError: If an option is invalid for this deployment.
    """

    config = await client.get_app_config()
    meta = config["meta"]
    # An env var upstream, so it may arrive as a string.
    max_batch = int(config["multiFrame"])

    chunk_duration = _positive_int(
        "chunk_duration",
        DEFAULT_CHUNK_DURATION if chunk_duration is None else chunk_duration,
        minimum=1,
    )
    overlap = _positive_int(
        "frame_overlap",
        config["frameOverlap"] if frame_overlap is None else frame_overlap,
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

    # Pipeline Manager only checks that a pipeline is named, not which.
    available = [option["value"] for option in meta["evamPipelines"]]
    if evam_pipeline and evam_pipeline not in available:
        raise VssError(
            f"Unknown evam_pipeline {evam_pipeline!r}; this deployment offers "
            f"{available}."
        )

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
        "evam": {"evamPipeline": evam_pipeline or config["evamPipeline"]},
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
        body["prompts"] = focus_prompts(config, focus, final_summary=final_summary)

    return body


#: Prompts that roll the chunk captions up into the final summary.
SUMMARY_PROMPTS = ("summaryMapPrompt", "summaryReducePrompt", "summarySinglePrompt")


def focus_prompts(
    config: dict[str, Any], focus: str, *, final_summary: bool
) -> dict[str, str]:
    """Extend the deployment's prompts with ``focus``, so the frame captions
    and the final summary built from them both keep it in view.

    The deployment's own prompts are kept, not replaced; a prompt the
    deployment does not define is left to VSS.
    """

    subject = focus.strip()
    instructions = {
        "framePrompt": (
            f"Pay particular attention to: {subject}. "
            "Describe it explicitly whenever it appears."
        )
    }
    if final_summary:
        for name in SUMMARY_PROMPTS:
            instructions[name] = (
                f"Pay particular attention to: {subject}. Say when it appears "
                "and what it does, or say that it does not appear."
            )
    prompts = {}
    for name, instruction in instructions.items():
        base = (config.get(name) or "").strip()
        if name == "framePrompt" or base:
            prompts[name] = f"{base}\n\n{instruction}".strip()
    return prompts


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


def produced_final_summary(state: dict[str, Any]) -> bool:
    """Whether a run was asked for a final summary; VSS defaults to yes."""

    return (state.get("systemConfig") or {}).get("produceFinalSummary") is not False


async def summarize_video(
    deps: Deps,
    video_id: str,
    *,
    focus: str | None = None,
    final_summary: bool = True,
    wait_seconds: float | None = None,
    ctx: Context | None = None,
    **options: Any,
) -> VideoSummary:
    """Caption a video chunk by chunk and, by default, roll the captions up
    into a final summary, as VSS does. Returns only the final summary then,
    or the full timeline with ``final_summary=False``. ``completed`` is false
    when the wait budget expires first.

    ``options`` are the sampling, EVAM and audio options of
    :func:`build_summary_body`.

    Raises:
        VssError: If the video does not exist or the pipeline cannot start.
    """

    video = await require_video(deps, video_id)
    state_id, state, completed = await run_summary(
        deps,
        video,
        focus=focus,
        final_summary=final_summary,
        wait_seconds=wait_seconds,
        ctx=ctx,
        **options,
    )

    result = slim_summary(
        state or {"videoId": video_id, "stateId": state_id},
        final_summary=final_summary,
        include_timeline=not final_summary,
    )
    return {**result, "state_id": state_id, "completed": completed}


async def get_video_timeline(
    deps: Deps, video_id: str | None = None, state_id: str | None = None
) -> Timeline:
    """Return the caption timeline of a run, by ``state_id`` or else the
    most recently created run for ``video_id`` (preferring a completed one).

    Raises:
        VssError: If neither argument is given, or no run exists.
    """

    if state_id:
        state = await deps.client.get_ui_state(state_id)
        if not state:
            raise VssError(f"No pipeline run with id {state_id}.")
        return slim_summary(state, final_summary=produced_final_summary(state))

    if not video_id:
        raise VssError("Provide either video_id or state_id.")

    states = [
        state
        for state in await deps.client.list_ui_states()
        if state.get("videoId") == video_id
    ]
    if not states:
        raise VssError(
            f"Video {video_id} has not been summarized yet. Call "
            "vss_summarize_video first."
        )
    done = [state for state in states if is_timeline_done(state)]
    state = await _newest_run(deps, done or states)
    return slim_summary(state, final_summary=produced_final_summary(state))


async def _newest_run(deps: Deps, states: list[dict[str, Any]]) -> dict[str, Any]:
    """Pick the most recently created of ``states``.

    ``GET /summary/ui`` is in no defined order (an unsorted database read),
    so creation times come from each run's raw state. A run whose time
    cannot be read sorts oldest; ties keep the backend's order.
    """

    if len(states) == 1:
        return states[0]

    async def created(state: dict[str, Any]) -> float:
        try:
            stamp = await deps.client.get_state_created_at(state["stateId"])
        except VssError as exc:
            logger.warning(
                "Creation time of run %s unreadable; ranking it oldest: %s",
                state["stateId"], exc,
            )
            stamp = None
        epoch = parse_iso_epoch(stamp)
        return epoch if epoch is not None else float("-inf")

    epochs = await asyncio.gather(*(created(state) for state in states))
    newest = max(range(len(states)), key=lambda index: (epochs[index], index))
    return states[newest]


def register(mcp: FastMCP, deps: Deps) -> None:
    """Register the summarization tools on ``mcp`` where summary is on.

    The read-only timeline tool follows the feature too: without captioning
    runs it can only answer "not summarized yet", which a model acts on by
    starting a summarization this deployment cannot run.
    """

    if not deps.features.summary:
        return

    @mcp.tool(annotations=STARTS_WORK)
    async def vss_summarize_video(
        ctx: Context,
        video_id: str,
        focus: str | None = None,
        final_summary: bool = True,
        chunk_duration: int | None = None,
        sampling_frames: int | None = None,
        frame_overlap: int | None = None,
        evam_pipeline: str | None = None,
        audio: bool = True,
        audio_model: str | None = None,
        audio_full_transcript_summary: bool = False,
        wait_seconds: float | None = None,
    ) -> VideoSummary:
        """Summarize a video and return its final summary, in full.

        Defaults match the VSS UI and API. Set final_summary=false to get
        the chunk-level timeline (what happens when) instead, which is
        faster. completed=false means the wait budget ran out: call
        vss_get_video_summary_timeline with state_id later for the result. Leave
        the sampling, pipeline and audio options unset unless the user asks
        for them; an invalid value is rejected with the allowed ones.

        Args:
            video_id: Video to summarize.
            focus: Steer the captions and the final summary, e.g.
                "forklifts and pedestrians". Extends the deployment's
                prompts rather than replacing them.
            final_summary: Roll the captions up into one prose summary and
                return only that (default true, as in VSS). False returns
                the timeline instead.
            chunk_duration: Seconds of video per chunk (default 8).
            sampling_frames: Frames sampled per chunk (default 8, capped by
                the deployment's batch size).
            frame_overlap: Frames shared with the previous chunk (default:
                the deployment's setting, normally 0). sampling_frames +
                frame_overlap must not exceed the deployment's batch size.
            evam_pipeline: Video ingestion pipeline, e.g. "object_detection"
                or "video_ingestion" (default: the deployment's).
            audio: Transcribe the audio track when the deployment offers an
                audio model (default true).
            audio_model: Audio model id (default: the deployment's).
            audio_full_transcript_summary: Summarize the full transcript,
                for speech-heavy videos. Only applies with final_summary.
            wait_seconds: How long to wait before returning a progress handle.
        """

        return await summarize_video(
            deps,
            video_id,
            focus=focus,
            final_summary=final_summary,
            wait_seconds=wait_seconds,
            ctx=ctx,
            chunk_duration=chunk_duration,
            sampling_frames=sampling_frames,
            frame_overlap=frame_overlap,
            evam_pipeline=evam_pipeline,
            audio=audio,
            audio_model=audio_model,
            audio_full_transcript_summary=audio_full_transcript_summary,
        )

    @mcp.tool(annotations=READ_ONLY)
    async def vss_get_video_summary_timeline(
        video_id: str | None = None, state_id: str | None = None
    ) -> Timeline:
        """Return the full caption timeline of an already-summarized video,
        with its final summary when the run produced one.

        completed=false means the run is still going.

        Args:
            video_id: Video whose most recently created run should be used,
                preferring a completed one.
            state_id: A specific run, taking precedence over video_id.
        """

        return await get_video_timeline(deps, video_id=video_id, state_id=state_id)

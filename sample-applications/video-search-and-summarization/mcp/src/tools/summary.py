# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Summarization tools."""

from __future__ import annotations

from typing import Any

from fastmcp import Context, FastMCP

from ..clients import VssError
from ..projections import is_timeline_done, slim_summary
from ..schemas import Timeline
from ._deps import READ_ONLY, STARTS_WORK, Deps, require_video, run_summary


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
) -> Timeline:
    """Caption a video chunk by chunk and, by default, roll the captions up
    into a final summary, as VSS does. Returns the result so far; it is
    partial (``completed`` false) when the budget expires first.

    ``options`` are the sampling, EVAM and audio options of
    :func:`~._deps.build_summary_body`.

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
    )
    return {**result, "state_id": state_id, "completed": completed}


async def get_video_timeline(
    deps: Deps, video_id: str | None = None, state_id: str | None = None
) -> Timeline:
    """Return the caption timeline of a run, by ``state_id`` or else the
    latest run for ``video_id`` (preferring a completed one).

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
            "summarize_video first."
        )
    done = [state for state in states if is_timeline_done(state)]
    state = (done or states)[-1]
    return slim_summary(state, final_summary=produced_final_summary(state))


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
    ) -> Timeline:
        """Summarize a video: a timeline of what happens when, plus one
        overall prose summary.

        Defaults match the VSS UI and API. Set final_summary=false for only
        the chunk-level timeline, which is faster. completed=false means the
        wait budget ran out: the result holds the captions so far, and
        vss_get_video_timeline with state_id returns the rest later. Leave
        the sampling, pipeline and audio options unset unless the user asks
        for them; an invalid value is rejected with the allowed ones.

        Args:
            video_id: Video to summarize.
            focus: Steer the captions, e.g. "forklifts and pedestrians".
            final_summary: Also roll the captions up into one prose summary
                (default true, as in VSS). False returns the timeline only.
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
    async def vss_get_video_timeline(
        video_id: str | None = None, state_id: str | None = None
    ) -> Timeline:
        """Return the caption timeline of an already-summarized video, with
        its final summary when the run produced one.

        completed=false means the run is still going.

        Args:
            video_id: Video whose most recent run should be used.
            state_id: A specific run, taking precedence over video_id.
        """

        return await get_video_timeline(deps, video_id=video_id, state_id=state_id)

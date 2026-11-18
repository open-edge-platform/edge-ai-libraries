# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import asyncio
import logging
import os
import tempfile
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import BinaryIO
from uuid import uuid4

from audio_assets import AudioAssetsManager
from audio_errors import (
    AudioInputTooLargeError,
    AudioJobNotFoundError,
    AudioJobNotRunningError,
    AudioPipelineError,
    AudioPipelineNotFoundError,
    AudioPipelineVariantNotFoundError,
    AudioRecordingInputNotAcceptedError,
    AudioRecordingNotFoundError,
    AudioSTTInputNotAcceptedError,
    AudioTTSInputNotAcceptedError,
    SpeechServiceError,
)
from internal_types import (
    InternalAudioJobState,
    InternalAudioPipeline,
    InternalAudioPipelineJob,
    InternalAudioPipelineOperation,
    InternalAudioPipelineRecordingInput,
    InternalAudioPipelineSTTInput,
)
from managers.audio_pipeline_manager import AudioPipelineManager

logger = logging.getLogger("audio_pipeline_jobs")

Transcribe = Callable[[BinaryIO, str, str, str, str], Awaitable[tuple[str, float]]]
Synthesize = Callable[[str, str, str], Awaitable[tuple[bytes, float]]]

DEFAULT_MAX_TERMINAL_JOBS = 500

MAX_STT_UPLOAD_BYTES = 200 * 1024 * 1024
_STAGE_CHUNK_BYTES = 1024 * 1024


TERMINAL_STATUSES = {
    InternalAudioJobState.COMPLETED,
    InternalAudioJobState.FAILED,
}

_ALLOWED_TRANSITIONS = {
    InternalAudioJobState.RUNNING: {
        InternalAudioJobState.COMPLETED,
        InternalAudioJobState.FAILED,
    },
}


@dataclass(frozen=True)
class _StagedSTTInput:
    """Manager-owned upload copy that outlives the incoming HTTP request."""

    path: Path
    filename: str
    content_type: str
    language: str


class AudioPipelineJobManager:
    """Coordinate in-memory speech jobs, background tasks, and owned files.

    Injected callbacks perform speech conversion without tying the manager to
    HTTP. A lock protects job bookkeeping; completed task references and owned
    temporary inputs are cleaned up independently of request lifetimes.
    """

    def __init__(
        self,
        pipelines: AudioPipelineManager,
        assets: AudioAssetsManager,
        transcribe: Transcribe,
        synthesize: Synthesize,
        max_terminal_jobs: int = DEFAULT_MAX_TERMINAL_JOBS,
    ) -> None:
        """Bind catalog, assets, and conversion callbacks and create staging storage.

        ``max_terminal_jobs`` bounds retained completed and failed job records;
        pruning those records also schedules removal of their audio artifacts.

        Raises:
            ValueError: The terminal-job retention limit is negative.
        """
        if max_terminal_jobs < 0:
            raise ValueError("max_terminal_jobs must not be negative")
        self.pipelines = pipelines
        self.assets = assets
        self.transcribe = transcribe
        self.synthesize = synthesize
        self._jobs: dict[str, InternalAudioPipelineJob] = {}
        self._tasks: dict[str, asyncio.Task[None]] = {}
        self._cleanup_tasks: set[asyncio.Task[None]] = set()
        self._started_job_ids: set[str] = set()
        self._lock = asyncio.Lock()
        self._max_terminal_jobs = max_terminal_jobs
        self._input_directory_owner = tempfile.TemporaryDirectory(
            prefix="vippet-audio-job-inputs-"
        )
        self._input_directory = Path(self._input_directory_owner.name).resolve()

    async def start_job(
        self,
        pipeline_id: str,
        variant_id: str,
        *,
        input_text: str | None = None,
        voice: str | None = None,
        stt_input: InternalAudioPipelineSTTInput | None = None,
        recording_input: InternalAudioPipelineRecordingInput | None = None,
    ) -> InternalAudioPipelineJob:
        """Validate inputs, stage any upload, and schedule a background conversion.

        Speech-to-text accepts an upload or registered recording; text-to-speech
        requires text and voice. Uploads are copied before returning so the job
        does not depend on the request keeping its file stream open.

        Returns:
            A snapshot of the newly registered RUNNING job, not its final result.

        Raises:
            AudioPipelineError: The pipeline, variant, recording, or input is
                invalid, including an upload exceeding the configured size cap.
            RuntimeError: An uploaded input cannot be staged.
        """
        pipeline = self.pipelines.get_pipeline(pipeline_id)
        if pipeline is None:
            raise AudioPipelineNotFoundError(
                f"Audio pipeline '{pipeline_id}' not found."
            )
        if pipeline.operation is not InternalAudioPipelineOperation.TEXT_TO_SPEECH and (
            input_text is not None or voice is not None
        ):
            raise AudioTTSInputNotAcceptedError(
                "Speech-to-text pipelines do not accept TTS overrides."
            )
        if (
            pipeline.operation is not InternalAudioPipelineOperation.SPEECH_TO_TEXT
            and stt_input is not None
        ):
            raise AudioSTTInputNotAcceptedError(
                "Text-to-speech pipelines do not accept STT input."
            )
        if recording_input is not None:
            if pipeline.operation is not InternalAudioPipelineOperation.SPEECH_TO_TEXT:
                raise AudioRecordingInputNotAcceptedError(
                    "Text-to-speech pipelines do not accept recording input."
                )
            if self.assets.get_path(recording_input.filename) is None:
                raise AudioRecordingNotFoundError(
                    f"Audio recording '{recording_input.filename}' not found."
                )
        if pipeline.operation is InternalAudioPipelineOperation.SPEECH_TO_TEXT:
            if stt_input is None and recording_input is None:
                raise AudioPipelineError(
                    "Speech-to-text pipelines require audio input."
                )
        elif input_text is None or voice is None:
            raise AudioPipelineError("Text-to-speech pipelines require text and voice.")
        variant = next(
            (
                candidate
                for candidate in pipeline.variants
                if candidate.id == variant_id
            ),
            None,
        )
        if variant is None:
            raise AudioPipelineVariantNotFoundError(
                f"Audio pipeline '{pipeline_id}' variant '{variant_id}' not found."
            )
        now = datetime.now(timezone.utc)
        job = InternalAudioPipelineJob(
            id=str(uuid4()),
            pipeline_id=pipeline.id,
            pipeline_name=pipeline.name,
            variant_id=variant.id,
            variant_name=variant.name,
            device=variant.device,
            operation=pipeline.operation,
            status=InternalAudioJobState.RUNNING,
            created_at=now,
            modified_at=now,
        )
        staged_stt_input = (
            await self._stage_stt_input_async(stt_input)
            if stt_input is not None
            else None
        )
        try:
            async with self._lock:
                self._jobs[job.id] = job
                task = asyncio.create_task(
                    self._execute(
                        job.id,
                        pipeline,
                        input_text=input_text,
                        voice=voice,
                        stt_input=staged_stt_input,
                        recording_input=recording_input,
                    )
                )
                self._tasks[job.id] = task
                task.add_done_callback(
                    lambda completed, job_id=job.id: self._on_task_done(
                        job_id, completed
                    )
                )
        except BaseException:
            await self._delete_staged_input(staged_stt_input)
            raise
        return replace(job)

    async def _stage_stt_input_async(
        self,
        source: InternalAudioPipelineSTTInput,
    ) -> _StagedSTTInput:
        """Stage an upload in a worker thread without leaking files on cancellation.

        Shield the copy because cancelling an await cannot stop the worker.
        If the caller is interrupted, wait for the worker and delete any completed
        copy before propagating the original interruption.
        """
        task = asyncio.create_task(asyncio.to_thread(self._stage_stt_input, source))
        try:
            return await asyncio.shield(task)
        except BaseException:
            try:
                staged = await task
            except Exception:
                pass
            else:
                await self._delete_staged_input(staged)
            raise

    def _stage_stt_input(
        self, source: InternalAudioPipelineSTTInput
    ) -> _StagedSTTInput:
        """Copy an upload to a uniquely named private file with a bounded size.

        Leave the source stream open and remove incomplete output on failure.
        Oversized input raises AudioInputTooLargeError; other copy errors become
        RuntimeError without exposing private filesystem details.
        """
        destination = self._input_directory / f"{uuid4()}.upload"
        try:
            written = 0
            with destination.open("xb") as target:
                while chunk := source.file.read(_STAGE_CHUNK_BYTES):
                    written += len(chunk)
                    if written > MAX_STT_UPLOAD_BYTES:
                        raise AudioInputTooLargeError(
                            "Audio input exceeds the upload size limit."
                        )
                    target.write(chunk)
        except Exception as exc:
            try:
                destination.unlink(missing_ok=True)
            except OSError:
                logger.error("Failed to remove incomplete staged Audio input")
            if isinstance(exc, AudioInputTooLargeError):
                raise
            raise RuntimeError("Unable to stage Audio input.") from None
        return _StagedSTTInput(
            path=destination,
            filename=source.filename,
            content_type=source.content_type,
            language=source.language,
        )

    async def _execute(
        self,
        job_id: str,
        pipeline: InternalAudioPipeline,
        *,
        input_text: str | None,
        voice: str | None,
        stt_input: _StagedSTTInput | None,
        recording_input: InternalAudioPipelineRecordingInput | None = None,
    ) -> None:
        """Run conversion, publish its result, and finalize job-owned resources.

        Publish only while the job remains active. Cancellation completes it
        without a result; other execution failures mark it FAILED with a generic
        public message. Remove staged input and discard uncommitted artifacts.
        """
        uncommitted_artifact_path: str | None = None
        try:
            async with self._lock:
                job = self._jobs.get(job_id)
                if job is None or job.status in TERMINAL_STATUSES:
                    return
                self._started_job_ids.add(job_id)
                device = job.device

            if pipeline.operation is InternalAudioPipelineOperation.SPEECH_TO_TEXT:
                transcript, duration = await self._execute_stt(
                    device,
                    stt_input,
                    recording_input,
                )
                artifact_path = None
                artifact_filename = None
            else:
                artifact_path, artifact_filename, duration = await self._execute_tts(
                    job_id,
                    device,
                    input_text=input_text or "",
                    voice=voice or "",
                )
                uncommitted_artifact_path = artifact_path
                transcript = None

            async with self._lock:
                job = self._jobs.get(job_id)
                if job is None or job.status in TERMINAL_STATUSES:
                    cleanup_paths: list[str] = []
                else:
                    job.transcript = transcript
                    job.artifact_path = artifact_path
                    job.artifact_filename = artifact_filename
                    job.service_round_trip_ms = duration
                    self._transition_locked(job, InternalAudioJobState.COMPLETED)
                    uncommitted_artifact_path = None
                    cleanup_paths = self._prune_terminal_jobs_locked()
            await self._delete_artifacts(
                cleanup_paths
                + (
                    [uncommitted_artifact_path]
                    if uncommitted_artifact_path is not None
                    else []
                )
            )
        except asyncio.CancelledError:
            # A cancelled job without a result completes; it carries no transcript or artifact.
            async with self._lock:
                job = self._jobs.get(job_id)
                if job is not None and job.status not in TERMINAL_STATUSES:
                    self._transition_locked(job, InternalAudioJobState.COMPLETED)
                cleanup_paths = self._prune_terminal_jobs_locked()
            await self._delete_artifacts(
                cleanup_paths
                + (
                    [uncommitted_artifact_path]
                    if uncommitted_artifact_path is not None
                    else []
                )
            )
            raise
        except Exception as exc:
            reason = str(exc) if isinstance(exc, SpeechServiceError) else None
            logger.error(
                "Audio pipeline job %s failed (%s%s)",
                job_id,
                type(exc).__name__,
                f": {reason}" if reason else "",
            )
            async with self._lock:
                job = self._jobs.get(job_id)
                if job is not None and job.status not in TERMINAL_STATUSES:
                    job.error = "Audio pipeline execution failed."
                    self._transition_locked(job, InternalAudioJobState.FAILED)
                cleanup_paths = self._prune_terminal_jobs_locked()
            await self._delete_artifacts(
                cleanup_paths
                + (
                    [uncommitted_artifact_path]
                    if uncommitted_artifact_path is not None
                    else []
                )
            )
        finally:
            self._started_job_ids.discard(job_id)
            await self._delete_staged_input(stt_input)

    async def _execute_stt(
        self,
        device: str,
        stt_input: _StagedSTTInput | None,
        recording_input: InternalAudioPipelineRecordingInput | None,
    ) -> tuple[str, float]:
        """Open a registered recording or staged upload for the transcription callback.

        Registered input takes precedence when both inputs are supplied. Keep the
        file open throughout conversion and return text with round-trip time in
        milliseconds. Raise RuntimeError if no usable input remains.
        """
        if recording_input is not None:
            filename = recording_input.filename
            path = self.assets.get_path(filename)
            if path is None:
                raise RuntimeError("Selected audio recording became unavailable")
            content_type = "audio/wav"
            language = recording_input.language
        elif stt_input is not None:
            filename = stt_input.filename
            path = str(stt_input.path)
            content_type = stt_input.content_type
            language = stt_input.language
        else:
            raise RuntimeError("Speech-to-text job has no audio input")
        with open(path, "rb") as audio_file:
            transcript, duration = await self.transcribe(
                audio_file,
                filename,
                content_type,
                language,
                device,
            )
        return transcript, duration

    async def _execute_tts(
        self,
        job_id: str,
        device: str,
        *,
        input_text: str,
        voice: str,
    ) -> tuple[str, str, float]:
        """Synthesize speech and atomically publish its job-specific WAV file.

        Write through a temporary file in the output directory so readers never
        observe a partially written destination. Return its path, download
        filename, and service round-trip time in milliseconds.
        """
        content, duration = await self.synthesize(input_text, voice, device)
        output_directory = Path(self.assets.get_output_directory())
        output_directory.mkdir(parents=True, exist_ok=True)
        destination = output_directory / f"{job_id}.wav"
        temporary_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="wb",
                prefix=".audio-job-",
                suffix=".wav",
                dir=output_directory,
                delete=False,
            ) as temporary_file:
                temporary_path = Path(temporary_file.name)
                temporary_file.write(content)
            os.replace(temporary_path, destination)
            temporary_path = None
        finally:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)
        return str(destination), destination.name, duration

    @staticmethod
    def _transition_locked(
        job: InternalAudioPipelineJob,
        status: InternalAudioJobState,
    ) -> None:
        """Apply an allowed state transition and refresh its UTC timestamp.

        The caller must hold the manager lock. Invalid transitions raise
        RuntimeError rather than silently overwriting a terminal state.
        """
        if status not in _ALLOWED_TRANSITIONS.get(job.status, set()):
            raise RuntimeError(
                f"Invalid Audio job transition: {job.status} -> {status}"
            )
        job.status = status
        job.modified_at = datetime.now(timezone.utc)

    def _prune_terminal_jobs_locked(self) -> list[str]:
        """Evict the oldest terminal records and return artifacts to delete.

        The caller must hold the manager lock and delete the returned paths
        after releasing it. Active jobs do not count toward the retention limit.
        """
        terminal_jobs = sorted(
            (job for job in self._jobs.values() if job.status in TERMINAL_STATUSES),
            key=lambda candidate: candidate.modified_at,
            reverse=True,
        )
        artifact_paths: list[str] = []
        for job in terminal_jobs[self._max_terminal_jobs :]:
            removed = self._jobs.pop(job.id, None)
            if removed is not None and removed.artifact_path is not None:
                artifact_paths.append(removed.artifact_path)
        return artifact_paths

    async def _delete_artifacts(self, artifact_paths: list[str]) -> None:
        """Best-effort removal of artifacts confined to the configured output tree.

        Deduplicate paths, reject resolved locations outside the output directory,
        and log deletion failures without aborting job bookkeeping.
        """
        if not artifact_paths:
            return
        output_directory = Path(self.assets.get_output_directory()).resolve()
        for artifact_path in set(artifact_paths):
            candidate = Path(artifact_path).resolve()
            if candidate == output_directory or not candidate.is_relative_to(
                output_directory
            ):
                logger.warning(
                    "Refusing to delete Audio artifact outside output directory: %s",
                    candidate,
                )
                continue
            try:
                candidate.unlink(missing_ok=True)
            except OSError:
                logger.exception("Failed to delete Audio artifact %s", candidate)

    async def _delete_staged_input(
        self,
        staged_input: _StagedSTTInput | None,
    ) -> None:
        """Remove an owned staged upload in a worker thread, if one exists.

        Reject resolved paths outside the staging directory and log unlink
        failures without replacing the job's execution outcome.
        """
        if staged_input is None:
            return
        candidate = staged_input.path.resolve()
        if candidate == self._input_directory or not candidate.is_relative_to(
            self._input_directory
        ):
            logger.warning(
                "Refusing to delete staged Audio input outside its directory"
            )
            return
        try:
            await asyncio.to_thread(candidate.unlink, missing_ok=True)
        except OSError as exc:
            logger.error(
                "Failed to delete staged Audio input (%s)",
                type(exc).__name__,
            )

    def _on_task_done(
        self,
        job_id: str,
        task: asyncio.Task[None],
    ) -> None:
        """Observe task completion and retain the asynchronous bookkeeping cleanup.

        Keep a strong reference to the cleanup task until its callback runs so
        it cannot disappear before removing the completed execution task.
        """
        try:
            task.exception()
        except asyncio.CancelledError:
            pass
        cleanup_task = asyncio.create_task(self._remove_task(job_id, task))
        self._cleanup_tasks.add(cleanup_task)
        cleanup_task.add_done_callback(self._on_cleanup_done)

    def _on_cleanup_done(self, task: asyncio.Task[None]) -> None:
        """Release the cleanup-task reference and observe any failure safely.

        Retrieve exceptions to avoid unhandled-task warnings, but do not log
        exception details that might contain private data.
        """
        self._cleanup_tasks.discard(task)
        if not task.cancelled() and task.exception() is not None:
            logger.error("Failed to clean up Audio job task")

    async def _remove_task(
        self,
        job_id: str,
        task: asyncio.Task[None],
    ) -> None:
        """Remove a task reference only if it still belongs to this job entry."""
        async with self._lock:
            if self._tasks.get(job_id) is task:
                self._tasks.pop(job_id, None)

    async def get_job(self, job_id: str) -> InternalAudioPipelineJob | None:
        """Return a job snapshot, or None when unknown or already pruned."""
        async with self._lock:
            job = self._jobs.get(job_id)
            return replace(job) if job is not None else None

    async def cancel_job(self, job_id: str) -> InternalAudioPipelineJob:
        """Stop an active job and return its completed snapshot without a result.

        A task not yet started is allowed to enter execution and perform its own
        input cleanup rather than being cancelled before its finally block runs.

        Raises:
            AudioJobNotFoundError: The job is unknown or has been pruned.
            AudioJobNotRunningError: The job is already in a terminal state.
        """
        async with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                raise AudioJobNotFoundError(f"Audio pipeline job '{job_id}' not found.")
            if job.status in TERMINAL_STATUSES:
                raise AudioJobNotRunningError(
                    f"Audio pipeline job '{job_id}' is not running "
                    f"(state: {job.status.value})."
                )
            # A task that has not started would skip its own cleanup if cancelled.
            was_started = job_id in self._started_job_ids
            task = self._tasks.get(job_id)
            if not was_started or task is None:
                self._transition_locked(job, InternalAudioJobState.COMPLETED)
            cleanup_paths = self._prune_terminal_jobs_locked()
        await self._delete_artifacts(cleanup_paths)
        if task is not None:
            if was_started:
                task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        async with self._lock:
            return replace(job)

    async def list_jobs(self) -> list[InternalAudioPipelineJob]:
        """Return retained job snapshots in ascending creation-time order."""
        async with self._lock:
            return [
                replace(job)
                for job in sorted(
                    self._jobs.values(),
                    key=lambda candidate: candidate.created_at,
                )
            ]

    async def wait(self, job_id: str) -> None:
        """Wait for execution and remove its task reference without returning a result.

        Execution errors are reflected in the job state rather than re-raised.
        An unknown or already pruned job raises AudioJobNotFoundError.
        """
        async with self._lock:
            task = self._tasks.get(job_id)
            job = self._jobs.get(job_id)
        if task is None and job is None:
            raise AudioJobNotFoundError(f"Audio pipeline job '{job_id}' not found.")
        if task is None:
            return
        await asyncio.gather(task, return_exceptions=True)
        await self._remove_task(job_id, task)

    async def shutdown(self) -> None:
        """Complete active jobs, cancel executions, and release staging storage.

        Await execution and retained cleanup tasks before removing the temporary
        input directory. Artifacts of retained completed jobs are not deleted
        merely because the manager shuts down.
        """
        async with self._lock:
            tasks = list(self._tasks.items())
            for job in self._jobs.values():
                if job.status not in TERMINAL_STATUSES:
                    self._transition_locked(job, InternalAudioJobState.COMPLETED)
            cleanup_paths = self._prune_terminal_jobs_locked()
        await self._delete_artifacts(cleanup_paths)
        for _, task in tasks:
            task.cancel()
        await asyncio.gather(
            *(task for _, task in tasks),
            return_exceptions=True,
        )
        for job_id, task in tasks:
            await self._remove_task(job_id, task)
        await asyncio.gather(*self._cleanup_tasks, return_exceptions=True)
        await asyncio.to_thread(self._input_directory_owner.cleanup)

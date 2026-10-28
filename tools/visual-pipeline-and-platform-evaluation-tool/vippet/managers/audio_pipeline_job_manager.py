# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import asyncio
import logging
import os
import shutil
import tempfile
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import BinaryIO
from uuid import uuid4

from audio_assets import AudioAssetsManager
from managers.audio_pipeline_manager import (
    AudioDevice,
    AudioPipeline,
    AudioPipelineManager,
    AudioPipelineOperation,
)

logger = logging.getLogger("audio_pipeline_jobs")

Transcribe = Callable[[BinaryIO, str, str, str, str], Awaitable[tuple[str, float]]]
Synthesize = Callable[[str, str, str], Awaitable[tuple[bytes, float]]]

DEFAULT_MAX_TERMINAL_JOBS = 500


class AudioPipelineJobStatus(str, Enum):
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


TERMINAL_STATUSES = {
    AudioPipelineJobStatus.COMPLETED,
    AudioPipelineJobStatus.FAILED,
    AudioPipelineJobStatus.CANCELLED,
}

_ALLOWED_TRANSITIONS = {
    AudioPipelineJobStatus.QUEUED: {
        AudioPipelineJobStatus.RUNNING,
        AudioPipelineJobStatus.CANCELLED,
    },
    AudioPipelineJobStatus.RUNNING: {
        AudioPipelineJobStatus.COMPLETED,
        AudioPipelineJobStatus.FAILED,
        AudioPipelineJobStatus.CANCELLED,
    },
}


@dataclass
class AudioPipelineJob:
    id: str
    pipeline_id: str
    pipeline_name: str
    variant_id: str
    variant_name: str
    device: AudioDevice
    operation: AudioPipelineOperation
    status: AudioPipelineJobStatus
    created_at: datetime
    modified_at: datetime
    transcript: str | None = None
    artifact_path: str | None = None
    artifact_filename: str | None = None
    service_round_trip_ms: float | None = None
    error: str | None = None


@dataclass(frozen=True)
class AudioPipelineSTTInput:
    file: BinaryIO
    filename: str
    content_type: str
    language: str


@dataclass(frozen=True)
class AudioPipelineRecordingInput:
    filename: str
    language: str


@dataclass(frozen=True)
class _StagedSTTInput:
    path: Path
    filename: str
    content_type: str
    language: str


class AudioPipelineJobManager:
    def __init__(
        self,
        pipelines: AudioPipelineManager,
        assets: AudioAssetsManager,
        transcribe: Transcribe,
        synthesize: Synthesize,
        max_terminal_jobs: int = DEFAULT_MAX_TERMINAL_JOBS,
    ) -> None:
        if max_terminal_jobs < 0:
            raise ValueError("max_terminal_jobs must not be negative")
        self.pipelines = pipelines
        self.assets = assets
        self.transcribe = transcribe
        self.synthesize = synthesize
        self._jobs: dict[str, AudioPipelineJob] = {}
        self._tasks: dict[str, asyncio.Task[None]] = {}
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
        stt_input: AudioPipelineSTTInput | None = None,
        recording_input: AudioPipelineRecordingInput | None = None,
    ) -> AudioPipelineJob:
        pipeline = self.pipelines.get_pipeline(pipeline_id)
        if pipeline is None:
            raise ValueError(f"Audio pipeline '{pipeline_id}' not found.")
        if pipeline.operation is not AudioPipelineOperation.TEXT_TO_SPEECH and (
            input_text is not None or voice is not None
        ):
            raise ValueError("Speech-to-text pipelines do not accept TTS overrides.")
        if (
            pipeline.operation is not AudioPipelineOperation.SPEECH_TO_TEXT
            and stt_input is not None
        ):
            raise ValueError("Text-to-speech pipelines do not accept STT input.")
        if recording_input is not None:
            if pipeline.operation is not AudioPipelineOperation.SPEECH_TO_TEXT:
                raise ValueError(
                    "Text-to-speech pipelines do not accept recording input."
                )
            if self.assets.get_path(recording_input.filename) is None:
                raise ValueError(
                    f"Audio recording '{recording_input.filename}' not found."
                )
        if pipeline.operation is AudioPipelineOperation.SPEECH_TO_TEXT:
            if stt_input is None and recording_input is None:
                raise ValueError("Speech-to-text pipelines require audio input.")
        elif input_text is None or voice is None:
            raise ValueError("Text-to-speech pipelines require text and voice.")
        variant = next(
            (
                candidate
                for candidate in pipeline.variants
                if candidate.id == variant_id
            ),
            None,
        )
        if variant is None:
            raise ValueError(
                f"Audio pipeline '{pipeline_id}' variant '{variant_id}' not found."
            )
        now = datetime.now(timezone.utc)
        job = AudioPipelineJob(
            id=str(uuid4()),
            pipeline_id=pipeline.id,
            pipeline_name=pipeline.name,
            variant_id=variant.id,
            variant_name=variant.name,
            device=variant.device,
            operation=pipeline.operation,
            status=AudioPipelineJobStatus.QUEUED,
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
        source: AudioPipelineSTTInput,
    ) -> _StagedSTTInput:
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

    def _stage_stt_input(self, source: AudioPipelineSTTInput) -> _StagedSTTInput:
        destination = self._input_directory / f"{uuid4()}.upload"
        try:
            with destination.open("xb") as target:
                shutil.copyfileobj(source.file, target, length=1024 * 1024)
        except Exception:
            try:
                destination.unlink(missing_ok=True)
            except OSError:
                logger.error("Failed to remove incomplete staged Audio input")
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
        pipeline: AudioPipeline,
        *,
        input_text: str | None,
        voice: str | None,
        stt_input: _StagedSTTInput | None,
        recording_input: AudioPipelineRecordingInput | None = None,
    ) -> None:
        uncommitted_artifact_path: str | None = None
        try:
            async with self._lock:
                job = self._jobs.get(job_id)
                if job is None or job.status in TERMINAL_STATUSES:
                    return
                self._transition_locked(job, AudioPipelineJobStatus.RUNNING)
                device = job.device

            if pipeline.operation is AudioPipelineOperation.SPEECH_TO_TEXT:
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
                    self._transition_locked(job, AudioPipelineJobStatus.COMPLETED)
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
            async with self._lock:
                job = self._jobs.get(job_id)
                if job is not None and job.status not in TERMINAL_STATUSES:
                    self._transition_locked(job, AudioPipelineJobStatus.CANCELLED)
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
            logger.error(
                "Audio pipeline job %s failed (%s)",
                job_id,
                type(exc).__name__,
            )
            async with self._lock:
                job = self._jobs.get(job_id)
                if job is not None and job.status not in TERMINAL_STATUSES:
                    job.error = "Audio pipeline execution failed."
                    self._transition_locked(job, AudioPipelineJobStatus.FAILED)
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
            await self._delete_staged_input(stt_input)

    async def _execute_stt(
        self,
        device: str,
        stt_input: _StagedSTTInput | None,
        recording_input: AudioPipelineRecordingInput | None,
    ) -> tuple[str, float]:
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
        job: AudioPipelineJob,
        status: AudioPipelineJobStatus,
    ) -> None:
        if status not in _ALLOWED_TRANSITIONS.get(job.status, set()):
            raise RuntimeError(
                f"Invalid Audio job transition: {job.status} -> {status}"
            )
        job.status = status
        job.modified_at = datetime.now(timezone.utc)

    def _prune_terminal_jobs_locked(self) -> list[str]:
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
        try:
            task.exception()
        except asyncio.CancelledError:
            pass
        asyncio.create_task(self._remove_task(job_id, task))

    async def _remove_task(
        self,
        job_id: str,
        task: asyncio.Task[None],
    ) -> None:
        async with self._lock:
            if self._tasks.get(job_id) is task:
                self._tasks.pop(job_id, None)

    async def get_job(self, job_id: str) -> AudioPipelineJob | None:
        async with self._lock:
            job = self._jobs.get(job_id)
            return replace(job) if job is not None else None

    async def cancel_job(self, job_id: str) -> AudioPipelineJob:
        async with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                raise ValueError(f"Audio pipeline job '{job_id}' not found.")
            if job.status in TERMINAL_STATUSES:
                raise ValueError(
                    f"Audio pipeline job '{job_id}' is not running "
                    f"(state: {job.status.value})."
                )
            # A task that has not started would skip its own cleanup if cancelled.
            was_queued = job.status is AudioPipelineJobStatus.QUEUED
            self._transition_locked(job, AudioPipelineJobStatus.CANCELLED)
            cleanup_paths = self._prune_terminal_jobs_locked()
            task = self._tasks.get(job_id)
            snapshot = replace(job)
        await self._delete_artifacts(cleanup_paths)
        if task is not None:
            if not was_queued:
                task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        return snapshot

    async def list_jobs(self) -> list[AudioPipelineJob]:
        async with self._lock:
            return [
                replace(job)
                for job in sorted(
                    self._jobs.values(),
                    key=lambda candidate: candidate.created_at,
                )
            ]

    async def wait(self, job_id: str) -> None:
        async with self._lock:
            task = self._tasks.get(job_id)
            job = self._jobs.get(job_id)
        if task is None and job is None:
            raise ValueError(f"Audio pipeline job '{job_id}' not found.")
        if task is None:
            return
        await asyncio.gather(task, return_exceptions=True)
        await self._remove_task(job_id, task)

    async def shutdown(self) -> None:
        async with self._lock:
            tasks = list(self._tasks.items())
            for job in self._jobs.values():
                if job.status not in TERMINAL_STATUSES:
                    self._transition_locked(job, AudioPipelineJobStatus.CANCELLED)
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
        await asyncio.to_thread(self._input_directory_owner.cleanup)

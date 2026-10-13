# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import asyncio
import logging
import os
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

Transcribe = Callable[
    [BinaryIO, str, str, str, str | None], Awaitable[tuple[str, float]]
]
Synthesize = Callable[[str, str, str | None], Awaitable[tuple[bytes, float]]]

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

    async def start_job(
        self,
        pipeline_id: str,
        variant_id: str | None = None,
        *,
        input_text: str | None = None,
        voice: str | None = None,
    ) -> AudioPipelineJob:
        pipeline = self.pipelines.get_pipeline(pipeline_id)
        if pipeline is None:
            raise ValueError(f"Audio pipeline '{pipeline_id}' not found.")
        if not pipeline.available:
            raise ValueError(f"Audio pipeline '{pipeline_id}' is unavailable.")
        if pipeline.operation is not AudioPipelineOperation.TEXT_TO_SPEECH and (
            input_text is not None or voice is not None
        ):
            raise ValueError("Speech-to-text pipelines do not accept TTS overrides.")
        variant = (
            pipeline.variants[0]
            if variant_id is None
            else next(
                (
                    candidate
                    for candidate in pipeline.variants
                    if candidate.id == variant_id
                ),
                None,
            )
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
        async with self._lock:
            self._jobs[job.id] = job
            task = asyncio.create_task(
                self._execute(
                    job.id,
                    pipeline,
                    input_text=input_text,
                    voice=voice,
                )
            )
            self._tasks[job.id] = task
            task.add_done_callback(
                lambda completed, job_id=job.id: self._on_task_done(job_id, completed)
            )
        return replace(job)

    async def _execute(
        self,
        job_id: str,
        pipeline: AudioPipeline,
        *,
        input_text: str | None,
        voice: str | None,
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
                transcript, duration = await self._execute_stt(pipeline, device)
                artifact_path = None
                artifact_filename = None
            else:
                artifact_path, artifact_filename, duration = await self._execute_tts(
                    job_id,
                    pipeline,
                    device,
                    input_text=input_text,
                    voice=voice,
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
        except Exception:
            logger.exception("Audio pipeline job %s failed", job_id)
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

    async def _execute_stt(
        self,
        pipeline: AudioPipeline,
        device: str,
    ) -> tuple[str, float]:
        defaults = pipeline.defaults
        filename = defaults.audio or ""
        path = self.assets.get_path(filename)
        if path is None:
            raise RuntimeError("Default audio input became unavailable")
        with open(path, "rb") as audio_file:
            transcript, duration = await self.transcribe(
                audio_file,
                filename,
                "audio/wav",
                defaults.language or "en",
                device,
            )
        return transcript, duration

    async def _execute_tts(
        self,
        job_id: str,
        pipeline: AudioPipeline,
        device: str,
        *,
        input_text: str | None,
        voice: str | None,
    ) -> tuple[str, str, float]:
        defaults = pipeline.defaults
        content, duration = await self.synthesize(
            input_text if input_text is not None else defaults.text or "",
            voice if voice is not None else defaults.voice or "Ryan",
            device,
        )
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

    async def list_jobs(self) -> list[AudioPipelineJob]:
        async with self._lock:
            return [
                replace(job)
                for job in sorted(
                    self._jobs.values(),
                    key=lambda candidate: candidate.created_at,
                    reverse=True,
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

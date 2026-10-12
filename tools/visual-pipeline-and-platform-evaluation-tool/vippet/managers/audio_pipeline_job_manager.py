# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import asyncio
import logging
import os
import tempfile
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import BinaryIO
from uuid import uuid4

from audio_assets import AudioAssetsManager
from managers.audio_pipeline_manager import (
    AudioPipeline,
    AudioPipelineManager,
    AudioPipelineOperation,
)

logger = logging.getLogger("audio_pipeline_jobs")

Transcribe = Callable[
    [BinaryIO, str, str, str, str | None], Awaitable[tuple[str, float]]
]
Synthesize = Callable[[str, str, str | None], Awaitable[tuple[bytes, float]]]


class AudioPipelineJobStatus(str, Enum):
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


@dataclass
class AudioPipelineJob:
    id: str
    pipeline_id: str
    pipeline_name: str
    variant_id: str
    variant_name: str
    device: str
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
    ) -> None:
        self.pipelines = pipelines
        self.assets = assets
        self.transcribe = transcribe
        self.synthesize = synthesize
        self._jobs: dict[str, AudioPipelineJob] = {}
        self._tasks: dict[str, asyncio.Task[None]] = {}

    def start_job(
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
        self._jobs[job.id] = job
        self._tasks[job.id] = asyncio.create_task(
            self._execute(job, pipeline, input_text=input_text, voice=voice)
        )
        return job

    async def _execute(
        self,
        job: AudioPipelineJob,
        pipeline: AudioPipeline,
        *,
        input_text: str | None,
        voice: str | None,
    ) -> None:
        self._set_status(job, AudioPipelineJobStatus.RUNNING)
        try:
            if pipeline.operation is AudioPipelineOperation.SPEECH_TO_TEXT:
                await self._execute_stt(job, pipeline)
            else:
                await self._execute_tts(
                    job,
                    pipeline,
                    input_text=input_text,
                    voice=voice,
                )
            self._set_status(job, AudioPipelineJobStatus.COMPLETED)
        except Exception:
            logger.exception("Audio pipeline job %s failed", job.id)
            job.error = "Audio pipeline execution failed."
            self._set_status(job, AudioPipelineJobStatus.FAILED)

    async def _execute_stt(
        self,
        job: AudioPipelineJob,
        pipeline: AudioPipeline,
    ) -> None:
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
                job.device,
            )
        job.transcript = transcript
        job.service_round_trip_ms = duration

    async def _execute_tts(
        self,
        job: AudioPipelineJob,
        pipeline: AudioPipeline,
        *,
        input_text: str | None,
        voice: str | None,
    ) -> None:
        defaults = pipeline.defaults
        content, duration = await self.synthesize(
            input_text if input_text is not None else defaults.text or "",
            voice if voice is not None else defaults.voice or "Ryan",
            job.device,
        )
        output_directory = Path(self.assets.get_output_directory())
        output_directory.mkdir(parents=True, exist_ok=True)
        destination = output_directory / f"{job.id}.wav"
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
        job.artifact_path = str(destination)
        job.artifact_filename = destination.name
        job.service_round_trip_ms = duration

    @staticmethod
    def _set_status(
        job: AudioPipelineJob,
        status: AudioPipelineJobStatus,
    ) -> None:
        job.status = status
        job.modified_at = datetime.now(timezone.utc)

    def get_job(self, job_id: str) -> AudioPipelineJob | None:
        return self._jobs.get(job_id)

    async def wait(self, job_id: str) -> None:
        task = self._tasks.get(job_id)
        if task is None:
            raise ValueError(f"Audio pipeline job '{job_id}' not found.")
        await task

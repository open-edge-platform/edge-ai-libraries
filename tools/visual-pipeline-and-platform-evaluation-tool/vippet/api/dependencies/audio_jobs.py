# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from collections.abc import Callable

from managers.audio_pipeline_job_manager import AudioPipelineJobManager

AudioJobManagerFactory = Callable[[], AudioPipelineJobManager]

_factory: AudioJobManagerFactory | None = None
_manager: AudioPipelineJobManager | None = None


def configure_audio_pipeline_job_manager_factory(
    factory: AudioJobManagerFactory,
) -> None:
    global _factory
    _factory = factory


def get_audio_pipeline_job_manager() -> AudioPipelineJobManager:
    global _manager
    if _manager is None:
        if _factory is None:
            raise RuntimeError("Audio pipeline job manager is not configured")
        _manager = _factory()
    return _manager


async def shutdown_audio_pipeline_job_manager() -> None:
    if _manager is not None:
        await _manager.shutdown()


def _reset_audio_pipeline_job_manager_for_tests() -> None:
    global _factory, _manager
    _factory = None
    _manager = None

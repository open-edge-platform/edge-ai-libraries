# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0


class SpeechServiceError(RuntimeError):
    """A speech service failed with a sanitized, safe-to-log message."""


class SampleAudioDownloadError(RuntimeError):
    """An allowlisted sample could not be downloaded or validated."""


class SampleAudioDownloadTimeoutError(SampleAudioDownloadError):
    """An allowlisted sample download exceeded its deadline."""


class SampleAudioStorageError(RuntimeError):
    """A downloaded sample could not be installed locally."""


class AudioPipelineError(ValueError):
    """An audio pipeline operation cannot be performed."""


class AudioPipelineNotFoundError(AudioPipelineError):
    pass


class AudioPipelineVariantNotFoundError(AudioPipelineError):
    pass


class AudioRecordingNotFoundError(AudioPipelineError):
    pass


class AudioTTSInputNotAcceptedError(AudioPipelineError):
    pass


class AudioSTTInputNotAcceptedError(AudioPipelineError):
    pass


class AudioRecordingInputNotAcceptedError(AudioPipelineError):
    pass


class AudioInputTooLargeError(AudioPipelineError):
    pass


class AudioJobNotFoundError(AudioPipelineError):
    pass


class AudioJobNotRunningError(AudioPipelineError):
    pass

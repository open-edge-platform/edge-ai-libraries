# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0


class SpeechServiceError(RuntimeError):
    """A speech service failed with a sanitized, safe-to-log message."""


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

# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
"""PCM16 buffering, WAV serialization, and energy-based voice activity detection.

Used by the realtime WebSocket transcription endpoint
(``api/realtime_endpoints.py``) to turn a continuous push-based audio stream
into silence-bounded utterances that the existing ffmpeg/ASR pipeline can
transcribe.

Audio is handled as signed 16-bit little-endian PCM (``pcm16``), which is the
format OpenAI's Realtime API uses. Buffers are kept at the client's declared
sample rate; downstream ffmpeg/Whisper resample to 16 kHz as needed, so no
resampling is performed here.
"""
from __future__ import annotations

import wave

import numpy as np

BYTES_PER_SAMPLE = 2
DEFAULT_SAMPLE_RATE = 16000
DEFAULT_CHANNELS = 1

# Energy VAD defaults. `threshold` is normalized RMS in 0..1 (not OpenAI's
# VAD probability) — 0.02 reliably separates speech from room tone while
# staying permissive enough for quiet talkers.
DEFAULT_VAD_THRESHOLD = 0.02
DEFAULT_SILENCE_DURATION_MS = 500
DEFAULT_PREFIX_PADDING_MS = 300
FRAME_MS = 30


def write_wav(path: str, pcm_bytes: bytes, sample_rate: int, channels: int = DEFAULT_CHANNELS) -> str:
    """Write raw PCM16 bytes to a WAV container at `path`."""
    with wave.open(path, "wb") as handle:
        handle.setnchannels(channels)
        handle.setsampwidth(BYTES_PER_SAMPLE)
        handle.setframerate(sample_rate)
        handle.writeframes(pcm_bytes)
    return path


def pcm_duration_sec(pcm_bytes: bytes, sample_rate: int, channels: int = DEFAULT_CHANNELS) -> float:
    if sample_rate <= 0 or channels <= 0:
        return 0.0
    frames = len(pcm_bytes) / (BYTES_PER_SAMPLE * channels)
    return frames / float(sample_rate)


def _normalized_rms(frame: bytes) -> float:
    """RMS of a PCM16 frame normalized to 0..1."""
    if not frame:
        return 0.0
    # Trim to a whole number of samples; a partial trailing sample would
    # otherwise raise inside frombuffer.
    usable = len(frame) - (len(frame) % BYTES_PER_SAMPLE)
    if usable <= 0:
        return 0.0
    samples = np.frombuffer(frame[:usable], dtype="<i2").astype(np.float32)
    if samples.size == 0:
        return 0.0
    return float(np.sqrt(np.mean(np.square(samples))) / 32768.0)


class EnergyVad:
    """Streaming energy-based speech/silence detector over PCM16.

    Emits ``speech_started`` once audio rises above `threshold`, and
    ``speech_stopped`` after `silence_duration_ms` of continuous sub-threshold
    audio. This mirrors the semantics of OpenAI's ``server_vad`` turn
    detection closely enough for drop-in client compatibility.
    """

    def __init__(
        self,
        sample_rate: int = DEFAULT_SAMPLE_RATE,
        threshold: float = DEFAULT_VAD_THRESHOLD,
        silence_duration_ms: int = DEFAULT_SILENCE_DURATION_MS,
        prefix_padding_ms: int = DEFAULT_PREFIX_PADDING_MS,
    ):
        self.sample_rate = sample_rate
        self.threshold = threshold
        self.silence_duration_ms = silence_duration_ms
        self.prefix_padding_ms = prefix_padding_ms
        self.frame_bytes = max(
            BYTES_PER_SAMPLE,
            int(sample_rate * (FRAME_MS / 1000.0)) * BYTES_PER_SAMPLE,
        )
        self._residual = b""
        self.speech_active = False
        self._silence_ms = 0.0
        self._speech_ms = 0.0

    def reset(self) -> None:
        self._residual = b""
        self.speech_active = False
        self._silence_ms = 0.0
        self._speech_ms = 0.0

    def process(self, pcm_bytes: bytes) -> list[str]:
        """Feed audio; return ordered events ('speech_started'/'speech_stopped')."""
        events: list[str] = []
        buffer = self._residual + pcm_bytes
        offset = 0

        while len(buffer) - offset >= self.frame_bytes:
            frame = buffer[offset:offset + self.frame_bytes]
            offset += self.frame_bytes
            is_speech = _normalized_rms(frame) >= self.threshold

            if is_speech:
                self._silence_ms = 0.0
                self._speech_ms += FRAME_MS
                if not self.speech_active and self._speech_ms >= FRAME_MS:
                    self.speech_active = True
                    events.append("speech_started")
            else:
                if self.speech_active:
                    self._silence_ms += FRAME_MS
                    if self._silence_ms >= self.silence_duration_ms:
                        self.speech_active = False
                        self._speech_ms = 0.0
                        self._silence_ms = 0.0
                        events.append("speech_stopped")
                else:
                    self._speech_ms = 0.0

        self._residual = buffer[offset:]
        return events


class PcmStreamBuffer:
    """Accumulates PCM16 audio for the current (uncommitted) utterance."""

    def __init__(self, sample_rate: int = DEFAULT_SAMPLE_RATE, channels: int = DEFAULT_CHANNELS):
        self.sample_rate = sample_rate
        self.channels = channels
        self._chunks: list[bytes] = []
        self._size = 0

    def append(self, pcm_bytes: bytes) -> None:
        if pcm_bytes:
            self._chunks.append(pcm_bytes)
            self._size += len(pcm_bytes)

    @property
    def size(self) -> int:
        return self._size

    @property
    def duration_sec(self) -> float:
        return pcm_duration_sec(b"".join(self._chunks), self.sample_rate, self.channels)

    def clear(self) -> None:
        self._chunks = []
        self._size = 0

    def take(self) -> bytes:
        """Return and clear the buffered audio."""
        data = b"".join(self._chunks)
        self.clear()
        return data

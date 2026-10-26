"""Zero-subprocess inspection of uncompressed WAV files.

Every request to /v1/audio/transcriptions used to spawn several ffmpeg/ffprobe
processes purely to answer questions the RIFF header already contains ("is this
audio?", "how long is it?", "what sample rate?"). For the short (1-2s) chunks
that streaming clients post on every turn, those spawns cost more wall-clock
than the transcription itself. Reading the header directly removes them.

Callers must treat ``None`` as "not an uncompressed WAV" and fall back to
ffprobe/ffmpeg — this module deliberately understands only the one format that
matters on the hot path.
"""

from __future__ import annotations

import logging
import os
import wave
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# Format the ASR backends expect.
TARGET_SAMPLE_RATE = 16000
TARGET_CHANNELS = 1
TARGET_SAMPLE_WIDTH = 2  # bytes — pcm_s16le


@dataclass(frozen=True)
class WavInfo:
    """Header facts about an uncompressed PCM WAV file."""

    duration_seconds: float
    sample_rate: int
    channels: int
    sample_width: int

    def matches_target_format(self) -> bool:
        """True when no resample/downmix/re-encode pass is needed."""
        return (
            self.sample_rate == TARGET_SAMPLE_RATE
            and self.channels == TARGET_CHANNELS
            and self.sample_width == TARGET_SAMPLE_WIDTH
        )


def _find_data_chunk_offset(audio_path: str) -> int | None:
    """Return the absolute byte offset of the ``data`` chunk's payload.

    A minimal RIFF walk, used instead of ``wave.Wave_read._data_chunk`` so this
    module does not depend on a private CPython attribute whose meaning (an
    offset relative to the enclosing RIFF chunk, not the file) is both
    undocumented and easy to misread.

    Args:
        audio_path: Path to the candidate WAV file.

    Returns:
        The offset just past the ``data`` chunk header, or ``None`` when the
        file is not RIFF/WAVE or has no ``data`` chunk.
    """
    with open(audio_path, "rb") as handle:
        header = handle.read(12)
        if len(header) < 12 or header[0:4] != b"RIFF" or header[8:12] != b"WAVE":
            return None
        offset = 12
        while True:
            handle.seek(offset)
            chunk_header = handle.read(8)
            if len(chunk_header) < 8:
                return None
            chunk_id = chunk_header[0:4]
            chunk_size = int.from_bytes(chunk_header[4:8], "little")
            payload_start = offset + 8
            if chunk_id == b"data":
                return payload_start
            # RIFF chunks are word-aligned: an odd size is followed by a pad byte.
            offset = payload_start + chunk_size + (chunk_size % 2)


def read_pcm_wav_info(audio_path: str) -> WavInfo | None:
    """Return header facts for an uncompressed WAV, or ``None`` if unreadable.

    The frame count is clamped to the bytes actually present on disk rather
    than trusted from the ``data`` chunk header. Two real cases make the
    declared size unreliable, and both used to be handled implicitly by
    ffprobe (which clamps to file size):

    * ffmpeg writes ``0xFFFFFFFF`` as a placeholder RIFF/data size while a
      recording is still in progress and only backfills the true size on
      close. ``chunk_audiostream_by_silence`` reads exactly such a file while
      ffmpeg is still writing it, so an unclamped read reports ~134,000 s and
      the chunking loop cuts at timestamps that have not been recorded yet.
    * A truncated or hand-crafted upload can declare any size at all. Since
      ``_audio_stream_exists`` now accepts a readable PCM WAV without probing,
      an unclamped duration would drive thousands of ffmpeg spawns in
      ``chunk_audio_by_silence``.

    Args:
        audio_path: Path to the candidate audio file.

    Returns:
        A ``WavInfo`` when the file is a readable uncompressed (PCM) WAV with a
        non-zero frame count, otherwise ``None``.
    """
    if not str(audio_path).lower().endswith(".wav"):
        return None
    try:
        with wave.open(audio_path, "rb") as wav_file:
            if wav_file.getcomptype() != "NONE":
                return None
            sample_rate = wav_file.getframerate()
            frame_count = wav_file.getnframes()
            channels = wav_file.getnchannels()
            sample_width = wav_file.getsampwidth()
            if not sample_rate or not frame_count or not channels or not sample_width:
                return None
            # Clamp to what is actually readable on disk, since the declared
            # data-chunk size is not trustworthy (see the docstring above).
            frame_bytes = channels * sample_width
            data_start = _find_data_chunk_offset(audio_path)
            if data_start is None:
                return None
            available_frames = max(os.path.getsize(audio_path) - data_start, 0) // frame_bytes
            frame_count = min(frame_count, available_frames)
            if not frame_count:
                return None
            return WavInfo(
                duration_seconds=frame_count / float(sample_rate),
                sample_rate=sample_rate,
                channels=channels,
                sample_width=sample_width,
            )
    except (wave.Error, EOFError, OSError) as exc:
        logger.debug("WAV header read failed for %s (%s); caller must fall back", audio_path, exc)
        return None

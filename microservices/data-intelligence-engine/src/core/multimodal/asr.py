# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
"""Speech recognition: an audio file in, timed text segments out.

Not an embedding model, and so not in the multimodal registry. What it produces
is text -- `l2_transcript` blocks (`transcription.py`) -- and it is whichever
source takes derived text (GME) that turns those into vectors. A recording is
therefore found by what was *said* in it, through the same text tower a query
goes through.

Configured like every other model (`config.ASR_*`): a runtime, a Hugging Face
id, a local path, a device. Only `openvino` is implemented. The path may hold
prepared OpenVINO IR directly or under `<path>/openvino`. Download and export
the model, processor, and tokenizer beforehand; this runtime never prepares it.

Three things hold for every result:

1. **Segments are in time order and carry their range**, in seconds, so a block
   cut from them can say where in the recording it is.
2. **Audio is decoded by ffmpeg**, to 16 kHz mono float32, which is what
   Whisper's feature extractor expects. ffprobe is already required for video
   durations; ffmpeg ships with it, so no audio library is added.
3. **Long audio is cut here, not by Whisper's timestamps**, at two levels. A
   *segment* -- one transcript block -- is at most `ENGINE_ASR_SEGMENT_SECONDS`
   (default 30 s); within it, each *window* handed to the model is at most
   30 s, which is what Whisper sees at once, and the windows' text is joined
   back into the segment. Every cut ends at the quietest moment of the last few
   seconds before the limit, so it rarely lands mid-word, and a segment's range
   is exact. The pipeline's own timestamp mode was tried and rejected: on
   unpunctuated Mandarin it emitted one "segment" for most of a recording and
   looped on its text.

The runtime is not thread-safe and one instance is shared, so calls are locked.
"""

import subprocess
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, List, Optional, Tuple

import config

SAMPLE_RATE = 16000
# Whisper sees 30 s at a time; a window never exceeds it. A segment (one
# transcript block) is `config.ASR_SEGMENT_SECONDS` and may hold several.
WINDOW_SECONDS = 30.0
# How far back from a window's end to look for a quiet place to cut.
_SEARCH_SECONDS = 5.0
_FRAME_SECONDS = 0.1
# Less than this is not worth a pass through the model.
_MIN_WINDOW_SECONDS = 0.2
_IR_SUBDIR = "openvino"
_IR_FILES = ("openvino_encoder_model.xml", "openvino_decoder_model.xml")


class TranscriptionError(RuntimeError):
    """The audio could not be decoded or the model could not be run."""


@dataclass(frozen=True)
class Segment:
    """One stretch of recognized speech."""

    start_s: float
    end_s: float
    text: str


def find_ir_dir(model_path: str) -> Optional[Path]:
    """Where the exported IR is: the path itself, or its `openvino/`, if either."""
    root = Path(model_path)
    for candidate in (root, root / _IR_SUBDIR):
        if all(
            (candidate / name).is_file()
            and (candidate / name).with_suffix(".bin").is_file()
            for name in _IR_FILES
        ):
            return candidate
    return None


def decode_audio(path: str) -> Any:
    """The audio at `path` as a 16 kHz mono float32 array."""
    import numpy as np  # noqa: PLC0415

    try:
        completed = subprocess.run(
            [
                "ffmpeg", "-nostdin", "-v", "error", "-i", path,
                "-f", "f32le", "-ac", "1", "-ar", str(SAMPLE_RATE), "-",
            ],
            capture_output=True,
            check=True,
        )
    except FileNotFoundError as error:
        raise TranscriptionError("ffmpeg is not installed") from error
    except subprocess.CalledProcessError as error:
        message = error.stderr.decode("utf-8", "replace").strip()
        raise TranscriptionError(f"ffmpeg could not decode {path!r}: {message}") from error
    return np.frombuffer(completed.stdout, dtype=np.float32)


def windows(
    audio: Any, sample_rate: int = SAMPLE_RATE, max_seconds: float = WINDOW_SECONDS
) -> List[Tuple[int, int]]:
    """`(start, end)` sample ranges covering `audio`, each at most `max_seconds`.

    A range that has to be cut is cut at the quietest frame of its last few
    seconds rather than at exactly the limit.
    """
    import numpy as np  # noqa: PLC0415

    total = int(audio.size)
    limit = max(1, int(max_seconds * sample_rate))
    search = min(int(_SEARCH_SECONDS * sample_rate), limit // 2)
    frame = max(1, int(_FRAME_SECONDS * sample_rate))
    ranges: List[Tuple[int, int]] = []
    start = 0
    while start < total:
        end = start + limit
        if end >= total:
            end = total
        else:
            region = audio[end - search:end]
            frames = region[: (region.size // frame) * frame].reshape(-1, frame)
            if frames.size:
                loudness = np.sqrt((frames ** 2).mean(axis=1))
                # Ties go to the latest frame, so even loudness costs no length.
                quietest = len(loudness) - 1 - int(np.argmin(loudness[::-1]))
                end = end - search + quietest * frame + frame // 2
        if end - start >= _MIN_WINDOW_SECONDS * sample_rate:
            ranges.append((start, end))
        start = end
    return ranges


class WhisperOpenVINO:
    """Whisper through optimum-intel, wrapped in the transformers ASR pipeline."""

    def __init__(
        self,
        model_path: str,
        model_id: Optional[str] = None,
        device: str = "CPU",
        language: Optional[str] = None,
        prompt: Optional[str] = None,
        segment_seconds: float = WINDOW_SECONDS,
    ):
        self.model_path = str(model_path)
        self.model_id = model_id
        self.device = (device or "CPU").upper()
        self.language = language or None
        if segment_seconds <= 0:
            raise ValueError(f"segment_seconds must be positive, got {segment_seconds}")
        self.segment_seconds = float(segment_seconds)
        ir_dir = find_ir_dir(self.model_path)
        if ir_dir is None:
            raise FileNotFoundError(
                f"No prepared Whisper OpenVINO model at {self.model_path!r}. "
                "Prepare the encoder/decoder XML and BIN files and the processor "
                "and tokenizer before starting the engine. The engine does not "
                "download or export models."
            )
        from optimum.intel import OVModelForSpeechSeq2Seq  # noqa: PLC0415
        from transformers import AutoProcessor, pipeline  # noqa: PLC0415

        processor = AutoProcessor.from_pretrained(str(ir_dir), local_files_only=True)
        model = OVModelForSpeechSeq2Seq.from_pretrained(
            str(ir_dir), device=self.device, local_files_only=True, export=False
        )
        self._pipeline = pipeline(
            "automatic-speech-recognition",
            model=model,
            tokenizer=processor.tokenizer,
            feature_extractor=processor.feature_extractor,
        )
        # Text Whisper conditions on as if it had just heard it. Steers script
        # and style -- simplified rather than traditional Chinese, punctuation
        # -- and is not part of the output.
        self._prompt_ids = (
            processor.tokenizer.get_prompt_ids(prompt, return_tensors="pt")
            if prompt
            else None
        )
        self._lock = threading.Lock()

    def transcribe(self, path: str) -> List[Segment]:
        audio = decode_audio(path)
        generate_kwargs: dict = {"task": "transcribe"}
        if self.language:
            generate_kwargs["language"] = self.language
        if self._prompt_ids is not None:
            generate_kwargs["prompt_ids"] = self._prompt_ids
        segments: List[Segment] = []
        for start, end in windows(audio, max_seconds=self.segment_seconds):
            piece = audio[start:end]
            texts = []
            for low, high in windows(piece, max_seconds=WINDOW_SECONDS):
                with self._lock:
                    result = self._pipeline(
                        {"raw": piece[low:high], "sampling_rate": SAMPLE_RATE},
                        generate_kwargs=generate_kwargs,
                    )
                texts.append(str(result.get("text") or "").strip())
            text = join_text(texts)
            if text:
                segments.append(
                    Segment(start / SAMPLE_RATE, end / SAMPLE_RATE, text)
                )
        return segments


def join_text(texts: Iterable[str]) -> str:
    """Windows' text as one passage: no space between CJK, one elsewhere."""
    joined = ""
    for text in texts:
        if not text:
            continue
        if joined and not (_is_cjk(joined[-1]) or _is_cjk(text[0])):
            joined += " "
        joined += text
    return joined


def _is_cjk(char: str) -> bool:
    code = ord(char)
    return (
        0x3000 <= code <= 0x30FF      # CJK punctuation, kana
        or 0x3400 <= code <= 0x9FFF   # CJK ideographs
        or 0xAC00 <= code <= 0xD7AF   # Hangul
        or 0xFF00 <= code <= 0xFFEF   # full-width forms
    )


_INSTANCE_LOCK = threading.Lock()
_INSTANCE: Optional[WhisperOpenVINO] = None


def get_transcriber() -> WhisperOpenVINO:
    """The engine's speech recognizer, built once from `config.ASR_*`."""
    global _INSTANCE
    with _INSTANCE_LOCK:
        if _INSTANCE is None:
            if config.ASR_BACKEND != "openvino":
                raise TranscriptionError(
                    f"ENGINE_ASR_BACKEND={config.ASR_BACKEND!r} is not supported; "
                    "speech recognition runs on openvino"
                )
            from core.multimodal.registry import local_path  # noqa: PLC0415

            _INSTANCE = WhisperOpenVINO(
                model_path=str(local_path(config.ASR_MODEL_PATH)),
                model_id=config.ASR_MODEL_ID,
                device=config.ASR_DEVICE,
                language=config.ASR_LANGUAGE,
                prompt=config.ASR_PROMPT,
                segment_seconds=config.ASR_SEGMENT_SECONDS,
            )
        return _INSTANCE


__all__ = [
    "SAMPLE_RATE",
    "Segment",
    "TranscriptionError",
    "WINDOW_SECONDS",
    "WhisperOpenVINO",
    "decode_audio",
    "find_ir_dir",
    "get_transcriber",
    "join_text",
    "windows",
]

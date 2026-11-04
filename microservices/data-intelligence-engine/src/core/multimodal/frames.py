# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
"""Turning a clip into the fixed number of frames a video encoder expects.

Sampling is uniform across the whole clip rather than at a fixed rate, because
the encoder takes a fixed count: a rate would make the span covered depend on
the video's length, so a 10-second clip and a 50-second clip would be described
by different amounts of it. Uniform sampling describes all of both.

A clip shorter than the frame count is padded by repeating its own frames in
order, not by appending blanks. The temporal model reads the sequence as
motion, and blank frames read as the scene ending.
"""

import os
import tempfile
from typing import Any, List, Optional, Sequence


def sample_frames(path: str, count: int = 32) -> List[Any]:
    """`count` PIL images spanning the whole of the video at `path`.

    Decoded by index rather than by sequential read: a 60-second clip holds
    well over a thousand frames and all but `count` of them would be decoded
    and thrown away.
    """
    import cv2  # noqa: PLC0415 - heavy, and only this path needs it
    from PIL import Image  # noqa: PLC0415

    if count <= 0:
        raise ValueError(f"Frame count must be positive, got {count}")
    capture = cv2.VideoCapture(path)
    if not capture.isOpened():
        raise ValueError(f"Could not open video file {path!r}")
    try:
        total = int(capture.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        frames: List[Any] = []
        if total > 0:
            for index in _indices(total, count):
                capture.set(cv2.CAP_PROP_POS_FRAMES, index)
                ok, frame = capture.read()
                if ok:
                    frames.append(Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)))
        if not frames:
            # Either the container did not report a frame count, or seeking did
            # not work on it. Reading straight through is slower but always
            # works, and a clip we are here for is short.
            frames = _read_through(capture, count)
    finally:
        capture.release()
    if not frames:
        raise ValueError(f"No frames could be decoded from {path!r}")
    return pad_to(frames, count)


def _indices(total: int, count: int) -> List[int]:
    """`count` indices spread evenly over `[0, total)`, duplicates allowed.

    Duplicates are how a clip with fewer frames than `count` still produces a
    full sequence -- the same answer `pad_to` would give, arrived at without a
    second pass.
    """
    if total <= 1:
        return [0] * count
    step = (total - 1) / max(1, count - 1) if count > 1 else 0
    return [min(total - 1, int(round(position * step))) for position in range(count)]


def _read_through(capture, count: int) -> List[Any]:
    import cv2  # noqa: PLC0415
    from PIL import Image  # noqa: PLC0415

    capture.set(cv2.CAP_PROP_POS_FRAMES, 0)
    decoded = []
    while True:
        ok, frame = capture.read()
        if not ok:
            break
        decoded.append(Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)))
    if not decoded:
        return []
    return [decoded[index] for index in _indices(len(decoded), count)]


def pad_to(frames: Sequence[Any], count: int) -> List[Any]:
    """Exactly `count` frames: truncated, or cycled until long enough."""
    frames = list(frames)
    if not frames:
        return []
    if len(frames) >= count:
        return frames[:count]
    return [frames[index % len(frames)] for index in range(count)]


def materialize(data: bytes, suffix: str = ".mp4") -> str:
    """Media bytes as a file path, because the decoders only take paths.

    The caller removes it -- see `discard`. Content lives in an object store and
    a projection holds it as bytes, but OpenCV and ffprobe both want something
    seekable on disk.
    """
    handle, path = tempfile.mkstemp(suffix=suffix, prefix="engine-media-")
    try:
        with os.fdopen(handle, "wb") as file:
            file.write(data)
    except Exception:
        discard(path)
        raise
    return path


def discard(path: Optional[str]) -> None:
    """Remove a temporary file, if it is still there."""
    if not path:
        return
    try:
        os.unlink(path)
    except OSError:
        pass


__all__ = ["discard", "materialize", "pad_to", "sample_frames"]

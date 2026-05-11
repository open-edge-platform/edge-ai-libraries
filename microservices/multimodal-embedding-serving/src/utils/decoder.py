# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
Video Frame Extraction Utility for data preparation
Provides efficient, batched video frame extraction from various sources (files, RTSP streams, bytes) using PyAV.
"""

from __future__ import annotations

import ast
import io
import os
import queue
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
from dataclasses import dataclass
from dataclasses import field
from enum import Enum
from fractions import Fraction
from multiprocessing import shared_memory
from typing import Any
from typing import Dict
from typing import Generator
from typing import List
from typing import Tuple
from typing import Union

import av
import numpy as np
from PIL import Image

from .common import logger

INTERRUPT = object()  # interrupt signal (unique, non-colliding)
DONE = object()  # consumer → main completion signal


def _get_video_config():
    """Lazy load video configuration to avoid circular imports."""
    try:
        from .common import settings

        return settings
    except ImportError:

        class FallbackSettings:
            VIDEO_FRAME_LOG_LEVEL = os.getenv("VIDEO_FRAME_LOG_LEVEL", "INFO")
            VIDEO_FRAME_DECODER_WORKERS = int(
                os.getenv("VIDEO_FRAME_DECODER_WORKERS", "8")
            )
            VIDEO_FRAME_BATCH_SIZE = int(os.getenv("VIDEO_FRAME_BATCH_SIZE", "128"))
            VIDEO_FRAME_QUEUE_SIZE = int(os.getenv("VIDEO_FRAME_QUEUE_SIZE", "32"))
            VIDEO_FRAME_SHM_POOL_BLOCK_SIZE = int(
                os.getenv("VIDEO_FRAME_SHM_POOL_BLOCK_SIZE", str(1920 * 1080 * 3))
            )
            VIDEO_FRAME_SHM_POOL_BLOCKS_MULTIPLIER = int(
                os.getenv("VIDEO_FRAME_SHM_POOL_BLOCKS_MULTIPLIER", "2")
            )

        return FallbackSettings()


_video_config = _get_video_config()
logger.setLevel(_video_config.VIDEO_FRAME_LOG_LEVEL)


class SharedMemoryPool:
    def __init__(self, max_blocks, block_size):
        self.max_blocks = max_blocks
        self.block_size = block_size
        self.free = queue.SimpleQueue()
        self.blocks = []
        self.in_use = set()

        for _ in range(max_blocks):
            shm = shared_memory.SharedMemory(create=True, size=block_size)
            self.blocks.append(shm)
            self.free.put(shm.name)

    def acquire(self):
        name = self.free.get()
        self.in_use.add(name)
        return name

    def release(self, name):
        if name in self.in_use:
            self.in_use.remove(name)
            self.free.put(name)

    def total_blocks(self):
        return self.max_blocks

    def used_blocks(self):
        return len(self.in_use)

    def free_blocks(self):
        return self.max_blocks - len(self.in_use)

    def is_full(self):
        return self.used_blocks() == self.max_blocks

    def is_empty(self):
        return self.used_blocks() == 0

    def stats(self):
        return {
            "total": self.total_blocks(),
            "used": self.used_blocks(),
            "free": self.free_blocks(),
            "block_size": self.block_size,
        }

    def close(self):
        for shm in self.blocks:
            shm.close()

    def unlink(self):
        try:
            for shm in self.blocks:
                shm.unlink()
        except FileNotFoundError:
            logger.info("Shared memory already unlinked")
            pass

    def shutdown(self):
        self.close()
        self.unlink()

    def __del__(self):
        try:
            self.shutdown()
        except Exception:
            pass


@dataclass(frozen=True)
class VideoStreamMetadata:
    """Metadata about the video stream for tracability."""

    source_type: VideoSourceType
    video_index: int
    stream_name: str | None
    stream_source: str | None
    total_frames: int | None
    fps: float | None
    duration_seconds: float | None
    stream_id: int | None
    time_base: str | None
    total_frames: int | None
    average_rate: str | None
    base_rate: str | None
    guessed_rate: str | None
    width: int | None
    height: int | None
    pixel_format: str | None
    aspect_ratio: str | None
    display_aspect_ratio: str | None
    duration_seconds: float | None
    duration: float | None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class FrameMetadata:
    """Metadata for individual video frames."""

    stream_id: int
    frame_id: int
    shm: str
    shape: str
    dtype: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class BatchFrameMetadata:
    """Metadata for a batch of video frames."""

    stream_id: int = -1
    batch_id: int = -1
    batch_size: int = 0
    frames: List[FrameMetadata] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "stream_id": self.stream_id,
            "batch_id": self.batch_id,
            "batch_size": len(self.frames),
            "frames": [frame.to_dict() for frame in self.frames],
        }


class VideoSourceType(Enum):
    """Supported video input source types."""

    FILE = "file"
    RTSP = "rtsp"
    BYTES = "bytes"


@dataclass(frozen=True)
class VideoInput:
    """Represents a video input source with its type."""

    source: Union[str, bytes]
    source_type: VideoSourceType

    @classmethod
    def from_file(cls, path: str) -> VideoInput:
        """Create input from a file path."""
        return cls(path, VideoSourceType.FILE)

    @classmethod
    def from_rtsp(cls, url: str) -> VideoInput:
        """Create input from an RTSP stream URL."""
        return cls(url, VideoSourceType.RTSP)

    @classmethod
    def from_bytes(cls, data: bytes) -> VideoInput:
        """Create input from bytes in memory."""
        return cls(data, VideoSourceType.BYTES)

    @classmethod
    def auto_detect(cls, source: Union[str, bytes]) -> VideoInput:
        """Auto-detect source type from the input."""
        if isinstance(source, bytes):
            return cls.from_bytes(source)
        elif isinstance(source, str):
            if source.startswith("rtsp://") or source.startswith("rtsps://"):
                return cls.from_rtsp(source)
            else:
                return cls.from_file(source)
        else:
            raise TypeError(f"Unsupported source type: {type(source)}")


@dataclass(frozen=True)
class VideoFrameConfig:
    """Configuration for video frame extraction."""

    batch_size: int = field(
        default_factory=lambda: _video_config.VIDEO_FRAME_BATCH_SIZE
    )
    num_workers: int | None = None
    queue_size: int = field(
        default_factory=lambda: _video_config.VIDEO_FRAME_QUEUE_SIZE
    )
    frame_interval: int = 1
    keyframes_only: bool = False
    # Segment config for temporal frame extraction
    start_offset_sec: int = field(
        default_factory=lambda: _video_config.DEFAULT_START_OFFSET_SEC
    )
    clip_duration: int = field(
        default_factory=lambda: _video_config.DEFAULT_CLIP_DURATION
    )
    frame_indexes: List[int] | None = None
    extraction_fps: float | None = None
    num_frames: int = field(default_factory=lambda: _video_config.DEFAULT_NUM_FRAMES)

    def __post_init__(self):
        if self.batch_size < 1:
            raise ValueError("batch_size must be >= 1")
        if self.queue_size < 1:
            raise ValueError("queue_size must be >= 1")
        if self.frame_interval < 1:
            raise ValueError("frame_interval must be >= 1")
        if self.keyframes_only and self.frame_interval != 1:
            raise ValueError("`frame_interval` must be 1 when `keyframes_only` is True")
        if self.num_frames < 0:
            raise ValueError("num_frames must be >= 0")
        if self.extraction_fps is not None and self.extraction_fps <= 0:
            raise ValueError("extraction_fps must be positive")
        if self.start_offset_sec < 0:
            raise ValueError("start_offset_sec must be >= 0")

    @property
    def effective_workers(self) -> int:
        """Return worker count, auto-detecting if not specified."""
        if self.num_workers is not None:
            return self.num_workers
        return _video_config.VIDEO_FRAME_DECODER_WORKERS


def _calculate_target_frame_indices(
    total_frames: int,
    fps: float,
    stream_config: VideoFrameConfig,
) -> set[int]:
    """
    Calculate target frame indices based on segment configuration.

    Implements priority-based frame extraction:
    1. frame_indexes (highest priority) - specific frame indices
    2. extraction_fps - uniform sampling at specified rate
    3. num_frames (lowest priority) - uniform sampling of specified number

    Args:
        total_frames: Total number of frames in the video
        fps: Frames per second of the video
        stream_config: Video frame configuration with segment parameters

    Returns:
        Set of frame indices to extract
    """
    # Calculate segment boundaries
    start_idx = int(fps * stream_config.start_offset_sec)
    end_idx = (
        min(total_frames, start_idx + int(fps * stream_config.clip_duration))
        if stream_config.clip_duration != -1
        else total_frames
    )

    logger.debug(
        f"Video segment boundaries - fps: {fps}, total_frames: {total_frames}, "
        f"start_idx: {start_idx}, end_idx: {end_idx}"
    )

    # Priority 1: frame_indexes - specific frame indices (highest priority)
    if stream_config.frame_indexes is not None:
        frame_indexes = np.array(stream_config.frame_indexes, dtype=int)
        # Filter indices to be within the video segment bounds
        valid_indices = frame_indexes[
            (frame_indexes >= start_idx) & (frame_indexes < end_idx)
        ]

        if len(valid_indices) == 0:
            logger.warning(
                f"No valid frame indices found within segment bounds [{start_idx}, {end_idx}), "
                f"falling back to uniform sampling"
            )
            # Fall back to default uniform sampling
            frame_idx = np.linspace(
                start_idx,
                end_idx,
                num=stream_config.num_frames if stream_config.num_frames > 0 else end_idx - start_idx,
                endpoint=False,
                dtype=int,
            )
        else:
            frame_idx = valid_indices

        logger.debug(f"Using frame_indexes with {len(frame_idx)} valid indices")
        return set(frame_idx.tolist())

    # Priority 2: fps - uniform sampling at specified rate
    if stream_config.extraction_fps is not None:
        # Calculate frame interval based on user fps
        frame_interval = float(fps) / float(stream_config.extraction_fps)

        # Generate frame indices at the specified fps rate
        frame_indices = []
        current_frame = float(start_idx)

        while current_frame < end_idx:
            frame_indices.append(int(current_frame))
            current_frame += frame_interval

        logger.debug(
            f"Using extraction_fps={stream_config.extraction_fps} for sampling, "
            f"generated {len(frame_indices)} frames"
        )
        return set(frame_indices)

    # Priority 3: num_frames - use explicit value for uniform sampling (lowest priority)
    frame_idx = np.linspace(
        start_idx, end_idx, num=stream_config.num_frames if stream_config.num_frames > 0 else end_idx - start_idx, endpoint=False, dtype=int
    )
    logger.debug(
        f"Using default num_frames={stream_config.num_frames} for uniform sampling"
    )
    return set(frame_idx.tolist())


def convert_and_store_frame(
    stream_id: int,
    frame_id: int,
    frame: tuple[int, av.video.frame.VideoFrame],
    shm_pool: SharedMemoryPool,
):
    rgb = frame.to_ndarray(format="rgb24")

    shm_name = shm_pool.acquire()
    shm = shared_memory.SharedMemory(name=shm_name)

    arr = np.ndarray(rgb.shape, dtype=rgb.dtype, buffer=shm.buf)
    arr[:] = rgb

    shm.close()

    return FrameMetadata(
        stream_id=stream_id,
        frame_id=frame_id,
        shm=shm_name,
        shape=str(rgb.shape),  # Store shape as string for metadata
        dtype=rgb.dtype.name,
    )


def decode_stream_and_batch_generator(
    container: av.container.Container,
    stream_id: int,
    stream_config: VideoFrameConfig,
    shm_pool: SharedMemoryPool,
    batch_size: int | None = None,
    shutdown_event: threading.Event | None = None,
) -> Generator[Union[Dict[str, Any], Tuple[object, int]], None, None]:

    if batch_size is None:
        batch_size = _video_config.VIDEO_FRAME_BATCH_SIZE

    logger.info(
        f"Stream {stream_id} started decoding with config: {stream_config}, batch_size: {batch_size}"
    )

    def flush_batch(batch, batch_id):
        frames_meta = list(
            thread_pool.map(
                lambda item: convert_and_store_frame(
                    stream_id, item[0], item[1], shm_pool
                ),
                batch,
            )
        )
        return BatchFrameMetadata(
            stream_id=stream_id,
            batch_id=batch_id,
            frames=frames_meta,
        ).to_dict()

    batch: list[tuple[int, av.VideoFrame]] = []
    batch_id = 0
    global_frame_idx = 0
    start_time = time.perf_counter()
    with container, ThreadPoolExecutor(
        max_workers=_video_config.VIDEO_FRAME_DECODER_WORKERS
    ) as thread_pool:
        stream = container.streams.video[0]
        stream.thread_type = "AUTO"

        if stream_config.keyframes_only:
            stream.skip_frame = "NONKEY"

        try:
            for packet in container.demux(stream):

                if shutdown_event and shutdown_event.is_set():
                    end_time = time.perf_counter()
                    logger.info(
                        f"Stream {stream_id} stopped by shutdown event during decoding"
                    )
                    yield (
                        INTERRUPT,
                        stream_id,
                        (start_time, end_time, end_time - start_time),
                    )
                    break

                if packet.dts is None:
                    continue

                try:
                    frames = packet.decode()
                except av.AVError:
                    # RTSP transient decode failure — continue
                    continue

                batch_start_time = time.perf_counter()
                for frame in frames:
                    if shutdown_event and shutdown_event.is_set():
                        end_time = time.perf_counter()
                        logger.info(
                            f"Stream {stream_id} stopped by shutdown event during decoding"
                        )
                        yield (
                            INTERRUPT,
                            stream_id,
                            (start_time, end_time, end_time - start_time),
                        )
                        break

                    if global_frame_idx % stream_config.frame_interval != 0:
                        global_frame_idx += 1
                        continue

                    batch.append((global_frame_idx, frame))
                    global_frame_idx += 1

                    if len(batch) >= batch_size:
                        yield flush_batch(batch, batch_id), (
                            batch_start_time,
                            time.perf_counter(),
                            time.perf_counter() - batch_start_time,
                        )
                        batch_start_time = time.perf_counter()
                        batch.clear()
                        batch_id += 1

            # Final drain (only on shutdown or true EOS)
            if batch:
                yield flush_batch(batch, batch_id), (
                    batch_start_time,
                    time.perf_counter(),
                    time.perf_counter() - batch_start_time,
                )
                batch_start_time = time.perf_counter()
                batch.clear()

            yield (
                DONE,
                stream_id,
                (start_time, end_time, end_time - start_time),
            )

        finally:
            if shutdown_event and shutdown_event.is_set():
                logger.info(f"Stream {stream_id} stopped by shutdown event")
            else:
                logger.info(f"Stream {stream_id} ended")


def decode_and_batch_generator(
    container: av.container.Container,
    stream_id: int,
    stream_config: VideoFrameConfig,
    shm_pool: SharedMemoryPool,
    batch_size: int | None = None,
    shutdown_event: threading.Event = None,
) -> Generator[Union[Dict[str, Any], Tuple[object, int]], None, None]:

    if batch_size is None:
        batch_size = _video_config.VIDEO_FRAME_BATCH_SIZE

    batch = []
    batch_id = 0
    logger.info(
        f"Stream {stream_id} shutdown_event ID: {id(shutdown_event)}, batch_size: {batch_size}"
    )
    start_time = time.perf_counter()
    with container, ThreadPoolExecutor(
        max_workers=_video_config.VIDEO_FRAME_DECODER_WORKERS
    ) as _thread_pool:
        stream = container.streams.video[0]
        stream.thread_type = "AUTO"

        if stream_config.keyframes_only:
            stream.skip_frame = "NONKEY"

        # Calculate target frame indices based on segment config
        fps = float(stream.average_rate) if stream.average_rate else 25.0
        total_frames = stream.frames if stream.frames else 0
        target_frame_indices = None

        logger.info(f"Stream {stream_id} total frames: {total_frames}")

        # Only calculate target indices if segment config is provided (not default)
        if (
            stream_config.frame_indexes is not None
            or stream_config.extraction_fps is not None
            or stream_config.start_offset_sec != 0
            or stream_config.clip_duration != -1
            or stream_config.num_frames != 0
        ):
            if total_frames > 0:
                target_frame_indices = _calculate_target_frame_indices(
                    total_frames, fps, stream_config
                )
                logger.info(
                    f"Stream {stream_id} targeting {len(target_frame_indices)} frames "
                    f"from {total_frames} total frames"
                )

        batch_start_time = time.perf_counter()
        for frame_id, frame in enumerate(container.decode(video=0)):

            if shutdown_event and shutdown_event.is_set():
                logger.info(
                    f"Stream {stream_id} stopped by shutdown event during decoding"
                )
                end_time = time.perf_counter()
                yield (
                    INTERRUPT,
                    stream_id,
                    (start_time, end_time, end_time - start_time),
                )
                break

            # Apply frame filtering based on target indices if calculated
            if target_frame_indices is not None:
                if frame_id not in target_frame_indices:
                    continue
            else:
                # Fall back to frame_interval if no segment config
                if frame_id % stream_config.frame_interval != 0:
                    continue

            batch.append((frame_id, frame))

            if len(batch) >= batch_size:
                frames_meta = list(
                    _thread_pool.map(
                        lambda f: convert_and_store_frame(
                            stream_id, f[0], f[1], shm_pool
                        ),
                        batch,
                    )
                )
                logger.info(
                    f"[Decoder] Stream {stream_id} batch {batch_id} with {len(frames_meta)} frames"
                )
                yield BatchFrameMetadata(
                    stream_id=stream_id, batch_id=batch_id, frames=frames_meta
                ).to_dict(), (
                    batch_start_time,
                    time.perf_counter(),
                    time.perf_counter() - batch_start_time,
                )

                batch = []
                batch_start_time = time.perf_counter()
                batch_id += 1

        if len(batch) > 0:
            frames_meta = list(
                _thread_pool.map(
                    lambda f: convert_and_store_frame(stream_id, f[0], f[1], shm_pool),
                    batch,
                )
            )
            logger.info(
                f"[Decoder] Stream {stream_id} final batch with {len(frames_meta)} frames"
            )
            yield BatchFrameMetadata(
                stream_id=stream_id, batch_id=batch_id, frames=frames_meta
            ).to_dict(), (
                batch_start_time,
                time.perf_counter(),
                time.perf_counter() - batch_start_time,
            )
            batch_start_time = time.perf_counter()

        end_time = time.perf_counter()
        logger.info(f"[Decoder] Stream {stream_id} ended")
        yield (
            DONE,
            stream_id,
            (start_time, end_time, end_time - start_time),
        )


def generator_to_queue(gen, result_queue):
    for item in gen:
        result_queue.put(item)
        if isinstance(item, tuple) and item[0] is INTERRUPT:
            break


class VideoFrameExtractor:
    """
    Extracts and converts video frames to numpy arrays efficiently.

    Uses a producer-consumer pattern with multiprocessing support for
    parallel decoding of multiple video sources.
    """

    def __init__(
        self,
        video_input: VideoInput | str | bytes | list[VideoInput | str | bytes],
        configs: VideoFrameConfig | list[VideoFrameConfig] | None = None,
        shm_pool: SharedMemoryPool | None = None,
        shutdown_event: threading.Event | None = None,
    ):
        self.configs = configs

        if configs is None:
            self.configs = (
                [VideoFrameConfig()] * len(video_input)
                if isinstance(video_input, list)
                else [VideoFrameConfig()]
            )
        if isinstance(self.configs, VideoFrameConfig):
            self.configs = (
                [self.configs]
                if not isinstance(video_input, list)
                else [self.configs] * len(video_input)
            )

        logger.info(f"VideoFrameExtractor initialized with configs: {self.configs}")
        self.shm_pool = shm_pool

        # Use external shutdown_event if provided, else create internal one
        self._shutdown = shutdown_event

        self.finished_set = set()
        if isinstance(video_input, list):
            self.video_inputs = [VideoInput.auto_detect(vi) for vi in video_input]
        else:
            self.video_inputs = [VideoInput.auto_detect(video_input)]

        self.metadata_list = []

        if len(self.video_inputs) > 0:
            for video_index, video_input in enumerate(self.video_inputs):
                with self._open_video_source(video_input) as container:
                    stream = container.streams.video[0]

                    self.metadata_list.append(
                        VideoStreamMetadata(
                            video_index=video_index,
                            stream_id=stream.index,
                            stream_name=stream.name,
                            stream_source=(
                                video_input.source
                                if video_input.source_type
                                in (VideoSourceType.FILE, VideoSourceType.RTSP)
                                else "BYTES_SOURCE"
                            ),
                            time_base=str(stream.time_base),
                            source_type=str(video_input.source_type),
                            total_frames=stream.frames,
                            fps=(
                                float(stream.average_rate)
                                if stream.average_rate
                                else None
                            ),
                            average_rate=(
                                str(stream.average_rate)
                                if stream.average_rate
                                else None
                            ),
                            base_rate=(
                                str(stream.base_rate) if stream.base_rate else None
                            ),
                            guessed_rate=(
                                str(stream.guessed_rate)
                                if stream.guessed_rate
                                else None
                            ),
                            width=stream.width,
                            height=stream.height,
                            pixel_format=stream.format.name if stream.format else None,
                            aspect_ratio=(
                                str(stream.sample_aspect_ratio)
                                if stream.sample_aspect_ratio
                                else None
                            ),
                            display_aspect_ratio=(
                                str(stream.display_aspect_ratio)
                                if stream.display_aspect_ratio
                                else None
                            ),
                            duration_seconds=(
                                float(stream.duration * Fraction(str(stream.time_base)))
                                if stream.duration and stream.time_base
                                else None
                            ),
                            duration=stream.duration,
                        ).to_dict()
                    )

    def get_metadata(self) -> list[Dict[str, Any]]:
        """Return metadata for all video streams."""
        return self.metadata_list

    def stop(self):
        """
        Request graceful shutdown of frame extraction.

        Call this from any thread to stop the decode_frames() loop.
        The generator will yield INTERRUPT and exit cleanly.
        """
        logger.info("Stop requested, setting shutdown event...")
        self._shutdown.set()

    @property
    def shutdown_event(self) -> threading.Event:
        """Return the shutdown event for external monitoring/control."""
        return self._shutdown

    def _open_video_source(self, video_input: VideoInput) -> av.container.Container:
        """Open video source based on type."""
        if video_input.source_type == VideoSourceType.FILE:
            return av.open(video_input.source)
        elif video_input.source_type == VideoSourceType.RTSP:
            return av.open(
                video_input.source,
                options={
                    "rtsp_transport": "tcp",
                    "rtsp_flags": "prefer_tcp",
                    "stimeout": "10000000",
                    "max_delay": "500000",
                    "analyzeduration": "10000000",
                    "probesize": "10000000",
                },
            )
        elif video_input.source_type == VideoSourceType.BYTES:
            bytes_io = io.BytesIO(video_input.source)
            return av.open(bytes_io)
        else:
            raise ValueError(f"Unsupported source type: {video_input.source_type}")

    def decode_frames(self) -> Generator[List[Dict[str, Any]], None, None]:
        """
        Extract frames from single or multiple video sources in parallel.

        Yields:
            List of dictionaries containing frame metadata and frame data for each batch from all sources.
        """
        inputs = [
            inp if isinstance(inp, VideoInput) else VideoInput.auto_detect(inp)
            for inp in self.video_inputs
        ]

        queue_size = (
            _video_config.VIDEO_FRAME_QUEUE_SIZE * len(inputs)
            if self.configs and isinstance(self.configs, list) and len(self.configs) > 0
            else _video_config.VIDEO_FRAME_QUEUE_SIZE
        )
        result_queue: queue.Queue = queue.Queue(maxsize=queue_size)
        finished_set = set()

        threads = []
        for video_index, video_input in enumerate(inputs):
            container = self._open_video_source(video_input)

            if video_input.source_type == VideoSourceType.RTSP:
                # For streaming sources, we can start decoding immediately
                stream_gen = decode_stream_and_batch_generator(
                    container=container,
                    stream_id=video_index,
                    stream_config=self.configs[video_index],
                    shm_pool=self.shm_pool,
                    batch_size=self.configs[video_index].batch_size,
                    shutdown_event=self._shutdown,
                )
            else:
                stream_gen = decode_and_batch_generator(
                    container=container,
                    stream_id=video_index,
                    stream_config=self.configs[video_index],
                    shm_pool=self.shm_pool,
                    batch_size=self.configs[video_index].batch_size,
                    shutdown_event=self._shutdown,
                )

            t = threading.Thread(
                target=generator_to_queue, args=(stream_gen, result_queue), daemon=True
            )
            t.start()
            threads.append(t)

        try:
            while len(finished_set) < len(inputs):
                try:
                    batch = result_queue.get(timeout=0.1)

                except queue.Empty:
                    if self._shutdown.is_set():
                        logger.info(
                            "[DECODER MAIN] Shutdown event set, stopping frame extraction"
                        )
                        break
                    continue

                # Handle DONE and INTERRUPT sentinel
                if isinstance(batch, tuple):

                    if batch[0] is INTERRUPT:
                        logger.info(
                            f"[DECODER MAIN] Interrupt signal received for stream {batch[1]}, shutting down..."
                        )
                        logger.info(
                            f"[DECODER MAIN] Timing info: start_time={batch[2][0]}, end_time={batch[2][1]}, duration={batch[2][2]}"
                        )
                        break

                    if batch[0] is DONE:
                        _, stream_id, timing_info = batch
                        logger.info(
                            f"[DECODER MAIN] Stream {stream_id} completed. Timing info: start_time={timing_info[0]}, end_time={timing_info[1]}, duration={timing_info[2]}"
                        )
                        finished_set.add(stream_id)

                        t = threads[stream_id]
                        if t.is_alive():
                            t.join(timeout=1.0)

                        continue

                yield batch

        except Exception as e:
            self._shutdown.set()
            logger.error(
                f"[DECODER MAIN] Error during frame extraction: {e}", exc_info=True
            )
            raise

        finally:
            logger.info("[DECODER MAIN] All threads have been signaled to shutdown.")


def extract_batched_frames(
    video_inputs: VideoInput | str | bytes | list[VideoInput | str | bytes],
    frame_interval: int = 1,
    batch_size: int | None = None,
    keyframes_only: bool = False,
    shm_pool: SharedMemoryPool | None = None,
    segment_config: dict | None = None,
) -> Generator[List[Image.Image], None, None]:
    """
    Convenience function to extract frames from multiple video sources using threading.

    Uses threading.Thread instead of multiprocessing for simpler implementation.
    Supports temporal frame extraction via segment_config with multiple extraction strategies.
    May have GIL limitations but avoids shared memory complexity.

    Args:
        video_inputs: List of VideoInput objects, file paths, RTSP URLs, or bytes.
        frame_interval: Extract every Nth frame (ignored if segment_config is provided).
        batch_size: Number of frames per batch (uses VIDEO_FRAME_BATCH_SIZE env if None).
        keyframes_only: Whether to extract only keyframes.
        shm_pool: Optional pre-allocated shared memory pool.
        segment_config: Configuration dictionary for video segmentation with options:
            - startOffsetSec: Starting offset in seconds (default: 0)
            - clip_duration: Duration of clip to extract from (-1 for full video, default: -1)
            - frame_indexes: Array of specific frame indices (highest priority)
            - extraction_fps: Frames per second for uniform sampling (can be fractional)
            - num_frames: Number of frames for uniform sampling (default: 64)

            Priority order: frame_indexes > extraction_fps > num_frames
            If segment_config is not provided, frame_interval is used as fallback.

    Yields:
        Batches of PIL.Image frames from all sources.
    """
    if batch_size is None:
        batch_size = _video_config.VIDEO_FRAME_BATCH_SIZE

    # Parse segment_config if provided
    start_offset_sec = 0
    clip_duration = -1
    frame_indexes = None
    extraction_fps = None
    num_frames = _video_config.DEFAULT_NUM_FRAMES

    if segment_config is not None:
        start_offset_sec = segment_config.get(
            "startOffsetSec", _video_config.DEFAULT_START_OFFSET_SEC
        )
        clip_duration = segment_config.get(
            "clip_duration", _video_config.DEFAULT_CLIP_DURATION
        )
        frame_indexes = segment_config.get("frame_indexes")
        extraction_fps = segment_config.get("extraction_fps")
        num_frames = segment_config.get("num_frames", _video_config.DEFAULT_NUM_FRAMES)

    logger.info(
        f"Starting frame extraction with frame_interval={frame_interval}, batch_size={batch_size}, "
        f"keyframes_only={keyframes_only}, start_offset_sec={start_offset_sec}, clip_duration={clip_duration}, "
        f"frame_indexes={frame_indexes}, extraction_fps={extraction_fps}, num_frames={num_frames}"
    )
    config = VideoFrameConfig(
        frame_interval=frame_interval,
        batch_size=batch_size,
        keyframes_only=keyframes_only,
        start_offset_sec=start_offset_sec,
        clip_duration=clip_duration,
        frame_indexes=frame_indexes,
        extraction_fps=extraction_fps,
        num_frames=num_frames,
    )
    if shm_pool is None:
        # Create a default shared memory pool if not provided
        # Use configurable block size and multiplier
        max_blocks = batch_size * _video_config.VIDEO_FRAME_SHM_POOL_BLOCKS_MULTIPLIER
        block_size = _video_config.VIDEO_FRAME_SHM_POOL_BLOCK_SIZE
        logger.info(
            f"Creating shared memory pool: max_blocks={max_blocks}, block_size={block_size} bytes"
        )
        shm_pool = SharedMemoryPool(max_blocks=max_blocks, block_size=block_size)

    shutdown_event = threading.Event()
    extractor = VideoFrameExtractor(
        video_inputs,
        config,
        shm_pool=shm_pool,
        shutdown_event=shutdown_event,
    )
    logger.info(f"extractor metadata: {extractor.metadata_list}")
    try:
        for batch in extractor.decode_frames():

            if isinstance(batch, tuple) and (batch[0] is INTERRUPT or batch[0] is DONE):
                logger.info(
                    f"Received signal {batch[0]} for stream {batch[1]}, stopping extraction."
                )
                shutdown_event.set()
                break

            batch_dict, _ = batch

            batch_frame_pil = []

            frames_metadata = (
                batch_dict["frames"]
                if isinstance(batch_dict, dict) and "frames" in batch_dict
                else []
            )

            for frame_meta in frames_metadata:
                shm = shared_memory.SharedMemory(name=frame_meta["shm"])
                arr = Image.fromarray(
                    np.ndarray(
                        ast.literal_eval(frame_meta["shape"]),
                        dtype=frame_meta["dtype"],
                        buffer=shm.buf,
                    ),
                    mode="RGB",
                )
                logger.debug(
                    f"stream_id={frame_meta['stream_id']}, frame_id={frame_meta['frame_id']}, "
                    f"arr.size={arr.size}, arr.mode={arr.mode}"
                )
                batch_frame_pil.append(arr)

            yield batch_frame_pil

            batch_frame_pil.clear()

            for frame_meta in frames_metadata:
                logger.debug(
                    f"Releasing shared memory {frame_meta['shm']} for frame {frame_meta['frame_id']} "
                    f"of stream {frame_meta['stream_id']}"
                )
                shm_pool.release(frame_meta["shm"])
    finally:
        shm_pool.shutdown()
        shutdown_event.set()

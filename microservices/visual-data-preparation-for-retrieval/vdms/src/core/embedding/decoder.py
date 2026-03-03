"""
Video Frame Extraction Utility for Multimodal Embedding Serving.
Provides efficient, batched video frame extraction with concurrent
PIL image conversion using a producer-consumer pattern with multiprocessing support.
"""

from __future__ import annotations

import io
import logging
import os
import queue
import signal
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
from dataclasses import dataclass
from dataclasses import field
from enum import Enum
from fractions import Fraction
from typing import Any
from typing import Dict
from typing import Generator
from typing import List
from typing import Tuple
from typing import Union

import av
import numpy as np

INTERRUPT = object()  # interrupt signal (unique, non-colliding)
DONE = object()  # consumer → main completion signal

import queue
from multiprocessing import shared_memory

import numpy as np

shutdown_Event = threading.Event()
logger = logging.getLogger(__name__)

class SharedMemoryPool:
    def __init__(self, max_blocks, block_size):
        self.free = queue.SimpleQueue()
        self.blocks = []

        for _ in range(max_blocks):
            shm = shared_memory.SharedMemory(create=True, size=block_size)
            self.blocks.append(shm)
            self.free.put(shm.name)

    def acquire(self):
        return self.free.get()

    def release(self, name):
        self.free.put(name)

    def close(self):
        for shm in self.blocks:
            shm.close()
            shm.unlink()


@dataclass(frozen=True)
class VideoStreamMetadata:
    """Metadata about the video stream for tracability."""

    source_type: VideoSourceType
    stream_name: str | None
    stream_source: str | None
    total_frames: int | None
    fps: float | None
    duration_seconds: float | None
    stream_id: int | None
    time_base: str | None
    source_type: VideoSourceType
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

    batch_size: int = 1
    num_workers: int | None = None
    num_decoders: int = 1
    queue_size: int = 32
    frame_interval: int = 1
    keyframes_only: bool = False

    def __post_init__(self):
        if self.batch_size < 1:
            raise ValueError("batch_size must be >= 1")
        if self.queue_size < 1:
            raise ValueError("queue_size must be >= 1")
        if self.frame_interval < 1:
            raise ValueError("frame_interval must be >= 1")
        if self.num_decoders < 1:
            raise ValueError("num_decoders must be >= 1")
        if self.keyframes_only and self.frame_interval != 1:
            raise ValueError("`frame_interval` must be 1 when `keyframes_only` is True")

    @property
    def effective_workers(self) -> int:
        """Return worker count, auto-detecting if not specified."""
        if self.num_workers is not None:
            return self.num_workers
        return min(8, (os.cpu_count() or 4) * 2)


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
    batch_size: int = 64,
    shutdown_event: threading.Event | None = None,
) -> Generator[Union[Dict[str, Any], Tuple[object, int]], None, None]:

    logger.info(f"Stream {stream_id} started decoding with config: {stream_config}")

    def flush_batch(batch, batch_id):
        frames_meta = list(
            thread_pool.map(
                lambda item: convert_and_store_frame(stream_id, item[0], item[1], shm_pool),
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

    with container, ThreadPoolExecutor(max_workers=8) as thread_pool:
        stream = container.streams.video[0]
        stream.thread_type = "AUTO"

        if stream_config.keyframes_only:
            stream.skip_frame = "NONKEY"

        try:
            for packet in container.demux(stream):

                if shutdown_event and shutdown_event.is_set():
                    yield (INTERRUPT, stream_id)
                    break

                if packet.dts is None:
                    continue

                try:
                    frames = packet.decode()
                except av.AVError:
                    # RTSP transient decode failure — continue
                    continue

                for frame in frames:
                    if shutdown_event and shutdown_event.is_set():
                        break

                    if global_frame_idx % stream_config.frame_interval != 0:
                        global_frame_idx += 1
                        continue

                    batch.append((global_frame_idx, frame))
                    global_frame_idx += 1

                    if len(batch) >= batch_size:
                        yield flush_batch(batch, batch_id)
                        batch.clear()
                        batch_id += 1

            # Final drain (only on shutdown or true EOS)
            if batch:
                yield flush_batch(batch, batch_id)

        finally:
            if shutdown_event and shutdown_event.is_set():
                logger.info(f"Stream {stream_id} stopped by shutdown event")
            else:
                logger.info(f"Stream {stream_id} ended")

            yield (DONE, stream_id)


def decode_and_batch_generator(
    container: av.container.Container,
    stream_id: int,
    stream_config: VideoFrameConfig,
    shm_pool: SharedMemoryPool,
    batch_size: int = 64,
    shutdown_event: threading.Event = None,
) -> Generator[Union[Dict[str, Any], Tuple[object, int]], None, None]:
    batch = []
    batch_id = 0
    _thread_pool = ThreadPoolExecutor(max_workers=8)
    with container:
        stream = container.streams.video[0]
        stream.thread_type = "AUTO"

        if stream_config.keyframes_only:
            stream.skip_frame = "NONKEY"

        for frame_id, frame in enumerate(container.decode(video=0)):

            # TODO: Shutdown signal check
            if shutdown_event and shutdown_event.is_set():
                yield (INTERRUPT, stream_id)
                break

            if frame_id % stream_config.frame_interval != 0:
                continue

            batch.append((frame_id, frame))

            if len(batch) >= batch_size:
                frames_meta = list(
                    _thread_pool.map(
                        lambda f: convert_and_store_frame(stream_id, f[0], f[1], shm_pool), batch
                    )
                )
                yield BatchFrameMetadata(
                    stream_id=stream_id, batch_id=batch_id, frames=frames_meta
                ).to_dict()

                batch = []
                batch_id += 1

        if len(batch) > 0:
            frames_meta = list(
                _thread_pool.map(
                    lambda f: convert_and_store_frame(stream_id, f[0], f[1], shm_pool), batch
                )
            )
            yield BatchFrameMetadata(
                stream_id=stream_id, batch_id=batch_id, frames=frames_meta
            ).to_dict()

        yield (DONE, stream_id)  # end-of-stream sentinel


def generator_to_queue(gen, result_queue):
    for item in gen:
        result_queue.put(item)
        if item is None or (isinstance(item, tuple) and item[0] is INTERRUPT):
            break


class VideoFrameExtractor:
    """
    Extracts and converts video frames to numpy arrays efficiently.

    Uses a producer-consumer pattern with multiprocessing support for
    parallel decoding of multiple video sources.

    Example:
        # Single video file
        extractor = VideoFrameExtractor(input, config)
        for batch in extractor.extract_batches(VideoInput.from_file("video.mp4")):
            embeddings = model.encode(batch)

        # RTSP stream
        for batch in extractor.extract_batches(VideoInput.from_rtsp("rtsp://...")):
            process(batch)

        # Multiple parallel sources
        inputs = [VideoInput.from_file(f) for f in video_files]
        for batch in extractor.extract_batches_parallel(inputs):
            process(batch)
    """

    def __init__(
        self,
        video_input: VideoInput | str | bytes | list[VideoInput | str | bytes],
        config: VideoFrameConfig | None = None,
        shm_pool: SharedMemoryPool | None = None,
    ):
        self.config = config or VideoFrameConfig()
        self.shm_pool = shm_pool

        self._shutdown = threading.Event()
        self._shutdown.clear()

        def handle_sigint(sig, frame):
            logger.info("Shutdown signal received, stopping frame extraction...")
            self._shutdown.set()

        signal.signal(signal.SIGINT, handle_sigint)

        self.finished_set = set()
        if isinstance(video_input, list):
            self.video_inputs = [VideoInput.auto_detect(vi) for vi in video_input]
        else:
            self.video_inputs = [VideoInput.auto_detect(video_input)]

        self.metadata_list = []

        if len(self.video_inputs) > 0:
            for video_input in self.video_inputs:
                with self._open_video_source(video_input) as container:
                    stream = container.streams.video[0]

                    self.metadata_list.append(
                        VideoStreamMetadata(
                            stream_id=stream.index,
                            stream_name=stream.name,
                            stream_source=(
                                video_input.source
                                if video_input.source_type
                                in (VideoSourceType.FILE, VideoSourceType.RTSP)
                                else "BYTES_SOURCE"
                            ),
                            time_base=str(stream.time_base),
                            source_type=video_input.source_type,
                            total_frames=stream.frames,
                            fps=float(stream.average_rate) if stream.average_rate else None,
                            average_rate=str(stream.average_rate) if stream.average_rate else None,
                            base_rate=str(stream.base_rate) if stream.base_rate else None,
                            guessed_rate=str(stream.guessed_rate) if stream.guessed_rate else None,
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
                        )
                    )

    def get_metadata(self) -> list[VideoStreamMetadata]:
        """Return metadata for all video streams."""
        return self.metadata_list[0] if self.metadata_list else None

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

        result_queue: queue.Queue = queue.Queue(maxsize=self.config.queue_size)
        finished_set = set()

        threads = []
        for video_index, video_input in enumerate(inputs):
            container = self._open_video_source(video_input)

            if video_input.source_type == VideoSourceType.RTSP:
                # For streaming sources, we can start decoding immediately
                stream_gen = decode_stream_and_batch_generator(
                    container=container,
                    stream_id=video_index,
                    stream_config=self.config,
                    shm_pool=self.shm_pool,
                    batch_size=self.config.batch_size,
                    shutdown_event=self._shutdown,
                )
            else:
                stream_gen = decode_and_batch_generator(
                    container=container,
                    stream_id=video_index,
                    stream_config=self.config,
                    shm_pool=self.shm_pool,
                    batch_size=self.config.batch_size,
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
                    continue

                # Handle DONE and INTERRUPT sentinel
                if isinstance(batch, tuple):

                    if batch[0] is INTERRUPT:
                        break

                    if batch[0] is DONE:
                        _, stream_id = batch

                        finished_set.add(stream_id)

                        t = threads[stream_id]
                        if t.is_alive():
                            t.join(timeout=1.0)

                        continue

                yield batch

        except Exception as e:
            self._shutdown.set()
            logger.error(f"Error during frame extraction: {e}", exc_info=True)
            raise

        finally:
            self.shm_pool.close()
            logger.info("All threads have been signaled to shutdown and shared memory has been released.")


def extract_batched_frames(
    video_inputs: VideoInput | str | bytes | list[VideoInput | str | bytes],
    frame_interval: int = 1,
    batch_size: int = 128,
    keyframes_only: bool = False,
    shm_pool: SharedMemoryPool | None = None,
) -> Generator[List[Tuple[int, np.ndarray]], None, None]:
    """
    Convenience function to extract frames from multiple video sources using threading.

    Uses threading.Thread instead of multiprocessing for simpler implementation.
    May have GIL limitations but avoids shared memory complexity.

    Args:
        video_inputs: List of VideoInput objects, file paths, RTSP URLs, or bytes.
        frame_interval: Extract every Nth frame.
        batch_size: Number of frames per batch.
        keyframes_only: Whether to extract only keyframes.

    Yields:
        Batches of (video_index, np.ndarray) frames from all sources.
    """
    config = VideoFrameConfig(
        frame_interval=frame_interval,
        batch_size=batch_size,
        keyframes_only=keyframes_only,
    )

    extractor = VideoFrameExtractor(video_inputs, config, shm_pool=shm_pool)
    print(f"extractor metadata: {extractor.metadata_list[0].to_dict()}")
    yield from extractor.decode_frames()

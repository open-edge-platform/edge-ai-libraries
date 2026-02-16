"""
Video Frame Extraction Utility for Multimodal Embedding Serving.
Provides efficient, batched video frame extraction with concurrent
PIL image conversion using a producer-consumer pattern.
"""

from __future__ import annotations

import os
import queue
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
import time
from typing import Generator

import av
from httpx import stream
from PIL import Image


@dataclass(frozen=True)
class VideoFrameConfig:
    """Configuration for video frame extraction."""

    batch_size: int = 16
    num_workers: int | None = None
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
        if self.keyframes_only and self.frame_interval != 1:
            raise ValueError("`frame_interval` must be 1 when `keyframes_only` is True")

    @property
    def effective_workers(self) -> int:
        """Return worker count, auto-detecting if not specified."""
        if self.num_workers is not None:
            return self.num_workers
        return min(16, (os.cpu_count() or 4) * 2)


class VideoFrameExtractor:
    """
    Extracts and converts video frames to PIL Images efficiently.

    Uses a producer-consumer pattern with threaded batch conversion
    to maximize throughput. 
    Memory usage is controlled by batching and queue sizes.

    Example:
        extractor = VideoFrameExtractor(config)
        for batch in extractor.extract_batches(video_path):
            embeddings = model.encode_images(batch)
    """

    def __init__(self, config: VideoFrameConfig | None = None):
        self.config = config or VideoFrameConfig()
        self._shutdown = threading.Event()

    def extract_batches(
        self, video_path: str
    ) -> Generator[list[Image.Image], None, None]:
        """
        Extract frames from video as batches of PIL Images.

        Args:
            video_path: Path to the video file.

        Yields:
            List of PIL Images for each batch.
        """
        frame_queue: queue.Queue = queue.Queue(maxsize=self.config.batch_size * 2)
        result_queue: queue.Queue = queue.Queue(maxsize=4)

        self._shutdown.clear()

        producer = threading.Thread(
            target=self._decode_frames, args=(video_path, frame_queue), daemon=True
        )
        consumer = threading.Thread(
            target=self._batch_consumer, args=(frame_queue, result_queue), daemon=True
        )

        producer.start()
        consumer.start()

        try:
            while True:
                try:
                    batch = result_queue.get(timeout=0.5)
                    if batch is None:
                        break
                    yield batch
                except queue.Empty:
                    if not consumer.is_alive() and result_queue.empty():
                        break
        finally:
            self._shutdown.set()
            producer.join(timeout=1.0)
            consumer.join(timeout=1.0)

    def _decode_frames(self, video_path: str, frame_queue: queue.Queue) -> None:
        """Decode video frames for conversion."""
        try:
            with av.open(video_path) as container:
                stream = container.streams.video[0]
                setattr(stream, "thread_type", "AUTO")

                self.config.keyframes_only and setattr(stream, "skip_frame", "NONKEY")
                start = time.perf_counter()
                put_time = 0.0
                for i, frame in enumerate(container.decode(stream)):
                    if self._shutdown.is_set():
                        break

                    if i % self.config.frame_interval == 0:
                        put_start = time.perf_counter()
                        frame_queue.put(frame)
                        put_time += time.perf_counter() - put_start
                end = time.perf_counter()
                print(f"Decoded frames in {end - start:.2f} seconds (put time: {put_time:.2f} seconds)")
        finally:
            frame_queue.put(None)

    def _batch_consumer(
        self, frame_queue: queue.Queue, result_queue: queue.Queue
    ) -> None:
        """Convert frames to PIL Images in batches using thread pool."""
        with ThreadPoolExecutor(max_workers=self.config.effective_workers) as pool:
            batch: list = []
            start = time.perf_counter()
            while not self._shutdown.is_set():
                try:
                    item = frame_queue.get(timeout=0.1)
                except queue.Empty:
                    continue

                if item is None:
                    break

                batch.append(item)

                if len(batch) >= self.config.batch_size:
                    images = list(pool.map(_frame_to_image, batch))
                    result_queue.put(images)
                    batch.clear()

            # Process remaining frames
            if batch and not self._shutdown.is_set():
                images = list(pool.map(_frame_to_image, batch))
                result_queue.put(images)
                batch.clear()
            end_time = time.perf_counter()
            print(f"Consumer Converted frames in {end_time - start:.2f} seconds")

        result_queue.put(None)


def _frame_to_image(frame) -> Image.Image:
    """
    Convert a video frame to PIL Image.
    Single unit of work for the consumer thread pool.
    Args:
        frame: av.VideoFrame
    Returns: PIL Image
    """
    return Image.fromarray(frame.to_ndarray(format="rgb24"))


def extract_frames(
    video_path: str,
    frame_interval: int = 1,
    batch_size: int = 128,
    keyframes_only: bool = False,
) -> Generator[list[Image.Image], None, None]:
    """
    Convenient function to extract frames.
    This performs the same extraction as VideoFrameExtractor but with a simpler interface.

    Args:
        video_path: Path to the video file.
        frame_interval: Extract every Nth frame.
        batch_size: Number of frames per batch.
        keyframes_only: Whether to extract only keyframes.
    Yields:
        Batches of PIL Images.
    """
    config = VideoFrameConfig(
        frame_interval=frame_interval,
        batch_size=batch_size,
        keyframes_only=keyframes_only,
    )
    extractor = VideoFrameExtractor(config)
    yield from extractor.extract_batches(video_path)

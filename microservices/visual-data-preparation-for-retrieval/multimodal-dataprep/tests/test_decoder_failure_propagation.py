# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Regression tests for decoder failure propagation.

A decoder producer runs on its own thread and hands batches to the consumer
through a queue, signalling completion with a DONE sentinel. When the producer
raised (for example a 4K frame that does not fit a shared-memory block), the
thread died without ever sending DONE, so the consumer spun on an empty queue
forever: the ingestion request never completed and never failed, it just hung
while the downstream workers logged "Queue empty, waiting..." indefinitely.

These tests pin the two halves of the fix:
  * a failing producer forwards its exception instead of dying silently, and
  * the consumer re-raises it rather than looping forever.
"""

import queue
import threading
from unittest import mock

import numpy as np
import pytest

from src.core.embedding.decoder import (
    DONE,
    FAILED,
    FrameTooLargeForPoolError,
    SharedMemoryPool,
    VideoFrameExtractor,
    convert_and_store_frame,
    generator_to_queue,
)


class _FakeFrame:
    """Minimal stand-in for ``av.video.frame.VideoFrame``."""

    def __init__(self, height: int, width: int):
        self._array = np.zeros((height, width, 3), dtype=np.uint8)

    def to_ndarray(self, format: str = "rgb24"):  # noqa: A002 - matches PyAV API
        return self._array


@pytest.fixture
def small_pool():
    """A pool whose blocks hold exactly one 64x64 RGB frame."""
    pool = SharedMemoryPool(max_blocks=2, block_size=64 * 64 * 3)
    try:
        yield pool
    finally:
        pool.shutdown()


class TestConvertAndStoreFrame:
    def test_frame_that_fits_is_stored(self, small_pool):
        meta = convert_and_store_frame(0, 1, _FakeFrame(64, 64), small_pool)

        assert meta.shape == "(64, 64, 3)"
        assert meta.dtype == "uint8"

    def test_oversized_frame_raises_actionable_error(self, small_pool):
        # 2160x3840 is the resolution from the reported failure.
        with pytest.raises(FrameTooLargeForPoolError) as excinfo:
            convert_and_store_frame(0, 1, _FakeFrame(3840, 2160), small_pool)

        message = str(excinfo.value)
        assert "MM_DATAPREP_VIDEO_SHM_BLOCK_SIZE" in message
        assert str(2160 * 3840 * 3) in message
        assert "2160x3840" in message

    def test_oversized_frame_does_not_leak_a_block(self, small_pool):
        before = small_pool.free_blocks()

        with pytest.raises(FrameTooLargeForPoolError):
            convert_and_store_frame(0, 1, _FakeFrame(3840, 2160), small_pool)

        assert small_pool.free_blocks() == before


class TestGeneratorToQueue:
    def test_successful_generator_forwards_every_item(self):
        result_queue: queue.Queue = queue.Queue()

        generator_to_queue(iter(["a", "b"]), result_queue, stream_id=0)

        assert result_queue.get_nowait() == "a"
        assert result_queue.get_nowait() == "b"
        assert result_queue.empty()

    def test_failing_generator_forwards_a_failed_sentinel(self):
        result_queue: queue.Queue = queue.Queue()
        boom = FrameTooLargeForPoolError("frame too big")

        def gen():
            yield "first"
            raise boom

        generator_to_queue(gen(), result_queue, stream_id=3)

        assert result_queue.get_nowait() == "first"
        sentinel, stream_id, exc = result_queue.get_nowait()
        assert sentinel is FAILED
        assert stream_id == 3
        assert exc is boom

    def test_generator_failing_immediately_still_reports(self):
        result_queue: queue.Queue = queue.Queue()

        def gen():
            raise RuntimeError("died before first yield")
            yield  # pragma: no cover

        generator_to_queue(gen(), result_queue, stream_id=0)

        sentinel, _, exc = result_queue.get_nowait()
        assert sentinel is FAILED
        assert isinstance(exc, RuntimeError)


def _extractor_with_producer(monkeypatch, producer):
    """Build a VideoFrameExtractor whose single stream runs ``producer``."""
    from src.core.embedding.decoder import VideoInput

    extractor = VideoFrameExtractor.__new__(VideoFrameExtractor)
    extractor.configs = [mock.Mock(queue_size=2, batch_size=1)]
    extractor.video_inputs = [VideoInput.from_bytes(b"fake-video")]
    extractor.shm_pool = mock.Mock()
    extractor.tracer = None
    extractor._shutdown = threading.Event()

    monkeypatch.setattr(
        VideoFrameExtractor, "_open_video_source", lambda self, _inp: mock.Mock(), raising=False
    )
    monkeypatch.setattr(
        "src.core.embedding.decoder.decode_and_batch_generator",
        lambda **kwargs: producer(),
    )
    return extractor


class TestDecodeFramesFailurePropagation:
    """The consumer must fail fast instead of hanging."""

    def test_producer_failure_is_raised_not_hung(self, monkeypatch):
        boom = FrameTooLargeForPoolError("buffer is too small for requested array")

        def producer():
            raise boom
            yield  # pragma: no cover

        extractor = _extractor_with_producer(monkeypatch, producer)

        done = threading.Event()
        captured = {}

        def drain():
            try:
                list(extractor.decode_frames())
            except BaseException as exc:  # noqa: BLE001
                captured["exc"] = exc
            finally:
                done.set()

        threading.Thread(target=drain, daemon=True).start()

        assert done.wait(timeout=15), "decode_frames hung instead of failing"
        assert captured.get("exc") is boom

    def test_shutdown_is_set_after_a_producer_failure(self, monkeypatch):
        def producer():
            raise RuntimeError("decode exploded")
            yield  # pragma: no cover

        extractor = _extractor_with_producer(monkeypatch, producer)

        with pytest.raises(RuntimeError, match="decode exploded"):
            list(extractor.decode_frames())

        assert extractor._shutdown.is_set()

    def test_silent_producer_death_does_not_hang(self, monkeypatch):
        """Belt-and-braces: a producer that vanishes without any sentinel."""

        def producer():
            return iter(())

        extractor = _extractor_with_producer(monkeypatch, producer)
        # Bypass the FAILED path entirely to exercise the liveness guard.
        monkeypatch.setattr(
            "src.core.embedding.decoder.generator_to_queue",
            lambda gen, result_queue, stream_id=None: None,
        )

        done = threading.Event()
        captured = {}

        def drain():
            try:
                list(extractor.decode_frames())
            except BaseException as exc:  # noqa: BLE001
                captured["exc"] = exc
            finally:
                done.set()

        threading.Thread(target=drain, daemon=True).start()

        assert done.wait(timeout=15), "decode_frames hung on a dead producer"
        assert isinstance(captured.get("exc"), RuntimeError)
        assert "exited before signalling completion" in str(captured["exc"])

    def test_normal_completion_still_works(self, monkeypatch):
        def producer():
            yield ({"frames": []}, (0, 1, 0.001))
            yield (DONE, 0, (0, 1, 0.001))

        extractor = _extractor_with_producer(monkeypatch, producer)

        batches = list(extractor.decode_frames())

        assert len(batches) == 1
        assert batches[0][0] == {"frames": []}
        assert not extractor._shutdown.is_set()


class TestFirstBatchFailureNotMasked:
    """The pipeline's batch loop must not mask a first-batch failure.

    The handler around the batch loop formats the batch index into its log
    message. When the frame generator raises before yielding anything, that
    index was unbound, so an UnboundLocalError replaced the real cause and the
    API reported "cannot access local variable 'i'" instead of the decoder error.
    """

    def test_batch_index_is_bound_before_the_loop(self):
        import inspect

        from src.core.embedding import embedding_helper

        source = inspect.getsource(embedding_helper._process_video_from_memory_simple_pipeline)
        generator_at = source.index("frame_generator = extractor.decode_frames()")
        handler_at = source.index("Error processing frames ")

        assert "i = -1" in source[generator_at:handler_at], (
            "the batch index must be pre-bound between decode_frames() and the "
            "handler that reports it, or a first-batch failure is masked"
        )

    def test_unbound_index_would_mask_the_real_error(self):
        """Demonstrates the failure mode the pre-binding prevents."""
        real_error = RuntimeError("frame too large for pool")

        def run_without_prebinding():
            try:
                for i, _batch in enumerate(iter([])):
                    pass
                raise real_error
            except Exception as exc:  # noqa: BLE001
                raise RuntimeError(f"Error processing frame batch {i}: {exc}") from exc

        with pytest.raises(UnboundLocalError):
            run_without_prebinding()

        def run_with_prebinding():
            i = -1
            try:
                for i, _batch in enumerate(iter([])):
                    pass
                raise real_error
            except Exception as exc:  # noqa: BLE001
                raise RuntimeError(f"Error processing frame batch {i}: {exc}") from exc

        with pytest.raises(RuntimeError, match="frame too large for pool"):
            run_with_prebinding()


class TestApiSurfacesActionableError:
    """A too-large frame must reject the request with the actionable message.

    Previously the decoder error reached the endpoint's generic ``except
    Exception`` handler, which replied 500 with an opaque "server error", so the
    caller never learned which resolution was rejected or how to fix it.
    """

    def test_error_is_a_valueerror_so_endpoints_return_400(self):
        assert issubclass(FrameTooLargeForPoolError, ValueError), (
            "endpoints map ValueError to 400 with the real message; any other "
            "base class collapses this into an opaque 500"
        )


class TestPoolShutdownIsIdempotent:
    """shutdown() runs twice: once explicitly, once from __del__ at GC.

    The second pass used to re-unlink every already-released segment, emitting a
    spurious "already unlinked" DEBUG line per block on every successful run.
    """

    def test_second_shutdown_is_a_no_op(self):
        from src.core.embedding.decoder import SharedMemoryPool

        pool = SharedMemoryPool(block_size=1024, max_blocks=3)

        pool.shutdown()

        with mock.patch.object(pool, "unlink") as unlink, mock.patch.object(pool, "close") as close:
            pool.shutdown()

        unlink.assert_not_called()
        close.assert_not_called()

    def test_first_shutdown_still_releases_blocks(self):
        from src.core.embedding.decoder import SharedMemoryPool

        pool = SharedMemoryPool(block_size=1024, max_blocks=2)

        with mock.patch.object(pool, "unlink") as unlink, mock.patch.object(pool, "close") as close:
            pool.shutdown()

        unlink.assert_called_once()
        close.assert_called_once()

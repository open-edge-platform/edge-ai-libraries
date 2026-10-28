# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Regression tests for the video pipeline stall watchdog.

A detection inference wedged by a GPU hang never returns, so its worker thread
stays alive but never hands the batch on. The completion wait only checked for
*dead* workers, so the ingestion stayed "running" forever. The watchdog fails the
pipeline once no stage has made progress for PIPELINE_STALL_TIMEOUT_S.
"""

import queue
import threading
import time
from unittest import mock

import pytest

from src.core.embedding import embedding_helper as eh


@pytest.fixture
def fast_timeouts():
    with (
        mock.patch.object(eh.settings, "PIPELINE_STALL_TIMEOUT_S", 0.3),
        mock.patch.object(eh.settings, "PIPELINE_QUEUE_GET_TIMEOUT_S", 0.05),
    ):
        yield


class TestHeartbeatQueue:
    def test_put_and_get_record_progress(self):
        hb = eh._PipelineHeartbeat()
        q = eh._HeartbeatQueue(2, hb)

        before = hb.last
        time.sleep(0.01)
        q.put("a")
        after_put = hb.last
        time.sleep(0.01)
        assert q.get() == "a"

        assert before < after_put < hb.last

    def test_timeouts_do_not_record_progress(self):
        hb = eh._PipelineHeartbeat()
        q = eh._HeartbeatQueue(1, hb)
        q.put("a")

        with pytest.raises(queue.Full):
            q.put("b", timeout=0.01)
        q.get()
        last = hb.last
        with pytest.raises(queue.Empty):
            q.get(timeout=0.01)

        assert hb.last == last


class TestRaiseIfPipelineStalled:
    def test_raises_after_limit(self, fast_timeouts):
        hb = eh._PipelineHeartbeat()
        start = time.monotonic()
        time.sleep(0.35)

        with pytest.raises(eh.PipelineStalledError) as excinfo:
            eh._raise_if_pipeline_stalled(hb, start, "waiting for detection")

        message = str(excinfo.value)
        assert "waiting for detection" in message
        assert "MM_DATAPREP_PIPELINE_STALL_TIMEOUT_S" in message

    def test_recent_progress_keeps_pipeline_alive(self, fast_timeouts):
        hb = eh._PipelineHeartbeat()
        start = time.monotonic()
        time.sleep(0.35)
        hb.beat()

        eh._raise_if_pipeline_stalled(hb, start, "waiting")

    def test_idle_time_before_wait_started_is_ignored(self, fast_timeouts):
        # A live source may legitimately produce nothing for a long time; only time
        # spent waiting on the workers counts.
        hb = eh._PipelineHeartbeat()
        time.sleep(0.35)

        eh._raise_if_pipeline_stalled(hb, time.monotonic(), "waiting")

    def test_zero_disables_watchdog(self):
        hb = eh._PipelineHeartbeat()
        with mock.patch.object(eh.settings, "PIPELINE_STALL_TIMEOUT_S", 0):
            eh._raise_if_pipeline_stalled(hb, time.monotonic() - 10_000, "waiting")


class TestPutWithStallWatchdog:
    def test_put_into_wedged_full_queue_fails(self, fast_timeouts):
        hb = eh._PipelineHeartbeat()
        q = eh._HeartbeatQueue(1, hb)
        q.put("occupied")  # consumer is hung and never drains it

        with pytest.raises(eh.PipelineStalledError):
            eh._put_with_stall_watchdog(q, "next", hb, "queueing batch 1")

    def test_put_succeeds_once_consumer_drains(self, fast_timeouts):
        hb = eh._PipelineHeartbeat()
        q = eh._HeartbeatQueue(1, hb)
        q.put("occupied")
        threading.Timer(0.1, q.get).start()

        eh._put_with_stall_watchdog(q, "next", hb, "queueing batch 1")

        assert q.get_nowait() == "next"

    def test_slow_but_progressing_consumer_is_not_a_stall(self, fast_timeouts):
        # Other stages beating the heartbeat keep a long wait alive.
        hb = eh._PipelineHeartbeat()
        q = eh._HeartbeatQueue(1, hb)
        q.put("occupied")
        stop = threading.Event()

        def other_stage():
            while not stop.wait(0.05):
                hb.beat()

        t = threading.Thread(target=other_stage)
        t.start()
        threading.Timer(0.6, q.get).start()
        try:
            eh._put_with_stall_watchdog(q, "next", hb, "queueing batch 1")
        finally:
            stop.set()
            t.join()

        assert q.get_nowait() == "next"


def _tiny_mp4(frames: int = 8) -> bytes:
    av = pytest.importorskip("av")
    import io

    import numpy as np

    buf = io.BytesIO()
    with av.open(buf, mode="w", format="mp4") as container:
        stream = container.add_stream("mpeg4", rate=8)
        stream.width, stream.height, stream.pix_fmt = 64, 64, "yuv420p"
        for _ in range(frames):
            frame = av.VideoFrame.from_ndarray(
                np.zeros((64, 64, 3), dtype=np.uint8), format="rgb24"
            )
            container.mux(stream.encode(frame))
        container.mux(stream.encode())
    return buf.getvalue()


class TestPipelineFailsOnHungInference:
    def test_hung_detection_fails_the_pipeline_instead_of_hanging(self, fast_timeouts):
        release = threading.Event()

        def hung_detection_worker(detection_meta_queue, *_args, **_kwargs):
            detection_meta_queue.get()
            release.wait(30)  # simulates an OpenVINO infer() wedged by a GPU hang

        result = {}

        def run():
            try:
                eh._process_video_from_memory_simple_pipeline(
                    video_source=_tiny_mp4(),
                    embedding_client=mock.MagicMock(),
                    metadata_dict={"video_id": "v", "filename": "v.mp4"},
                    frame_interval=1,
                    enable_object_detection=True,
                    shutdown_event=threading.Event(),
                )
            except Exception as exc:  # noqa: BLE001 - asserting on the type below
                result["error"] = exc

        with (
            mock.patch.object(eh, "detection_worker", hung_detection_worker),
            mock.patch.object(eh.settings, "VIDEO_FRAME_TRANSPORT", "heap"),
        ):
            t = threading.Thread(target=run, daemon=True)
            t.start()
            t.join(20)
        release.set()

        assert not t.is_alive(), "pipeline hung instead of failing"
        assert isinstance(result.get("error"), eh.PipelineStalledError)

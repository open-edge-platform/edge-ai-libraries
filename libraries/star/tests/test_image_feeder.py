# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import pytest
from pathlib import Path

from PIL import Image

from semantic_img_comp.image_feeder import FEEDER_DONE, feed_images
from semantic_img_comp.image_feeder import feeder as feeder_module


class _DummyLogger:
    def debug(self, *args, **kwargs) -> None:
        return None

    def info(self, *args, **kwargs) -> None:
        return None


def test_feed_images_logs_total_input_bytes_enqueued(tmp_path: Path, monkeypatch):
    img1 = tmp_path / "frame_001.jpg"
    img2 = tmp_path / "frame_002.jpg"
    Image.new("RGB", (8, 6), color="red").save(img1, format="JPEG")
    Image.new("RGB", (10, 6), color="blue").save(img2, format="JPEG")
    expected_total = img1.stat().st_size + img2.stat().st_size

    events = []
    q = feeder_module.queue.Queue()
    stop_event = feeder_module.threading.Event()

    monkeypatch.setattr(feeder_module, "log_json", lambda logger, record: events.append(record))

    feed_images(
        image_paths=[img1, img2],
        out_queue=q,
        target_mbps=None,
        run_duration_sec=None,
        log_feeder_events=False,
        duration_stop_event=stop_event,
        logger=_DummyLogger(),
    )

    # feeder_enqueued is intentionally muted; verify feeder still queued both images.
    queue_items = []
    while True:
        item = q.get_nowait()
        queue_items.append(item)
        if item is FEEDER_DONE:
            break
    assert queue_items.count(FEEDER_DONE) == 1
    assert sum(1 for item in queue_items if item is not FEEDER_DONE) == 2

    feeder_event = next(e for e in events if e["event"] == "feeder_enqueue_completed")
    assert feeder_event["images_released"] == 2
    assert feeder_event["total_input_bytes_enqueued"] == expected_total


def test_feed_images_preserves_seeded_order_and_logs_seed(tmp_path: Path, monkeypatch):
    img1 = tmp_path / "frame_001.jpg"
    img2 = tmp_path / "frame_002.jpg"
    img3 = tmp_path / "frame_003.jpg"
    for img in (img1, img2, img3):
        Image.new("RGB", (8, 6), color="red").save(img, format="JPEG")

    events = []
    q = feeder_module.queue.Queue()
    stop_event = feeder_module.threading.Event()

    monkeypatch.setattr(feeder_module, "log_json", lambda logger, record: events.append(record))

    seeded_order = [img2, img1, img3]
    feed_images(
        image_paths=seeded_order,
        out_queue=q,
        target_mbps=None,
        run_duration_sec=None,
        log_feeder_events=True,
        duration_stop_event=stop_event,
        logger=_DummyLogger(),
        catalog_random_seed=123,
    )

    released = []
    while True:
        item = q.get_nowait()
        if item is FEEDER_DONE:
            break
        released.append(item)

    assert released == seeded_order
    enqueue_events = [e for e in events if e["event"] == "feeder_enqueued"]
    assert [e["feed_index"] for e in enqueue_events] == [1, 2, 3]
    assert all(e["catalog_random_seed"] == 123 for e in enqueue_events)


def test_feed_images_logs_rate_limited_and_enqueued_when_enabled(tmp_path: Path, monkeypatch):
    img1 = tmp_path / "frame_001.jpg"
    img2 = tmp_path / "frame_002.jpg"
    Image.new("RGB", (8, 6), color="red").save(img1, format="JPEG")
    Image.new("RGB", (10, 6), color="blue").save(img2, format="JPEG")

    events = []
    q = feeder_module.queue.Queue()
    stop_event = feeder_module.threading.Event()
    slept = []

    monkeypatch.setattr(feeder_module.time, "perf_counter", lambda: 0.0)
    monkeypatch.setattr(feeder_module.time, "sleep", lambda s: slept.append(s))
    monkeypatch.setattr(feeder_module, "log_json", lambda logger, record: events.append(record))

    feed_images(
        image_paths=[img1, img2],
        out_queue=q,
        target_mbps=1.1,
        run_duration_sec=None,
        log_feeder_events=True,
        duration_stop_event=stop_event,
        logger=_DummyLogger(),
    )

    event_names = [event["event"] for event in events]
    assert "feeder_enqueued" in event_names
    assert "feeder_rate_limited" in event_names
    assert "feeder_enqueue_completed" in event_names
    assert slept and slept[0] > 0

# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
"""Unit tests for core.gst_worker module (FPS counting logic)."""

import json
import sys
import threading
import time
from unittest.mock import MagicMock, patch

import pytest

# Mock GStreamer so the module can be imported without a real GStreamer install
sys.modules['gi'] = MagicMock()
sys.modules['gi.repository'] = MagicMock()
sys.modules['gi.repository.Gst'] = MagicMock()
sys.modules['gi.repository.GLib'] = MagicMock()

# Import after mocking
from core.gst_worker import GstWorker, _Instance, _emit, _metric_event
from gi.repository import Gst, GLib


def _make_iterator(items):
    """Build a mock GStreamer Iterator whose .next() yields
    (Gst.IteratorResult.OK, item) for each item, then (Gst.IteratorResult.DONE, None),
    matching the protocol GstWorker._attach_fps_probes consumes."""
    results = [(Gst.IteratorResult.OK, item) for item in items]
    results.append((Gst.IteratorResult.DONE, None))
    it = MagicMock()
    it.next.side_effect = results
    return it


def _make_sink(pads):
    """Build a mock sink element whose iterate_sink_pads() yields *pads*."""
    elem = MagicMock()
    elem.iterate_sink_pads.return_value = _make_iterator(pads)
    return elem


# Test classes follow
class TestOnBufferProbe:
    """Test the buffer probe callback (GstWorker._on_buffer_probe): counts
    exactly one frame per buffer flowing through the pad it's attached to."""

    def test_probe_callback_increments_frame_count(self):
        """A single call increments both the windowed and total counters."""
        mock_inst = MagicMock()
        mock_inst.frame_count = 0
        mock_inst.total_frame_count = 0
        mock_inst.frames_after_warmup = 0
        mock_inst.warmup_frames = 0
        mock_inst.first_frame_sent = True
        mock_inst.frame_count_lock = threading.Lock()

        result = GstWorker._on_buffer_probe(None, None, mock_inst)

        assert mock_inst.frame_count == 1
        assert mock_inst.total_frame_count == 1
        # Verify the probe returns OK to continue processing.
        assert result is Gst.PadProbeReturn.OK

    def test_probe_callback_thread_safety(self):
        """Repeated calls (simulating the streaming thread) increment
        correctly under the instance's frame_count_lock."""
        mock_inst = MagicMock()
        mock_inst.frame_count = 0
        mock_inst.total_frame_count = 0
        mock_inst.frames_after_warmup = 0
        mock_inst.warmup_frames = 0
        mock_inst.first_frame_sent = True
        mock_inst.frame_count_lock = threading.Lock()

        for _ in range(10):
            GstWorker._on_buffer_probe(None, None, mock_inst)

        assert mock_inst.frame_count == 10
        assert mock_inst.total_frame_count == 10


class TestAttachFpsProbes:
    """Test GstWorker._attach_fps_probes: attaches a buffer-counting probe
    to exactly the first terminal sink pad found, regardless of how many
    sinks the pipeline has."""

    def test_attaches_probe_to_first_sink_pad(self):
        """A single-sink pipeline gets exactly one probe, and returns 1."""
        pad = MagicMock()
        sink = _make_sink([pad])
        pipeline = MagicMock()
        pipeline.iterate_sinks.return_value = _make_iterator([sink])
        inst = MagicMock()

        result = GstWorker._attach_fps_probes(pipeline, inst)

        assert result == 1
        pad.add_probe.assert_called_once_with(Gst.PadProbeType.BUFFER, GstWorker._on_buffer_probe, inst)

    def test_no_sinks_returns_zero(self):
        """No terminal sinks found: no probe attached, returns 0."""
        pipeline = MagicMock()
        pipeline.iterate_sinks.return_value = _make_iterator([])
        inst = MagicMock()

        result = GstWorker._attach_fps_probes(pipeline, inst)

        assert result == 0

    def test_multiple_sinks_only_first_gets_probe(self):
        """Simulates a tee fan-out to 3 destinations: only the first sink's
        pad gets a probe; the other two are left untouched. This is what
        prevents the fps-tripling bug (probing every sink would count each
        duplicated frame once per destination)."""
        pad1, pad2, pad3 = MagicMock(), MagicMock(), MagicMock()
        sink1 = _make_sink([pad1])
        sink2 = _make_sink([pad2])
        sink3 = _make_sink([pad3])
        pipeline = MagicMock()
        pipeline.iterate_sinks.return_value = _make_iterator([sink1, sink2, sink3])
        inst = MagicMock()

        result = GstWorker._attach_fps_probes(pipeline, inst)

        assert result == 1
        pad1.add_probe.assert_called_once()
        pad2.add_probe.assert_not_called()
        pad3.add_probe.assert_not_called()

    def test_tee_fanout_frame_count_not_multiplied(self):
        """End-to-end regression for the fps-tripling bug: attach probes on a
        3-sink (tee fan-out) pipeline via the real _attach_fps_probes, then
        drive the actually-registered callback like GStreamer would --
        frame_count must equal the number of buffers, not 3x."""
        pad1, pad2, pad3 = MagicMock(), MagicMock(), MagicMock()
        sink1 = _make_sink([pad1])
        sink2 = _make_sink([pad2])
        sink3 = _make_sink([pad3])
        pipeline = MagicMock()
        pipeline.iterate_sinks.return_value = _make_iterator([sink1, sink2, sink3])
        inst = _Instance(instance_id="test", pipeline=pipeline)

        attached = GstWorker._attach_fps_probes(pipeline, inst)
        assert attached == 1

        # Extract the callback + inst that _attach_fps_probes actually
        # registered on the first sink's pad, and drive it as GStreamer would
        # for every real buffer that flows through the pipeline.
        _, callback, callback_inst = pad1.add_probe.call_args[0]
        for _ in range(10):
            callback(pad1, None, callback_inst)

        assert inst.frame_count == 10
        assert inst.total_frame_count == 10


class TestPollFps:
    """Test GstWorker._poll_fps: computes windowed ("last_fps") and
    cumulative ("avg_fps") fps from the instance's frame counters and emits
    an 'fps' status event."""

    @staticmethod
    def _make_inst(frame_count, total_frame_count, window_elapsed, total_elapsed):
        now = time.monotonic()
        return _Instance(
            instance_id="test-instance",
            pipeline=MagicMock(),
            frame_count=frame_count,
            total_frame_count=total_frame_count,
            frames_after_warmup=total_frame_count,
            warmup_frame_time=now - total_elapsed,
            start_time=now - total_elapsed,
            last_poll_time=now - window_elapsed,
        )

    def test_emits_fps_event_with_expected_values(self):
        """30 frames over a ~1s window, 90 frames over a ~3s lifetime."""
        inst = self._make_inst(frame_count=30, total_frame_count=90, window_elapsed=1.0, total_elapsed=3.0)
        worker = GstWorker()

        with patch("core.gst_worker._emit") as mock_emit:
            worker._poll_fps(inst)

        mock_emit.assert_called_once()
        payload = mock_emit.call_args[0][0]
        assert payload["instance_id"] == "test-instance"
        assert payload["event"] == "fps"
        assert payload["last_fps"] == pytest.approx(30.0, rel=0.05)
        assert payload["avg_fps"] == pytest.approx(30.0, rel=0.05)

    def test_resets_window_count_but_not_total(self):
        """frame_count (windowed) resets to 0 after each poll; total_frame_count does not."""
        inst = self._make_inst(frame_count=15, total_frame_count=45, window_elapsed=1.0, total_elapsed=2.0)
        worker = GstWorker()

        with patch("core.gst_worker._emit"):
            worker._poll_fps(inst)

        assert inst.frame_count == 0
        assert inst.total_frame_count == 45

    def test_returns_source_continue(self):
        """_poll_fps always returns GLib.SOURCE_CONTINUE so the timer keeps firing."""
        inst = self._make_inst(frame_count=1, total_frame_count=1, window_elapsed=1.0, total_elapsed=1.0)
        worker = GstWorker()

        with patch("core.gst_worker._emit"):
            result = worker._poll_fps(inst)

        assert result is GLib.SOURCE_CONTINUE

    def test_skips_emit_when_window_elapsed_non_positive(self):
        """Guards against a divide-by-zero / meaningless spike if polled
        again before any wall-clock time has actually passed."""
        now = time.monotonic()
        inst = _Instance(
            instance_id="test",
            pipeline=MagicMock(),
            frame_count=5,
            total_frame_count=5,
            start_time=now,
            last_poll_time=now + 10,  # in the future -> window_elapsed < 0
        )
        worker = GstWorker()

        with patch("core.gst_worker._emit") as mock_emit:
            worker._poll_fps(inst)

        mock_emit.assert_not_called()


class TestTeardownFlushesFinalFps:
    """Test GstWorker._teardown: flushes one final "fps" event (via
    _poll_fps) before emitting "stopped", so pipelines stopped/aborted
    before the periodic poll timer ever got to fire on its own (i.e. torn
    down within the first _FPS_POLL_INTERVAL_SECONDS of running) still
    report real fps instead of 0."""

    def test_emits_final_fps_event_for_short_lived_pipeline(self):
        """A pipeline that processed frames but is torn down before its
        first periodic poll must still report non-zero fps, not 0, and
        that final fps event must precede "stopped"."""
        now = time.monotonic()
        inst = _Instance(
            instance_id="short-lived",
            pipeline=MagicMock(),
            frame_count=5,
            total_frame_count=5,
            frames_after_warmup=5,
            warmup_frame_time=now - 0.2,
            start_time=now - 0.2,
            last_poll_time=now - 0.2,
        )
        worker = GstWorker()
        with worker._lock:
            worker._instances["short-lived"] = inst

        with patch("core.gst_worker._emit") as mock_emit:
            worker._teardown("short-lived")

        events = [call.args[0] for call in mock_emit.call_args_list]
        assert [e["event"] for e in events] == ["fps", "stopped"]
        assert events[0]["avg_fps"] > 0

    def test_destroys_fps_source_before_final_poll(self):
        """fps_source.destroy() happens first, so the periodic timer is
        guaranteed not to fire again concurrently with the final poll."""
        fps_source = MagicMock()
        inst = _Instance(instance_id="inst", pipeline=MagicMock(), fps_source=fps_source)
        worker = GstWorker()
        with worker._lock:
            worker._instances["inst"] = inst

        with patch("core.gst_worker._emit"):
            worker._teardown("inst")

        fps_source.destroy.assert_called_once()


class TestStopUnknownInstance:
    """Stop for an instance that never registered must still report "stopped"."""

    def test_emits_stopped_for_unknown_instance(self):
        worker = GstWorker()
        with patch("core.gst_worker._emit") as mock_emit:
            worker.stop("never-started")

        mock_emit.assert_called_once_with({"instance_id": "never-started", "event": "stopped"})


class TestFailedStartReportsStopped:
    """A start that fails before registering a pipeline must still end with "stopped"."""

    def test_parse_failure_emits_error_then_stopped(self):
        worker = GstWorker()
        with patch("core.gst_worker.Gst.parse_launch", side_effect=RuntimeError("boom")), \
                patch("core.gst_worker._emit") as mock_emit:
            worker.start("bad-start", "fakesrc ! fakesink")

        events = [call.args[0] for call in mock_emit.call_args_list]
        assert [e["event"] for e in events] == ["error", "stopped"]
        assert all(e["instance_id"] == "bad-start" for e in events)


class _FakeStructure:
    def __init__(self, name, fields):
        self._name = name
        self._fields = fields

    def get_name(self):
        return self._name

    def n_fields(self):
        return len(self._fields)

    def nth_field_name(self, index):
        return list(self._fields)[index]

    def get_value(self, field_name):
        return self._fields[field_name]


def _element_message(structure, src_name="sink"):
    message = MagicMock()
    message.get_structure.return_value = structure
    message.src.get_name.return_value = src_name
    return message


class TestMetricEvent:
    """dlstreamer/* element messages become "metric" events; anything else is ignored."""

    def test_latency_window_message_is_forwarded(self):
        fields = {"version": 1, "pipeline": "inst", "source": "src", "sink": "sink",
                  "window_ms": 1000.5, "count": 30, "sum_ms": 90.0, "min_ms": 2.0, "max_ms": 4.0}
        event = _metric_event("inst", _element_message(_FakeStructure("dlstreamer/latency-window", fields)))
        assert event["event"] == "metric"
        assert event["instance_id"] == "inst"
        assert event["kind"] == "latency-window"
        assert event["element"] == "sink"
        assert event["fields"]["count"] == 30 and "version" not in event["fields"]

    def test_foreign_element_message_is_ignored(self):
        message = _element_message(_FakeStructure("level", {"rms": [0.1]}))
        assert _metric_event("inst", message) is None

    def test_message_without_structure_is_ignored(self):
        assert _metric_event("inst", _element_message(None)) is None

    def test_unsupported_schema_version_is_not_forwarded(self):
        fields = {"version": 2, "count": 30}
        assert _metric_event("inst", _element_message(_FakeStructure("dlstreamer/latency-window", fields))) is None

    def test_field_json_cannot_encode_does_not_break_the_event(self, capsys):
        class Opaque:
            def __str__(self):
                return "opaque"

        _emit({"instance_id": "inst", "event": "metric", "fields": {"value": Opaque()}})
        assert json.loads(capsys.readouterr().out) == {
            "instance_id": "inst", "event": "metric", "fields": {"value": "opaque"},
        }

    def test_gst_value_arrays_are_forwarded_as_lists(self, monkeypatch, capsys):
        from core import gst_worker

        class FakeValueArray:
            """Mimics gi.overrides.Gst.ValueArray: indexable, str() is "<1,2,0>"."""

            def __init__(self, items):
                self.array = list(items)

            def __getitem__(self, index):
                return self.array[index]

            def __len__(self):
                return len(self.array)

            def __str__(self):
                return "<" + ",".join(str(item) for item in self.array) + ">"

        class FakeValueList(FakeValueArray):
            pass

        monkeypatch.setattr(gst_worker.Gst, "ValueArray", FakeValueArray, raising=False)
        monkeypatch.setattr(gst_worker.Gst, "ValueList", FakeValueList, raising=False)
        fields = {"version": 1, "source": "src", "sink": "sink", "window_ms": 1000.0, "count": 3,
                  "sum_ms": 6.0, "min_ms": 1.0, "max_ms": 3.0, "sum_sq_ms": 14.0,
                  "bucket_bounds_ms": FakeValueArray([1.0, 2.5]), "bucket_counts": FakeValueArray([1, 2, 0]),
                  "nested": FakeValueList([FakeValueArray([1, 2])])}
        event = _metric_event("inst", _element_message(_FakeStructure("dlstreamer/latency-window", fields)))
        assert event["fields"]["bucket_bounds_ms"] == [1.0, 2.5]
        assert event["fields"]["bucket_counts"] == [1, 2, 0]
        assert event["fields"]["nested"] == [[1, 2]]

        _emit(event)
        emitted = json.loads(capsys.readouterr().out)["fields"]
        assert emitted["bucket_counts"] == [1, 2, 0] and emitted["sum_sq_ms"] == 14.0

    def test_field_gi_cannot_convert_is_dropped_not_fatal(self):
        class Structure(_FakeStructure):
            def get_value(self, field_name):
                if field_name == "bucket_counts":
                    raise TypeError("unknown type GstValueArray")
                return super().get_value(field_name)

        fields = {"version": 1, "count": 3, "bucket_counts": None}
        event = _metric_event("inst", _element_message(Structure("dlstreamer/latency-window", fields)))
        assert event["fields"] == {"count": 3}

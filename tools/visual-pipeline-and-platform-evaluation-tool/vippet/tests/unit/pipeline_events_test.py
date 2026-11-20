# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import json
import os
import tempfile
import unittest
from unittest.mock import MagicMock, patch

import pipeline_events
from pipeline_events import (
    EventCapture,
    remove_event_folders,
    EventFileReader,
    EventSource,
    add_event_outputs,
    parse_record,
)

CV_TRIGGERED_VLM = (
    "filesrc location=/videos/a.ts ! decodebin3 ! gvadetect name=detect_s0 ! tee name=t "
    "t. ! queue ! fakesink name=default_output_sink "
    "t. ! queue ! gvaproximitytrigger_py name=trigger_s0 class-a=car class-b=person ! "
    'gvagenai name=genai_s0 prompt="Is it safe? Reply ! briefly" metrics=true ! '
    "gvametaconvert ! fakesink"
)


class TestAddEventOutputs(unittest.TestCase):
    def test_rewrites_trigger_and_genai(self):
        command, sources = add_event_outputs(
            CV_TRIGGERED_VLM, "/metadata/.events/j/r", "s0"
        )

        trigger_path = "/metadata/.events/j/r/s0-0.jsonl"
        genai_path = "/metadata/.events/j/r/s0-1.jsonl"
        self.assertEqual(
            sources,
            {
                trigger_path: EventSource("trigger", "trigger_s0", stream_id="s0"),
                genai_path: EventSource(
                    "vlm", "genai_s0", "Is it safe? Reply ! briefly", "s0"
                ),
            },
        )
        self.assertIn(f"class-b=person events-file={trigger_path} ! gvagenai", command)
        self.assertIn(
            "metrics=true ! gvametapublish file-format=json-lines "
            f"file-path={genai_path} ! gvametaconvert",
            command,
        )
        # The quoted "!" in the prompt is not taken for a separator.
        self.assertIn('prompt="Is it safe? Reply ! briefly"', command)

    def test_keeps_an_explicit_events_file(self):
        command = (
            "videotestsrc ! gvaproximitytrigger_py events-file=/x.jsonl ! fakesink"
        )
        self.assertEqual(add_event_outputs(command, "/d", "s"), (command, {}))

    def test_leaves_pipelines_without_event_elements_unchanged(self):
        command = "videotestsrc ! gvadetect ! fakesink"
        self.assertEqual(add_event_outputs(command, "/d", "s"), (command, {}))

    def test_stream_id_is_made_safe_for_a_path(self):
        _, sources = add_event_outputs(
            "videotestsrc ! gvagenai ! fakesink", "/d", "a/b c"
        )
        self.assertEqual(list(sources), ["/d/a_b_c-0.jsonl"])


class TestParseRecord(unittest.TestCase):
    def test_trigger_record(self):
        event, fields = parse_record(
            {"source": "proximity-trigger", "text": " fired ", "pts-seconds": 1.5},
            EventSource("trigger", "trigger_s0"),
        )
        assert event is not None
        self.assertEqual(
            (event.source, event.text, event.element, event.pts_seconds),
            ("proximity-trigger", "fired", "trigger_s0", 1.5),
        )
        self.assertIsNone(fields)

    def test_vlm_answer_with_metrics(self):
        event, fields = parse_record(
            {
                "result": "No. Nobody is hit.",
                "timestamp_seconds": 3,
                "metrics": {
                    "ttft_mean": 10,
                    "tpot_mean": 2.5,
                    "generate_duration_mean": 90,
                },
            },
            EventSource("vlm", "genai_s0", "Is it safe?"),
        )
        assert event is not None
        self.assertEqual(
            (event.source, event.text, event.element, event.pts_seconds, event.prompt),
            ("vlm", "No. Nobody is hit.", "genai_s0", 3.0, "Is it safe?"),
        )
        self.assertEqual(
            fields, {"ttft_ms": 10.0, "tpot_ms": 2.5, "generate_duration_ms": 90.0}
        )

    def test_records_without_text_or_complete_metrics(self):
        source = EventSource("vlm")
        self.assertEqual(parse_record({"objects": []}, source), (None, None))
        self.assertEqual(
            parse_record({"result": "", "metrics": {"ttft_mean": 1}}, source),
            (None, None),
        )
        self.assertEqual(
            parse_record({"text": 1}, EventSource("trigger")), (None, None)
        )


class TestEventFileReader(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = os.path.join(self.tmp.name, "s0-0.jsonl")
        self.events = []
        self.metrics = []
        self.reader = EventFileReader(
            {self.path: EventSource("vlm", "genai_s0")},
            self.events.append,
            lambda fields, element: self.metrics.append((fields, element)),
        )

    def tearDown(self):
        self.tmp.cleanup()

    def _append(self, data: str) -> None:
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(data)

    def test_missing_file_is_skipped(self):
        self.reader.read_once()
        self.assertEqual(self.events, [])

    def test_partial_record_waits_for_its_newline(self):
        record = json.dumps({"result": "Yes"})
        self._append(record[:5])
        self.reader.read_once()
        self.assertEqual(self.events, [])

        self._append(record[5:] + "\n")
        self.reader.read_once()
        self.assertEqual([e.text for e in self.events], ["Yes"])

    def test_blank_malformed_and_non_object_records_are_skipped(self):
        self._append("\n{not json\n[1, 2]\n" + json.dumps({"result": "A"}) + "\n")
        self.reader.read_once()
        self.reader.read_once()
        self.assertEqual([e.text for e in self.events], ["A"])

    def test_metrics_go_to_the_metrics_callback(self):
        self._append(
            json.dumps(
                {
                    "result": "A",
                    "metrics": {
                        "ttft_mean": 1,
                        "tpot_mean": 2,
                        "generate_duration_mean": 3,
                    },
                }
            )
            + "\n"
        )
        self.reader.read_once()
        self.assertEqual(
            self.metrics,
            [
                (
                    {"ttft_ms": 1.0, "tpot_ms": 2.0, "generate_duration_ms": 3.0},
                    "genai_s0",
                )
            ],
        )

    def test_metrics_of_an_unnamed_element_are_tagged_with_the_stream(self):
        metrics = []
        reader = EventFileReader(
            {self.path: EventSource("vlm", stream_id="s0")},
            self.events.append,
            lambda fields, element: metrics.append(element),
        )
        self._append(
            json.dumps(
                {
                    "result": "A",
                    "metrics": {
                        "ttft_mean": 1,
                        "tpot_mean": 2,
                        "generate_duration_mean": 3,
                    },
                }
            )
            + "\n"
        )
        reader.read_once()
        self.assertEqual(metrics, ["s0"])

    def test_handler_error_does_not_stop_reading(self):
        on_event = MagicMock(side_effect=[RuntimeError("boom"), None])
        reader = EventFileReader({self.path: EventSource("vlm")}, on_event)
        self._append(
            json.dumps({"result": "A"}) + "\n" + json.dumps({"result": "B"}) + "\n"
        )
        with self.assertLogs("pipeline_events", level="ERROR"):
            reader.read_once()
        self.assertEqual(on_event.call_count, 2)

    def test_stop_reads_what_is_left(self):
        self.reader.poll_interval = 60
        self.reader.start()
        self._append(json.dumps({"result": "late"}) + "\n")
        self.reader.stop()
        self.assertEqual([e.text for e in self.events], ["late"])


class TestEventCapture(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        patcher = patch.object(pipeline_events, "EVENTS_DIR", self.tmp.name)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(self.tmp.cleanup)

    def test_no_capture_without_event_elements(self):
        capture = EventCapture.create({"s0": "videotestsrc ! fakesink"}, "job", print)
        self.assertIsNone(capture)
        self.assertEqual(os.listdir(self.tmp.name), [])

    def test_lifecycle(self):
        events = []
        capture = EventCapture.create(
            {"s0": "videotestsrc ! gvagenai ! fakesink"}, "job-1", events.append
        )
        assert capture is not None
        self.assertTrue(
            capture.directory.startswith(os.path.join(self.tmp.name, "job-1"))
        )
        self.assertTrue(os.path.isdir(capture.directory))
        (path,) = capture.sources
        self.assertIn(f"file-path={path}", capture.commands["s0"])

        capture.reader.poll_interval = 60
        capture.start()
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps({"result": "from the run"}) + "\n")
        capture.close()

        self.assertEqual([e.text for e in events], ["from the run"])
        self.assertEqual(os.listdir(self.tmp.name), [])

    def test_remove_event_folders_deletes_leftovers(self):
        capture = EventCapture.create(
            {"s0": "videotestsrc ! gvagenai ! fakesink"}, "job-1", print
        )
        assert capture is not None
        (path,) = capture.sources
        with open(path, "w", encoding="utf-8") as f:
            f.write(json.dumps({"result": "left behind"}) + "\n")

        remove_event_folders()

        self.assertFalse(os.path.exists(self.tmp.name))
        remove_event_folders()  # nothing left: no error

    def test_folder_that_cannot_be_created_disables_events(self):
        with (
            patch("pipeline_events.os.makedirs", side_effect=PermissionError("ro")),
            self.assertLogs("pipeline_events", level="WARNING"),
        ):
            capture = EventCapture.create(
                {"s0": "videotestsrc ! gvagenai ! fakesink"}, "job", print
            )
        self.assertIsNone(capture)


if __name__ == "__main__":
    unittest.main()

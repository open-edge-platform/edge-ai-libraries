"""Unit tests for the result types in ``pipeline_runner``."""

import unittest

from pipeline_runner import LatencyTracerSample, PipelineResult


class TestPipelineResultRepr(unittest.TestCase):
    """Coverage for the custom ``PipelineResult.__repr__``.

    The implementation formats ``latency_tracer_metrics`` by its
    cardinality so the repr stays compact when many streams are
    running; both branches (``None`` and non-empty dict) must be
    covered.
    """

    def test_repr_with_latency_metrics_none(self):
        """When tracer is disabled the repr uses the literal ``None`` marker."""
        result = PipelineResult(total_fps=10.0, per_stream_fps=5.0, num_streams=2)
        text = repr(result)
        self.assertIn("PipelineResult(", text)
        self.assertIn("latency_tracer_metrics=None", text)

    def test_repr_with_latency_metrics_streams(self):
        """When tracer produced samples the repr summarises their count."""
        sample = LatencyTracerSample(
            interval_ms=1000.0,
            avg_ms=10.0,
            min_ms=1.0,
            max_ms=100.0,
            latency_ms=5.0,
        )
        result = PipelineResult(
            total_fps=10.0,
            per_stream_fps=5.0,
            num_streams=2,
            latency_tracer_metrics={"a": sample, "b": sample},
        )
        text = repr(result)
        self.assertIn("latency_tracer_metrics=<2 stream(s)>", text)


class TestPipelineResultMinStreamFps(unittest.TestCase):
    def test_none_without_per_stream_fps(self):
        self.assertIsNone(PipelineResult(total_fps=10.0).min_stream_fps)

    def test_slowest_stream(self):
        result = PipelineResult(stream_fps={"a": 30.0, "b": 12.5})
        self.assertEqual(result.min_stream_fps, 12.5)


if __name__ == "__main__":
    unittest.main()

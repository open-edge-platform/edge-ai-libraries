import itertools
import unittest
from unittest.mock import MagicMock, patch

from pipeline_runner import PipelineRunner, PipelineRunResult
from gstpipeline import GstPipeline


class TestPipeline(GstPipeline):
    def __init__(self, pipeline_description):
        super().__init__(pipeline_description=pipeline_description)

    def evaluate(self, regular_channels, inference_channels):
        return "gst-launch-1.0 -q " + " ".join(
            [self._pipeline_description] * (inference_channels + regular_channels)
        )


class TestPipelineRunner(unittest.TestCase):
    def setUp(self):
        test_pipeline_description = (
            "videotestsrc "
            " num-buffers=5 "
            " pattern=snow ! "
            "videoconvert ! "
            "gvafpscounter ! "
            "fakesink"
        )
        self.pipeline = TestPipeline(test_pipeline_description)

    @patch("pipeline_runner.Popen")
    @patch("pipeline_runner.ps")
    @patch("pipeline_runner.select.select")
    def test_run_pipeline(self, mock_select, mock_ps, mock_popen):
        expected_result = PipelineRunResult(
            total_fps=100.0, per_stream_fps=100.0, num_streams=1
        )

        # Mock process
        process_mock = MagicMock()
        process_mock.poll.side_effect = [None, 0]
        # Avoid StopIteration by returning empty bytes forever after the real line
        process_mock.stdout.readline.side_effect = itertools.chain(
            [
                f"FpsCounter(average 10.0sec): total={expected_result.total_fps} fps, number-streams={expected_result.num_streams}, per-stream={expected_result.per_stream_fps} fps\n".encode(
                    "utf-8"
                )
            ],
            itertools.repeat(b""),
        )
        process_mock.pid = 1234
        # Ensure fileno returns an int to avoid TypeError in select and bad fd errors
        process_mock.stdout.fileno.return_value = 10
        process_mock.stderr.fileno.return_value = 11
        process_mock.wait.return_value = 0
        mock_select.return_value = ([process_mock.stdout], [], [])
        mock_popen.return_value = process_mock
        mock_ps.Process.return_value.status.return_value = "zombie"

        runner = PipelineRunner()
        results = runner.run(
            pipeline_description=self.pipeline, regular_channels=2, inference_channels=2
        )

        self.assertIsInstance(results, PipelineRunResult)
        self.assertEqual(results.total_fps, expected_result.total_fps)
        self.assertEqual(results.per_stream_fps, expected_result.per_stream_fps)
        self.assertEqual(results.num_streams, expected_result.num_streams)

    @patch("pipeline_runner.Popen")
    def test_stop_pipeline(self, mock_popen):
        expected_result = PipelineRunResult(
            total_fps=0, per_stream_fps=0, num_streams=0
        )

        # Mock process
        process_mock = MagicMock()
        process_mock.poll.side_effect = [None]
        process_mock.wait.return_value = -1
        mock_popen.return_value = process_mock

        runner = PipelineRunner()
        runner.cancel()
        results = runner.run(
            pipeline_description=self.pipeline, regular_channels=2, inference_channels=2
        )

        self.assertTrue(runner.is_cancelled())
        self.assertIsInstance(results, PipelineRunResult)
        self.assertEqual(results.total_fps, expected_result.total_fps)
        self.assertEqual(results.per_stream_fps, expected_result.per_stream_fps)
        self.assertEqual(results.num_streams, expected_result.num_streams)


if __name__ == "__main__":
    unittest.main()

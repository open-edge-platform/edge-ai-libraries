import time
import unittest
from unittest.mock import patch

from api.api_schemas import (
    PipelineRequestRun,
    PipelineParametersRun,
    PipelineRequestBenchmark,
    PipelineParametersBenchmark,
    PipelineInstanceState,
    PipelineType,
    Source,
    SourceType,
)
from managers.instance_manager import InstanceManager, PipelineInstance


class TestInstanceManager(unittest.TestCase):
    def test_run_pipeline_calls_execute_pipeline_and_returns_instance_id(self):
        manager = InstanceManager()
        initial_count = len(manager.instances)

        pipeline_request = PipelineRequestRun(
            source=Source(
                type=SourceType.URI,
                uri="test-recording-uri",
            ),
            parameters=PipelineParametersRun(
                inferencing_channels=1,
                recording_channels=0,
                launch_config="gst-launch-1.0 -q filesrc location=/tmp/dummy-video.mp4 ! decodebin3 ! autovideosink",
            ),
            tags=None,
        )

        with patch.object(manager, "_execute_pipeline") as mock_execute:
            instance_id = manager.run_pipeline(
                "user-defined-pipelines", "test-pipeline", pipeline_request
            )
            self.assertIsInstance(instance_id, str)
            self.assertIn(instance_id, manager.instances)
            self.assertEqual(initial_count + 1, len(manager.instances))
            mock_execute.assert_called_once_with(
                instance_id, "user-defined-pipelines", "test-pipeline", pipeline_request
            )

    def test_run_pipeline_creates_instance_with_running_state(self):
        manager = InstanceManager()
        pipeline_request = PipelineRequestRun(
            source=Source(
                type=SourceType.URI,
                uri="test-recording-uri",
            ),
            parameters=PipelineParametersRun(
                inferencing_channels=1,
                recording_channels=0,
                launch_config="gst-launch-1.0 -q filesrc location=/tmp/dummy-video.mp4 ! decodebin3 ! autovideosink",
            ),
            tags=None,
        )

        with patch.object(manager, "_execute_pipeline"):
            instance_id = manager.run_pipeline(
                "user-defined-pipelines", "test-pipeline", pipeline_request
            )
            instance = manager.instances[instance_id]
            self.assertEqual(instance.name, "user-defined-pipelines")
            self.assertEqual(instance.version, "test-pipeline")
            self.assertEqual(instance.request, pipeline_request)
            self.assertEqual(instance.state.name, PipelineInstanceState.RUNNING)
            self.assertIsInstance(instance.start_time, int)
            self.assertIsNone(instance.end_time)

    def test_benchmark_pipeline_creates_instance_with_running_state_and_returns_instance_id(
        self,
    ):
        manager = InstanceManager()
        initial_count = len(manager.instances)

        pipeline_request = PipelineRequestBenchmark(
            source=Source(
                type=SourceType.URI,
                uri="test-recording-uri",
            ),
            parameters=PipelineParametersBenchmark(
                fps_floor=30,
                ai_stream_rate=100,
                launch_config="gst-launch-1.0 -q filesrc location=/tmp/dummy-video.mp4 ! decodebin3 ! autovideosink",
            ),
            tags=None,
        )

        with patch.object(manager, "_execute_benchmark") as mock_execute:
            instance_id = manager.benchmark_pipeline(
                "user-defined-pipelines", "test-pipeline", pipeline_request
            )
            self.assertIsInstance(instance_id, str)
            self.assertEqual(initial_count + 1, len(manager.instances))

            instance = manager.instances[instance_id]
            self.assertEqual(instance.name, "user-defined-pipelines")
            self.assertEqual(instance.version, "test-pipeline")
            self.assertEqual(instance.request, pipeline_request)
            self.assertEqual(instance.state.name, PipelineInstanceState.RUNNING)
            self.assertIsInstance(instance.start_time, int)
            self.assertIsNone(instance.end_time)

            mock_execute.assert_called_once_with(
                instance_id, "user-defined-pipelines", "test-pipeline", pipeline_request
            )

    def test_get_all_instance_statuses_returns_correct_statuses(self):
        manager = InstanceManager()

        # Create two instances
        pipeline_request_run = PipelineRequestRun(
            source=Source(
                type=SourceType.URI,
                uri="test-recording-uri",
            ),
            parameters=PipelineParametersRun(
                inferencing_channels=1,
                recording_channels=0,
                launch_config="gst-launch-1.0 -q filesrc location=/tmp/dummy-video.mp4 ! decodebin3 ! autovideosink",
            ),
            tags=None,
        )

        pipeline_request_benchmark = PipelineRequestBenchmark(
            source=Source(
                type=SourceType.URI,
                uri="test-recording-uri",
            ),
            parameters=PipelineParametersBenchmark(
                fps_floor=30,
                ai_stream_rate=100,
                launch_config="gst-launch-1.0 -q filesrc location=/tmp/dummy-video.mp4 ! decodebin3 ! autovideosink",
            ),
            tags=None,
        )

        with (
            patch.object(manager, "_execute_pipeline"),
            patch.object(manager, "_execute_benchmark"),
        ):
            instance_id_run = manager.run_pipeline(
                "user-defined-pipelines", "test-pipeline", pipeline_request_run
            )
            instance_id_benchmark = manager.benchmark_pipeline(
                "user-defined-pipelines", "test-pipeline", pipeline_request_benchmark
            )

        statuses = manager.get_all_instance_statuses()
        self.assertEqual(len(statuses), 2)

        status_run = next((s for s in statuses if s.id == instance_id_run), None)
        status_benchmark = next(
            (s for s in statuses if s.id == instance_id_benchmark), None
        )

        self.assertIsNotNone(status_run)
        self.assertIsNotNone(status_benchmark)
        assert status_run is not None  # for pyright type checking
        assert status_benchmark is not None  # for pyright type checking
        self.assertEqual(status_run.state.name, PipelineInstanceState.RUNNING)
        self.assertEqual(status_benchmark.state.name, PipelineInstanceState.RUNNING)

    def test_get_instance_status_returns_none_for_nonexistent_instance(self):
        manager = InstanceManager()
        status = manager.get_instance_status("nonexistent-instance-id")
        self.assertIsNone(status)

    def test_get_instance_status_returns_correct_status(self):
        manager = InstanceManager()

        # Create an instance manually and add it to the manager
        pipeline_request_run = PipelineRequestRun(
            source=Source(
                type=SourceType.URI,
                uri="test-recording-uri",
            ),
            parameters=PipelineParametersRun(
                inferencing_channels=1,
                recording_channels=0,
                launch_config="gst-launch-1.0 -q filesrc location=/tmp/dummy-video.mp4 ! decodebin3 ! autovideosink",
            ),
            tags=None,
        )
        instance = PipelineInstance(
            id="test-instance-id",
            name="user-defined-pipelines",
            version="test-pipeline",
            request=pipeline_request_run,
            start_time=int(time.time()),
            state=PipelineInstanceState.RUNNING,
            total_fps=120,
            per_stream_fps=30,
            ai_streams=3,
            non_ai_streams=0,
        )
        manager.instances[instance.id] = instance

        status = manager.get_instance_status(instance.id)
        self.assertIsNotNone(status)
        assert status is not None  # for pyright type checking
        self.assertEqual(status.id, instance.id)
        self.assertEqual(status.state, instance.state)
        self.assertEqual(status.total_fps, instance.total_fps)
        self.assertEqual(status.per_stream_fps, instance.per_stream_fps)
        self.assertEqual(status.ai_streams, instance.ai_streams)
        self.assertEqual(status.non_ai_streams, instance.non_ai_streams)

    def test_get_instance_summary_returns_none_for_nonexistent_instance(self):
        manager = InstanceManager()
        summary = manager.get_instance_summary("nonexistent-instance-id")
        self.assertIsNone(summary)

    def test_get_instance_summary_returns_correct_summary(self):
        manager = InstanceManager()

        # Create an instance manually and add it to the manager
        pipeline_request = PipelineRequestRun(
            source=Source(
                type=SourceType.URI,
                uri="test-recording-uri",
            ),
            parameters=PipelineParametersRun(
                inferencing_channels=1,
                recording_channels=0,
                launch_config="gst-launch-1.0 -q filesrc location=/tmp/dummy-video.mp4 ! decodebin3 ! autovideosink",
            ),
            tags=None,
        )

        instance = PipelineInstance(
            id="test-instance-id",
            name="user-defined-pipelines",
            version="test-pipeline",
            request=pipeline_request,
            start_time=int(time.time()),
            state=PipelineInstanceState.RUNNING,
        )
        manager.instances[instance.id] = instance

        summary = manager.get_instance_summary(instance.id)
        self.assertIsNotNone(summary)
        assert summary is not None  # for pyright type checking
        self.assertEqual(summary.id, instance.id)
        self.assertEqual(summary.request, instance.request)
        self.assertEqual(summary.type, PipelineType.GSTREAMER)

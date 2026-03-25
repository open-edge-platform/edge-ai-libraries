import time
import unittest
from unittest.mock import patch, MagicMock

from benchmark import BenchmarkResult
from graph import Graph
from internal_types import (
    InternalDensityJobStatus,
    InternalDensityJobSummary,
    InternalExecutionConfig,
    InternalOutputMode,
    InternalPerformanceJobStatus,
    InternalPerformanceJobSummary,
    InternalPipelineDensitySpec,
    InternalPipelinePerformanceSpec,
    InternalPipelineStreamSpec,
    InternalDensityTestSpec,
    InternalPerformanceTestSpec,
    InternalTestJobState,
)
from managers.tests_manager import TestsManager
from managers.pipeline_manager import PipelineManager
from pipeline_runner import PipelineRunner, PipelineResult


def create_simple_graph() -> Graph:
    """Helper to create a simple valid pipeline Graph object from a dict."""
    return Graph.from_dict(
        {
            "nodes": [
                {"id": "0", "type": "fakesrc", "data": {}},
                {"id": "1", "type": "fakesink", "data": {}},
            ],
            "edges": [{"id": "0", "source": "0", "target": "1"}],
        }
    )


def create_usb_camera_graph(device: str = "/dev/video0") -> Graph:
    """Helper to create a pipeline Graph object with USB camera source (v4l2src)."""
    return Graph.from_dict(
        {
            "nodes": [
                {"id": "0", "type": "v4l2src", "data": {"device": device}},
                {"id": "1", "type": "fakesink", "data": {}},
            ],
            "edges": [{"id": "0", "source": "0", "target": "1"}],
        }
    )


def create_internal_execution_config(
    output_mode: InternalOutputMode = InternalOutputMode.DISABLED,
    max_runtime: float = 0,
) -> InternalExecutionConfig:
    """Helper to create InternalExecutionConfig for testing."""
    return InternalExecutionConfig(
        output_mode=output_mode,
        max_runtime=max_runtime,
    )


def create_internal_performance_spec(
    pipeline_id: str = "/pipelines/pipeline-test123/variants/variant-abc",
    pipeline_name: str = "Test Pipeline",
    streams: int = 1,
) -> InternalPipelinePerformanceSpec:
    """Helper to create InternalPipelinePerformanceSpec for testing."""
    return InternalPipelinePerformanceSpec(
        pipeline_id=pipeline_id,
        pipeline_name=pipeline_name,
        pipeline_graph=create_simple_graph(),
        streams=streams,
    )


def create_internal_density_spec(
    pipeline_id: str = "/pipelines/pipeline-test123/variants/variant-abc",
    pipeline_name: str = "Test Pipeline",
    stream_rate: int = 100,
) -> InternalPipelineDensitySpec:
    """Helper to create InternalPipelineDensitySpec for testing."""
    return InternalPipelineDensitySpec(
        pipeline_id=pipeline_id,
        pipeline_name=pipeline_name,
        pipeline_graph=create_simple_graph(),
        stream_rate=stream_rate,
    )


def create_internal_performance_test_spec(
    pipeline_specs: list[InternalPipelinePerformanceSpec] | None = None,
    execution_config: InternalExecutionConfig | None = None,
    original_request: dict | None = None,
) -> InternalPerformanceTestSpec:
    """Helper to create InternalPerformanceTestSpec for testing."""
    if pipeline_specs is None:
        pipeline_specs = [create_internal_performance_spec()]
    if execution_config is None:
        execution_config = create_internal_execution_config()
    if original_request is None:
        original_request = {"pipeline_performance_specs": [], "execution_config": {}}
    return InternalPerformanceTestSpec(
        pipeline_performance_specs=pipeline_specs,
        execution_config=execution_config,
        original_request=original_request,
    )


def create_internal_density_test_spec(
    pipeline_specs: list[InternalPipelineDensitySpec] | None = None,
    fps_floor: int = 30,
    execution_config: InternalExecutionConfig | None = None,
    original_request: dict | None = None,
) -> InternalDensityTestSpec:
    """Helper to create InternalDensityTestSpec for testing."""
    if pipeline_specs is None:
        pipeline_specs = [create_internal_density_spec()]
    if execution_config is None:
        execution_config = create_internal_execution_config()
    if original_request is None:
        original_request = {
            "fps_floor": fps_floor,
            "pipeline_density_specs": [],
            "execution_config": {},
        }
    return InternalDensityTestSpec(
        fps_floor=fps_floor,
        pipeline_density_specs=pipeline_specs,
        execution_config=execution_config,
        original_request=original_request,
    )


class TestTestsManager(unittest.TestCase):
    def setUp(self):
        """Reset singleton state before each test."""
        TestsManager._instance = None
        PipelineManager._instance = None

    def tearDown(self):
        """Reset singleton state after each test."""
        TestsManager._instance = None
        PipelineManager._instance = None

    @patch("managers.tests_manager.PipelineManager")
    def test_test_performance_calls_execute_performance_test_and_returns_job_id(
        self, mock_pipeline_manager_cls
    ):
        mock_pipeline_manager_cls.return_value = MagicMock()

        manager = TestsManager()
        initial_count = len(manager.jobs)

        internal_spec = create_internal_performance_test_spec()

        with patch.object(manager, "_execute_performance_test") as mock_execute:
            job_id = manager.test_performance(internal_spec)
            self.assertIsInstance(job_id, str)
            self.assertIn(job_id, manager.jobs)
            self.assertEqual(initial_count + 1, len(manager.jobs))
            mock_execute.assert_called_once_with(job_id, internal_spec)

    @patch("managers.tests_manager.PipelineManager")
    def test_test_performance_creates_job_with_running_state(
        self, mock_pipeline_manager_cls
    ):
        mock_pipeline_manager_cls.return_value = MagicMock()

        manager = TestsManager()
        original_request = {
            "pipeline_performance_specs": [
                {
                    "pipeline": {
                        "source": "variant",
                        "pipeline_id": "pipeline-test456",
                        "variant_id": "variant-def",
                    },
                    "streams": 1,
                }
            ],
            "execution_config": {"output_mode": "disabled", "max_runtime": 0},
        }
        internal_spec = create_internal_performance_test_spec(
            pipeline_specs=[
                create_internal_performance_spec(
                    pipeline_id="/pipelines/pipeline-test456/variants/variant-def",
                    pipeline_name="Test Pipeline 456",
                )
            ],
            original_request=original_request,
        )

        with patch.object(manager, "_execute_performance_test"):
            job_id = manager.test_performance(internal_spec)
            job = manager.jobs[job_id]
            assert isinstance(job, InternalPerformanceJobStatus)
            self.assertEqual(job.request, original_request)
            self.assertEqual(job.state, InternalTestJobState.RUNNING)
            self.assertIsInstance(job.start_time, int)
            self.assertIsNone(job.end_time)
            self.assertEqual(job.details, [])

    @patch("managers.tests_manager.PipelineManager")
    def test_test_density_creates_job_with_running_state_and_returns_job_id(
        self, mock_pipeline_manager_cls
    ):
        mock_pipeline_manager_cls.return_value = MagicMock()

        manager = TestsManager()
        initial_count = len(manager.jobs)

        original_request = {
            "fps_floor": 30,
            "pipeline_density_specs": [
                {
                    "pipeline": {
                        "source": "variant",
                        "pipeline_id": "pipeline-test789",
                        "variant_id": "variant-ghi",
                    },
                    "stream_rate": 100,
                }
            ],
            "execution_config": {"output_mode": "disabled", "max_runtime": 0},
        }
        internal_spec = create_internal_density_test_spec(
            pipeline_specs=[
                create_internal_density_spec(
                    pipeline_id="/pipelines/pipeline-test789/variants/variant-ghi",
                    pipeline_name="Test Pipeline 789",
                )
            ],
            original_request=original_request,
        )

        with patch.object(manager, "_execute_density_test") as mock_execute:
            job_id = manager.test_density(internal_spec)
            self.assertIsInstance(job_id, str)
            self.assertEqual(initial_count + 1, len(manager.jobs))

            job = manager.jobs[job_id]
            assert isinstance(job, InternalDensityJobStatus)
            self.assertEqual(job.request, original_request)
            self.assertEqual(job.state, InternalTestJobState.RUNNING)
            self.assertIsInstance(job.start_time, int)
            self.assertIsNone(job.end_time)
            self.assertEqual(job.details, [])

            mock_execute.assert_called_once_with(job_id, internal_spec)

    @patch("managers.tests_manager.PipelineManager")
    def test_get_job_statuses_by_type_returns_correct_statuses(
        self, mock_pipeline_manager_cls
    ):
        mock_pipeline_manager_cls.return_value = MagicMock()

        manager = TestsManager()

        # Create two jobs with different types
        performance_spec = create_internal_performance_test_spec(
            pipeline_specs=[
                create_internal_performance_spec(
                    pipeline_id="/pipelines/pipeline-perf123/variants/variant-perf",
                )
            ],
        )

        density_spec = create_internal_density_test_spec(
            pipeline_specs=[
                create_internal_density_spec(
                    pipeline_id="/pipelines/pipeline-dens456/variants/variant-dens",
                )
            ],
        )

        with (
            patch.object(manager, "_execute_performance_test"),
            patch.object(manager, "_execute_density_test"),
        ):
            job_id_performance = manager.test_performance(performance_spec)
            job_id_density = manager.test_density(density_spec)

        performance_statuses = manager.get_job_statuses_by_type(
            InternalPerformanceJobStatus
        )
        self.assertEqual(len(performance_statuses), 1)

        density_statuses = manager.get_job_statuses_by_type(InternalDensityJobStatus)
        self.assertEqual(len(density_statuses), 1)

        status_performance = next(
            (s for s in performance_statuses if s.id == job_id_performance), None
        )
        status_density = next(
            (s for s in density_statuses if s.id == job_id_density), None
        )

        self.assertIsNotNone(status_performance)
        self.assertIsNotNone(status_density)
        assert status_performance is not None
        assert status_density is not None
        self.assertIsInstance(status_performance, InternalPerformanceJobStatus)
        self.assertIsInstance(status_density, InternalDensityJobStatus)
        self.assertEqual(status_performance.state, InternalTestJobState.RUNNING)
        self.assertEqual(status_density.state, InternalTestJobState.RUNNING)

    @patch("managers.tests_manager.PipelineManager")
    def test_get_job_status_returns_none_for_nonexistent_job(
        self, mock_pipeline_manager_cls
    ):
        mock_pipeline_manager_cls.return_value = MagicMock()

        manager = TestsManager()
        status = manager.get_job_status("nonexistent-job-id")
        self.assertIsNone(status)

    @patch("managers.tests_manager.PipelineManager")
    def test_get_job_status_returns_correct_status(self, mock_pipeline_manager_cls):
        mock_pipeline_manager_cls.return_value = MagicMock()

        manager = TestsManager()

        original_request = {
            "pipeline_performance_specs": [],
            "execution_config": {},
        }

        streams_per_pipeline = [
            InternalPipelineStreamSpec(
                id="/pipelines/pipeline-abc123/variants/variant-abc",
                streams=1,
            )
        ]

        job = InternalPerformanceJobStatus(
            id="test-job-id",
            request=original_request,
            start_time=int(time.time() * 1000),
            state=InternalTestJobState.RUNNING,
            total_fps=120,
            per_stream_fps=30,
            total_streams=1,
            streams_per_pipeline=streams_per_pipeline,
        )
        manager.jobs[job.id] = job

        status = manager.get_job_status(job.id)
        self.assertIsNotNone(status)
        assert status is not None
        self.assertIsInstance(status, InternalPerformanceJobStatus)
        self.assertEqual(status.id, job.id)
        self.assertEqual(status.state, InternalTestJobState.RUNNING)
        self.assertEqual(status.total_fps, job.total_fps)
        self.assertEqual(status.per_stream_fps, job.per_stream_fps)
        self.assertEqual(status.total_streams, job.total_streams)
        self.assertEqual(status.details, [])

        self.assertIsNotNone(status.streams_per_pipeline)
        for spec in status.streams_per_pipeline or []:
            self.assertIsInstance(spec, InternalPipelineStreamSpec)

    @patch("managers.tests_manager.PipelineManager")
    def test_get_job_summary_returns_none_for_nonexistent_job(
        self, mock_pipeline_manager_cls
    ):
        mock_pipeline_manager_cls.return_value = MagicMock()

        manager = TestsManager()
        summary = manager.get_job_summary("nonexistent-job-id")
        self.assertIsNone(summary)

    @patch("managers.tests_manager.PipelineManager")
    def test_get_job_summary_returns_correct_summary(self, mock_pipeline_manager_cls):
        mock_pipeline_manager_cls.return_value = MagicMock()

        manager = TestsManager()

        original_request = {
            "pipeline_performance_specs": [
                {
                    "pipeline": {
                        "source": "variant",
                        "pipeline_id": "pipeline-def456",
                        "variant_id": "variant-def",
                    },
                    "streams": 1,
                }
            ],
            "execution_config": {"output_mode": "disabled", "max_runtime": 0},
        }

        job = InternalPerformanceJobStatus(
            id="test-job-id",
            request=original_request,
            start_time=int(time.time() * 1000),
            state=InternalTestJobState.RUNNING,
        )
        manager.jobs[job.id] = job

        summary = manager.get_job_summary(job.id)
        self.assertIsNotNone(summary)
        assert summary is not None
        self.assertIsInstance(summary, InternalPerformanceJobSummary)
        self.assertEqual(summary.id, job.id)
        self.assertEqual(summary.request, job.request)

    @patch("managers.tests_manager.PipelineManager")
    def test_get_job_summary_returns_density_summary_for_density_job(
        self, mock_pipeline_manager_cls
    ):
        mock_pipeline_manager_cls.return_value = MagicMock()

        manager = TestsManager()

        original_request = {
            "fps_floor": 30,
            "pipeline_density_specs": [],
            "execution_config": {},
        }

        job = InternalDensityJobStatus(
            id="test-density-summary",
            request=original_request,
            start_time=int(time.time() * 1000),
            state=InternalTestJobState.RUNNING,
        )
        manager.jobs[job.id] = job

        summary = manager.get_job_summary(job.id)
        self.assertIsNotNone(summary)
        assert summary is not None
        self.assertIsInstance(summary, InternalDensityJobSummary)
        self.assertEqual(summary.id, job.id)
        self.assertEqual(summary.request, job.request)

    @patch("managers.tests_manager.PipelineManager")
    def test_stop_job_stops_running_job(self, mock_pipeline_manager_cls):
        mock_pipeline_manager_cls.return_value = MagicMock()

        manager = TestsManager()

        # Create a job and runner manually and add them to the manager
        original_request = {"pipeline_performance_specs": [], "execution_config": {}}

        job_id = "test-job-id"
        job = InternalPerformanceJobStatus(
            id=job_id,
            request=original_request,
            start_time=int(time.time() * 1000),
            state=InternalTestJobState.RUNNING,
        )
        manager.jobs[job_id] = job
        manager.runners[job_id] = PipelineRunner(mode="normal", max_runtime=0)

        success, message = manager.stop_job(job_id)
        self.assertTrue(success)
        self.assertIn(f"Job {job_id} stopped", message)

    @patch("managers.tests_manager.PipelineManager")
    def test_stop_job_returns_false_for_nonexistent_job(
        self, mock_pipeline_manager_cls
    ):
        mock_pipeline_manager_cls.return_value = MagicMock()

        manager = TestsManager()
        success, message = manager.stop_job("nonexistent-job-id")
        self.assertFalse(success)
        self.assertIn("not found", message)

    @patch("managers.tests_manager.PipelineManager")
    def test_stop_job_returns_false_for_nonexistent_runner(
        self, mock_pipeline_manager_cls
    ):
        mock_pipeline_manager_cls.return_value = MagicMock()

        manager = TestsManager()

        # Create a job without a runner
        original_request = {"pipeline_performance_specs": [], "execution_config": {}}

        job_id = "test-job-id"
        job = InternalPerformanceJobStatus(
            id=job_id,
            request=original_request,
            start_time=int(time.time() * 1000),
            state=InternalTestJobState.RUNNING,
        )
        manager.jobs[job_id] = job

        success, message = manager.stop_job(job_id)
        self.assertFalse(success)
        self.assertIn(
            f"No active runner found for job {job_id}. It may have already completed or was never started.",
            message,
        )

    @patch("managers.tests_manager.PipelineManager")
    def test_stop_job_returns_false_for_not_running_job(
        self, mock_pipeline_manager_cls
    ):
        mock_pipeline_manager_cls.return_value = MagicMock()

        manager = TestsManager()

        # Create a job that is not running
        original_request = {"pipeline_performance_specs": [], "execution_config": {}}

        job_id = "test-job-id"
        job = InternalPerformanceJobStatus(
            id=job_id,
            request=original_request,
            start_time=int(time.time() * 1000),
            state=InternalTestJobState.COMPLETED,
        )
        manager.jobs[job_id] = job
        manager.runners[job_id] = PipelineRunner(mode="normal", max_runtime=0)

        success, message = manager.stop_job(job_id)
        self.assertFalse(success)
        self.assertIn(f"Job {job_id} is not running", message)

    @patch("managers.tests_manager.PipelineManager")
    def test_execute_performance_test_starts_pipeline(self, mock_pipeline_manager_cls):
        mock_pipeline_manager_instance = MagicMock()
        mock_pipeline_manager_instance.build_pipeline_command.return_value = (
            "fakesrc ! fakesink",
            {},
            {},
        )
        mock_pipeline_manager_cls.return_value = mock_pipeline_manager_instance

        manager = TestsManager()

        internal_spec = create_internal_performance_test_spec(
            pipeline_specs=[
                create_internal_performance_spec(
                    pipeline_id="/pipelines/pipeline-pqr678/variants/variant-pqr",
                )
            ],
        )

        job_id = "test-job-start"
        job = InternalPerformanceJobStatus(
            id=job_id,
            request=internal_spec.original_request,
            start_time=int(time.time() * 1000),
            state=InternalTestJobState.RUNNING,
        )
        manager.jobs[job_id] = job

        with (
            patch.object(
                PipelineRunner,
                "run",
                return_value=PipelineResult(
                    total_fps=100.0, per_stream_fps=100.0, num_streams=1, exit_code=0
                ),
            ) as mock_run,
            patch(
                "managers.tests_manager.collect_video_outputs_from_dirs",
                return_value={},
            ),
        ):
            manager._execute_performance_test(job_id, internal_spec)
            self.assertIn(job_id, manager.jobs)
            mock_run.assert_called_once()
            # Verify build_pipeline_command was called with job_id
            mock_pipeline_manager_instance.build_pipeline_command.assert_called_once()
            call_args = mock_pipeline_manager_instance.build_pipeline_command.call_args
            self.assertEqual(
                call_args[0][2], job_id
            )  # Third positional argument is job_id

    @patch("managers.tests_manager.PipelineManager")
    def test_execute_performance_test_updates_metrics_on_completion(
        self, mock_pipeline_manager_cls
    ):
        mock_pipeline_manager_instance = MagicMock()
        mock_pipeline_manager_instance.build_pipeline_command.return_value = (
            "fakesrc ! fakesink",
            {},
            {},
        )
        mock_pipeline_manager_cls.return_value = mock_pipeline_manager_instance

        manager = TestsManager()

        internal_spec = create_internal_performance_test_spec(
            pipeline_specs=[
                create_internal_performance_spec(
                    pipeline_id="/pipelines/pipeline-test/variants/variant-1",
                    streams=1,
                ),
                create_internal_performance_spec(
                    pipeline_id="/pipelines/pipeline-test/variants/variant-2",
                    streams=2,
                ),
            ],
        )

        job_id = "test-job-metrics"
        job = InternalPerformanceJobStatus(
            id=job_id,
            request=internal_spec.original_request,
            start_time=int(time.time() * 1000),
            state=InternalTestJobState.RUNNING,
        )
        manager.jobs[job_id] = job

        with (
            patch.object(
                PipelineRunner,
                "run",
                return_value=PipelineResult(
                    total_fps=300.0, per_stream_fps=100.0, num_streams=3, exit_code=0
                ),
            ),
            patch(
                "managers.tests_manager.collect_video_outputs_from_dirs",
                return_value={},
            ),
        ):
            manager._execute_performance_test(job_id, internal_spec)

        updated = manager.jobs[job_id]
        self.assertEqual(updated.state, InternalTestJobState.COMPLETED)
        self.assertEqual(updated.details, ["Pipeline completed successfully"])
        self.assertEqual(updated.total_fps, 300.0)
        self.assertEqual(updated.per_stream_fps, 100.0)
        self.assertEqual(updated.total_streams, 3)
        self.assertIsNotNone(updated.streams_per_pipeline)
        self.assertEqual(len(updated.streams_per_pipeline or []), 2)

        # Verify streams_per_pipeline uses InternalPipelineStreamSpec internally
        if updated.streams_per_pipeline:
            for spec in updated.streams_per_pipeline:
                self.assertIsInstance(spec, InternalPipelineStreamSpec)
                self.assertTrue(spec.id.startswith("/pipelines/"))
                self.assertIn("/variants/", spec.id)

        self.assertNotIn(job_id, manager.runners)

    @patch("managers.tests_manager.PipelineManager")
    def test_execute_performance_test_cancelled_with_zero_exit_code_marks_completed(
        self, mock_pipeline_manager_cls
    ):
        """When cancelled and exit code is 0, job should be COMPLETED with result data saved."""
        mock_pipeline_manager_instance = MagicMock()
        # build_pipeline_command now returns dict[str, str] (directory paths)
        mock_pipeline_manager_instance.build_pipeline_command.return_value = (
            "fakesrc ! fakesink",
            {"/pipelines/p/variants/v": "/tmp/output/pipeline_dir"},
            {},
        )
        mock_pipeline_manager_cls.return_value = mock_pipeline_manager_instance

        manager = TestsManager()

        internal_spec = create_internal_performance_test_spec()

        job_id = "test-job-cancel-completed"
        job = InternalPerformanceJobStatus(
            id=job_id,
            request=internal_spec.original_request,
            start_time=int(time.time() * 1000),
            state=InternalTestJobState.RUNNING,
        )
        manager.jobs[job_id] = job

        # collect_video_outputs_from_dirs converts dir paths to file lists
        collected_files = {
            "/pipelines/p/variants/v": ["/tmp/output/pipeline_dir/main_output.mp4"]
        }

        with (
            patch.object(
                PipelineRunner,
                "run",
                return_value=PipelineResult(
                    total_fps=100.0,
                    per_stream_fps=100.0,
                    num_streams=1,
                    exit_code=0,
                    cancelled=True,
                ),
            ),
            patch(
                "managers.tests_manager.collect_video_outputs_from_dirs",
                return_value=collected_files,
            ),
        ):
            manager._execute_performance_test(job_id, internal_spec)

        updated = manager.jobs[job_id]
        self.assertEqual(updated.state, InternalTestJobState.COMPLETED)
        self.assertEqual(updated.details, ["Cancelled by user"])
        # Result data should be saved
        self.assertEqual(updated.total_fps, 100.0)
        self.assertEqual(updated.per_stream_fps, 100.0)
        self.assertEqual(updated.total_streams, 1)
        self.assertIsNotNone(updated.video_output_paths)
        self.assertEqual(
            updated.video_output_paths,
            {"/pipelines/p/variants/v": ["/tmp/output/pipeline_dir/main_output.mp4"]},
        )
        self.assertNotIn(job_id, manager.runners)

    @patch("managers.tests_manager.PipelineManager")
    def test_execute_performance_test_cancelled_with_nonzero_exit_code_marks_failed(
        self, mock_pipeline_manager_cls
    ):
        """When cancelled and exit code is non-zero, job should be FAILED."""
        mock_pipeline_manager_instance = MagicMock()
        mock_pipeline_manager_instance.build_pipeline_command.return_value = (
            "fakesrc ! fakesink",
            {},
            {},
        )
        mock_pipeline_manager_cls.return_value = mock_pipeline_manager_instance

        manager = TestsManager()

        internal_spec = create_internal_performance_test_spec()

        job_id = "test-job-cancel-failed"
        job = InternalPerformanceJobStatus(
            id=job_id,
            request=internal_spec.original_request,
            start_time=int(time.time() * 1000),
            state=InternalTestJobState.RUNNING,
        )
        manager.jobs[job_id] = job

        with (
            patch.object(
                PipelineRunner,
                "run",
                return_value=PipelineResult(
                    total_fps=0.0,
                    per_stream_fps=0.0,
                    num_streams=1,
                    exit_code=1,
                    cancelled=True,
                ),
            ),
            patch(
                "managers.tests_manager.collect_video_outputs_from_dirs",
                return_value={},
            ),
        ):
            manager._execute_performance_test(job_id, internal_spec)

        updated = manager.jobs[job_id]
        self.assertEqual(updated.state, InternalTestJobState.FAILED)
        self.assertIn("Cancelled by user", updated.details)
        self.assertNotIn(job_id, manager.runners)

    @patch("managers.tests_manager.PipelineManager")
    def test_execute_performance_test_sets_error_on_exception(
        self, mock_pipeline_manager_cls
    ):
        mock_pipeline_manager_instance = MagicMock()
        mock_pipeline_manager_instance.build_pipeline_command.side_effect = ValueError(
            "boom"
        )
        mock_pipeline_manager_cls.return_value = mock_pipeline_manager_instance

        manager = TestsManager()

        internal_spec = create_internal_performance_test_spec()

        job_id = "test-job-exception"
        job = InternalPerformanceJobStatus(
            id=job_id,
            request=internal_spec.original_request,
            start_time=int(time.time() * 1000),
            state=InternalTestJobState.RUNNING,
        )
        manager.jobs[job_id] = job

        manager._execute_performance_test(job_id, internal_spec)

        updated = manager.jobs[job_id]
        self.assertEqual(updated.state, InternalTestJobState.FAILED)
        self.assertIsInstance(updated.details, list)
        self.assertTrue(len(updated.details) > 0)
        self.assertIn("boom", updated.details[0])
        self.assertNotIn(job_id, manager.runners)

    @patch("managers.tests_manager.Benchmark")
    @patch("managers.tests_manager.PipelineManager")
    def test_execute_density_test_updates_metrics_on_completion(
        self, mock_pipeline_manager_cls, mock_benchmark_cls
    ):
        mock_pipeline_manager_cls.return_value = MagicMock()

        mock_benchmark_instance = MagicMock()
        # BenchmarkResult.video_output_paths is now dict[str, str] (directory paths)
        mock_benchmark_instance.run.return_value = BenchmarkResult(
            n_streams=3,
            streams_per_pipeline=[
                InternalPipelineStreamSpec(
                    id="/pipelines/pipeline-test/variants/variant-1",
                    streams=2,
                ),
                InternalPipelineStreamSpec(
                    id="/pipelines/pipeline-test/variants/variant-2",
                    streams=1,
                ),
            ],
            per_stream_fps=90.0,
            video_output_paths={},
        )
        mock_benchmark_instance.runner.is_cancelled.return_value = False
        mock_benchmark_cls.return_value = mock_benchmark_instance

        manager = TestsManager()

        internal_spec = create_internal_density_test_spec(
            pipeline_specs=[
                create_internal_density_spec(
                    pipeline_id="/pipelines/pipeline-test/variants/variant-1",
                    stream_rate=50,
                ),
                create_internal_density_spec(
                    pipeline_id="/pipelines/pipeline-test/variants/variant-2",
                    stream_rate=50,
                ),
            ],
        )

        job_id = "test-density-success"
        job = InternalDensityJobStatus(
            id=job_id,
            request=internal_spec.original_request,
            start_time=int(time.time() * 1000),
            state=InternalTestJobState.RUNNING,
        )
        manager.jobs[job_id] = job

        with patch(
            "managers.tests_manager.collect_video_outputs_from_dirs", return_value={}
        ):
            manager._execute_density_test(job_id, internal_spec)

        mock_benchmark_instance.run.assert_called_once()
        call_kwargs = mock_benchmark_instance.run.call_args[1]
        self.assertEqual(call_kwargs["job_id"], job_id)

        updated = manager.jobs[job_id]
        self.assertEqual(updated.state, InternalTestJobState.COMPLETED)
        self.assertEqual(updated.details, ["Density test completed successfully"])
        self.assertEqual(updated.per_stream_fps, 90.0)
        self.assertEqual(len(updated.streams_per_pipeline or []), 2)
        self.assertEqual(updated.total_streams, 3)
        self.assertNotIn(job_id, manager.runners)

    @patch("managers.tests_manager.Benchmark")
    @patch("managers.tests_manager.PipelineManager")
    def test_execute_density_test_cancelled_marks_failed(
        self, mock_pipeline_manager_cls, mock_benchmark_cls
    ):
        """Cancelled density tests are always FAILED regardless of results."""
        mock_pipeline_manager_cls.return_value = MagicMock()

        mock_benchmark_instance = MagicMock()
        # BenchmarkResult.video_output_paths is now dict[str, str] (directory paths)
        mock_benchmark_instance.run.return_value = BenchmarkResult(
            n_streams=3,
            streams_per_pipeline=[
                InternalPipelineStreamSpec(
                    id="/pipelines/pipeline-test/variants/variant-1",
                    streams=3,
                ),
            ],
            per_stream_fps=90.0,
            video_output_paths={},
        )
        mock_benchmark_instance.runner.is_cancelled.return_value = True
        mock_benchmark_cls.return_value = mock_benchmark_instance

        manager = TestsManager()

        internal_spec = create_internal_density_test_spec()

        job_id = "test-density-cancel"
        job = InternalDensityJobStatus(
            id=job_id,
            request=internal_spec.original_request,
            start_time=int(time.time() * 1000),
            state=InternalTestJobState.RUNNING,
        )
        manager.jobs[job_id] = job

        with patch(
            "managers.tests_manager.collect_video_outputs_from_dirs", return_value={}
        ):
            manager._execute_density_test(job_id, internal_spec)

        updated = manager.jobs[job_id]
        self.assertEqual(updated.state, InternalTestJobState.FAILED)
        self.assertEqual(updated.details, ["Cancelled by user"])
        self.assertNotIn(job_id, manager.runners)

    @patch("managers.tests_manager.Benchmark")
    @patch("managers.tests_manager.PipelineManager")
    def test_execute_density_test_sets_error_on_exception(
        self, mock_pipeline_manager_cls, mock_benchmark_cls
    ):
        mock_pipeline_manager_cls.return_value = MagicMock()

        mock_benchmark_instance = MagicMock()
        mock_benchmark_instance.run.side_effect = RuntimeError("density test failed")
        mock_benchmark_cls.return_value = mock_benchmark_instance

        manager = TestsManager()

        internal_spec = create_internal_density_test_spec()

        job_id = "test-density-exception"
        job = InternalDensityJobStatus(
            id=job_id,
            request=internal_spec.original_request,
            start_time=int(time.time() * 1000),
            state=InternalTestJobState.RUNNING,
        )
        manager.jobs[job_id] = job

        manager._execute_density_test(job_id, internal_spec)

        updated = manager.jobs[job_id]
        self.assertEqual(updated.state, InternalTestJobState.FAILED)
        self.assertIsInstance(updated.details, list)
        self.assertTrue(len(updated.details) > 0)
        self.assertIn("density test failed", updated.details[0])
        self.assertNotIn(job_id, manager.runners)


class TestExecutionConfigValidation(unittest.TestCase):
    """Test cases for ExecutionConfig validation in TestsManager."""

    def setUp(self):
        """Reset singleton state before each test."""
        TestsManager._instance = None
        PipelineManager._instance = None

    def tearDown(self):
        """Reset singleton state after each test."""
        TestsManager._instance = None
        PipelineManager._instance = None

    @patch("managers.tests_manager.PipelineManager")
    def test_validate_execution_config_file_with_max_runtime_raises_error(
        self, mock_pipeline_manager_cls
    ):
        mock_pipeline_manager_cls.return_value = MagicMock()

        manager = TestsManager()
        execution_config = create_internal_execution_config(
            output_mode=InternalOutputMode.FILE,
            max_runtime=60,
        )

        with self.assertRaises(ValueError) as context:
            manager._validate_execution_config(execution_config, is_density_test=False)

        self.assertIn(
            "output_mode='file' cannot be combined with max_runtime > 0",
            str(context.exception),
        )

    @patch("managers.tests_manager.PipelineManager")
    def test_validate_execution_config_file_with_zero_runtime_succeeds(
        self, mock_pipeline_manager_cls
    ):
        mock_pipeline_manager_cls.return_value = MagicMock()

        manager = TestsManager()
        execution_config = create_internal_execution_config(
            output_mode=InternalOutputMode.FILE,
            max_runtime=0,
        )

        manager._validate_execution_config(execution_config, is_density_test=False)

    @patch("managers.tests_manager.PipelineManager")
    def test_validate_execution_config_live_stream_for_density_raises_error(
        self, mock_pipeline_manager_cls
    ):
        mock_pipeline_manager_cls.return_value = MagicMock()

        manager = TestsManager()
        execution_config = create_internal_execution_config(
            output_mode=InternalOutputMode.LIVE_STREAM,
            max_runtime=60,
        )

        with self.assertRaises(ValueError) as context:
            manager._validate_execution_config(execution_config, is_density_test=True)

        self.assertIn(
            "Density tests do not support output_mode='live_stream'",
            str(context.exception),
        )

    @patch("managers.tests_manager.PipelineManager")
    def test_validate_execution_config_live_stream_for_performance_succeeds(
        self, mock_pipeline_manager_cls
    ):
        mock_pipeline_manager_cls.return_value = MagicMock()

        manager = TestsManager()
        execution_config = create_internal_execution_config(
            output_mode=InternalOutputMode.LIVE_STREAM,
            max_runtime=60,
        )

        manager._validate_execution_config(execution_config, is_density_test=False)

    @patch("managers.tests_manager.PipelineManager")
    def test_validate_execution_config_disabled_with_max_runtime_succeeds(
        self, mock_pipeline_manager_cls
    ):
        mock_pipeline_manager_cls.return_value = MagicMock()

        manager = TestsManager()
        execution_config = create_internal_execution_config(
            output_mode=InternalOutputMode.DISABLED,
            max_runtime=60,
        )

        manager._validate_execution_config(execution_config, is_density_test=False)
        manager._validate_execution_config(execution_config, is_density_test=True)


class TestUSBCameraValidation(unittest.TestCase):
    """Test cases for USB camera validation in TestsManager."""

    def setUp(self):
        TestsManager._instance = None
        PipelineManager._instance = None

    def tearDown(self):
        TestsManager._instance = None
        PipelineManager._instance = None

    @patch("managers.tests_manager.PipelineManager")
    def test_performance_single_usb_camera_single_stream_succeeds(
        self, mock_pipeline_manager_cls
    ):
        mock_pipeline_manager_cls.return_value = MagicMock()
        manager = TestsManager()
        spec = InternalPipelinePerformanceSpec(
            pipeline_id="/pipelines/usb-test/variants/v1",
            pipeline_name="USB Camera Pipeline",
            pipeline_graph=create_usb_camera_graph("/dev/video0"),
            streams=1,
        )
        manager._validate_usb_camera_for_performance([spec])

    @patch("managers.tests_manager.PipelineManager")
    def test_performance_single_usb_camera_multiple_streams_raises_error(
        self, mock_pipeline_manager_cls
    ):
        mock_pipeline_manager_cls.return_value = MagicMock()
        manager = TestsManager()
        spec = InternalPipelinePerformanceSpec(
            pipeline_id="/pipelines/usb-test/variants/v1",
            pipeline_name="USB Camera Pipeline",
            pipeline_graph=create_usb_camera_graph("/dev/video0"),
            streams=3,
        )
        with self.assertRaises(ValueError) as context:
            manager._validate_usb_camera_for_performance([spec])
        error_msg = str(context.exception)
        self.assertIn("/dev/video0", error_msg)
        self.assertIn("can only be used in one pipeline with one stream", error_msg)
        self.assertIn("total 3 stream(s)", error_msg)

    @patch("managers.tests_manager.PipelineManager")
    def test_performance_same_usb_camera_multiple_pipelines_raises_error(
        self, mock_pipeline_manager_cls
    ):
        mock_pipeline_manager_cls.return_value = MagicMock()
        manager = TestsManager()
        spec1 = InternalPipelinePerformanceSpec(
            pipeline_id="/pipelines/usb-test1/variants/v1",
            pipeline_name="USB Camera Pipeline 1",
            pipeline_graph=create_usb_camera_graph("/dev/video0"),
            streams=1,
        )
        spec2 = InternalPipelinePerformanceSpec(
            pipeline_id="/pipelines/usb-test2/variants/v2",
            pipeline_name="USB Camera Pipeline 2",
            pipeline_graph=create_usb_camera_graph("/dev/video0"),
            streams=1,
        )
        with self.assertRaises(ValueError) as context:
            manager._validate_usb_camera_for_performance([spec1, spec2])
        error_msg = str(context.exception)
        self.assertIn("/dev/video0", error_msg)
        self.assertIn("can only be used in one pipeline with one stream", error_msg)
        self.assertIn("2 pipeline(s)", error_msg)

    @patch("managers.tests_manager.PipelineManager")
    def test_performance_different_usb_cameras_succeeds(
        self, mock_pipeline_manager_cls
    ):
        mock_pipeline_manager_cls.return_value = MagicMock()
        manager = TestsManager()
        spec1 = InternalPipelinePerformanceSpec(
            pipeline_id="/pipelines/usb-test1/variants/v1",
            pipeline_name="USB Camera Pipeline 1",
            pipeline_graph=create_usb_camera_graph("/dev/video0"),
            streams=1,
        )
        spec2 = InternalPipelinePerformanceSpec(
            pipeline_id="/pipelines/usb-test2/variants/v2",
            pipeline_name="USB Camera Pipeline 2",
            pipeline_graph=create_usb_camera_graph("/dev/video1"),
            streams=1,
        )
        manager._validate_usb_camera_for_performance([spec1, spec2])

    @patch("managers.tests_manager.PipelineManager")
    def test_performance_mixed_sources_with_usb_camera_succeeds(
        self, mock_pipeline_manager_cls
    ):
        mock_pipeline_manager_cls.return_value = MagicMock()
        manager = TestsManager()
        spec1 = InternalPipelinePerformanceSpec(
            pipeline_id="/pipelines/usb-test/variants/v1",
            pipeline_name="USB Camera Pipeline",
            pipeline_graph=create_usb_camera_graph("/dev/video0"),
            streams=1,
        )
        spec2 = InternalPipelinePerformanceSpec(
            pipeline_id="/pipelines/file-test/variants/v2",
            pipeline_name="File Source Pipeline",
            pipeline_graph=create_simple_graph(),
            streams=5,
        )
        manager._validate_usb_camera_for_performance([spec1, spec2])

    @patch("managers.tests_manager.PipelineManager")
    def test_density_with_usb_camera_raises_error(self, mock_pipeline_manager_cls):
        mock_pipeline_manager_cls.return_value = MagicMock()
        manager = TestsManager()
        spec = InternalPipelineDensitySpec(
            pipeline_id="/pipelines/usb-test/variants/v1",
            pipeline_name="USB Camera Pipeline",
            pipeline_graph=create_usb_camera_graph("/dev/video0"),
            stream_rate=100,
        )
        with self.assertRaises(ValueError) as context:
            manager._validate_no_usb_camera_for_density([spec])
        error_msg = str(context.exception)
        self.assertIn(
            "USB camera input sources are not supported in density tests", error_msg
        )
        self.assertIn("/dev/video0", error_msg)
        self.assertIn("USB Camera Pipeline", error_msg)

    @patch("managers.tests_manager.PipelineManager")
    def test_density_with_multiple_usb_cameras_raises_error(
        self, mock_pipeline_manager_cls
    ):
        mock_pipeline_manager_cls.return_value = MagicMock()
        manager = TestsManager()
        spec1 = InternalPipelineDensitySpec(
            pipeline_id="/pipelines/usb-test1/variants/v1",
            pipeline_name="USB Camera Pipeline 1",
            pipeline_graph=create_usb_camera_graph("/dev/video0"),
            stream_rate=50,
        )
        spec2 = InternalPipelineDensitySpec(
            pipeline_id="/pipelines/usb-test2/variants/v2",
            pipeline_name="USB Camera Pipeline 2",
            pipeline_graph=create_usb_camera_graph("/dev/video1"),
            stream_rate=50,
        )
        with self.assertRaises(ValueError) as context:
            manager._validate_no_usb_camera_for_density([spec1, spec2])
        error_msg = str(context.exception)
        self.assertIn(
            "USB camera input sources are not supported in density tests", error_msg
        )
        self.assertIn("/dev/video0", error_msg)
        self.assertIn("/dev/video1", error_msg)
        self.assertIn("USB Camera Pipeline 1", error_msg)
        self.assertIn("USB Camera Pipeline 2", error_msg)

    @patch("managers.tests_manager.PipelineManager")
    def test_density_without_usb_camera_succeeds(self, mock_pipeline_manager_cls):
        mock_pipeline_manager_cls.return_value = MagicMock()
        manager = TestsManager()
        spec = InternalPipelineDensitySpec(
            pipeline_id="/pipelines/file-test/variants/v1",
            pipeline_name="File Source Pipeline",
            pipeline_graph=create_simple_graph(),
            stream_rate=100,
        )
        manager._validate_no_usb_camera_for_density([spec])


class TestLiveStreamUrlsInPerformanceJob(unittest.TestCase):
    """Test cases for live_stream_urls handling in performance tests."""

    def setUp(self):
        TestsManager._instance = None
        PipelineManager._instance = None

    def tearDown(self):
        TestsManager._instance = None
        PipelineManager._instance = None

    @patch("managers.tests_manager.PipelineManager")
    def test_performance_job_status_includes_live_stream_urls(
        self, mock_pipeline_manager_cls
    ):
        mock_pipeline_manager_cls.return_value = MagicMock()
        manager = TestsManager()
        original_request = {"pipeline_performance_specs": [], "execution_config": {}}
        job = InternalPerformanceJobStatus(
            id="test-job-live-stream",
            request=original_request,
            start_time=int(time.time() * 1000),
            state=InternalTestJobState.RUNNING,
            live_stream_urls={
                "/pipelines/pipeline-test/variants/variant-test": "rtsp://mediamtx:8554/stream_test"
            },
        )
        manager.jobs[job.id] = job
        status = manager.get_job_status(job.id)
        self.assertIsNotNone(status)
        assert status is not None

        # get_job_status returns internal type
        self.assertIsInstance(status, InternalPerformanceJobStatus)
        assert isinstance(status, InternalPerformanceJobStatus)
        self.assertEqual(
            status.live_stream_urls,
            {
                "/pipelines/pipeline-test/variants/variant-test": "rtsp://mediamtx:8554/stream_test"
            },
        )

    @patch("managers.tests_manager.PipelineManager")
    def test_density_job_status_does_not_include_live_stream_urls(
        self, mock_pipeline_manager_cls
    ):
        mock_pipeline_manager_cls.return_value = MagicMock()
        manager = TestsManager()
        original_request = {
            "fps_floor": 30,
            "pipeline_density_specs": [],
            "execution_config": {},
        }
        job = InternalDensityJobStatus(
            id="test-density-job",
            request=original_request,
            start_time=int(time.time() * 1000),
            state=InternalTestJobState.RUNNING,
        )
        manager.jobs[job.id] = job
        status = manager.get_job_status(job.id)
        self.assertIsNotNone(status)
        assert status is not None

        # get_job_status returns internal type
        self.assertIsInstance(status, InternalDensityJobStatus)
        self.assertFalse(hasattr(status, "live_stream_urls"))

    @patch("managers.tests_manager.PipelineManager")
    def test_execute_performance_test_updates_live_stream_urls(
        self, mock_pipeline_manager_cls
    ):
        expected_urls = {
            "/pipelines/pipeline-test/variants/variant-test": "rtsp://mediamtx:8554/stream_pipeline-test"
        }
        mock_pipeline_manager_instance = MagicMock()
        mock_pipeline_manager_instance.build_pipeline_command.return_value = (
            "fakesrc ! fakesink",
            {},
            expected_urls,
        )
        mock_pipeline_manager_cls.return_value = mock_pipeline_manager_instance
        manager = TestsManager()
        internal_spec = create_internal_performance_test_spec(
            execution_config=create_internal_execution_config(
                output_mode=InternalOutputMode.LIVE_STREAM, max_runtime=60
            ),
        )
        job_id = "test-job-live-urls"
        job = InternalPerformanceJobStatus(
            id=job_id,
            request=internal_spec.original_request,
            start_time=int(time.time() * 1000),
            state=InternalTestJobState.RUNNING,
        )
        manager.jobs[job_id] = job
        with (
            patch.object(
                PipelineRunner,
                "run",
                return_value=PipelineResult(
                    total_fps=100.0, per_stream_fps=100.0, num_streams=1, exit_code=0
                ),
            ),
            patch(
                "managers.tests_manager.collect_video_outputs_from_dirs",
                return_value={},
            ),
        ):
            manager._execute_performance_test(job_id, internal_spec)
        updated = manager.jobs[job_id]
        assert isinstance(updated, InternalPerformanceJobStatus)
        self.assertEqual(updated.live_stream_urls, expected_urls)


class TestExecutionConfigWithMaxRuntime(unittest.TestCase):
    """Test cases for max_runtime behavior in tests."""

    def setUp(self):
        TestsManager._instance = None
        PipelineManager._instance = None

    def tearDown(self):
        TestsManager._instance = None
        PipelineManager._instance = None

    @patch("managers.tests_manager.PipelineRunner")
    @patch("managers.tests_manager.PipelineManager")
    def test_execute_performance_test_uses_max_runtime_from_config(
        self, mock_pipeline_manager_cls, mock_pipeline_runner_cls
    ):
        mock_pipeline_manager_instance = MagicMock()
        mock_pipeline_manager_instance.build_pipeline_command.return_value = (
            "fakesrc ! fakesink",
            {},
            {},
        )
        mock_pipeline_manager_cls.return_value = mock_pipeline_manager_instance
        mock_runner = MagicMock()
        mock_runner.run.return_value = PipelineResult(
            total_fps=100.0, per_stream_fps=100.0, num_streams=1, exit_code=0
        )
        mock_pipeline_runner_cls.return_value = mock_runner
        manager = TestsManager()
        internal_spec = create_internal_performance_test_spec(
            execution_config=create_internal_execution_config(
                output_mode=InternalOutputMode.DISABLED, max_runtime=120
            ),
        )
        job_id = "test-job-max-runtime"
        job = InternalPerformanceJobStatus(
            id=job_id,
            request=internal_spec.original_request,
            start_time=int(time.time() * 1000),
            state=InternalTestJobState.RUNNING,
        )
        manager.jobs[job_id] = job
        with patch(
            "managers.tests_manager.collect_video_outputs_from_dirs", return_value={}
        ):
            manager._execute_performance_test(job_id, internal_spec)
        mock_pipeline_runner_cls.assert_called_once_with(mode="normal", max_runtime=120)


class TestInlineGraphSupport(unittest.TestCase):
    """Test cases for inline graph support in tests."""

    def setUp(self):
        TestsManager._instance = None
        PipelineManager._instance = None

    def tearDown(self):
        TestsManager._instance = None
        PipelineManager._instance = None

    @patch("managers.tests_manager.PipelineManager")
    def test_performance_test_with_inline_graph(self, mock_pipeline_manager_cls):
        mock_pipeline_manager_cls.return_value = MagicMock()
        manager = TestsManager()
        internal_spec = create_internal_performance_test_spec(
            pipeline_specs=[
                create_internal_performance_spec(
                    pipeline_id="__graph-1234567890abcdef",
                    pipeline_name="__graph-1234567890abcdef",
                    streams=2,
                )
            ],
        )
        with patch.object(manager, "_execute_performance_test") as mock_execute:
            job_id = manager.test_performance(internal_spec)
            self.assertIsInstance(job_id, str)
            self.assertIn(job_id, manager.jobs)
            mock_execute.assert_called_once_with(job_id, internal_spec)

    @patch("managers.tests_manager.PipelineManager")
    def test_density_test_with_inline_graph(self, mock_pipeline_manager_cls):
        mock_pipeline_manager_cls.return_value = MagicMock()
        manager = TestsManager()
        internal_spec = create_internal_density_test_spec(
            pipeline_specs=[
                create_internal_density_spec(
                    pipeline_id="__graph-abcdef1234567890",
                    pipeline_name="__graph-abcdef1234567890",
                    stream_rate=100,
                )
            ],
        )
        with patch.object(manager, "_execute_density_test") as mock_execute:
            job_id = manager.test_density(internal_spec)
            self.assertIsInstance(job_id, str)
            self.assertIn(job_id, manager.jobs)
            mock_execute.assert_called_once_with(job_id, internal_spec)

    @patch("managers.tests_manager.PipelineManager")
    def test_performance_test_with_mixed_sources(self, mock_pipeline_manager_cls):
        mock_pipeline_manager_cls.return_value = MagicMock()
        manager = TestsManager()
        internal_spec = create_internal_performance_test_spec(
            pipeline_specs=[
                create_internal_performance_spec(
                    pipeline_id="/pipelines/pipeline-1/variants/variant-1",
                    pipeline_name="Pipeline 1",
                    streams=2,
                ),
                create_internal_performance_spec(
                    pipeline_id="__graph-1234567890abcdef",
                    pipeline_name="__graph-1234567890abcdef",
                    streams=3,
                ),
            ],
        )
        with patch.object(manager, "_execute_performance_test") as mock_execute:
            job_id = manager.test_performance(internal_spec)
            self.assertIn(job_id, manager.jobs)
            mock_execute.assert_called_once()

    @patch("managers.tests_manager.PipelineManager")
    def test_execute_performance_test_generates_correct_ids_for_inline_graphs(
        self, mock_pipeline_manager_cls
    ):
        mock_pipeline_manager_instance = MagicMock()
        mock_pipeline_manager_instance.build_pipeline_command.return_value = (
            "fakesrc ! fakesink",
            {},
            {},
        )
        mock_pipeline_manager_cls.return_value = mock_pipeline_manager_instance
        manager = TestsManager()
        internal_spec = create_internal_performance_test_spec(
            pipeline_specs=[
                create_internal_performance_spec(
                    pipeline_id="__graph-1234567890abcdef",
                    pipeline_name="__graph-1234567890abcdef",
                )
            ],
        )
        job_id = "test-job-inline-id"
        job = InternalPerformanceJobStatus(
            id=job_id,
            request=internal_spec.original_request,
            start_time=int(time.time() * 1000),
            state=InternalTestJobState.RUNNING,
        )
        manager.jobs[job_id] = job
        with (
            patch.object(
                PipelineRunner,
                "run",
                return_value=PipelineResult(
                    total_fps=100.0, per_stream_fps=100.0, num_streams=1, exit_code=0
                ),
            ),
            patch.object(PipelineRunner, "is_cancelled", return_value=False),
            patch(
                "managers.tests_manager.collect_video_outputs_from_dirs",
                return_value={},
            ),
        ):
            manager._execute_performance_test(job_id, internal_spec)
        updated = manager.jobs[job_id]
        self.assertEqual(updated.state, InternalTestJobState.COMPLETED)
        self.assertEqual(updated.details, ["Pipeline completed successfully"])
        self.assertIsNotNone(updated.streams_per_pipeline)
        if updated.streams_per_pipeline:
            spec = updated.streams_per_pipeline[0]
            self.assertIsInstance(spec, InternalPipelineStreamSpec)
            # ID should follow __graph-{hash} format for inline graphs
            self.assertTrue(spec.id.startswith("__graph-"))
            self.assertEqual(len(spec.id), len("__graph-") + 16)

    @patch("managers.tests_manager.PipelineManager")
    def test_execute_performance_test_generates_correct_ids_for_variant_refs(
        self, mock_pipeline_manager_cls
    ):
        mock_pipeline_manager_instance = MagicMock()
        mock_pipeline_manager_instance.build_pipeline_command.return_value = (
            "fakesrc ! fakesink",
            {},
            {},
        )
        mock_pipeline_manager_cls.return_value = mock_pipeline_manager_instance
        manager = TestsManager()
        internal_spec = create_internal_performance_test_spec(
            pipeline_specs=[
                create_internal_performance_spec(
                    pipeline_id="/pipelines/my-pipeline/variants/my-variant",
                    pipeline_name="My Pipeline",
                )
            ],
        )
        job_id = "test-job-variant-id"
        job = InternalPerformanceJobStatus(
            id=job_id,
            request=internal_spec.original_request,
            start_time=int(time.time() * 1000),
            state=InternalTestJobState.RUNNING,
        )
        manager.jobs[job_id] = job
        with (
            patch.object(
                PipelineRunner,
                "run",
                return_value=PipelineResult(
                    total_fps=100.0, per_stream_fps=100.0, num_streams=1, exit_code=0
                ),
            ),
            patch.object(PipelineRunner, "is_cancelled", return_value=False),
            patch(
                "managers.tests_manager.collect_video_outputs_from_dirs",
                return_value={},
            ),
        ):
            manager._execute_performance_test(job_id, internal_spec)
        updated = manager.jobs[job_id]
        self.assertEqual(updated.state, InternalTestJobState.COMPLETED)
        self.assertEqual(updated.details, ["Pipeline completed successfully"])
        self.assertIsNotNone(updated.streams_per_pipeline)
        if updated.streams_per_pipeline:
            spec = updated.streams_per_pipeline[0]
            self.assertIsInstance(spec, InternalPipelineStreamSpec)
            # ID should follow variant path format
            self.assertEqual(spec.id, "/pipelines/my-pipeline/variants/my-variant")


class TestPipelineStreamSpecInResults(unittest.TestCase):
    """Test cases for InternalPipelineStreamSpec format in job results."""

    def setUp(self):
        TestsManager._instance = None
        PipelineManager._instance = None

    def tearDown(self):
        TestsManager._instance = None
        PipelineManager._instance = None

    @patch("managers.tests_manager.PipelineManager")
    def test_streams_per_pipeline_uses_internal_type_in_job(
        self, mock_pipeline_manager_cls
    ):
        mock_pipeline_manager_cls.return_value = MagicMock()
        manager = TestsManager()
        original_request = {"pipeline_performance_specs": [], "execution_config": {}}
        streams_per_pipeline = [
            InternalPipelineStreamSpec(
                id="/pipelines/pipeline-a/variants/variant-a",
                streams=4,
            ),
            InternalPipelineStreamSpec(
                id="/pipelines/pipeline-b/variants/variant-b",
                streams=2,
            ),
        ]
        job = InternalPerformanceJobStatus(
            id="test-stream-spec",
            request=original_request,
            start_time=int(time.time() * 1000),
            state=InternalTestJobState.COMPLETED,
            details=["Pipeline completed successfully"],
            total_fps=180.0,
            per_stream_fps=30.0,
            total_streams=6,
            streams_per_pipeline=streams_per_pipeline,
        )
        manager.jobs[job.id] = job

        # Verify internal job uses InternalPipelineStreamSpec
        for spec in job.streams_per_pipeline or []:
            self.assertIsInstance(spec, InternalPipelineStreamSpec)

    @patch("managers.tests_manager.PipelineManager")
    def test_get_job_status_returns_internal_type_with_stream_specs(
        self, mock_pipeline_manager_cls
    ):
        mock_pipeline_manager_cls.return_value = MagicMock()
        manager = TestsManager()
        original_request = {"pipeline_performance_specs": [], "execution_config": {}}
        streams_per_pipeline = [
            InternalPipelineStreamSpec(
                id="/pipelines/pipeline-a/variants/variant-a",
                streams=4,
            ),
            InternalPipelineStreamSpec(
                id="/pipelines/pipeline-b/variants/variant-b",
                streams=2,
            ),
        ]
        job = InternalPerformanceJobStatus(
            id="test-stream-spec-internal",
            request=original_request,
            start_time=int(time.time() * 1000),
            state=InternalTestJobState.COMPLETED,
            details=["Pipeline completed successfully"],
            total_fps=180.0,
            per_stream_fps=30.0,
            total_streams=6,
            streams_per_pipeline=streams_per_pipeline,
        )
        manager.jobs[job.id] = job

        # get_job_status returns internal type
        status = manager.get_job_status(job.id)
        self.assertIsNotNone(status)
        assert status is not None
        self.assertIsInstance(status, InternalPerformanceJobStatus)
        self.assertIsNotNone(status.streams_per_pipeline)

        for spec in status.streams_per_pipeline or []:
            self.assertIsInstance(spec, InternalPipelineStreamSpec)
            self.assertIsInstance(spec.id, str)
            self.assertIsInstance(spec.streams, int)

    def test_internal_pipeline_stream_spec_id_format_for_variant(self):
        spec = InternalPipelineStreamSpec(
            id="/pipelines/test-pipeline/variants/test-variant",
            streams=5,
        )
        self.assertTrue(spec.id.startswith("/pipelines/"))
        self.assertIn("/variants/", spec.id)
        self.assertEqual(spec.streams, 5)

    def test_internal_pipeline_stream_spec_id_format_for_inline_graph(self):
        spec = InternalPipelineStreamSpec(
            id="__graph-1234567890abcdef",
            streams=3,
        )

        self.assertTrue(spec.id.startswith("__graph-"))
        self.assertEqual(len(spec.id), len("__graph-") + 16)
        self.assertEqual(spec.streams, 3)


if __name__ == "__main__":
    unittest.main()

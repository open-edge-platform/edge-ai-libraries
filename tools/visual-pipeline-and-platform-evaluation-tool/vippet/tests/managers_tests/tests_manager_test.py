import time
import unittest
from unittest.mock import patch

from api.api_schemas import (
    DensityJobStatus,
    DensityTestSpec,
    ExecutionConfig,
    OutputMode,
    PerformanceJobStatus,
    PerformanceTestSpec,
    PipelineDensitySpec,
    PipelinePerformanceSpec,
    TestJobState,
)
from benchmark import BenchmarkResult
from managers.tests_manager import DensityJob, PerformanceJob, TestsManager
from pipeline_runner import PipelineRunner, PipelineRunResult


class TestTestsManager(unittest.TestCase):
    def test_test_performance_calls_execute_performance_test_and_returns_job_id(self):
        manager = TestsManager()
        initial_count = len(manager.jobs)

        pipeline_request = PerformanceTestSpec(
            pipeline_performance_specs=[
                PipelinePerformanceSpec(
                    id="pipeline-test123",
                    streams=1,
                )
            ],
            execution_config=ExecutionConfig(output_mode=OutputMode.DISABLED),
        )

        with patch.object(manager, "_execute_performance_test") as mock_execute:
            job_id = manager.test_performance(pipeline_request)
            self.assertIsInstance(job_id, str)
            self.assertIn(job_id, manager.jobs)
            self.assertEqual(initial_count + 1, len(manager.jobs))
            mock_execute.assert_called_once_with(job_id, pipeline_request)

    def test_test_performance_creates_job_with_running_state(self):
        manager = TestsManager()
        pipeline_request = PerformanceTestSpec(
            pipeline_performance_specs=[
                PipelinePerformanceSpec(
                    id="pipeline-test456",
                    streams=1,
                )
            ],
            execution_config=ExecutionConfig(output_mode=OutputMode.DISABLED),
        )

        with patch.object(manager, "_execute_performance_test"):
            job_id = manager.test_performance(pipeline_request)
            job = manager.jobs[job_id]
            assert isinstance(job, PerformanceJob)  # for type checker
            self.assertEqual(job.request, pipeline_request)
            self.assertEqual(
                job.request.pipeline_performance_specs[0].id, "pipeline-test456"
            )
            self.assertEqual(job.request, pipeline_request)
            self.assertEqual(job.state.name, TestJobState.RUNNING)
            self.assertIsInstance(job.start_time, int)
            self.assertIsNone(job.end_time)

    def test_test_density_creates_job_with_running_state_and_returns_job_id(
        self,
    ):
        manager = TestsManager()
        initial_count = len(manager.jobs)

        pipeline_request = DensityTestSpec(
            fps_floor=30,
            pipeline_density_specs=[
                PipelineDensitySpec(
                    id="pipeline-test789",
                    stream_rate=100,
                )
            ],
            execution_config=ExecutionConfig(output_mode=OutputMode.DISABLED),
        )

        with patch.object(manager, "_execute_density_test") as mock_execute:
            job_id = manager.test_density(pipeline_request)
            self.assertIsInstance(job_id, str)
            self.assertEqual(initial_count + 1, len(manager.jobs))

            job = manager.jobs[job_id]
            assert isinstance(job, DensityJob)  # for type checker
            self.assertEqual(
                job.request.pipeline_density_specs[0].id, "pipeline-test789"
            )
            self.assertEqual(job.request, pipeline_request)
            self.assertEqual(job.state.name, TestJobState.RUNNING)
            self.assertIsInstance(job.start_time, int)
            self.assertIsNone(job.end_time)

            mock_execute.assert_called_once_with(job_id, pipeline_request)

    def test_get_job_statuses_by_type_returns_correct_statuses(self):
        manager = TestsManager()

        # Create two jobs
        pipeline_performance_request = PerformanceTestSpec(
            pipeline_performance_specs=[
                PipelinePerformanceSpec(
                    id="pipeline-perf123",
                    streams=1,
                )
            ],
            execution_config=ExecutionConfig(output_mode=OutputMode.DISABLED),
        )

        pipeline_density_request = DensityTestSpec(
            fps_floor=30,
            pipeline_density_specs=[
                PipelineDensitySpec(
                    id="pipeline-dens456",
                    stream_rate=100,
                )
            ],
            execution_config=ExecutionConfig(output_mode=OutputMode.DISABLED),
        )

        with (
            patch.object(manager, "_execute_performance_test"),
            patch.object(manager, "_execute_density_test"),
        ):
            job_id_performance = manager.test_performance(pipeline_performance_request)
            job_id_density = manager.test_density(pipeline_density_request)

        performance_statuses = manager.get_job_statuses_by_type(PerformanceJob)
        self.assertEqual(len(performance_statuses), 1)

        density_statuses = manager.get_job_statuses_by_type(DensityJob)
        self.assertEqual(len(density_statuses), 1)

        status_performance = next(
            (s for s in performance_statuses if s.id == job_id_performance), None
        )
        status_density = next(
            (s for s in density_statuses if s.id == job_id_density), None
        )

        self.assertIsNotNone(status_performance)
        self.assertIsNotNone(status_density)
        assert status_performance is not None  # for pyright type checking
        assert status_density is not None  # for pyright type checking
        self.assertEqual(status_performance.state.name, TestJobState.RUNNING)
        self.assertEqual(status_density.state.name, TestJobState.RUNNING)

    def test_get_job_status_returns_none_for_nonexistent_job(self):
        manager = TestsManager()
        status = manager.get_job_status("nonexistent-job-id")
        self.assertIsNone(status)

    def test_get_job_status_returns_correct_status(self):
        manager = TestsManager()

        # Create a job manually and add it to the manager
        pipeline_performance_request = PerformanceTestSpec(
            pipeline_performance_specs=[
                PipelinePerformanceSpec(
                    id="pipeline-abc123",
                    streams=1,
                )
            ],
            execution_config=ExecutionConfig(output_mode=OutputMode.DISABLED),
        )
        job = PerformanceJob(
            id="test-job-id",
            request=pipeline_performance_request,
            start_time=int(time.time()),
            state=TestJobState.RUNNING,
            total_fps=120,
            per_stream_fps=30,
            total_streams=1,
            streams_per_pipeline=pipeline_performance_request.pipeline_performance_specs,
        )
        manager.jobs[job.id] = job

        status = manager.get_job_status(job.id)
        self.assertIsNotNone(status)
        assert status is not None  # for pyright type checking
        self.assertEqual(status.id, job.id)
        self.assertEqual(status.state, job.state)
        self.assertEqual(status.total_fps, job.total_fps)
        self.assertEqual(status.per_stream_fps, job.per_stream_fps)
        self.assertEqual(status.total_streams, job.total_streams)
        self.assertEqual(status.streams_per_pipeline, job.streams_per_pipeline)

    def test_get_job_summary_returns_none_for_nonexistent_job(self):
        manager = TestsManager()
        summary = manager.get_job_summary("nonexistent-job-id")
        self.assertIsNone(summary)

    def test_get_job_summary_returns_correct_summary(self):
        manager = TestsManager()

        # Create a job manually and add it to the manager
        pipeline_request = PerformanceTestSpec(
            pipeline_performance_specs=[
                PipelinePerformanceSpec(
                    id="pipeline-def456",
                    streams=1,
                )
            ],
            execution_config=ExecutionConfig(output_mode=OutputMode.DISABLED),
        )

        job = PerformanceJob(
            id="test-job-id",
            request=pipeline_request,
            start_time=int(time.time()),
            state=TestJobState.RUNNING,
        )
        manager.jobs[job.id] = job

        summary = manager.get_job_summary(job.id)
        self.assertIsNotNone(summary)
        assert summary is not None  # for pyright type checking
        self.assertEqual(summary.id, job.id)
        self.assertEqual(summary.request, job.request)

    def test_stop_job_stops_running_job(self):
        manager = TestsManager()

        # Create a job and runner manually and add them to the manager
        pipeline_request = PerformanceTestSpec(
            pipeline_performance_specs=[
                PipelinePerformanceSpec(
                    id="pipeline-ghi789",
                    streams=1,
                )
            ],
            execution_config=ExecutionConfig(output_mode=OutputMode.DISABLED),
        )

        job_id = "test-job-id"
        job = PerformanceJob(
            id=job_id,
            request=pipeline_request,
            start_time=int(time.time()),
            state=TestJobState.RUNNING,
        )
        manager.jobs[job_id] = job
        # Create PipelineRunner with correct arguments
        manager.runners[job_id] = PipelineRunner(mode="normal", max_runtime=0)

        success, message = manager.stop_job(job_id)
        self.assertTrue(success)
        self.assertIn(f"Job {job_id} stopped", message)

    def test_stop_job_returns_false_for_nonexistent_job(self):
        manager = TestsManager()
        success, message = manager.stop_job("nonexistent-job-id")
        self.assertFalse(success)
        self.assertIn("not found", message)

    def test_stop_job_returns_false_for_nonexistent_runner(self):
        manager = TestsManager()

        # Create a job without a runner
        pipeline_request = PerformanceTestSpec(
            pipeline_performance_specs=[
                PipelinePerformanceSpec(
                    id="pipeline-jkl012",
                    streams=1,
                )
            ],
            execution_config=ExecutionConfig(output_mode=OutputMode.DISABLED),
        )

        job_id = "test-job-id"
        job = PerformanceJob(
            id=job_id,
            request=pipeline_request,
            start_time=int(time.time()),
            state=TestJobState.RUNNING,
        )
        manager.jobs[job_id] = job

        success, message = manager.stop_job(job_id)
        self.assertFalse(success)
        self.assertIn(
            f"No active runner found for job {job_id}. It may have already completed or was never started.",
            message,
        )

    def test_stop_job_returns_false_for_not_running_job(self):
        manager = TestsManager()

        # Create a job that is not running
        pipeline_request = PerformanceTestSpec(
            pipeline_performance_specs=[
                PipelinePerformanceSpec(
                    id="pipeline-mno345",
                    streams=1,
                )
            ],
            execution_config=ExecutionConfig(output_mode=OutputMode.DISABLED),
        )

        job_id = "test-job-id"
        job = PerformanceJob(
            id=job_id,
            request=pipeline_request,
            start_time=int(time.time()),
            state=TestJobState.COMPLETED,
        )
        manager.jobs[job_id] = job
        # Create PipelineRunner with correct arguments
        manager.runners[job_id] = PipelineRunner(mode="normal", max_runtime=0)

        success, message = manager.stop_job(job_id)
        self.assertFalse(success)
        self.assertIn(f"Job {job_id} is not running", message)

    def test_execute_performance_test_starts_pipeline(self):
        manager = TestsManager()

        pipeline_request = PerformanceTestSpec(
            pipeline_performance_specs=[
                PipelinePerformanceSpec(
                    id="pipeline-pqr678",
                    streams=1,
                )
            ],
            execution_config=ExecutionConfig(output_mode=OutputMode.DISABLED),
        )

        job_id = "test-job-start"
        job = PerformanceJob(
            id=job_id,
            request=pipeline_request,
            start_time=int(time.time()),
            state=TestJobState.RUNNING,
        )
        manager.jobs[job_id] = job

        with (
            patch(
                "managers.tests_manager.pipeline_manager.build_pipeline_command",
                return_value=("fakesrc ! fakesink", {}, {}),
            ),
            patch.object(PipelineRunner, "run", return_value=None) as mock_run,
        ):
            manager._execute_performance_test(
                job_id,
                pipeline_request,
            )
            self.assertIn(job_id, manager.jobs)
            mock_run.assert_called_once()

    def test_execute_performance_test_updates_metrics_on_completion(self):
        manager = TestsManager()

        pipeline_request = PerformanceTestSpec(
            pipeline_performance_specs=[
                PipelinePerformanceSpec(id="pipeline-test", streams=1),
                PipelinePerformanceSpec(id="pipeline-test", streams=2),
            ],
            execution_config=ExecutionConfig(output_mode=OutputMode.DISABLED),
        )

        job_id = "test-job-metrics"
        job = PerformanceJob(
            id=job_id,
            request=pipeline_request,
            start_time=int(time.time()),
            state=TestJobState.RUNNING,
        )
        manager.jobs[job_id] = job

        with (
            patch(
                "managers.tests_manager.pipeline_manager.build_pipeline_command",
                return_value=("fakesrc ! fakesink", {}, {}),
            ),
            patch.object(
                PipelineRunner,
                "run",
                return_value=PipelineRunResult(
                    total_fps=300.0, per_stream_fps=100.0, num_streams=3
                ),
            ),
            patch.object(PipelineRunner, "is_cancelled", return_value=False),
        ):
            manager._execute_performance_test(
                job_id,
                pipeline_request,
            )

        updated = manager.jobs[job_id]
        self.assertEqual(updated.state, TestJobState.COMPLETED)
        self.assertEqual(updated.total_fps, 300.0)
        self.assertEqual(updated.per_stream_fps, 100.0)
        self.assertEqual(updated.total_streams, 3)
        self.assertIsNotNone(updated.streams_per_pipeline)
        self.assertEqual(len(updated.streams_per_pipeline or []), 2)
        self.assertNotIn(job_id, manager.runners)

    def test_execute_performance_test_aborts_on_cancelled_runner(self):
        manager = TestsManager()
        pipeline_request = PerformanceTestSpec(
            pipeline_performance_specs=[
                PipelinePerformanceSpec(id="pipeline-test", streams=1),
            ],
            execution_config=ExecutionConfig(output_mode=OutputMode.DISABLED),
        )

        job_id = "test-job-cancel"
        job = PerformanceJob(
            id=job_id,
            request=pipeline_request,
            start_time=int(time.time()),
            state=TestJobState.RUNNING,
        )
        manager.jobs[job_id] = job

        with (
            patch(
                "managers.tests_manager.pipeline_manager.build_pipeline_command",
                return_value=("fakesrc ! fakesink", {}, {}),
            ),
            patch.object(
                PipelineRunner,
                "run",
                return_value=PipelineRunResult(
                    total_fps=100.0, per_stream_fps=100.0, num_streams=1
                ),
            ),
            patch.object(PipelineRunner, "is_cancelled", return_value=True),
        ):
            manager._execute_performance_test(
                job_id,
                pipeline_request,
            )

        updated = manager.jobs[job_id]
        self.assertEqual(updated.state, TestJobState.ABORTED)
        self.assertEqual(updated.error_message, "Cancelled by user")
        self.assertNotIn(job_id, manager.runners)

    def test_execute_performance_test_sets_error_on_exception(self):
        manager = TestsManager()
        pipeline_request = PerformanceTestSpec(
            pipeline_performance_specs=[
                PipelinePerformanceSpec(id="pipeline-test", streams=1),
            ],
            execution_config=ExecutionConfig(output_mode=OutputMode.DISABLED),
        )

        job_id = "test-job-exception"
        job = PerformanceJob(
            id=job_id,
            request=pipeline_request,
            start_time=int(time.time()),
            state=TestJobState.RUNNING,
        )
        manager.jobs[job_id] = job

        with patch(
            "managers.tests_manager.pipeline_manager.build_pipeline_command",
            side_effect=ValueError("boom"),
        ):
            manager._execute_performance_test(
                job_id,
                pipeline_request,
            )

        updated = manager.jobs[job_id]
        self.assertEqual(updated.state, TestJobState.ERROR)
        self.assertIn("boom", updated.error_message or "")
        self.assertNotIn(job_id, manager.runners)

    @patch("managers.tests_manager.Benchmark.run")
    def test_execute_density_test_updates_metrics_on_completion(
        self, mock_benchmark_run
    ):
        mock_benchmark_run.return_value = BenchmarkResult(
            n_streams=3,
            streams_per_pipeline=[
                PipelinePerformanceSpec(id="pipeline-test", streams=2),
                PipelinePerformanceSpec(id="pipeline-test", streams=1),
            ],
            per_stream_fps=90.0,
            video_output_paths={},
        )

        manager = TestsManager()
        pipeline_request = DensityTestSpec(
            fps_floor=30,
            pipeline_density_specs=[
                PipelineDensitySpec(id="pipeline-test", stream_rate=50),
                PipelineDensitySpec(id="pipeline-test", stream_rate=50),
            ],
            execution_config=ExecutionConfig(output_mode=OutputMode.DISABLED),
        )

        job_id = "test-density-success"
        job = DensityJob(
            id=job_id,
            request=pipeline_request,
            start_time=int(time.time()),
            state=TestJobState.RUNNING,
        )
        manager.jobs[job_id] = job

        mock_benchmark_run.return_value = BenchmarkResult(
            n_streams=3,
            streams_per_pipeline=[
                PipelinePerformanceSpec(id="pipeline-test", streams=2),
                PipelinePerformanceSpec(id="pipeline-test", streams=1),
            ],
            per_stream_fps=90.0,
            video_output_paths={},
        )

        manager._execute_density_test(job_id, pipeline_request)

        updated = manager.jobs[job_id]
        self.assertEqual(updated.state, TestJobState.COMPLETED)
        self.assertIsNone(updated.total_fps)  # density does not set total_fps
        self.assertEqual(updated.per_stream_fps, 90.0)
        self.assertEqual(len(updated.streams_per_pipeline or []), 2)
        self.assertEqual(updated.total_streams, 3)
        self.assertNotIn(job_id, manager.runners)

    def test_execute_density_test_aborts_on_cancelled_runner(self):
        manager = TestsManager()
        density_request = DensityTestSpec(
            fps_floor=30,
            pipeline_density_specs=[
                PipelineDensitySpec(id="pipeline-test", stream_rate=100),
            ],
            execution_config=ExecutionConfig(output_mode=OutputMode.DISABLED),
        )

        job_id = "test-density-cancel"
        job = DensityJob(
            id=job_id,
            request=density_request,
            start_time=int(time.time()),
            state=TestJobState.RUNNING,
        )
        manager.jobs[job_id] = job

        # Patch the job's runner.is_cancelled to return True
        with patch("managers.tests_manager.Benchmark") as MockBenchmark:
            mock_benchmark_job = MockBenchmark.return_value
            mock_benchmark_job.run.return_value = BenchmarkResult(
                n_streams=3,
                streams_per_pipeline=[
                    PipelinePerformanceSpec(id="pipeline-test", streams=2),
                    PipelinePerformanceSpec(id="pipeline-test", streams=1),
                ],
                per_stream_fps=90.0,
                video_output_paths={},
            )
            mock_benchmark_job.runner.is_cancelled.return_value = True

            manager._execute_density_test(
                job_id,
                density_request,
            )

        updated = manager.jobs[job_id]
        self.assertEqual(updated.state, TestJobState.ABORTED)
        self.assertEqual(updated.error_message, "Cancelled by user")
        self.assertIsNone(updated.per_stream_fps)
        self.assertIsNone(updated.streams_per_pipeline)
        self.assertNotIn(job_id, manager.runners)

    def test_execute_density_test_sets_error_on_exception(self):
        manager = TestsManager()
        density_request = DensityTestSpec(
            fps_floor=30,
            pipeline_density_specs=[
                PipelineDensitySpec(id="pipeline-test", stream_rate=100),
            ],
            execution_config=ExecutionConfig(output_mode=OutputMode.DISABLED),
        )

        job_id = "test-density-exception"
        job = DensityJob(
            id=job_id,
            request=density_request,
            start_time=int(time.time()),
            state=TestJobState.RUNNING,
        )
        manager.jobs[job_id] = job

        with patch("managers.tests_manager.Benchmark") as MockBenchmark:
            mock_benchmark_job = MockBenchmark.return_value
            # Use side_effect to make the mocked run() raise an exception
            mock_benchmark_job.run.side_effect = RuntimeError("density test failed")

            manager._execute_density_test(
                job_id,
                density_request,
            )

        updated = manager.jobs[job_id]
        self.assertEqual(updated.state, TestJobState.ERROR)
        self.assertIn("density test failed", updated.error_message or "")
        self.assertNotIn(job_id, manager.runners)


class TestExecutionConfigValidation(unittest.TestCase):
    """Test cases for ExecutionConfig validation in TestsManager."""

    def test_validate_execution_config_file_with_max_runtime_raises_error(self):
        """Test that file output mode with max_runtime > 0 raises ValueError."""
        manager = TestsManager()
        execution_config = ExecutionConfig(
            output_mode=OutputMode.FILE,
            max_runtime=60,
        )

        with self.assertRaises(ValueError) as context:
            manager._validate_execution_config(execution_config, is_density_test=False)

        self.assertIn(
            "output_mode='file' cannot be combined with max_runtime > 0",
            str(context.exception),
        )

    def test_validate_execution_config_file_with_zero_runtime_succeeds(self):
        """Test that file output mode with max_runtime=0 passes validation."""
        manager = TestsManager()
        execution_config = ExecutionConfig(
            output_mode=OutputMode.FILE,
            max_runtime=0,
        )

        # Should not raise any exception
        manager._validate_execution_config(execution_config, is_density_test=False)

    def test_validate_execution_config_live_stream_for_density_raises_error(self):
        """Test that live stream output mode raises ValueError for density tests."""
        manager = TestsManager()
        execution_config = ExecutionConfig(
            output_mode=OutputMode.LIVE_STREAM,
            max_runtime=60,
        )

        with self.assertRaises(ValueError) as context:
            manager._validate_execution_config(execution_config, is_density_test=True)

        self.assertIn(
            "Density tests do not support output_mode='live_stream'",
            str(context.exception),
        )

    def test_validate_execution_config_live_stream_for_performance_succeeds(self):
        """Test that live stream output mode passes validation for performance tests."""
        manager = TestsManager()
        execution_config = ExecutionConfig(
            output_mode=OutputMode.LIVE_STREAM,
            max_runtime=60,
        )

        # Should not raise any exception
        manager._validate_execution_config(execution_config, is_density_test=False)

    def test_validate_execution_config_disabled_with_max_runtime_succeeds(self):
        """Test that disabled output mode with max_runtime > 0 passes validation."""
        manager = TestsManager()
        execution_config = ExecutionConfig(
            output_mode=OutputMode.DISABLED,
            max_runtime=60,
        )

        # Should not raise any exception for both performance and density tests
        manager._validate_execution_config(execution_config, is_density_test=False)
        manager._validate_execution_config(execution_config, is_density_test=True)


class TestLiveStreamUrlsInPerformanceJob(unittest.TestCase):
    """Test cases for live_stream_urls handling in performance tests."""

    def test_performance_job_status_includes_live_stream_urls(self):
        """Test that PerformanceJobStatus includes live_stream_urls field."""
        manager = TestsManager()

        pipeline_request = PerformanceTestSpec(
            pipeline_performance_specs=[
                PipelinePerformanceSpec(id="pipeline-test", streams=1),
            ],
            execution_config=ExecutionConfig(output_mode=OutputMode.LIVE_STREAM),
        )

        job = PerformanceJob(
            id="test-job-live-stream",
            request=pipeline_request,
            start_time=int(time.time()),
            state=TestJobState.RUNNING,
            live_stream_urls={"pipeline-test": "rtsp://mediamtx:8554/stream_test"},
        )
        manager.jobs[job.id] = job

        status = manager.get_job_status(job.id)
        self.assertIsNotNone(status)
        assert status is not None

        self.assertIsInstance(status, PerformanceJobStatus)
        # Type narrowing for PerformanceJobStatus
        assert isinstance(status, PerformanceJobStatus)
        self.assertEqual(
            status.live_stream_urls,
            {"pipeline-test": "rtsp://mediamtx:8554/stream_test"},
        )

    def test_density_job_status_does_not_include_live_stream_urls(self):
        """Test that DensityJobStatus does not include live_stream_urls field."""
        manager = TestsManager()

        density_request = DensityTestSpec(
            fps_floor=30,
            pipeline_density_specs=[
                PipelineDensitySpec(id="pipeline-test", stream_rate=100),
            ],
            execution_config=ExecutionConfig(output_mode=OutputMode.DISABLED),
        )

        job = DensityJob(
            id="test-density-job",
            request=density_request,
            start_time=int(time.time()),
            state=TestJobState.RUNNING,
        )
        manager.jobs[job.id] = job

        status = manager.get_job_status(job.id)
        self.assertIsNotNone(status)
        assert status is not None

        self.assertIsInstance(status, DensityJobStatus)
        self.assertFalse(hasattr(status, "live_stream_urls"))

    def test_execute_performance_test_updates_live_stream_urls(self):
        """Test that _execute_performance_test updates live_stream_urls on job."""
        manager = TestsManager()

        pipeline_request = PerformanceTestSpec(
            pipeline_performance_specs=[
                PipelinePerformanceSpec(id="pipeline-test", streams=1),
            ],
            execution_config=ExecutionConfig(
                output_mode=OutputMode.LIVE_STREAM, max_runtime=60
            ),
        )

        job_id = "test-job-live-urls"
        job = PerformanceJob(
            id=job_id,
            request=pipeline_request,
            start_time=int(time.time()),
            state=TestJobState.RUNNING,
        )
        manager.jobs[job_id] = job

        expected_urls = {"pipeline-test": "rtsp://mediamtx:8554/stream_pipeline-test"}

        with (
            patch(
                "managers.tests_manager.pipeline_manager.build_pipeline_command",
                return_value=("fakesrc ! fakesink", {}, expected_urls),
            ),
            patch.object(
                PipelineRunner,
                "run",
                return_value=PipelineRunResult(
                    total_fps=100.0, per_stream_fps=100.0, num_streams=1
                ),
            ),
            patch.object(PipelineRunner, "is_cancelled", return_value=False),
        ):
            manager._execute_performance_test(job_id, pipeline_request)

        updated = manager.jobs[job_id]
        assert isinstance(updated, PerformanceJob)
        self.assertEqual(updated.live_stream_urls, expected_urls)


class TestExecutionConfigWithMaxRuntime(unittest.TestCase):
    """Test cases for max_runtime behavior in tests."""

    def test_execute_performance_test_uses_max_runtime_from_config(self):
        """Test that PipelineRunner is created with correct max_runtime."""
        manager = TestsManager()

        pipeline_request = PerformanceTestSpec(
            pipeline_performance_specs=[
                PipelinePerformanceSpec(id="pipeline-test", streams=1),
            ],
            execution_config=ExecutionConfig(
                output_mode=OutputMode.DISABLED, max_runtime=120
            ),
        )

        job_id = "test-job-max-runtime"
        job = PerformanceJob(
            id=job_id,
            request=pipeline_request,
            start_time=int(time.time()),
            state=TestJobState.RUNNING,
        )
        manager.jobs[job_id] = job

        with (
            patch(
                "managers.tests_manager.pipeline_manager.build_pipeline_command",
                return_value=("fakesrc ! fakesink", {}, {}),
            ),
            patch("managers.tests_manager.PipelineRunner") as MockPipelineRunner,
        ):
            mock_runner = MockPipelineRunner.return_value
            mock_runner.run.return_value = PipelineRunResult(
                total_fps=100.0, per_stream_fps=100.0, num_streams=1
            )
            mock_runner.is_cancelled.return_value = False

            manager._execute_performance_test(job_id, pipeline_request)

            # Verify PipelineRunner was created with correct max_runtime
            MockPipelineRunner.assert_called_once_with(mode="normal", max_runtime=120)

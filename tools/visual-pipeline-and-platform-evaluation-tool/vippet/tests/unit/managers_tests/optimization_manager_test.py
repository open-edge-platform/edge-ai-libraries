import time
import unittest
from unittest.mock import patch, MagicMock

from dlsps2_optimizer import (
    Dlsps2OptimizeResult,
    Dlsps2OptimizerCancelled,
    Dlsps2OptimizerError,
)

from graph import Graph
from internal_types import (
    InternalOptimizationJobStatus,
    InternalOptimizationJobState,
    InternalOptimizationJobSummary,
    InternalOptimizationType,
    InternalPipelineRequestOptimize,
    InternalVariant,
)
from managers.execution_coordinator import (
    PIPELINE_EXECUTION_GROUP,
    ExecutionCoordinator,
    ExecutionLease,
    JobExecutionConflictError,
)
from managers.optimization_manager import (
    OptimizationManager,
    OptimizationRunner,
    PipelineOptimizationResult,
)
from utils import get_current_timestamp


# Helper to create a mock Graph for testing
def _create_mock_graph() -> MagicMock:
    """Create a mock Graph object for testing.

    Returns a MagicMock with spec=Graph that has a working
    to_pipeline_description method. Used to avoid real graph processing
    which would fail because dummy video paths don't exist.
    """
    mock = MagicMock(spec=Graph)
    mock.to_pipeline_description.return_value = "filesrc ! decodebin3 ! autovideosink"
    mock.to_dict.return_value = {
        "nodes": [
            {"id": "0", "type": "filesrc", "data": {"location": "/tmp/dummy.mp4"}},
            {"id": "1", "type": "decodebin3", "data": {}},
            {"id": "2", "type": "autovideosink", "data": {}},
        ],
        "edges": [
            {"id": "0", "source": "0", "target": "1"},
            {"id": "1", "source": "1", "target": "2"},
        ],
    }
    return mock


def _create_test_graph() -> Graph:
    """Create a real internal Graph object from standard test graph.

    Used for tests that need a real Graph (e.g. _build_job_status
    conversion tests) but don't call to_pipeline_description.
    """
    graph_dict = {
        "nodes": [
            {"id": "0", "type": "filesrc", "data": {"location": "/tmp/dummy.mp4"}},
            {"id": "1", "type": "decodebin3", "data": {}},
            {"id": "2", "type": "autovideosink", "data": {}},
        ],
        "edges": [
            {"id": "0", "source": "0", "target": "1"},
            {"id": "1", "source": "1", "target": "2"},
        ],
    }
    return Graph.from_dict(graph_dict)


def _create_internal_variant(
    name: str = "CPU", read_only: bool = False
) -> InternalVariant:
    """Create an InternalVariant with mock Graph objects for testing."""
    mock_graph = _create_mock_graph()
    timestamp = get_current_timestamp()
    return InternalVariant(
        id=f"variant-{name.lower()}",
        name=name,
        read_only=read_only,
        pipeline_graph=mock_graph,
        pipeline_graph_simple=mock_graph,
        created_at=timestamp,
        modified_at=timestamp,
    )


class TestOptimizationManager(unittest.TestCase):
    """
    Unit tests for OptimizationManager.

    The tests focus on:
      * job creation and initial state,
      * status and summary retrieval (internal types only),
      * interaction with OptimizationRunner,
      * error handling paths.

    OptimizationManager works exclusively with internal types.
    API type conversion is tested separately in route-layer tests.
    """

    def setUp(self):
        """Reset singleton state before each test."""
        OptimizationManager._instance = None
        # Workers are mocked out here, so they never release their execution
        # lease; drop the coordinator to keep tests independent.
        ExecutionCoordinator._instance = None

    def tearDown(self):
        """Reset singleton state after each test."""
        OptimizationManager._instance = None
        ExecutionCoordinator._instance = None

    # ------------------------------------------------------------------
    # Singleton tests
    # ------------------------------------------------------------------

    def test_singleton_returns_same_instance(self):
        """OptimizationManager() should return the same instance on multiple calls."""
        instance1 = OptimizationManager()
        instance2 = OptimizationManager()
        self.assertIs(instance1, instance2)

    def test_generate_job_id_returns_unique_ids(self):
        """_generate_job_id should return unique identifiers on each call."""
        id1 = OptimizationManager._generate_job_id()
        id2 = OptimizationManager._generate_job_id()

        self.assertIsInstance(id1, str)
        self.assertIsInstance(id2, str)
        self.assertNotEqual(id1, id2)
        self.assertGreater(len(id1), 0)

    def _make_internal_request(
        self,
        opt_type: InternalOptimizationType = InternalOptimizationType.OPTIMIZE,
        parameters=None,
    ) -> InternalPipelineRequestOptimize:
        """Helper to create an internal optimization request for testing."""
        return InternalPipelineRequestOptimize(type=opt_type, parameters=parameters)

    # ------------------------------------------------------------------
    # Error handling
    # ------------------------------------------------------------------

    def test_update_job_error_sets_error_state(self):
        """_update_job_error should set job state to FAILED and store details as list."""
        manager = OptimizationManager()
        graph = _create_test_graph()
        request = self._make_internal_request()

        job_id = "job-error-update"
        job = InternalOptimizationJobStatus(
            id=job_id,
            original_pipeline_graph=graph,
            original_pipeline_graph_simple=graph,
            original_pipeline_description="filesrc ! decodebin3 ! sink",
            request=request,
            state=InternalOptimizationJobState.RUNNING,
            start_time=int(time.time() * 1000),
        )
        manager.jobs[job_id] = job

        error_msg = "Test error message"
        manager._update_job_error(job_id, error_msg)

        updated = manager.jobs[job_id]
        self.assertEqual(updated.state, InternalOptimizationJobState.FAILED)
        self.assertEqual(updated.details, [error_msg])
        self.assertIsNotNone(updated.end_time)

    def test_update_job_error_unknown_job_does_nothing(self):
        """_update_job_error on unknown job should not raise exception."""
        manager = OptimizationManager()
        manager._update_job_error("unknown-job", "Some error")

    # ------------------------------------------------------------------
    # Basic job creation
    # ------------------------------------------------------------------

    def test_run_optimization_creates_job_with_running_state(self):
        """
        run_optimization should:
          * use InternalVariant's Graph objects directly,
          * create a new InternalOptimizationJobStatus with RUNNING state,
          * start a background thread targeting _execute_optimization.
        """
        manager = OptimizationManager()

        variant = _create_internal_variant()
        request = self._make_internal_request()

        with patch.object(manager, "_execute_optimization") as mock_execute:
            job_id = manager.run_optimization(variant, request)

            self.assertIsInstance(job_id, str)
            self.assertIn(job_id, manager.jobs)

            job = manager.jobs[job_id]
            self.assertIsInstance(job.request, InternalPipelineRequestOptimize)
            self.assertEqual(job.request.type, InternalOptimizationType.OPTIMIZE)
            self.assertEqual(job.state, InternalOptimizationJobState.RUNNING)
            self.assertIsInstance(job.start_time, int)
            self.assertIsNone(job.end_time)

            # Internal state should store the variant's Graph objects
            self.assertEqual(job.original_pipeline_graph, variant.pipeline_graph)
            self.assertEqual(
                job.original_pipeline_graph_simple, variant.pipeline_graph_simple
            )

            # The runner is registered with the job, so it can be cancelled
            # before the background worker starts.
            self.assertIsInstance(manager.runners[job_id], OptimizationRunner)

            # Background worker must be started with correct arguments
            mock_execute.assert_called_once()
            call_args = mock_execute.call_args[0]
            self.assertEqual(call_args[0], job_id)
            self.assertIs(call_args[1], manager.runners[job_id])
            self.assertIsInstance(call_args[2], str)  # pipeline description
            self.assertIsInstance(call_args[3], InternalPipelineRequestOptimize)
            self.assertEqual(call_args[4], variant.name)

    def test_run_optimization_uses_variant_graphs(self):
        """
        run_optimization should use the variant's Graph objects directly.
        """
        manager = OptimizationManager()

        variant = _create_internal_variant()
        request = self._make_internal_request()

        with patch.object(manager, "_execute_optimization"):
            job_id = manager.run_optimization(variant, request)

            job = manager.jobs[job_id]
            self.assertEqual(job.original_pipeline_graph, variant.pipeline_graph)
            self.assertEqual(
                job.original_pipeline_graph_simple, variant.pipeline_graph_simple
            )

    def test_run_optimization_with_readonly_variant(self):
        """run_optimization should work with read-only variants."""
        manager = OptimizationManager()

        variant = _create_internal_variant("GPU", read_only=True)
        request = self._make_internal_request(InternalOptimizationType.OPTIMIZE)

        with patch.object(manager, "_execute_optimization"):
            job_id = manager.run_optimization(variant, request)

            self.assertIn(job_id, manager.jobs)
            job = manager.jobs[job_id]
            self.assertEqual(job.state, InternalOptimizationJobState.RUNNING)

    # ------------------------------------------------------------------
    # Status and summary retrieval
    # ------------------------------------------------------------------

    def test_get_all_job_statuses_returns_internal_statuses(self):
        """get_all_job_statuses should return internal job status objects."""
        manager = OptimizationManager()

        graph = _create_test_graph()
        request = self._make_internal_request()

        job1_id = "job-1"
        job2_id = "job-2"
        now = int(time.time() * 1000)

        manager.jobs[job1_id] = InternalOptimizationJobStatus(
            id=job1_id,
            original_pipeline_graph=graph,
            original_pipeline_graph_simple=graph,
            original_pipeline_description="filesrc ! decodebin3 ! sink",
            request=request,
            state=InternalOptimizationJobState.RUNNING,
            start_time=now,
        )

        manager.jobs[job2_id] = InternalOptimizationJobStatus(
            id=job2_id,
            original_pipeline_graph=graph,
            original_pipeline_graph_simple=graph,
            original_pipeline_description="filesrc ! decodebin3 ! sink",
            request=request,
            state=InternalOptimizationJobState.COMPLETED,
            start_time=now - 1000,
            end_time=now,
            total_fps=123.4,
        )

        statuses = manager.get_all_job_statuses()
        self.assertEqual(len(statuses), 2)

        # All returned objects should be internal types
        for status in statuses:
            self.assertIsInstance(status, InternalOptimizationJobStatus)

        ids = {s.id for s in statuses}
        self.assertIn(job1_id, ids)
        self.assertIn(job2_id, ids)

        status2 = next(s for s in statuses if s.id == job2_id)
        self.assertEqual(status2.state, InternalOptimizationJobState.COMPLETED)
        self.assertEqual(status2.total_fps, 123.4)

    def test_get_job_status_unknown_returns_none(self):
        """Unknown job ids should return None."""
        manager = OptimizationManager()
        self.assertIsNone(manager.get_job_status("does-not-exist"))

    def test_get_job_status_returns_internal_status(self):
        """get_job_status should return InternalOptimizationJobStatus."""
        manager = OptimizationManager()
        graph = _create_test_graph()
        request = self._make_internal_request(
            InternalOptimizationType.OPTIMIZE,
            parameters={"search_duration": 5},
        )

        job_id = "job-status-test"
        start_time = int(time.time() * 1000)
        job = InternalOptimizationJobStatus(
            id=job_id,
            original_pipeline_graph=graph,
            original_pipeline_graph_simple=graph,
            original_pipeline_description="filesrc ! decodebin3 ! sink",
            request=request,
            state=InternalOptimizationJobState.RUNNING,
            start_time=start_time,
            total_fps=None,
        )
        manager.jobs[job_id] = job

        status = manager.get_job_status(job_id)
        self.assertIsNotNone(status)
        assert status is not None
        self.assertIsInstance(status, InternalOptimizationJobStatus)
        self.assertEqual(status.id, job_id)
        self.assertEqual(status.state, InternalOptimizationJobState.RUNNING)
        self.assertEqual(
            status.original_pipeline_description, job.original_pipeline_description
        )

    def test_get_job_summary_unknown_returns_none(self):
        """Unknown job ids should yield no summary."""
        manager = OptimizationManager()
        self.assertIsNone(manager.get_job_summary("missing"))

    def test_get_job_summary_returns_internal_summary(self):
        """get_job_summary should return InternalOptimizationJobSummary."""
        manager = OptimizationManager()
        graph = _create_test_graph()
        request = self._make_internal_request(
            InternalOptimizationType.OPTIMIZE,
            parameters={"foo": "bar"},
        )

        job_id = "job-summary-test"
        job = InternalOptimizationJobStatus(
            id=job_id,
            original_pipeline_graph=graph,
            original_pipeline_graph_simple=graph,
            original_pipeline_description="filesrc ! decodebin3 ! sink",
            request=request,
            state=InternalOptimizationJobState.RUNNING,
            start_time=int(time.time() * 1000),
        )
        manager.jobs[job_id] = job

        summary = manager.get_job_summary(job_id)
        self.assertIsNotNone(summary)
        assert summary is not None
        self.assertIsInstance(summary, InternalOptimizationJobSummary)
        self.assertEqual(summary.id, job_id)
        self.assertIsInstance(summary.request, InternalPipelineRequestOptimize)
        self.assertEqual(summary.request.type, InternalOptimizationType.OPTIMIZE)
        self.assertEqual(summary.request.parameters, {"foo": "bar"})

    # ------------------------------------------------------------------
    # Unsupported types
    # ------------------------------------------------------------------

    def test_run_optimization_preprocess_ignores_durations(self):
        """PREPROCESS runs no search, so its durations are not validated."""
        manager = OptimizationManager()
        variant = _create_internal_variant()
        request = self._make_internal_request(
            InternalOptimizationType.PREPROCESS, parameters={"search_duration": "abc"}
        )

        with patch.object(manager, "_execute_optimization") as mock_execute:
            job_id = manager.run_optimization(variant, request)

        self.assertIn(job_id, manager.jobs)
        mock_execute.assert_called_once()

    def test_run_optimization_rejects_invalid_durations(self):
        """Invalid durations are rejected before a job is created or the lease is taken."""
        manager = OptimizationManager()
        variant = _create_internal_variant()
        cases = {
            "search_duration": ["abc", None, 0, -5, "inf", "nan", [30]],
            "sample_duration": ["", 0, float("inf")],
        }
        with patch.object(manager, "_execute_optimization") as mock_execute:
            for name, values in cases.items():
                for value in values:
                    with self.subTest(name=name, value=value):
                        request = self._make_internal_request(parameters={name: value})

                        with self.assertRaisesRegex(ValueError, f"Parameter '{name}'"):
                            manager.run_optimization(variant, request)

            self.assertEqual(manager.jobs, {})
            mock_execute.assert_not_called()

    # ------------------------------------------------------------------
    # _execute_optimization behaviour
    # ------------------------------------------------------------------

    def _add_running_job(
        self, manager: OptimizationManager, job_id: str, parameters=None
    ) -> MagicMock:
        """Register a RUNNING OPTIMIZE job with a mocked runner and return the runner."""
        graph = _create_test_graph()
        manager.jobs[job_id] = InternalOptimizationJobStatus(
            id=job_id,
            original_pipeline_graph=graph,
            original_pipeline_graph_simple=graph,
            original_pipeline_description="filesrc ! decodebin3 ! sink",
            request=self._make_internal_request(parameters=parameters),
            state=InternalOptimizationJobState.RUNNING,
            start_time=int(time.time() * 1000),
        )
        runner = MagicMock(spec=OptimizationRunner)
        runner.is_cancelled.return_value = False
        runner.run_optimization.return_value = PipelineOptimizationResult(
            optimized_pipeline_description="optimized ! sink", total_fps=55.5
        )
        manager.runners[job_id] = runner
        return runner

    def _execute(
        self,
        manager: OptimizationManager,
        job_id: str,
        runner: MagicMock,
        variant_name: str = "",
        lease: ExecutionLease | None = None,
    ) -> None:
        manager._execute_optimization(
            job_id,
            runner,
            pipeline_description="filesrc ! decodebin3 ! sink",
            optimization_request=manager.jobs[job_id].request,
            variant_name=variant_name,
            execution_lease=lease,
        )

    @patch("managers.optimization_manager.Graph")
    def test_execute_optimization_completes_with_both_views_and_fps(
        self, mock_graph_cls
    ):
        """A completed run stores the pipeline, both Graph views and the FPS."""
        manager = OptimizationManager()
        runner = self._add_running_job(
            manager, "job-ok", parameters={"search_duration": 42, "sample_duration": 7}
        )
        mock_optimized_graph = MagicMock(spec=Graph)
        mock_simple_graph = MagicMock(spec=Graph)
        mock_optimized_graph.to_simple_view.return_value = mock_simple_graph
        mock_graph_cls.from_pipeline_description.return_value = mock_optimized_graph

        self._execute(manager, "job-ok", runner)

        updated = manager.jobs["job-ok"]
        self.assertEqual(updated.state, InternalOptimizationJobState.COMPLETED)
        self.assertEqual(updated.details, ["Optimization completed successfully"])
        self.assertIsNotNone(updated.end_time)
        self.assertEqual(updated.total_fps, 55.5)
        self.assertEqual(updated.optimized_pipeline_description, "optimized ! sink")
        self.assertEqual(updated.optimized_pipeline_graph, mock_optimized_graph)
        self.assertEqual(updated.optimized_pipeline_graph_simple, mock_simple_graph)
        mock_graph_cls.from_pipeline_description.assert_called_once_with(
            "optimized ! sink"
        )
        runner.run_optimization.assert_called_once_with(
            pipeline_description="filesrc ! decodebin3 ! sink",
            search_duration=42,
            sample_duration=7,
            allowed_devices=None,
        )
        self.assertNotIn("job-ok", manager.runners)

    @patch("managers.optimization_manager.Graph")
    def test_execute_optimization_uses_default_durations(self, mock_graph_cls):
        """Missing parameters fall back to the default search and sample durations."""
        manager = OptimizationManager()
        runner = self._add_running_job(manager, "job-defaults")

        self._execute(manager, "job-defaults", runner)

        kwargs = runner.run_optimization.call_args.kwargs
        self.assertEqual(kwargs["search_duration"], 300)
        self.assertEqual(kwargs["sample_duration"], 10)

    @patch("managers.optimization_manager.Graph")
    def test_execute_optimization_converts_numeric_string_durations(
        self, mock_graph_cls
    ):
        """Numeric strings are accepted, like max-runtime of validation jobs."""
        manager = OptimizationManager()
        runner = self._add_running_job(
            manager,
            "job-strings",
            parameters={"search_duration": "30", "sample_duration": "2.5"},
        )

        self._execute(manager, "job-strings", runner)

        kwargs = runner.run_optimization.call_args.kwargs
        self.assertEqual(kwargs["search_duration"], 30.0)
        self.assertEqual(kwargs["sample_duration"], 2.5)
        self.assertIsInstance(kwargs["search_duration"], float)

    @patch("managers.optimization_manager.Graph")
    def test_execute_optimization_cancel_after_server_job_ended_marks_failed(
        self, mock_graph_cls
    ):
        """A cancel that lands after the server job ended still wins over the result."""
        manager = OptimizationManager()
        runner = self._add_running_job(manager, "job-late-cancel")
        runner.is_cancelled.return_value = True

        self._execute(manager, "job-late-cancel", runner)

        updated = manager.jobs["job-late-cancel"]
        self.assertEqual(updated.state, InternalOptimizationJobState.FAILED)
        self.assertEqual(updated.details, ["Cancelled by user"])
        self.assertIsNone(updated.optimized_pipeline_description)
        self.assertIsNone(updated.total_fps)

    @patch("managers.optimization_manager.Graph")
    def test_execute_optimization_maps_variant_name_to_allowed_devices(
        self, mock_graph_cls
    ):
        """CPU/GPU/NPU variant names restrict the search; other names do not."""
        cases = {
            "CPU": ["CPU"],
            "gpu": ["GPU"],
            " Npu ": ["NPU"],
            "GPU_NPU": None,
            "my-pipeline": None,
        }
        for variant_name, expected in cases.items():
            with self.subTest(variant_name=variant_name):
                manager = OptimizationManager()
                runner = self._add_running_job(manager, f"job-{variant_name}")

                self._execute(manager, f"job-{variant_name}", runner, variant_name)

                self.assertEqual(
                    runner.run_optimization.call_args.kwargs["allowed_devices"],
                    expected,
                )

    @patch("managers.optimization_manager.Graph")
    def test_execute_optimization_preprocess_completes_without_fps(
        self, mock_graph_cls
    ):
        """PREPROCESS uses the runner's preprocessing, never the optimizer search."""
        manager = OptimizationManager()
        runner = self._add_running_job(manager, "job-preprocess")
        manager.jobs["job-preprocess"].request = self._make_internal_request(
            InternalOptimizationType.PREPROCESS
        )
        runner.run_preprocessing.return_value = PipelineOptimizationResult(
            optimized_pipeline_description="preprocessed ! sink"
        )

        self._execute(manager, "job-preprocess", runner, variant_name="CPU")

        updated = manager.jobs["job-preprocess"]
        self.assertEqual(updated.state, InternalOptimizationJobState.COMPLETED)
        self.assertEqual(updated.optimized_pipeline_description, "preprocessed ! sink")
        self.assertIsNone(updated.total_fps)
        runner.run_preprocessing.assert_called_once_with("filesrc ! decodebin3 ! sink")
        runner.run_optimization.assert_not_called()

    def test_execute_optimization_graph_conversion_exception_sets_error(self):
        """If Graph.from_pipeline_description fails, job should be marked as FAILED."""
        manager = OptimizationManager()
        runner = self._add_running_job(manager, "job-graph-error")

        with patch("managers.optimization_manager.Graph") as mock_graph_cls:
            mock_graph_cls.from_pipeline_description.side_effect = RuntimeError(
                "Graph conversion failed"
            )
            self._execute(manager, "job-graph-error", runner)

        updated = manager.jobs["job-graph-error"]
        self.assertEqual(updated.state, InternalOptimizationJobState.FAILED)
        self.assertEqual(updated.details, ["Graph conversion failed"])
        self.assertIsNone(updated.optimized_pipeline_description)

    def test_execute_optimization_dlsps_error_sets_error_and_releases(self):
        """A failed DLSPS job marks the job FAILED, drops the runner and frees the lease."""
        manager = OptimizationManager()
        runner = self._add_running_job(manager, "job-dlsps-error")
        runner.run_optimization.side_effect = Dlsps2OptimizerError(
            "Optimizer job x failed on DLSPS 2.0: no element gvadetect"
        )
        lease = ExecutionCoordinator().acquire(
            job_id="job-dlsps-error",
            job_kind="optimization",
            groups=[PIPELINE_EXECUTION_GROUP],
        )

        self._execute(manager, "job-dlsps-error", runner, lease=lease)

        updated = manager.jobs["job-dlsps-error"]
        self.assertEqual(updated.state, InternalOptimizationJobState.FAILED)
        self.assertEqual(
            updated.details,
            ["Optimizer job x failed on DLSPS 2.0: no element gvadetect"],
        )
        self.assertNotIn("job-dlsps-error", manager.runners)
        # The lease is free again, so another job can take it.
        ExecutionCoordinator().acquire(
            job_id="next", job_kind="optimization", groups=[PIPELINE_EXECUTION_GROUP]
        )

    def test_execute_optimization_cancelled_job_marks_failed(self):
        """A cancelled run is always FAILED with the 'Cancelled by user' detail."""
        manager = OptimizationManager()
        runner = self._add_running_job(manager, "job-cancelled")
        runner.run_optimization.side_effect = Dlsps2OptimizerCancelled("cancelled")

        self._execute(manager, "job-cancelled", runner)

        updated = manager.jobs["job-cancelled"]
        self.assertEqual(updated.state, InternalOptimizationJobState.FAILED)
        self.assertEqual(updated.details, ["Cancelled by user"])
        self.assertIsNone(updated.optimized_pipeline_graph)

    # ------------------------------------------------------------------
    # cancel_job
    # ------------------------------------------------------------------

    def test_cancel_job_unknown_returns_not_found(self):
        """Cancelling an unknown job fails with a 'not found' message."""
        success, message = OptimizationManager().cancel_job("missing")

        self.assertFalse(success)
        self.assertIn("not found", message)

    def test_cancel_job_running_cancels_runner(self):
        """Cancelling a RUNNING job cancels its runner."""
        manager = OptimizationManager()
        runner = self._add_running_job(manager, "job-run")

        success, message = manager.cancel_job("job-run")

        self.assertTrue(success)
        self.assertIn("cancelled", message)
        runner.cancel.assert_called_once()

    def test_cancel_job_finished_returns_not_running(self):
        """Cancelling a job that already ended fails with a 'not running' message."""
        manager = OptimizationManager()
        runner = self._add_running_job(manager, "job-done")
        manager.jobs["job-done"].state = InternalOptimizationJobState.COMPLETED
        manager.runners.pop("job-done")

        success, message = manager.cancel_job("job-done")

        self.assertFalse(success)
        self.assertIn("not running", message)
        runner.cancel.assert_not_called()

    def test_resolve_allowed_devices_mapping(self):
        """_resolve_allowed_devices maps only exact CPU/GPU/NPU names."""
        self.assertEqual(OptimizationManager._resolve_allowed_devices("CPU"), ["CPU"])
        self.assertEqual(OptimizationManager._resolve_allowed_devices("cpu"), ["CPU"])
        self.assertEqual(OptimizationManager._resolve_allowed_devices("Gpu"), ["GPU"])
        self.assertEqual(OptimizationManager._resolve_allowed_devices(" npu "), ["NPU"])
        self.assertIsNone(OptimizationManager._resolve_allowed_devices(""))
        self.assertIsNone(OptimizationManager._resolve_allowed_devices("default"))
        self.assertIsNone(OptimizationManager._resolve_allowed_devices("my-pipeline"))


class TestOptimizationRunner(unittest.TestCase):
    """OptimizationRunner delegates to the DLSPS 2.0 optimizer client."""

    @patch("managers.optimization_manager.Dlsps2Optimizer")
    def test_run_optimization_forwards_to_dlsps_and_maps_result(self, mock_cls):
        mock_cls.return_value.optimize.return_value = Dlsps2OptimizeResult(
            pipeline="best ! sink", fps=99.0
        )

        result = OptimizationRunner().run_optimization(
            "orig ! sink",
            search_duration=60,
            sample_duration=5,
            allowed_devices=["GPU"],
        )

        mock_cls.return_value.optimize.assert_called_once_with(
            "orig ! sink",
            search_duration=60,
            sample_duration=5,
            allowed_devices=["GPU"],
        )
        self.assertEqual(result.optimized_pipeline_description, "best ! sink")
        self.assertEqual(result.total_fps, 99.0)

    @patch("managers.optimization_manager.Dlsps2Optimizer")
    def test_run_preprocessing_forwards_to_dlsps(self, mock_cls):
        mock_cls.return_value.preprocess.return_value = "preprocessed ! sink"

        result = OptimizationRunner().run_preprocessing("orig ! sink")

        mock_cls.return_value.preprocess.assert_called_once_with("orig ! sink")
        self.assertEqual(result.optimized_pipeline_description, "preprocessed ! sink")
        self.assertIsNone(result.total_fps)

    @patch("managers.optimization_manager.Dlsps2Optimizer")
    def test_cancel_delegates_to_client(self, mock_cls):
        runner = OptimizationRunner()
        mock_cls.return_value.is_cancelled.return_value = True

        runner.cancel()

        mock_cls.return_value.cancel.assert_called_once()
        self.assertTrue(runner.is_cancelled())


class TestOptimizationManagerWithVariant(unittest.TestCase):
    """
    Additional tests for variant-based optimization workflow using InternalVariant.
    """

    def setUp(self):
        """Reset singleton state before each test."""
        OptimizationManager._instance = None
        # Workers are mocked out here, so they never release their execution
        # lease; drop the coordinator to keep tests independent.
        ExecutionCoordinator._instance = None

    def tearDown(self):
        """Reset singleton state after each test."""
        OptimizationManager._instance = None
        ExecutionCoordinator._instance = None

    def test_run_optimization_rejects_second_concurrent_job(self):
        """A second optimization is rejected while the first still holds the lease."""
        manager = OptimizationManager()

        cpu_variant = _create_internal_variant("CPU")
        gpu_variant = _create_internal_variant("GPU")

        request = InternalPipelineRequestOptimize(
            type=InternalOptimizationType.OPTIMIZE, parameters=None
        )

        with patch.object(manager, "_execute_optimization"):
            job_id = manager.run_optimization(cpu_variant, request)

            with self.assertRaises(JobExecutionConflictError):
                manager.run_optimization(gpu_variant, request)

        self.assertEqual(list(manager.jobs), [job_id])
        self.assertEqual(list(manager.runners), [job_id])

    def test_run_optimization_rejects_invalid_rtsp_location(self):
        """An invalid rtspsrc location is rejected without taking the execution lease."""
        manager = OptimizationManager()
        graph = Graph.from_dict(
            {
                "nodes": [
                    {
                        "id": "0",
                        "type": "rtspsrc",
                        "data": {"location": "rtsp://host/a ! filesink location=/x"},
                    },
                    {"id": "1", "type": "decodebin3", "data": {}},
                    {"id": "2", "type": "fakesink", "data": {}},
                ],
                "edges": [
                    {"id": "0", "source": "0", "target": "1"},
                    {"id": "1", "source": "1", "target": "2"},
                ],
            }
        )
        timestamp = get_current_timestamp()
        variant = InternalVariant(
            id="variant-cpu",
            name="CPU",
            read_only=False,
            pipeline_graph=graph,
            pipeline_graph_simple=graph,
            created_at=timestamp,
            modified_at=timestamp,
        )
        request = InternalPipelineRequestOptimize(
            type=InternalOptimizationType.OPTIMIZE, parameters=None
        )

        with patch.object(manager, "_execute_optimization") as mock_execute:
            with self.assertRaises(ValueError) as ctx:
                manager.run_optimization(variant, request)

            self.assertIn("Invalid RTSP location", str(ctx.exception))
            mock_execute.assert_not_called()
            self.assertEqual(manager.jobs, {})

            # The lease was not taken, so a valid job can start right away.
            manager.run_optimization(_create_internal_variant("GPU"), request)

    def test_run_optimization_calls_to_pipeline_description(self):
        """run_optimization should call to_pipeline_description on variant's graph."""
        manager = OptimizationManager()

        variant = _create_internal_variant()
        request = InternalPipelineRequestOptimize(
            type=InternalOptimizationType.OPTIMIZE, parameters=None
        )

        with patch.object(manager, "_execute_optimization") as mock_execute:
            manager.run_optimization(variant, request)

            mock_graph: MagicMock = variant.pipeline_graph  # type: ignore[assignment]
            mock_graph.to_pipeline_description.assert_called_once()
            self.assertEqual(
                mock_execute.call_args[0][2], "filesrc ! decodebin3 ! autovideosink"
            )

import time
import types
import unittest
from unittest.mock import patch, MagicMock

from graph import Graph
from internal_types import (
    InternalOptimizationJobStatus,
    InternalOptimizationJobState,
    InternalOptimizationJobSummary,
    InternalOptimizationType,
    InternalPipelineRequestOptimize,
    InternalVariant,
)
from managers.optimization_manager import (
    OptimizationManager,
    OptimizationRunner,
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

    def tearDown(self):
        """Reset singleton state after each test."""
        OptimizationManager._instance = None

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
        opt_type: InternalOptimizationType = InternalOptimizationType.PREPROCESS,
        parameters=None,
    ) -> InternalPipelineRequestOptimize:
        """Helper to create an internal optimization request for testing."""
        return InternalPipelineRequestOptimize(type=opt_type, parameters=parameters)

    # ------------------------------------------------------------------
    # Error handling
    # ------------------------------------------------------------------

    def test_update_job_error_sets_error_state(self):
        """_update_job_error should set job state to ERROR and store error message."""
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
        self.assertEqual(updated.state, InternalOptimizationJobState.ERROR)
        self.assertEqual(updated.error_message, error_msg)
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
            self.assertEqual(job.request.type, InternalOptimizationType.PREPROCESS)
            self.assertEqual(job.state, InternalOptimizationJobState.RUNNING)
            self.assertIsInstance(job.start_time, int)
            self.assertIsNone(job.end_time)

            # Internal state should store the variant's Graph objects
            self.assertEqual(job.original_pipeline_graph, variant.pipeline_graph)
            self.assertEqual(
                job.original_pipeline_graph_simple, variant.pipeline_graph_simple
            )

            # Background worker must be started with correct arguments
            mock_execute.assert_called_once()
            call_args = mock_execute.call_args[0]
            self.assertEqual(call_args[0], job_id)
            self.assertIsInstance(call_args[1], str)  # pipeline description
            self.assertIsInstance(call_args[2], InternalPipelineRequestOptimize)

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
            InternalOptimizationType.PREPROCESS,
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
        self.assertEqual(summary.request.type, InternalOptimizationType.PREPROCESS)
        self.assertEqual(summary.request.parameters, {"foo": "bar"})

    # ------------------------------------------------------------------
    # _execute_optimization behaviour
    # ------------------------------------------------------------------

    @patch("managers.optimization_manager.Graph")
    @patch("managers.optimization_manager.OptimizationRunner")
    def test_execute_optimization_preprocess_completes_successfully(
        self, mock_runner_cls, mock_graph_cls
    ):
        """
        _execute_optimization should:
          * call OptimizationRunner.run_preprocessing,
          * update job state to COMPLETED,
          * store optimized pipeline description and Graph objects.
        """
        manager = OptimizationManager()

        graph = _create_test_graph()
        request = self._make_internal_request()

        job_id = "job-preprocess"
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

        mock_runner = MagicMock()
        mock_result = MagicMock()
        mock_result.optimized_pipeline_description = (
            "filesrc ! decodebin3 ! videoconvert ! autovideosink"
        )
        mock_result.total_fps = None
        mock_runner.run_preprocessing.return_value = mock_result
        mock_runner.is_cancelled.return_value = False
        mock_runner_cls.return_value = mock_runner

        mock_optimized_graph = MagicMock(spec=Graph)
        mock_simple_graph = MagicMock(spec=Graph)
        mock_optimized_graph.to_simple_view.return_value = mock_simple_graph
        mock_graph_cls.from_pipeline_description.return_value = mock_optimized_graph

        manager._execute_optimization(
            job_id,
            pipeline_description="filesrc ! decodebin3 ! sink",
            optimization_request=request,
        )

        updated = manager.jobs[job_id]
        self.assertEqual(updated.state, InternalOptimizationJobState.COMPLETED)
        self.assertIsNotNone(updated.end_time)
        self.assertEqual(
            updated.optimized_pipeline_description,
            "filesrc ! decodebin3 ! videoconvert ! autovideosink",
        )
        self.assertEqual(updated.optimized_pipeline_graph, mock_optimized_graph)
        self.assertEqual(updated.optimized_pipeline_graph_simple, mock_simple_graph)
        self.assertNotIn(job_id, manager.runners)
        mock_runner.run_preprocessing.assert_called_once()

    @patch("managers.optimization_manager.Graph")
    @patch("managers.optimization_manager.OptimizationRunner")
    def test_execute_optimization_preprocess_generates_simple_view(
        self, mock_runner_cls, mock_graph_cls
    ):
        """_execute_optimization should generate simple view Graph from optimized pipeline."""
        manager = OptimizationManager()

        graph = _create_test_graph()
        request = self._make_internal_request()

        job_id = "job-simple-view"
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

        mock_runner = MagicMock()
        mock_result = MagicMock()
        mock_result.optimized_pipeline_description = "filesrc ! decodebin3 ! sink"
        mock_result.total_fps = None
        mock_runner.run_preprocessing.return_value = mock_result
        mock_runner.is_cancelled.return_value = False
        mock_runner_cls.return_value = mock_runner

        mock_graph_instance = MagicMock(spec=Graph)
        mock_simple_graph_instance = MagicMock(spec=Graph)
        mock_graph_instance.to_simple_view.return_value = mock_simple_graph_instance
        mock_graph_cls.from_pipeline_description.return_value = mock_graph_instance

        manager._execute_optimization(
            job_id,
            pipeline_description="filesrc ! decodebin3 ! sink",
            optimization_request=request,
        )

        updated = manager.jobs[job_id]
        self.assertEqual(updated.state, InternalOptimizationJobState.COMPLETED)
        self.assertEqual(updated.optimized_pipeline_graph, mock_graph_instance)
        self.assertEqual(
            updated.optimized_pipeline_graph_simple, mock_simple_graph_instance
        )
        mock_graph_instance.to_simple_view.assert_called_once()

    @patch("managers.optimization_manager.Graph")
    @patch("managers.optimization_manager.OptimizationRunner")
    def test_execute_optimization_optimize_generates_both_views(
        self, mock_runner_cls, mock_graph_cls
    ):
        """_execute_optimization for OPTIMIZE should generate both Graph views."""
        manager = OptimizationManager()

        graph = _create_test_graph()
        request = self._make_internal_request(
            InternalOptimizationType.OPTIMIZE,
            parameters={"search_duration": 10, "sample_duration": 2},
        )

        job_id = "job-both-views"
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

        mock_runner = MagicMock()
        mock_result = MagicMock()
        mock_result.optimized_pipeline_description = "optimized ! sink"
        mock_result.total_fps = 75.0
        mock_runner.run_optimization.return_value = mock_result
        mock_runner.is_cancelled.return_value = False
        mock_runner_cls.return_value = mock_runner

        mock_optimized_graph = MagicMock(spec=Graph)
        mock_simple_graph = MagicMock(spec=Graph)
        mock_optimized_graph.to_simple_view.return_value = mock_simple_graph
        mock_graph_cls.from_pipeline_description.return_value = mock_optimized_graph

        manager._execute_optimization(
            job_id,
            pipeline_description="filesrc ! decodebin3 ! sink",
            optimization_request=request,
        )

        updated = manager.jobs[job_id]
        self.assertEqual(updated.total_fps, 75.0)
        self.assertIsNotNone(updated.optimized_pipeline_graph)
        self.assertIsNotNone(updated.optimized_pipeline_graph_simple)

    @patch("managers.optimization_manager.OptimizationRunner")
    def test_execute_optimization_graph_conversion_exception_sets_error(
        self, mock_runner_cls
    ):
        """If Graph.from_pipeline_description fails, job should be marked as ERROR."""
        manager = OptimizationManager()

        graph = _create_test_graph()
        request = self._make_internal_request()

        job_id = "job-graph-error"
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

        mock_runner = MagicMock()
        mock_result = MagicMock()
        mock_result.optimized_pipeline_description = "filesrc ! decodebin3 ! sink"
        mock_result.total_fps = None
        mock_runner.run_preprocessing.return_value = mock_result
        mock_runner.is_cancelled.return_value = False
        mock_runner_cls.return_value = mock_runner

        with patch("managers.optimization_manager.Graph") as mock_graph_cls:
            mock_graph_cls.from_pipeline_description.side_effect = RuntimeError(
                "Graph conversion failed"
            )

            manager._execute_optimization(
                job_id,
                pipeline_description="filesrc ! decodebin3 ! sink",
                optimization_request=request,
            )

        updated = manager.jobs[job_id]
        self.assertEqual(updated.state, InternalOptimizationJobState.ERROR)
        self.assertIsNotNone(updated.error_message)
        if updated.error_message:
            self.assertIn("Graph conversion failed", updated.error_message)

    @patch("managers.optimization_manager.OptimizationRunner")
    def test_execute_optimization_validates_optimization_type(self, mock_runner_cls):
        """_execute_optimization should validate that optimization type is known."""
        manager = OptimizationManager()

        graph = _create_test_graph()

        invalid_request = types.SimpleNamespace(type="INVALID_TYPE", parameters=None)

        job_id = "job-invalid-opt-type"
        job = InternalOptimizationJobStatus(
            id=job_id,
            original_pipeline_graph=graph,
            original_pipeline_graph_simple=graph,
            original_pipeline_description="filesrc ! decodebin3 ! sink",
            request=invalid_request,  # type: ignore[arg-type]
            state=InternalOptimizationJobState.RUNNING,
            start_time=int(time.time() * 1000),
        )
        manager.jobs[job_id] = job

        manager._execute_optimization(
            job_id,
            pipeline_description="filesrc ! decodebin3 ! sink",
            optimization_request=invalid_request,  # type: ignore[arg-type]
        )

        updated = manager.jobs[job_id]
        self.assertEqual(updated.state, InternalOptimizationJobState.ERROR)
        self.assertIsNotNone(updated.error_message)

    @patch("managers.optimization_manager.Graph")
    @patch("managers.optimization_manager.OptimizationRunner")
    def test_execute_optimization_optimize_uses_parameters_and_sets_fps(
        self, mock_runner_cls, mock_graph_cls
    ):
        """
        For InternalOptimizationType.OPTIMIZE:
          * custom parameters must be forwarded to OptimizationRunner.run_optimization,
          * resulting total_fps must be stored on the job.
        """
        manager = OptimizationManager()

        graph = _create_test_graph()
        request = self._make_internal_request(
            InternalOptimizationType.OPTIMIZE,
            parameters={"search_duration": 42, "sample_duration": 7},
        )

        job_id = "job-optimize"
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

        mock_runner = MagicMock()
        mock_result = MagicMock()
        mock_result.optimized_pipeline_description = "optimized-pipeline ! sink"
        mock_result.total_fps = 55.5
        mock_runner.run_optimization.return_value = mock_result
        mock_runner.is_cancelled.return_value = False
        mock_runner_cls.return_value = mock_runner

        mock_optimized_graph = MagicMock(spec=Graph)
        mock_simple_graph = MagicMock(spec=Graph)
        mock_optimized_graph.to_simple_view.return_value = mock_simple_graph
        mock_graph_cls.from_pipeline_description.return_value = mock_optimized_graph

        manager._execute_optimization(
            job_id,
            pipeline_description="filesrc ! decodebin3 ! sink",
            optimization_request=request,
        )

        updated = manager.jobs[job_id]
        self.assertEqual(updated.state, InternalOptimizationJobState.COMPLETED)
        self.assertEqual(updated.total_fps, 55.5)
        self.assertEqual(
            updated.optimized_pipeline_description, "optimized-pipeline ! sink"
        )

        mock_runner.run_optimization.assert_called_once_with(
            pipeline_description="filesrc ! decodebin3 ! sink",
            search_duration=42,
            sample_duration=7,
        )

    @patch("managers.optimization_manager.OptimizationRunner")
    def test_execute_optimization_cancelled_job_marks_aborted(self, mock_runner_cls):
        """If the runner reports cancellation, job state should become ABORTED."""
        manager = OptimizationManager()

        graph = _create_test_graph()
        request = self._make_internal_request()

        job_id = "job-cancelled"
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

        mock_runner = MagicMock()
        mock_runner.run_preprocessing.return_value = MagicMock(
            optimized_pipeline_description="irrelevant"
        )
        mock_runner.is_cancelled.return_value = True
        mock_runner_cls.return_value = mock_runner

        with patch("managers.optimization_manager.Graph"):
            manager._execute_optimization(
                job_id,
                pipeline_description="filesrc ! decodebin3 ! sink",
                optimization_request=request,
            )

        updated = manager.jobs[job_id]
        self.assertEqual(updated.state, InternalOptimizationJobState.ABORTED)
        self.assertEqual(updated.error_message, "Cancelled by user")
        self.assertIsNotNone(updated.end_time)

    def test_execute_optimization_unknown_type_sets_error(self):
        """Unsupported optimization type should result in ERROR state."""
        manager = OptimizationManager()
        graph = _create_test_graph()

        invalid_request = types.SimpleNamespace(type="SOMETHING-ELSE", parameters=None)

        job_id = "job-invalid-type"
        job = InternalOptimizationJobStatus(
            id=job_id,
            original_pipeline_graph=graph,
            original_pipeline_graph_simple=graph,
            original_pipeline_description="filesrc ! decodebin3 ! sink",
            request=invalid_request,  # type: ignore[arg-type]
            state=InternalOptimizationJobState.RUNNING,
            start_time=int(time.time() * 1000),
        )
        manager.jobs[job_id] = job

        with patch("managers.optimization_manager.OptimizationRunner"):
            manager._execute_optimization(
                job_id,
                pipeline_description="filesrc ! decodebin3 ! sink",
                optimization_request=invalid_request,  # type: ignore[arg-type]
            )

        updated = manager.jobs[job_id]
        self.assertEqual(updated.state, InternalOptimizationJobState.ERROR)
        self.assertIsNotNone(updated.error_message)

    @patch("managers.optimization_manager.OptimizationRunner")
    def test_execute_optimization_exception_sets_error_and_cleans_runner(
        self, mock_runner_cls
    ):
        """
        Any unexpected exception from the runner should:
          * remove the runner from manager.runners,
          * mark the job as ERROR with the exception message.
        """
        manager = OptimizationManager()
        graph = _create_test_graph()
        request = self._make_internal_request()

        job_id = "job-exception"
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

        mock_runner = MagicMock()
        mock_runner.run_preprocessing.side_effect = RuntimeError("boom")
        mock_runner_cls.return_value = mock_runner

        with patch("managers.optimization_manager.Graph"):
            manager._execute_optimization(
                job_id,
                pipeline_description="filesrc ! decodebin3 ! sink",
                optimization_request=request,
            )

        updated = manager.jobs[job_id]
        self.assertEqual(updated.state, InternalOptimizationJobState.ERROR)
        self.assertIsNotNone(updated.error_message)
        if updated.error_message is not None:
            self.assertIn("boom", updated.error_message)
        self.assertNotIn(job_id, manager.runners)


class TestOptimizationRunner(unittest.TestCase):
    """
    Focused tests for OptimizationRunner.

    The external optimizer module is replaced by a dummy module injected
    into sys.modules so we never import the real optimizer during tests.
    """

    def setUp(self) -> None:
        self.fake_optimizer = types.SimpleNamespace()
        self.fake_optimizer.preprocess_pipeline = lambda pipeline: pipeline.upper()

        self.fake_optimizer.get_optimized_pipeline = (
            lambda pipeline, search_duration, sample_duration: (
                pipeline + " ! OPTIMIZED",
                99.9,
            )
        )

        self.optimizer_patcher = patch.dict(
            "sys.modules", {"optimizer": self.fake_optimizer}
        )
        self.optimizer_patcher.start()

    def tearDown(self) -> None:
        self.optimizer_patcher.stop()

    def test_run_preprocessing_uses_optimizer_and_returns_result(self):
        runner = OptimizationRunner()
        result = runner.run_preprocessing("a ! b ! c")

        self.assertEqual(result.optimized_pipeline_description, "A ! B ! C")
        self.assertIsNone(result.total_fps)

    def test_run_optimization_uses_optimizer_and_returns_result(self):
        runner = OptimizationRunner()
        result = runner.run_optimization(
            "pipeline", search_duration=10, sample_duration=2
        )

        self.assertEqual(result.optimized_pipeline_description, "pipeline ! OPTIMIZED")
        self.assertEqual(result.total_fps, 99.9)

    def test_cancel_and_is_cancelled(self):
        runner = OptimizationRunner()
        self.assertFalse(runner.is_cancelled())
        runner.cancel()
        self.assertTrue(runner.is_cancelled())


class TestOptimizationManagerWithVariant(unittest.TestCase):
    """
    Additional tests for variant-based optimization workflow using InternalVariant.
    """

    def setUp(self):
        """Reset singleton state before each test."""
        OptimizationManager._instance = None

    def tearDown(self):
        """Reset singleton state after each test."""
        OptimizationManager._instance = None

    def test_run_optimization_stores_variant_graph_objects(self):
        """InternalVariant's Graph objects should be stored directly in job."""
        manager = OptimizationManager()

        variant = _create_internal_variant("GPU")
        request = InternalPipelineRequestOptimize(
            type=InternalOptimizationType.PREPROCESS, parameters=None
        )

        with patch.object(manager, "_execute_optimization"):
            job_id = manager.run_optimization(variant, request)

            job = manager.jobs[job_id]
            self.assertEqual(job.original_pipeline_graph, variant.pipeline_graph)
            self.assertEqual(
                job.original_pipeline_graph_simple, variant.pipeline_graph_simple
            )

    def test_run_optimization_with_different_variants(self):
        """Different variants can be optimized independently."""
        manager = OptimizationManager()

        cpu_variant = _create_internal_variant("CPU")
        gpu_variant = _create_internal_variant("GPU")

        request = InternalPipelineRequestOptimize(
            type=InternalOptimizationType.OPTIMIZE, parameters=None
        )

        with patch.object(manager, "_execute_optimization"):
            job_id_1 = manager.run_optimization(cpu_variant, request)
            job_id_2 = manager.run_optimization(gpu_variant, request)

            self.assertNotEqual(job_id_1, job_id_2)
            self.assertIn(job_id_1, manager.jobs)
            self.assertIn(job_id_2, manager.jobs)

    def test_run_optimization_calls_to_pipeline_description(self):
        """run_optimization should call to_pipeline_description on variant's graph."""
        manager = OptimizationManager()

        variant = _create_internal_variant()
        request = InternalPipelineRequestOptimize(
            type=InternalOptimizationType.PREPROCESS, parameters=None
        )

        with patch.object(manager, "_execute_optimization") as mock_execute:
            manager.run_optimization(variant, request)

            # Verify to_pipeline_description was called
            mock_graph: MagicMock = variant.pipeline_graph  # type: ignore[assignment]
            mock_graph.to_pipeline_description.assert_called_once()

            # Verify _execute_optimization received the pipeline description string
            call_args = mock_execute.call_args
            pipeline_desc = call_args[0][1]
            self.assertIsInstance(pipeline_desc, str)
            self.assertGreater(len(pipeline_desc), 0)

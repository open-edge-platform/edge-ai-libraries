import time
import types
import unittest
from unittest.mock import patch, MagicMock

from api.api_schemas import (
    Pipeline,
    PipelineGraph,
    PipelineParameters,
    PipelineRequestOptimize,
    OptimizationType,
    OptimizationJobState,
    PipelineType,
    PipelineSource,
)
from managers.optimization_manager import (
    OptimizationManager,
    OptimizationRunner,
)


class TestOptimizationManager(unittest.TestCase):
    """
    Unit tests for OptimizationManager.

    The tests focus on:
      * job creation and initial state,
      * status and summary retrieval,
      * interaction with OptimizationRunner,
      * error handling paths.
    """

    # Simple graph structure used across tests
    test_graph_json = """
    {
        "nodes": [
            {
                "id": "0",
                "type": "filesrc",
                "data": {
                    "location": "/tmp/dummy-video.mp4"
                }
            },
            {
                "id": "1",
                "type": "decodebin3",
                "data": {}
            },
            {
                "id": "2",
                "type": "autovideosink",
                "data": {}
            }
        ],
        "edges": [
            {
                "id": "0",
                "source": "0",
                "target": "1"
            },
            {
                "id": "1",
                "source": "1",
                "target": "2"
            }
        ]
    }
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
        """
        _generate_job_id should return unique identifiers on each call.
        """
        id1 = OptimizationManager._generate_job_id()
        id2 = OptimizationManager._generate_job_id()

        self.assertIsInstance(id1, str)
        self.assertIsInstance(id2, str)
        self.assertNotEqual(id1, id2)
        self.assertGreater(len(id1), 0)

    def test_build_job_status_elapsed_time_running(self):
        """
        _build_job_status should calculate elapsed_time correctly for running jobs.
        """
        manager = OptimizationManager()
        graph = PipelineGraph.model_validate_json(self.test_graph_json)
        request = PipelineRequestOptimize(
            type=OptimizationType.PREPROCESS, parameters=None
        )

        from managers.optimization_manager import OptimizationJob

        job_id = "job-status-elapsed"
        start_time = int(time.time() * 1000) - 5000  # 5 seconds ago
        job = OptimizationJob(
            id=job_id,
            original_pipeline_graph=graph,
            original_pipeline_graph_simple=graph,
            original_pipeline_description="filesrc ! decodebin3 ! sink",
            request=request,
            state=OptimizationJobState.RUNNING,
            start_time=start_time,
        )

        status = manager._build_job_status(job)

        self.assertEqual(status.id, job_id)
        self.assertGreaterEqual(status.elapsed_time, 5000)
        self.assertEqual(status.state, OptimizationJobState.RUNNING)

    def test_build_job_status_elapsed_time_completed(self):
        """
        _build_job_status should use end_time for completed jobs.
        """
        manager = OptimizationManager()
        graph = PipelineGraph.model_validate_json(self.test_graph_json)
        request = PipelineRequestOptimize(
            type=OptimizationType.OPTIMIZE, parameters=None
        )

        from managers.optimization_manager import OptimizationJob

        job_id = "job-status-completed"
        start_time = int(time.time() * 1000) - 10000
        end_time = int(time.time() * 1000) - 2000
        job = OptimizationJob(
            id=job_id,
            original_pipeline_graph=graph,
            original_pipeline_graph_simple=graph,
            original_pipeline_description="filesrc ! decodebin3 ! sink",
            request=request,
            state=OptimizationJobState.COMPLETED,
            start_time=start_time,
            end_time=end_time,
            total_fps=100.5,
            optimized_pipeline_description="filesrc ! decodebin3 ! sink",
            optimized_pipeline_graph=graph,
            optimized_pipeline_graph_simple=graph,
        )

        status = manager._build_job_status(job)

        self.assertEqual(status.elapsed_time, end_time - start_time)
        self.assertEqual(status.state, OptimizationJobState.COMPLETED)
        self.assertEqual(status.total_fps, 100.5)
        self.assertEqual(
            status.optimized_pipeline_description, "filesrc ! decodebin3 ! sink"
        )

    def test_build_job_status_preserves_both_views(self):
        """
        _build_job_status should preserve original and optimized graphs in both views.
        """
        manager = OptimizationManager()
        graph = PipelineGraph.model_validate_json(self.test_graph_json)
        request = PipelineRequestOptimize(
            type=OptimizationType.PREPROCESS, parameters=None
        )

        from managers.optimization_manager import OptimizationJob

        job_id = "job-status-views"
        job = OptimizationJob(
            id=job_id,
            original_pipeline_graph=graph,
            original_pipeline_graph_simple=graph,
            original_pipeline_description="filesrc ! decodebin3 ! sink",
            request=request,
            state=OptimizationJobState.COMPLETED,
            start_time=int(time.time() * 1000),
            end_time=int(time.time() * 1000),
            optimized_pipeline_graph=graph,
            optimized_pipeline_graph_simple=graph,
            optimized_pipeline_description="optimized ! sink",
        )

        status = manager._build_job_status(job)

        self.assertIsNotNone(status.original_pipeline_graph)
        self.assertIsNotNone(status.original_pipeline_graph_simple)
        self.assertIsNotNone(status.optimized_pipeline_graph)
        self.assertIsNotNone(status.optimized_pipeline_graph_simple)
        self.assertEqual(
            status.original_pipeline_description, job.original_pipeline_description
        )

    def test_update_job_error_sets_error_state(self):
        """
        _update_job_error should set job state to ERROR and store error message.
        """
        manager = OptimizationManager()
        graph = PipelineGraph.model_validate_json(self.test_graph_json)
        request = PipelineRequestOptimize(
            type=OptimizationType.PREPROCESS, parameters=None
        )

        from managers.optimization_manager import OptimizationJob

        job_id = "job-error-update"
        job = OptimizationJob(
            id=job_id,
            original_pipeline_graph=graph,
            original_pipeline_graph_simple=graph,
            original_pipeline_description="filesrc ! decodebin3 ! sink",
            request=request,
            state=OptimizationJobState.RUNNING,
            start_time=int(time.time() * 1000),
        )
        manager.jobs[job_id] = job

        error_msg = "Test error message"
        manager._update_job_error(job_id, error_msg)

        updated = manager.jobs[job_id]
        self.assertEqual(updated.state, OptimizationJobState.ERROR)
        self.assertEqual(updated.error_message, error_msg)
        self.assertIsNotNone(updated.end_time)

    def test_update_job_error_unknown_job_does_nothing(self):
        """
        _update_job_error on unknown job should not raise exception.
        """
        manager = OptimizationManager()

        # Should not raise
        manager._update_job_error("unknown-job", "Some error")

    def _build_pipeline(self) -> Pipeline:
        """Helper that constructs a minimal Pipeline instance."""
        graph = PipelineGraph.model_validate_json(self.test_graph_json)
        return Pipeline(
            id="pipeline-test123",
            name="user-defined-pipelines",
            version=1,
            description="A test pipeline",
            source=PipelineSource.USER_CREATED,
            # Use some valid PipelineType; value is irrelevant for these tests.
            type=PipelineType.GSTREAMER,
            # we only care about pipeline_graph here
            pipeline_graph=graph,
            pipeline_graph_simple=graph,
            parameters=PipelineParameters(default=None),
        )

    # ------------------------------------------------------------------
    # Basic job creation
    # ------------------------------------------------------------------

    @patch("managers.optimization_manager.Graph")
    def test_run_optimization_creates_job_with_running_state(self, mock_graph_cls):
        """
        run_optimization should:
          * create a new OptimizationJob with RUNNING state,
          * store it in manager.jobs,
          * start a background thread targeting _execute_optimization.
        """
        manager = OptimizationManager()

        # Mock Graph.from_dict(...).to_pipeline_description()
        mock_graph = MagicMock()
        mock_graph.to_pipeline_description.return_value = "filesrc ! decodebin3 ! sink"
        mock_graph_cls.from_dict.return_value = mock_graph

        pipeline = self._build_pipeline()
        request = PipelineRequestOptimize(
            type=OptimizationType.PREPROCESS, parameters=None
        )

        # Patch _execute_optimization so we do not actually run optimizer logic.
        with patch.object(manager, "_execute_optimization") as mock_execute:
            job_id = manager.run_optimization(pipeline, request)

            self.assertIsInstance(job_id, str)
            # Job must be registered
            self.assertIn(job_id, manager.jobs)

            job = manager.jobs[job_id]
            self.assertEqual(job.request, request)
            self.assertEqual(job.state, OptimizationJobState.RUNNING)
            self.assertIsInstance(job.start_time, int)
            self.assertIsNone(job.end_time)

            # Background worker must be started with correct arguments
            mock_execute.assert_called_once_with(
                job_id, "filesrc ! decodebin3 ! sink", request
            )

    # ------------------------------------------------------------------
    # Status and summary retrieval
    # ------------------------------------------------------------------

    def test_get_all_job_statuses_returns_correct_statuses(self):
        """
        get_all_job_statuses should build statuses for all jobs currently known.
        """
        manager = OptimizationManager()

        # We insert two jobs manually to avoid involving Graph / threads.
        graph = PipelineGraph.model_validate_json(self.test_graph_json)
        request = PipelineRequestOptimize(
            type=OptimizationType.PREPROCESS, parameters=None
        )

        job1_id = "job-1"
        job2_id = "job-2"
        now = int(time.time() * 1000)

        # Instead of constructing OptimizationJob directly (it is a dataclass),
        # use a tiny helper for clarity.
        from managers.optimization_manager import OptimizationJob

        manager.jobs[job1_id] = OptimizationJob(
            id=job1_id,
            original_pipeline_graph=graph,
            original_pipeline_graph_simple=graph,
            original_pipeline_description="filesrc ! decodebin3 ! sink",
            request=request,
            state=OptimizationJobState.RUNNING,
            start_time=now,
        )

        manager.jobs[job2_id] = OptimizationJob(
            id=job2_id,
            original_pipeline_graph=graph,
            original_pipeline_graph_simple=graph,
            original_pipeline_description="filesrc ! decodebin3 ! sink",
            request=request,
            state=OptimizationJobState.COMPLETED,
            start_time=now - 1000,
            end_time=now,
            total_fps=123.4,
        )

        statuses = manager.get_all_job_statuses()
        self.assertEqual(len(statuses), 2)

        ids = {s.id for s in statuses}
        self.assertIn(job1_id, ids)
        self.assertIn(job2_id, ids)

        # Ensure elapsed_time is positive and state is preserved
        status1 = next(s for s in statuses if s.id == job1_id)
        status2 = next(s for s in statuses if s.id == job2_id)
        self.assertGreaterEqual(status1.elapsed_time, 0)
        self.assertEqual(status2.state, OptimizationJobState.COMPLETED)
        self.assertEqual(status2.total_fps, 123.4)

    def test_get_job_status_unknown_returns_none(self):
        """Unknown job ids should return None."""
        manager = OptimizationManager()
        self.assertIsNone(manager.get_job_status("does-not-exist"))

    def test_get_job_status_returns_correct_status(self):
        """
        get_job_status should mirror the underlying OptimizationJob fields.
        """
        manager = OptimizationManager()
        graph = PipelineGraph.model_validate_json(self.test_graph_json)
        request = PipelineRequestOptimize(
            type=OptimizationType.OPTIMIZE, parameters={"search_duration": 5}
        )

        from managers.optimization_manager import OptimizationJob

        job_id = "job-status-test"
        start_time = int(time.time() * 1000)
        job = OptimizationJob(
            id=job_id,
            original_pipeline_graph=graph,
            original_pipeline_graph_simple=graph,
            original_pipeline_description="filesrc ! decodebin3 ! sink",
            request=request,
            state=OptimizationJobState.RUNNING,
            start_time=start_time,
            total_fps=None,
        )
        manager.jobs[job_id] = job

        status = manager.get_job_status(job_id)
        self.assertIsNotNone(status)
        assert status is not None  # for type checkers
        self.assertEqual(status.id, job_id)
        self.assertEqual(status.type, OptimizationType.OPTIMIZE)
        self.assertEqual(status.state, OptimizationJobState.RUNNING)
        self.assertEqual(
            status.original_pipeline_description, job.original_pipeline_description
        )

    def test_get_job_summary_unknown_returns_none(self):
        """Unknown job ids should yield no summary."""
        manager = OptimizationManager()
        self.assertIsNone(manager.get_job_summary("missing"))

    def test_get_job_summary_returns_correct_summary(self):
        """
        get_job_summary should return the request used to create the job.
        """
        manager = OptimizationManager()
        graph = PipelineGraph.model_validate_json(self.test_graph_json)
        request = PipelineRequestOptimize(
            type=OptimizationType.PREPROCESS, parameters={"foo": "bar"}
        )

        from managers.optimization_manager import OptimizationJob

        job_id = "job-summary-test"
        job = OptimizationJob(
            id=job_id,
            original_pipeline_graph=graph,
            original_pipeline_graph_simple=graph,
            original_pipeline_description="filesrc ! decodebin3 ! sink",
            request=request,
            state=OptimizationJobState.RUNNING,
            start_time=int(time.time() * 1000),
        )
        manager.jobs[job_id] = job

        summary = manager.get_job_summary(job_id)
        self.assertIsNotNone(summary)
        # mypy/pyright: summary is Optional, but we assert it's not None above
        if summary is not None:
            self.assertEqual(summary.id, job_id)
            self.assertEqual(summary.request, request)

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
          * store optimized pipeline description and graph.
        """
        manager = OptimizationManager()

        # Prepare a job in RUNNING state
        graph = PipelineGraph.model_validate_json(self.test_graph_json)
        request = PipelineRequestOptimize(
            type=OptimizationType.PREPROCESS, parameters=None
        )
        from managers.optimization_manager import OptimizationJob

        job_id = "job-preprocess"
        job = OptimizationJob(
            id=job_id,
            original_pipeline_graph=graph,
            original_pipeline_graph_simple=graph,
            original_pipeline_description="filesrc ! decodebin3 ! sink",
            request=request,
            state=OptimizationJobState.RUNNING,
            start_time=int(time.time() * 1000),
        )
        manager.jobs[job_id] = job

        # Mock OptimizationRunner instance and its result
        mock_runner = MagicMock()
        mock_result = MagicMock()
        mock_result.optimized_pipeline_description = (
            "filesrc ! decodebin3 ! videoconvert ! autovideosink"
        )
        mock_result.total_fps = None
        mock_runner.run_preprocessing.return_value = mock_result
        mock_runner.is_cancelled.return_value = False
        mock_runner_cls.return_value = mock_runner

        # Mock Graph.from_pipeline_description(...).to_dict() and to_simple_view()
        mock_graph = MagicMock()
        mock_graph.to_dict.return_value = {"nodes": [], "edges": []}
        mock_simple_graph = MagicMock()
        mock_simple_graph.to_dict.return_value = {"nodes": [], "edges": []}
        mock_graph.to_simple_view.return_value = mock_simple_graph
        mock_graph_cls.from_pipeline_description.return_value = mock_graph

        # Execute synchronously (no background thread in the test)
        manager._execute_optimization(
            job_id,
            pipeline_description="filesrc ! decodebin3 ! sink",
            optimization_request=request,
        )

        # Job should be updated
        updated = manager.jobs[job_id]
        self.assertEqual(updated.state, OptimizationJobState.COMPLETED)
        self.assertIsNotNone(updated.end_time)
        self.assertEqual(
            updated.optimized_pipeline_description,
            "filesrc ! decodebin3 ! videoconvert ! autovideosink",
        )
        self.assertIsNotNone(updated.optimized_pipeline_graph)
        # Runner should be removed from manager.runners
        self.assertNotIn(job_id, manager.runners)

        # Ensure runner was actually used
        mock_runner.run_preprocessing.assert_called_once()

    @patch("managers.optimization_manager.Graph")
    @patch("managers.optimization_manager.OptimizationRunner")
    def test_execute_optimization_preprocess_generates_simple_view(
        self, mock_runner_cls, mock_graph_cls
    ):
        """
        _execute_optimization should generate simple view from optimized pipeline graph.
        """
        manager = OptimizationManager()

        graph = PipelineGraph.model_validate_json(self.test_graph_json)
        request = PipelineRequestOptimize(
            type=OptimizationType.PREPROCESS, parameters=None
        )
        from managers.optimization_manager import OptimizationJob

        job_id = "job-simple-view"
        job = OptimizationJob(
            id=job_id,
            original_pipeline_graph=graph,
            original_pipeline_graph_simple=graph,
            original_pipeline_description="filesrc ! decodebin3 ! sink",
            request=request,
            state=OptimizationJobState.RUNNING,
            start_time=int(time.time() * 1000),
        )
        manager.jobs[job_id] = job

        # Mock runner and result
        mock_runner = MagicMock()
        mock_result = MagicMock()
        mock_result.optimized_pipeline_description = "filesrc ! decodebin3 ! sink"
        mock_result.total_fps = None
        mock_runner.run_preprocessing.return_value = mock_result
        mock_runner.is_cancelled.return_value = False
        mock_runner_cls.return_value = mock_runner

        # Valid graph structure matching PipelineGraph schema
        valid_graph_dict = {
            "nodes": [
                {"id": "0", "type": "filesrc", "data": {"location": "/tmp/test.mp4"}},
                {"id": "1", "type": "decodebin3", "data": {}},
                {"id": "2", "type": "autovideosink", "data": {}},
            ],
            "edges": [
                {"id": "0", "source": "0", "target": "1"},
                {"id": "1", "source": "1", "target": "2"},
            ],
        }

        # Mock Graph instance with properly structured to_dict output
        mock_graph_instance = MagicMock()
        mock_graph_instance.to_dict.return_value = valid_graph_dict

        # Mock simple graph instance with same valid structure
        mock_simple_graph_instance = MagicMock()
        mock_simple_graph_instance.to_dict.return_value = valid_graph_dict

        # Chain: graph.to_simple_view() returns simple_graph
        mock_graph_instance.to_simple_view.return_value = mock_simple_graph_instance

        # Configure the class method to return the configured instance
        mock_graph_cls.from_pipeline_description.return_value = mock_graph_instance

        manager._execute_optimization(
            job_id,
            pipeline_description="filesrc ! decodebin3 ! sink",
            optimization_request=request,
        )

        updated = manager.jobs[job_id]
        # If state is ERROR, the error_message will tell us what went wrong
        if updated.state == OptimizationJobState.ERROR:
            self.fail(f"Job ended in ERROR state with message: {updated.error_message}")

        self.assertEqual(updated.state, OptimizationJobState.COMPLETED)
        self.assertIsNotNone(updated.optimized_pipeline_graph)
        self.assertIsNotNone(updated.optimized_pipeline_graph_simple)

        # Verify that to_simple_view was called on the advanced graph
        mock_graph_instance.to_simple_view.assert_called_once()

    @patch("managers.optimization_manager.Graph")
    @patch("managers.optimization_manager.OptimizationRunner")
    def test_execute_optimization_optimize_generates_both_views(
        self, mock_runner_cls, mock_graph_cls
    ):
        """
        _execute_optimization for OPTIMIZE type should generate both advanced and simple views.
        """
        manager = OptimizationManager()

        graph = PipelineGraph.model_validate_json(self.test_graph_json)
        request = PipelineRequestOptimize(
            type=OptimizationType.OPTIMIZE,
            parameters={"search_duration": 10, "sample_duration": 2},
        )
        from managers.optimization_manager import OptimizationJob

        job_id = "job-both-views"
        job = OptimizationJob(
            id=job_id,
            original_pipeline_graph=graph,
            original_pipeline_graph_simple=graph,
            original_pipeline_description="filesrc ! decodebin3 ! sink",
            request=request,
            state=OptimizationJobState.RUNNING,
            start_time=int(time.time() * 1000),
        )
        manager.jobs[job_id] = job

        # Mock runner
        mock_runner = MagicMock()
        mock_result = MagicMock()
        mock_result.optimized_pipeline_description = "optimized ! sink"
        mock_result.total_fps = 75.0
        mock_runner.run_optimization.return_value = mock_result
        mock_runner.is_cancelled.return_value = False
        mock_runner_cls.return_value = mock_runner

        # Mock Graph
        mock_graph = MagicMock()
        mock_graph.to_dict.return_value = {"nodes": [], "edges": []}
        mock_simple_graph = MagicMock()
        mock_simple_graph.to_dict.return_value = {"nodes": [], "edges": []}
        mock_graph.to_simple_view.return_value = mock_simple_graph
        mock_graph_cls.from_pipeline_description.return_value = mock_graph

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
        """
        If Graph.from_pipeline_description fails, job should be marked as ERROR.
        """
        manager = OptimizationManager()

        graph = PipelineGraph.model_validate_json(self.test_graph_json)
        request = PipelineRequestOptimize(
            type=OptimizationType.PREPROCESS, parameters=None
        )
        from managers.optimization_manager import OptimizationJob

        job_id = "job-graph-error"
        job = OptimizationJob(
            id=job_id,
            original_pipeline_graph=graph,
            original_pipeline_graph_simple=graph,
            original_pipeline_description="filesrc ! decodebin3 ! sink",
            request=request,
            state=OptimizationJobState.RUNNING,
            start_time=int(time.time() * 1000),
        )
        manager.jobs[job_id] = job

        # Mock runner with result
        mock_runner = MagicMock()
        mock_result = MagicMock()
        mock_result.optimized_pipeline_description = "filesrc ! decodebin3 ! sink"
        mock_result.total_fps = None
        mock_runner.run_preprocessing.return_value = mock_result
        mock_runner.is_cancelled.return_value = False
        mock_runner_cls.return_value = mock_runner

        # Mock Graph to raise exception
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
        self.assertEqual(updated.state, OptimizationJobState.ERROR)
        self.assertIsNotNone(updated.error_message)
        if updated.error_message:
            self.assertIn("Graph conversion failed", updated.error_message)

    @patch("managers.optimization_manager.OptimizationRunner")
    def test_execute_optimization_validates_optimization_type(self, mock_runner_cls):
        """
        _execute_optimization should validate that optimization type is known.
        """
        manager = OptimizationManager()

        graph = PipelineGraph.model_validate_json(self.test_graph_json)

        # Use invalid type that is not PREPROCESS or OPTIMIZE
        invalid_request = types.SimpleNamespace(type="INVALID_TYPE", parameters=None)

        from managers.optimization_manager import OptimizationJob

        job_id = "job-invalid-opt-type"
        job = OptimizationJob(
            id=job_id,
            original_pipeline_graph=graph,
            original_pipeline_graph_simple=graph,
            original_pipeline_description="filesrc ! decodebin3 ! sink",
            request=invalid_request,  # type: ignore[arg-type]
            state=OptimizationJobState.RUNNING,
            start_time=int(time.time() * 1000),
        )
        manager.jobs[job_id] = job

        manager._execute_optimization(
            job_id,
            pipeline_description="filesrc ! decodebin3 ! sink",
            optimization_request=invalid_request,  # type: ignore[arg-type]
        )

        updated = manager.jobs[job_id]
        self.assertEqual(updated.state, OptimizationJobState.ERROR)
        self.assertIsNotNone(updated.error_message)

    @patch("managers.optimization_manager.Graph")
    @patch("managers.optimization_manager.OptimizationRunner")
    def test_execute_optimization_optimize_uses_parameters_and_sets_fps(
        self, mock_runner_cls, mock_graph_cls
    ):
        """
        For OptimizationType.OPTIMIZE:
          * custom parameters must be forwarded to OptimizationRunner.run_optimization,
          * resulting total_fps must be stored on the job.
        """
        manager = OptimizationManager()

        graph = PipelineGraph.model_validate_json(self.test_graph_json)
        request = PipelineRequestOptimize(
            type=OptimizationType.OPTIMIZE,
            parameters={"search_duration": 42, "sample_duration": 7},
        )
        from managers.optimization_manager import OptimizationJob

        job_id = "job-optimize"
        job = OptimizationJob(
            id=job_id,
            original_pipeline_graph=graph,
            original_pipeline_graph_simple=graph,
            original_pipeline_description="filesrc ! decodebin3 ! sink",
            request=request,
            state=OptimizationJobState.RUNNING,
            start_time=int(time.time() * 1000),
        )
        manager.jobs[job_id] = job

        # Mock runner and its result
        mock_runner = MagicMock()
        mock_result = MagicMock()
        mock_result.optimized_pipeline_description = "optimized-pipeline ! sink"
        mock_result.total_fps = 55.5
        mock_runner.run_optimization.return_value = mock_result
        mock_runner.is_cancelled.return_value = False
        mock_runner_cls.return_value = mock_runner

        # Mock Graph.from_pipeline_description for optimized pipeline
        mock_graph = MagicMock()
        mock_graph.to_dict.return_value = {"nodes": [], "edges": []}
        mock_simple_graph = MagicMock()
        mock_simple_graph.to_dict.return_value = {"nodes": [], "edges": []}
        mock_graph.to_simple_view.return_value = mock_simple_graph
        mock_graph_cls.from_pipeline_description.return_value = mock_graph

        manager._execute_optimization(
            job_id,
            pipeline_description="filesrc ! decodebin3 ! sink",
            optimization_request=request,
        )

        updated = manager.jobs[job_id]
        self.assertEqual(updated.state, OptimizationJobState.COMPLETED)
        self.assertEqual(updated.total_fps, 55.5)
        self.assertEqual(
            updated.optimized_pipeline_description, "optimized-pipeline ! sink"
        )

        # Check parameters forwarding
        mock_runner.run_optimization.assert_called_once_with(
            pipeline_description="filesrc ! decodebin3 ! sink",
            search_duration=42,
            sample_duration=7,
        )

    @patch("managers.optimization_manager.OptimizationRunner")
    def test_execute_optimization_cancelled_job_marks_aborted(self, mock_runner_cls):
        """
        If the runner reports cancellation, job state should become ABORTED.
        """
        manager = OptimizationManager()

        graph = PipelineGraph.model_validate_json(self.test_graph_json)
        request = PipelineRequestOptimize(
            type=OptimizationType.PREPROCESS, parameters=None
        )
        from managers.optimization_manager import OptimizationJob

        job_id = "job-cancelled"
        job = OptimizationJob(
            id=job_id,
            original_pipeline_graph=graph,
            original_pipeline_graph_simple=graph,
            original_pipeline_description="filesrc ! decodebin3 ! sink",
            request=request,
            state=OptimizationJobState.RUNNING,
            start_time=int(time.time() * 1000),
        )
        manager.jobs[job_id] = job

        # Runner that returns cancelled=True
        mock_runner = MagicMock()
        mock_runner.run_preprocessing.return_value = MagicMock(
            optimized_pipeline_description="irrelevant"
        )
        mock_runner.is_cancelled.return_value = True
        mock_runner_cls.return_value = mock_runner

        # We do not care about Graph here; patch minimal stub to avoid import
        with patch("managers.optimization_manager.Graph"):
            manager._execute_optimization(
                job_id,
                pipeline_description="filesrc ! decodebin3 ! sink",
                optimization_request=request,
            )

        updated = manager.jobs[job_id]
        self.assertEqual(updated.state, OptimizationJobState.ABORTED)
        self.assertEqual(updated.error_message, "Cancelled by user")
        self.assertIsNotNone(updated.end_time)

    def test_execute_optimization_unknown_type_sets_error(self):
        """
        Unsupported OptimizationType should result in ERROR state.
        """
        manager = OptimizationManager()
        graph = PipelineGraph.model_validate_json(self.test_graph_json)

        # Create a dummy request object with an invalid type.
        invalid_request = types.SimpleNamespace(type="SOMETHING-ELSE", parameters=None)

        from managers.optimization_manager import OptimizationJob

        job_id = "job-invalid-type"
        job = OptimizationJob(
            id=job_id,
            original_pipeline_graph=graph,
            original_pipeline_graph_simple=graph,
            original_pipeline_description="filesrc ! decodebin3 ! sink",
            request=invalid_request,  # type: ignore[arg-type]
            state=OptimizationJobState.RUNNING,
            start_time=int(time.time() * 1000),
        )
        manager.jobs[job_id] = job

        # Patch OptimizationRunner so it is not instantiated
        with patch("managers.optimization_manager.OptimizationRunner"):
            manager._execute_optimization(
                job_id,
                pipeline_description="filesrc ! decodebin3 ! sink",
                optimization_request=invalid_request,  # type: ignore[arg-type]
            )

        updated = manager.jobs[job_id]
        self.assertEqual(updated.state, OptimizationJobState.ERROR)
        self.assertIsNotNone(updated.error_message)

    @patch("managers.optimization_manager.OptimizationRunner")
    def test_execute_optimization_exception_sets_error_and_cleans_runner(
        self, mock_runner_cls
    ):
        """
        Any unexpected exception coming from the runner should:
          * remove the runner from manager.runners,
          * mark the job as ERROR with the exception message.
        """
        manager = OptimizationManager()
        graph = PipelineGraph.model_validate_json(self.test_graph_json)
        request = PipelineRequestOptimize(
            type=OptimizationType.PREPROCESS, parameters=None
        )
        from managers.optimization_manager import OptimizationJob

        job_id = "job-exception"
        job = OptimizationJob(
            id=job_id,
            original_pipeline_graph=graph,
            original_pipeline_graph_simple=graph,
            original_pipeline_description="filesrc ! decodebin3 ! sink",
            request=request,
            state=OptimizationJobState.RUNNING,
            start_time=int(time.time() * 1000),
        )
        manager.jobs[job_id] = job

        # Runner raising an exception
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
        self.assertEqual(updated.state, OptimizationJobState.ERROR)
        # updated.error_message is Optional[str]; guard against None for type-checkers
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
        # Create a fake optimizer module with the required API.
        self.fake_optimizer = types.SimpleNamespace()
        self.fake_optimizer.preprocess_pipeline = lambda pipeline: pipeline.upper()

        self.fake_optimizer.get_optimized_pipeline = (
            lambda pipeline, search_duration, sample_duration: (
                pipeline + " ! OPTIMIZED",
                99.9,
            )
        )

        # Inject into sys.modules so "import optimizer" resolves to this object.
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


if __name__ == "__main__":
    unittest.main()

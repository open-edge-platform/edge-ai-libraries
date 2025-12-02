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
    get_optimization_manager,
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
            original_pipeline_description="filesrc ! decodebin3 ! sink",
            request=request,
            state=OptimizationJobState.RUNNING,
            start_time=now,
        )

        manager.jobs[job2_id] = OptimizationJob(
            id=job2_id,
            original_pipeline_graph=graph,
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

        # Mock Graph.from_pipeline_description(...).to_dict()
        mock_graph = MagicMock()
        mock_graph.to_dict.return_value = {"nodes": [], "edges": []}
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

    # ------------------------------------------------------------------
    # Singleton helper
    # ------------------------------------------------------------------

    @patch("managers.optimization_manager.OptimizationManager")
    def test_get_optimization_manager_returns_singleton(self, mock_mgr_cls):
        """
        get_optimization_manager should lazily create and cache a singleton.
        """
        # Reset any global state that might have been set by other tests
        from managers import optimization_manager as mod

        mod._optimization_manager_instance = None

        instance1 = get_optimization_manager()
        instance2 = get_optimization_manager()

        # OptimizationManager() must have been called exactly once
        mock_mgr_cls.assert_called_once()
        self.assertIs(instance1, instance2)


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

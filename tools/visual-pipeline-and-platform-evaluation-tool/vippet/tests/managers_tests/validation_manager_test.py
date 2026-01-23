import time
import unittest
from unittest.mock import patch, MagicMock

from api.api_schemas import (
    PipelineValidation,
    PipelineGraph,
    ValidationJobState,
)
from managers.validation_manager import (
    ValidationManager,
    ValidationJob,
    get_validation_manager,
)
from pipeline_runner import PipelineValidationResult


class TestValidationManager(unittest.TestCase):
    """
    Unit tests for ValidationManager.

    The tests focus on:
      * job creation and initial state,
      * status and summary retrieval,
      * interaction with PipelineRunner,
      * input validation and error paths.
    """

    test_graph_json = """
    {
        "nodes": [
            {
                "id": "0",
                "type": "filesrc",
                "data": {"location": "/tmp/dummy-video.mp4"}
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
            {"id": "0", "source": "0", "target": "1"},
            {"id": "1", "source": "1", "target": "2"}
        ]
    }
    """

    def _build_validation_request(
        self, parameters: dict | None = None
    ) -> PipelineValidation:
        """Helper that constructs a minimal PipelineValidation instance."""
        graph = PipelineGraph.model_validate_json(self.test_graph_json)
        return PipelineValidation(
            pipeline_graph=graph,
            parameters=parameters,
        )

    # ------------------------------------------------------------------
    # Basic job creation
    # ------------------------------------------------------------------

    @patch("managers.validation_manager.Graph")
    def test_run_validation_creates_job_with_running_state(self, mock_graph_cls):
        """
        run_validation should:
          * convert the graph to a pipeline description,
          * create a new ValidationJob with RUNNING state,
          * start a background worker thread that uses PipelineRunner.
        """
        manager = ValidationManager()

        mock_graph = MagicMock()
        mock_graph.to_pipeline_description.return_value = (
            "filesrc ! decodebin3 ! autovideosink"
        )
        mock_graph_cls.from_dict.return_value = mock_graph

        request = self._build_validation_request(parameters=None)

        with patch.object(manager, "_execute_validation") as mock_execute:
            job_id = manager.run_validation(request)

        self.assertIsInstance(job_id, str)
        self.assertIn(job_id, manager.jobs)

        job = manager.jobs[job_id]
        self.assertEqual(job.request, request)
        self.assertEqual(job.state, ValidationJobState.RUNNING)
        self.assertIsInstance(job.start_time, int)
        self.assertIsNone(job.end_time)
        self.assertEqual(
            job.pipeline_description, "filesrc ! decodebin3 ! autovideosink"
        )

        mock_execute.assert_called_once()
        called_job_id, called_pipe_desc, called_max_rt, called_hard_to = (
            mock_execute.call_args[0]
        )
        self.assertEqual(called_job_id, job_id)
        self.assertEqual(called_pipe_desc, "filesrc ! decodebin3 ! autovideosink")
        self.assertEqual(called_max_rt, 10)
        self.assertEqual(called_hard_to, 70)

    # ------------------------------------------------------------------
    # Parameter validation
    # ------------------------------------------------------------------

    @patch("managers.validation_manager.Graph")
    def test_run_validation_uses_default_max_runtime(self, mock_graph_cls):
        """When max-runtime not provided, should default to 10 seconds."""
        manager = ValidationManager()

        mock_graph = MagicMock()
        mock_graph.to_pipeline_description.return_value = "pipeline"
        mock_graph_cls.from_dict.return_value = mock_graph

        request = self._build_validation_request(parameters={})

        with patch.object(manager, "_execute_validation") as mock_execute:
            manager.run_validation(request)

        _, _, max_rt, hard_timeout = mock_execute.call_args[0]
        self.assertEqual(max_rt, 10)
        self.assertEqual(hard_timeout, 70)

    @patch("managers.validation_manager.Graph")
    def test_run_validation_raises_error_for_non_int_max_runtime(self, mock_graph_cls):
        """Non-integer max-runtime should raise ValueError."""
        manager = ValidationManager()

        mock_graph = MagicMock()
        mock_graph.to_pipeline_description.return_value = "pipeline"
        mock_graph_cls.from_dict.return_value = mock_graph

        request = self._build_validation_request(parameters={"max-runtime": "abc"})

        with patch.object(manager, "_execute_validation"):
            with self.assertRaises(ValueError) as ctx:
                manager.run_validation(request)

        self.assertIn("must be an integer", str(ctx.exception))

    @patch("managers.validation_manager.Graph")
    def test_run_validation_raises_error_for_too_small_max_runtime(
        self, mock_graph_cls
    ):
        """max-runtime < 1 should raise ValueError."""
        manager = ValidationManager()

        mock_graph = MagicMock()
        mock_graph.to_pipeline_description.return_value = "pipeline"
        mock_graph_cls.from_dict.return_value = mock_graph

        request = self._build_validation_request(parameters={"max-runtime": 0})

        with patch.object(manager, "_execute_validation"):
            with self.assertRaises(ValueError) as ctx:
                manager.run_validation(request)

        self.assertIn("greater than or equal to 1", str(ctx.exception))

    # ------------------------------------------------------------------
    # _execute_validation behaviour
    # ------------------------------------------------------------------

    @patch("managers.validation_manager.PipelineRunner")
    def test_execute_validation_marks_job_completed_on_success(self, mock_runner_cls):
        """On successful validation, job should be marked COMPLETED."""
        manager = ValidationManager()

        graph = PipelineGraph.model_validate_json(self.test_graph_json)
        request = PipelineValidation(pipeline_graph=graph, parameters=None)

        job_id = "job-success"
        job = ValidationJob(
            id=job_id,
            request=request,
            pipeline_description="filesrc ! decodebin3 ! autovideosink",
            state=ValidationJobState.RUNNING,
            start_time=int(time.time() * 1000),
        )
        manager.jobs[job_id] = job

        # Mock PipelineRunner returning valid result
        mock_runner = MagicMock()
        mock_runner.run.return_value = PipelineValidationResult(
            is_valid=True, errors=[]
        )
        mock_runner_cls.return_value = mock_runner

        manager._execute_validation(
            job_id,
            pipeline_description=job.pipeline_description,
            max_runtime=10,
            hard_timeout=70,
        )

        updated = manager.jobs[job_id]
        self.assertEqual(updated.state, ValidationJobState.COMPLETED)
        self.assertTrue(updated.is_valid)
        self.assertIsNone(updated.error_message)
        self.assertIsNotNone(updated.end_time)

    @patch("managers.validation_manager.PipelineRunner")
    def test_execute_validation_marks_job_error_on_invalid_pipeline(
        self, mock_runner_cls
    ):
        """When pipeline is invalid, job should be marked ERROR."""
        manager = ValidationManager()

        graph = PipelineGraph.model_validate_json(self.test_graph_json)
        request = PipelineValidation(pipeline_graph=graph, parameters=None)

        job_id = "job-invalid"
        job = ValidationJob(
            id=job_id,
            request=request,
            pipeline_description="invalid-pipeline",
            state=ValidationJobState.RUNNING,
            start_time=int(time.time() * 1000),
        )
        manager.jobs[job_id] = job

        mock_runner = MagicMock()
        mock_runner.run.return_value = PipelineValidationResult(
            is_valid=False, errors=["no element foo", "some other error"]
        )
        mock_runner_cls.return_value = mock_runner

        manager._execute_validation(
            job_id,
            pipeline_description=job.pipeline_description,
            max_runtime=10,
            hard_timeout=70,
        )

        updated = manager.jobs[job_id]
        self.assertEqual(updated.state, ValidationJobState.ERROR)
        self.assertFalse(updated.is_valid)
        self.assertEqual(updated.error_message, ["no element foo", "some other error"])

    @patch("managers.validation_manager.PipelineRunner")
    def test_execute_validation_sets_error_on_exception(self, mock_runner_cls):
        """Unexpected exception should mark job as ERROR."""
        manager = ValidationManager()

        graph = PipelineGraph.model_validate_json(self.test_graph_json)
        request = PipelineValidation(pipeline_graph=graph, parameters=None)

        job_id = "job-exception"
        job = ValidationJob(
            id=job_id,
            request=request,
            pipeline_description="pipeline",
            state=ValidationJobState.RUNNING,
            start_time=int(time.time() * 1000),
        )
        manager.jobs[job_id] = job

        mock_runner = MagicMock()
        mock_runner.run.side_effect = RuntimeError("runner exploded")
        mock_runner_cls.return_value = mock_runner

        manager._execute_validation(
            job_id,
            pipeline_description=job.pipeline_description,
            max_runtime=10,
            hard_timeout=70,
        )

        updated = manager.jobs[job_id]
        self.assertEqual(updated.state, ValidationJobState.ERROR)
        self.assertIsNotNone(updated.error_message)
        self.assertIn("runner exploded", " ".join(updated.error_message or []))

    # ------------------------------------------------------------------
    # Status and summary retrieval
    # ------------------------------------------------------------------

    def test_get_all_job_statuses_returns_correct_statuses(self):
        """get_all_job_statuses should build statuses for all jobs."""
        manager = ValidationManager()

        graph = PipelineGraph.model_validate_json(self.test_graph_json)
        request = PipelineValidation(pipeline_graph=graph, parameters=None)

        now = int(time.time() * 1000)

        job1 = ValidationJob(
            id="job-1",
            request=request,
            pipeline_description="pipeline-1",
            state=ValidationJobState.RUNNING,
            start_time=now,
        )
        job2 = ValidationJob(
            id="job-2",
            request=request,
            pipeline_description="pipeline-2",
            state=ValidationJobState.COMPLETED,
            start_time=now - 1000,
            end_time=now,
            is_valid=True,
        )

        manager.jobs[job1.id] = job1
        manager.jobs[job2.id] = job2

        statuses = manager.get_all_job_statuses()
        self.assertEqual(len(statuses), 2)

        ids = {s.id for s in statuses}
        self.assertIn("job-1", ids)
        self.assertIn("job-2", ids)

        status2 = next(s for s in statuses if s.id == "job-2")
        self.assertEqual(status2.state, ValidationJobState.COMPLETED)
        self.assertTrue(status2.is_valid)

    def test_get_job_status_unknown_returns_none(self):
        """Unknown job ids should return None."""
        manager = ValidationManager()
        self.assertIsNone(manager.get_job_status("does-not-exist"))

    def test_get_job_status_returns_correct_status(self):
        """
        get_job_status should mirror the underlying ValidationJob fields.
        """
        manager = ValidationManager()

        graph = PipelineGraph.model_validate_json(self.test_graph_json)
        request = PipelineValidation(pipeline_graph=graph, parameters=None)

        job_id = "job-status"
        start = int(time.time() * 1000)
        job = ValidationJob(
            id=job_id,
            request=request,
            pipeline_description="pipeline-desc",
            state=ValidationJobState.RUNNING,
            start_time=start,
        )
        manager.jobs[job_id] = job

        status = manager.get_job_status(job_id)
        self.assertIsNotNone(status)
        assert status is not None  # for type checkers
        self.assertEqual(status.id, job_id)
        self.assertEqual(status.state, ValidationJobState.RUNNING)
        self.assertIsNone(status.is_valid)

    def test_get_job_summary_unknown_returns_none(self):
        """Unknown job ids should yield no summary."""
        manager = ValidationManager()
        self.assertIsNone(manager.get_job_summary("missing"))

    def test_get_job_summary_returns_correct_summary(self):
        """
        get_job_summary should return the request used to create the job.
        """
        manager = ValidationManager()

        graph = PipelineGraph.model_validate_json(self.test_graph_json)
        request = PipelineValidation(
            pipeline_graph=graph, parameters={"max-runtime": 5}
        )

        job_id = "job-summary"
        job = ValidationJob(
            id=job_id,
            request=request,
            pipeline_description="pipeline-desc",
            state=ValidationJobState.RUNNING,
            start_time=int(time.time() * 1000),
        )
        manager.jobs[job_id] = job

        summary = manager.get_job_summary(job_id)
        self.assertIsNotNone(summary)
        assert summary is not None  # for type checkers
        self.assertEqual(summary.id, job_id)
        self.assertEqual(summary.request, request)


class TestGetValidationManagerSingleton(unittest.TestCase):
    """Tests for get_validation_manager singleton accessor."""

    @patch("managers.validation_manager.ValidationManager")
    def test_get_validation_manager_returns_singleton(self, mock_mgr_cls):
        """get_validation_manager should lazily create and cache singleton."""
        from managers import validation_manager as mod

        mod._validation_manager_instance = None

        instance1 = get_validation_manager()
        instance2 = get_validation_manager()

        mock_mgr_cls.assert_called_once()
        self.assertIs(instance1, instance2)


if __name__ == "__main__":
    unittest.main()

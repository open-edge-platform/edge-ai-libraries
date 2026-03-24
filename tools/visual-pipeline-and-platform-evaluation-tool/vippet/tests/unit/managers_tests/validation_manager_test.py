import time
import unittest
from unittest.mock import patch, MagicMock

from graph import Graph
from internal_types import (
    InternalPipelineValidation,
    InternalValidationJob,
    InternalValidationJobState,
    InternalValidationJobStatus,
    InternalValidationJobSummary,
)
from managers.validation_manager import ValidationManager
from pipeline_runner import PipelineResult


# Helper to create an internal Graph from the standard test graph
def _create_test_graph() -> Graph:
    """Create an internal Graph object from the standard test graph."""
    graph_dict = {
        "nodes": [
            {
                "id": "0",
                "type": "filesrc",
                "data": {"location": "/tmp/dummy-video.mp4"},
            },
            {"id": "1", "type": "decodebin3", "data": {}},
            {"id": "2", "type": "autovideosink", "data": {}},
        ],
        "edges": [
            {"id": "0", "source": "0", "target": "1"},
            {"id": "1", "source": "1", "target": "2"},
        ],
    }
    return Graph.from_dict(graph_dict)


class TestValidationManager(unittest.TestCase):
    """
    Unit tests for ValidationManager.

    The tests focus on:
      * job creation and initial state,
      * status and summary retrieval,
      * interaction with PipelineRunner,
      * input validation and error paths.

    Validation jobs cannot be cancelled by the user.

    All tests use internal types only. The manager does not depend on
    API schema types.
    """

    def setUp(self):
        """Reset singleton state before each test."""
        ValidationManager._instance = None

    def tearDown(self):
        """Reset singleton state after each test."""
        ValidationManager._instance = None

    def _build_internal_validation(
        self, parameters: dict | None = None
    ) -> InternalPipelineValidation:
        """Helper that constructs an InternalPipelineValidation with Graph object."""
        graph = _create_test_graph()
        return InternalPipelineValidation(
            pipeline_graph=graph,
            parameters=parameters,
        )

    # ------------------------------------------------------------------
    # Singleton tests
    # ------------------------------------------------------------------

    def test_singleton_returns_same_instance(self):
        """ValidationManager() should return the same instance on multiple calls."""
        instance1 = ValidationManager()
        instance2 = ValidationManager()
        self.assertIs(instance1, instance2)

    # ------------------------------------------------------------------
    # Basic job creation
    # ------------------------------------------------------------------

    def test_run_validation_creates_job_with_running_state(self):
        """
        run_validation should:
          * convert the internal Graph to a pipeline description,
          * create a new InternalValidationJob with RUNNING state,
          * store Graph object in internal state,
          * start a background worker thread that uses PipelineRunner.
        """
        manager = ValidationManager()

        mock_graph = MagicMock()
        mock_graph.to_pipeline_description.return_value = (
            "filesrc ! decodebin3 ! autovideosink"
        )

        internal_request = InternalPipelineValidation(
            pipeline_graph=mock_graph,
            parameters=None,
        )

        with patch.object(manager, "_execute_validation") as mock_execute:
            job_id = manager.run_validation(internal_request)

        self.assertIsInstance(job_id, str)
        self.assertIn(job_id, manager.jobs)

        job = manager.jobs[job_id]
        # Job stores internal request type with Graph object
        self.assertIsInstance(job.request, InternalPipelineValidation)
        self.assertEqual(job.state, InternalValidationJobState.RUNNING)
        self.assertIsInstance(job.start_time, int)
        self.assertIsNone(job.end_time)
        self.assertEqual(job.details, [])
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

    def test_run_validation_uses_default_max_runtime(self):
        """When max-runtime not provided, should default to 10 seconds."""
        manager = ValidationManager()

        mock_graph = MagicMock()
        mock_graph.to_pipeline_description.return_value = "pipeline"

        internal_request = InternalPipelineValidation(
            pipeline_graph=mock_graph,
            parameters={},
        )

        with patch.object(manager, "_execute_validation") as mock_execute:
            manager.run_validation(internal_request)

        _, _, max_rt, hard_timeout = mock_execute.call_args[0]
        self.assertEqual(max_rt, 10)
        self.assertEqual(hard_timeout, 70)

    def test_run_validation_raises_error_for_non_int_max_runtime(self):
        """Non-integer max-runtime should raise ValueError."""
        manager = ValidationManager()

        mock_graph = MagicMock()
        mock_graph.to_pipeline_description.return_value = "pipeline"

        internal_request = InternalPipelineValidation(
            pipeline_graph=mock_graph,
            parameters={"max-runtime": "abc"},
        )

        with patch.object(manager, "_execute_validation"):
            with self.assertRaises(ValueError) as ctx:
                manager.run_validation(internal_request)

        self.assertIn("must be an integer", str(ctx.exception))

    def test_run_validation_raises_error_for_too_small_max_runtime(self):
        """max-runtime < 1 should raise ValueError."""
        manager = ValidationManager()

        mock_graph = MagicMock()
        mock_graph.to_pipeline_description.return_value = "pipeline"

        internal_request = InternalPipelineValidation(
            pipeline_graph=mock_graph,
            parameters={"max-runtime": 0},
        )

        with patch.object(manager, "_execute_validation"):
            with self.assertRaises(ValueError) as ctx:
                manager.run_validation(internal_request)

        self.assertIn("greater than or equal to 1", str(ctx.exception))

    # ------------------------------------------------------------------
    # _execute_validation behaviour
    # ------------------------------------------------------------------

    @patch("managers.validation_manager.PipelineRunner")
    def test_execute_validation_marks_job_completed_on_success(self, mock_runner_cls):
        """On successful validation (exit_code=0, no stderr), job should be COMPLETED."""
        manager = ValidationManager()

        internal_request = self._build_internal_validation()

        job_id = "job-success"
        job = InternalValidationJob(
            id=job_id,
            request=internal_request,
            pipeline_description="filesrc ! decodebin3 ! autovideosink",
            state=InternalValidationJobState.RUNNING,
            start_time=int(time.time() * 1000),
        )
        manager.jobs[job_id] = job

        # Mock PipelineRunner returning valid result (exit_code=0, empty stderr)
        mock_runner = MagicMock()
        mock_runner.run.return_value = PipelineResult(
            exit_code=0, stderr=[], stdout=["Pipeline parsed successfully."]
        )
        mock_runner_cls.return_value = mock_runner

        manager._execute_validation(
            job_id,
            pipeline_description=job.pipeline_description,
            max_runtime=10,
            hard_timeout=70,
        )

        updated = manager.jobs[job_id]
        self.assertEqual(updated.state, InternalValidationJobState.COMPLETED)
        self.assertEqual(updated.details, ["Pipeline is valid"])
        self.assertTrue(updated.is_valid)
        self.assertIsNotNone(updated.end_time)

    @patch("managers.validation_manager.PipelineRunner")
    def test_execute_validation_marks_job_failed_on_invalid_pipeline(
        self, mock_runner_cls
    ):
        """When pipeline is invalid (non-zero exit or stderr errors), job should be FAILED."""
        manager = ValidationManager()

        internal_request = self._build_internal_validation()

        job_id = "job-invalid"
        job = InternalValidationJob(
            id=job_id,
            request=internal_request,
            pipeline_description="invalid-pipeline",
            state=InternalValidationJobState.RUNNING,
            start_time=int(time.time() * 1000),
        )
        manager.jobs[job_id] = job

        mock_runner = MagicMock()
        mock_runner.run.return_value = PipelineResult(
            exit_code=1,
            stderr=[
                "gst_runner - ERROR - no element foo",
                "gst_runner - ERROR - some other error",
            ],
            stdout=[],
        )
        mock_runner._parse_validation_stderr.return_value = [
            "no element foo",
            "some other error",
        ]
        mock_runner_cls.return_value = mock_runner

        manager._execute_validation(
            job_id,
            pipeline_description=job.pipeline_description,
            max_runtime=10,
            hard_timeout=70,
        )

        updated = manager.jobs[job_id]
        self.assertEqual(updated.state, InternalValidationJobState.FAILED)
        self.assertIsInstance(updated.details, list)
        self.assertTrue(len(updated.details) > 0)
        # Details should contain error information
        self.assertTrue(any("no element foo" in d for d in updated.details))
        self.assertFalse(updated.is_valid)

    @patch("managers.validation_manager.PipelineRunner")
    def test_execute_validation_sets_failed_on_exception(self, mock_runner_cls):
        """Unexpected exception should mark job as FAILED with error in details list."""
        manager = ValidationManager()

        internal_request = self._build_internal_validation()

        job_id = "job-exception"
        job = InternalValidationJob(
            id=job_id,
            request=internal_request,
            pipeline_description="pipeline",
            state=InternalValidationJobState.RUNNING,
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
        self.assertEqual(updated.state, InternalValidationJobState.FAILED)
        self.assertIsInstance(updated.details, list)
        self.assertTrue(len(updated.details) > 0)
        self.assertIn("runner exploded", updated.details[0])

    # ------------------------------------------------------------------
    # Status and summary retrieval
    # ------------------------------------------------------------------

    def test_get_all_job_statuses_returns_correct_statuses(self):
        """get_all_job_statuses should return internal status objects for all jobs."""
        manager = ValidationManager()

        internal_request = self._build_internal_validation()

        now = int(time.time() * 1000)

        job1 = InternalValidationJob(
            id="job-1",
            request=internal_request,
            pipeline_description="pipeline-1",
            state=InternalValidationJobState.RUNNING,
            start_time=now,
        )
        job2 = InternalValidationJob(
            id="job-2",
            request=internal_request,
            pipeline_description="pipeline-2",
            state=InternalValidationJobState.COMPLETED,
            start_time=now - 1000,
            end_time=now,
            details=["Pipeline is valid"],
            is_valid=True,
        )

        manager.jobs[job1.id] = job1
        manager.jobs[job2.id] = job2

        statuses = manager.get_all_job_statuses()
        self.assertEqual(len(statuses), 2)

        # All returned statuses are internal types
        for s in statuses:
            self.assertIsInstance(s, InternalValidationJobStatus)

        ids = {s.id for s in statuses}
        self.assertIn("job-1", ids)
        self.assertIn("job-2", ids)

        status1 = next(s for s in statuses if s.id == "job-1")
        self.assertEqual(status1.details, [])

        status2 = next(s for s in statuses if s.id == "job-2")
        self.assertEqual(status2.state, InternalValidationJobState.COMPLETED)
        self.assertEqual(status2.details, ["Pipeline is valid"])
        self.assertTrue(status2.is_valid)

    def test_get_job_status_unknown_returns_none(self):
        """Unknown job ids should return None."""
        manager = ValidationManager()
        self.assertIsNone(manager.get_job_status("does-not-exist"))

    def test_get_job_status_returns_correct_status(self):
        """
        get_job_status should return an InternalValidationJobStatus
        mirroring the underlying InternalValidationJob fields.
        """
        manager = ValidationManager()

        internal_request = self._build_internal_validation()

        job_id = "job-status"
        start = int(time.time() * 1000)
        job = InternalValidationJob(
            id=job_id,
            request=internal_request,
            pipeline_description="pipeline-desc",
            state=InternalValidationJobState.RUNNING,
            start_time=start,
        )
        manager.jobs[job_id] = job

        status = manager.get_job_status(job_id)
        self.assertIsNotNone(status)
        assert status is not None  # for type checkers
        self.assertIsInstance(status, InternalValidationJobStatus)
        self.assertEqual(status.id, job_id)
        self.assertEqual(status.state, InternalValidationJobState.RUNNING)
        self.assertIsNone(status.is_valid)
        self.assertEqual(status.details, [])

    def test_get_job_summary_unknown_returns_none(self):
        """Unknown job ids should yield no summary."""
        manager = ValidationManager()
        self.assertIsNone(manager.get_job_summary("missing"))

    def test_get_job_summary_returns_correct_summary(self):
        """
        get_job_summary should return an InternalValidationJobSummary
        with the original internal request (Graph object, not API type).
        """
        manager = ValidationManager()

        internal_request = self._build_internal_validation(
            parameters={"max-runtime": 5}
        )

        job_id = "job-summary"
        job = InternalValidationJob(
            id=job_id,
            request=internal_request,
            pipeline_description="pipeline-desc",
            state=InternalValidationJobState.RUNNING,
            start_time=int(time.time() * 1000),
        )
        manager.jobs[job_id] = job

        summary = manager.get_job_summary(job_id)
        self.assertIsNotNone(summary)
        assert summary is not None  # for type checkers
        self.assertIsInstance(summary, InternalValidationJobSummary)
        self.assertEqual(summary.id, job_id)
        # Summary returns internal type with Graph object
        self.assertIsInstance(summary.request, InternalPipelineValidation)
        self.assertIsInstance(summary.request.pipeline_graph, Graph)
        self.assertEqual(summary.request.parameters, {"max-runtime": 5})


if __name__ == "__main__":
    unittest.main()

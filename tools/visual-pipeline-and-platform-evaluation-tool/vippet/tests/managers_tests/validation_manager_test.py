import time
import unittest
from typing import List
from unittest.mock import patch, MagicMock

from api.api_schemas import (
    PipelineValidation,
    PipelineGraph,
    ValidationJobState,
)
from managers.validation_manager import (
    ValidationManager,
    ValidatorRunner,
    ValidationJob,
    get_validation_manager,
)


class TestValidationManager(unittest.TestCase):
    """
    Unit tests for ValidationManager.

    The tests focus on:
      * job creation and initial state,
      * status and summary retrieval,
      * interaction with ValidatorRunner,
      * input validation and error paths.
    """

    # Simple graph structure reused across tests (mirrors other manager tests)
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
    def test_run_validation_creates_job_with_running_state_and_pipeline_description(
        self, mock_graph_cls
    ):
        """
        run_validation should:
          * convert the graph to a pipeline description,
          * create a new ValidationJob with RUNNING state,
          * store the converted pipeline_description on the job,
          * start a background worker thread.
        """
        manager = ValidationManager()

        # Mock Graph.from_dict(...).to_pipeline_description()
        mock_graph = MagicMock()
        mock_graph.to_pipeline_description.return_value = (
            "filesrc ! decodebin3 ! autovideosink"
        )
        mock_graph_cls.from_dict.return_value = mock_graph

        request = self._build_validation_request(parameters=None)

        # Patch _execute_validation so we do not actually spawn validator.py
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

        # Background worker must be started with correct arguments
        mock_execute.assert_called_once()
        called_job_id, called_pipe_desc, called_max_rt, called_hard_to = (
            mock_execute.call_args[0]
        )
        self.assertEqual(called_job_id, job_id)
        self.assertEqual(called_pipe_desc, "filesrc ! decodebin3 ! autovideosink")
        # Default max-runtime is 10, hard-timeout is 10 + 60
        self.assertEqual(called_max_rt, 10)
        self.assertEqual(called_hard_to, 70)

    # ------------------------------------------------------------------
    # Parameter validation (max-runtime)
    # ------------------------------------------------------------------

    @patch("managers.validation_manager.Graph")
    def test_run_validation_uses_default_max_runtime_when_not_provided(
        self, mock_graph_cls
    ):
        """
        When 'max-runtime' is not provided in parameters, run_validation
        should default it to 10 seconds.
        """
        manager = ValidationManager()

        mock_graph = MagicMock()
        mock_graph.to_pipeline_description.return_value = "pipeline"
        mock_graph_cls.from_dict.return_value = mock_graph

        request = self._build_validation_request(parameters={})

        with patch.object(manager, "_execute_validation") as mock_execute:
            job_id = manager.run_validation(request)

        # Ensure thread was scheduled with default values
        _, _, max_rt, hard_timeout = mock_execute.call_args[0]
        self.assertEqual(max_rt, 10)
        self.assertEqual(hard_timeout, 70)
        self.assertIn(job_id, manager.jobs)

    @patch("managers.validation_manager.Graph")
    def test_run_validation_raises_value_error_for_non_int_max_runtime(
        self, mock_graph_cls
    ):
        """
        Non-integer 'max-runtime' should result in a ValueError.
        """
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
    def test_run_validation_raises_value_error_for_too_small_max_runtime(
        self, mock_graph_cls
    ):
        """
        max-runtime < 1 should result in a ValueError.
        """
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

    @patch("managers.validation_manager.ValidatorRunner")
    def test_execute_validation_marks_job_completed_on_success(self, mock_runner_cls):
        """
        On successful validator run:
          * job.state should become COMPLETED,
          * is_valid must be True,
          * error_message should remain None.
        """
        manager = ValidationManager()

        # Prepare a job in RUNNING state
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

        # Mock runner returning (True, [])
        mock_runner = MagicMock()
        mock_runner.run.return_value = (True, [])
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

    @patch("managers.validation_manager.ValidatorRunner")
    def test_execute_validation_marks_job_error_on_invalid_pipeline(
        self, mock_runner_cls
    ):
        """
        When validator reports invalid pipeline:
          * job.state should become ERROR,
          * is_valid must be False,
          * error_message should contain the reported errors.
        """
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
        mock_runner.run.return_value = (False, ["no element foo", "some other error"])
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

    @patch("managers.validation_manager.ValidatorRunner")
    def test_execute_validation_sets_error_on_exception(self, mock_runner_cls):
        """
        Any unexpected exception from ValidatorRunner should:
          * mark the job as ERROR,
          * append the exception message to error_message.
        """
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
        mock_runner.run.side_effect = RuntimeError("validator exploded")
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
        self.assertIn("validator exploded", " ".join(updated.error_message or []))

    # ------------------------------------------------------------------
    # Status and summary retrieval
    # ------------------------------------------------------------------

    def test_get_all_job_statuses_returns_correct_statuses(self):
        """
        get_all_job_statuses should build statuses for all jobs currently known.
        """
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


class TestValidatorRunner(unittest.TestCase):
    """
    Focused tests for ValidatorRunner._parse_stderr.

    ValidatorRunner.run() itself is not invoked here because it launches
    a real subprocess; instead we verify that stderr parsing behaves as
    expected for various shapes of validator output.
    """

    def test_parse_stderr_collects_only_validator_error_lines(self):
        """
        _parse_stderr should:
          * keep only lines starting with 'validator - ERROR - ',
          * strip that prefix,
          * drop empty/whitespace-only messages.
        """
        raw = "\n".join(
            [
                "some-other-tool - INFO - hello",
                "validator - ERROR - first error",
                "validator - ERROR -   second error   ",
                "validator - ERROR -    ",
                "completely unrelated line",
            ]
        )

        # Use the static method directly
        errors: List[str] = ValidatorRunner._parse_stderr(raw)
        self.assertEqual(errors, ["first error", "second error"])

    def test_parse_stderr_handles_empty_input(self):
        """Empty stderr should produce an empty list."""
        errors = ValidatorRunner._parse_stderr("")
        self.assertEqual(errors, [])

    def test_parse_stderr_ignores_non_prefixed_lines(self):
        """Lines without the expected prefix must be ignored."""
        raw = "validator - INFO - not-an-error\nother - ERROR - also-ignored"
        errors = ValidatorRunner._parse_stderr(raw)
        self.assertEqual(errors, [])


class TestGetValidationManagerSingleton(unittest.TestCase):
    """
    Tests for the get_validation_manager singleton accessor.
    """

    @patch("managers.validation_manager.ValidationManager")
    def test_get_validation_manager_returns_singleton(self, mock_mgr_cls):
        """
        get_validation_manager should lazily create and cache a singleton.
        """
        from managers import validation_manager as mod

        # Reset global state for this test
        mod._validation_manager_instance = None

        instance1 = get_validation_manager()
        instance2 = get_validation_manager()

        mock_mgr_cls.assert_called_once()
        self.assertIs(instance1, instance2)


if __name__ == "__main__":
    unittest.main()

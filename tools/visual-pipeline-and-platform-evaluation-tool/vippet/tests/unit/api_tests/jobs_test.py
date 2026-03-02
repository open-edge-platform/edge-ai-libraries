import time
import unittest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from fastapi.routing import APIRoute
from unittest.mock import patch, MagicMock

import api.api_schemas as schemas
from graph import Graph
from internal_types import (
    InternalOptimizationJobStatus,
    InternalOptimizationJobState,
    InternalOptimizationJobSummary,
    InternalOptimizationType,
    InternalPipelineRequestOptimize,
    InternalPipelineValidation,
    InternalValidationJobState,
    InternalValidationJobStatus,
    InternalValidationJobSummary,
)
from api.routes.jobs import router as jobs_router


class TestJobsAPI(unittest.TestCase):
    """
    Integration-style unit tests for the jobs HTTP API.

    The tests use FastAPI's TestClient and patch the manager classes
    so we can precisely control the behavior of the underlying managers
    without touching their real implementation or any background threads.

    Managers return internal types. The route layer converts them to API
    types. Tests must mock managers to return internal types.
    """

    @classmethod
    def setUpClass(cls):
        app = FastAPI()
        app.include_router(jobs_router, prefix="/jobs")
        cls.client = TestClient(app)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _make_minimal_graph(self) -> schemas.PipelineGraph:
        """Build a very small pipeline graph for API-level assertions."""
        return schemas.PipelineGraph(
            nodes=[
                schemas.Node(
                    id="0",
                    type="filesrc",
                    data={"location": "/tmp/dummy.mp4"},
                )
            ],
            edges=[],
        )

    def _make_mock_graph(self) -> MagicMock:
        """Build a mock Graph object that can be converted to API PipelineGraph."""
        mock = MagicMock(spec=Graph)
        mock.to_dict.return_value = {
            "nodes": [
                {"id": "0", "type": "filesrc", "data": {"location": "/tmp/dummy.mp4"}},
            ],
            "edges": [],
        }
        return mock

    # ------------------------------------------------------------------
    # /jobs/optimization/status
    # ------------------------------------------------------------------

    @patch("api.routes.jobs.OptimizationManager")
    def test_get_optimization_statuses_returns_list(
        self, mock_optimization_manager_cls
    ):
        """
        The /jobs/optimization/status endpoint should return a list of
        OptimizationJobStatus objects as JSON.

        Manager returns InternalOptimizationJobStatus objects. Route layer
        converts them to API OptimizationJobStatus.
        """
        mock_graph = self._make_mock_graph()
        now = int(time.time() * 1000)

        mock_manager = MagicMock()
        mock_manager.get_all_job_statuses.return_value = [
            InternalOptimizationJobStatus(
                id="job-1",
                original_pipeline_graph=mock_graph,
                original_pipeline_graph_simple=mock_graph,
                original_pipeline_description="filesrc ! decodebin ! sink",
                request=InternalPipelineRequestOptimize(
                    type=InternalOptimizationType.PREPROCESS, parameters=None
                ),
                state=InternalOptimizationJobState.RUNNING,
                start_time=now,
                type=InternalOptimizationType.PREPROCESS,
            ),
            InternalOptimizationJobStatus(
                id="job-2",
                original_pipeline_graph=mock_graph,
                original_pipeline_graph_simple=mock_graph,
                original_pipeline_description="filesrc ! decodebin ! sink",
                request=InternalPipelineRequestOptimize(
                    type=InternalOptimizationType.OPTIMIZE, parameters=None
                ),
                state=InternalOptimizationJobState.COMPLETED,
                start_time=now - 500,
                type=InternalOptimizationType.OPTIMIZE,
                end_time=now,
                total_fps=123.4,
                optimized_pipeline_graph=mock_graph,
                optimized_pipeline_graph_simple=mock_graph,
                optimized_pipeline_description="optimized-pipeline",
            ),
        ]
        mock_optimization_manager_cls.return_value = mock_manager

        response = self.client.get("/jobs/optimization/status")

        self.assertEqual(response.status_code, 200)
        data = response.json()

        self.assertIsInstance(data, list)
        self.assertEqual(len(data), 2)

        first, second = data[0], data[1]

        # Spot-check first job (converted to API types by route layer)
        self.assertEqual(first["id"], "job-1")
        self.assertEqual(first["type"], "preprocess")
        self.assertEqual(first["state"], "RUNNING")
        self.assertIsNone(first["total_fps"])
        self.assertIn("original_pipeline_graph", first)
        self.assertIsNone(first["optimized_pipeline_graph"])

        # Spot-check second job
        self.assertEqual(second["id"], "job-2")
        self.assertEqual(second["type"], "optimize")
        self.assertEqual(second["state"], "COMPLETED")
        self.assertEqual(second["total_fps"], 123.4)
        self.assertEqual(second["optimized_pipeline_description"], "optimized-pipeline")

    # ------------------------------------------------------------------
    # /jobs/optimization/{job_id}
    # ------------------------------------------------------------------

    @patch("api.routes.jobs.OptimizationManager")
    def test_get_optimization_job_summary_found(self, mock_optimization_manager_cls):
        """
        When the manager returns an InternalOptimizationJobSummary, the endpoint
        converts it to API OptimizationJobSummary and responds with HTTP 200.
        """
        mock_manager = MagicMock()
        mock_manager.get_job_summary.return_value = InternalOptimizationJobSummary(
            id="job-123",
            request=InternalPipelineRequestOptimize(
                type=InternalOptimizationType.PREPROCESS,
                parameters={"foo": "bar"},
            ),
        )
        mock_optimization_manager_cls.return_value = mock_manager

        response = self.client.get("/jobs/optimization/job-123")

        self.assertEqual(response.status_code, 200)
        data = response.json()

        self.assertEqual(data["id"], "job-123")
        self.assertIn("request", data)
        self.assertEqual(data["request"]["type"], "preprocess")
        self.assertEqual(data["request"]["parameters"], {"foo": "bar"})

        mock_manager.get_job_summary.assert_called_once_with("job-123")

    @patch("api.routes.jobs.OptimizationManager")
    def test_get_optimization_job_summary_not_found(
        self, mock_optimization_manager_cls
    ):
        """
        When the manager returns None, the endpoint should return a 404.
        """
        mock_manager = MagicMock()
        mock_manager.get_job_summary.return_value = None
        mock_optimization_manager_cls.return_value = mock_manager

        missing_job_id = "missing-job"
        response = self.client.get(f"/jobs/optimization/{missing_job_id}")

        self.assertEqual(response.status_code, 404)
        self.assertEqual(
            response.json(),
            schemas.MessageResponse(
                message=f"Optimization job {missing_job_id} not found"
            ).model_dump(),
        )

    # ------------------------------------------------------------------
    # /jobs/optimization/{job_id}/status
    # ------------------------------------------------------------------

    @patch("api.routes.jobs.OptimizationManager")
    def test_get_optimization_job_status_found(self, mock_optimization_manager_cls):
        """
        When the job exists, /optimization/{job_id}/status must return the
        OptimizationJobStatus with HTTP 200.

        Manager returns InternalOptimizationJobStatus. Route layer converts it.
        """
        mock_graph = self._make_mock_graph()
        now = int(time.time() * 1000)

        mock_manager = MagicMock()
        mock_manager.get_job_status.return_value = InternalOptimizationJobStatus(
            id="job-status-1",
            original_pipeline_graph=mock_graph,
            original_pipeline_graph_simple=mock_graph,
            original_pipeline_description="filesrc ! decodebin ! sink",
            request=InternalPipelineRequestOptimize(
                type=InternalOptimizationType.OPTIMIZE, parameters=None
            ),
            state=InternalOptimizationJobState.RUNNING,
            start_time=now,
            type=InternalOptimizationType.OPTIMIZE,
        )
        mock_optimization_manager_cls.return_value = mock_manager

        response = self.client.get("/jobs/optimization/job-status-1/status")

        self.assertEqual(response.status_code, 200)
        data = response.json()

        self.assertEqual(data["id"], "job-status-1")
        self.assertEqual(data["type"], "optimize")
        self.assertEqual(data["state"], "RUNNING")
        self.assertIn("original_pipeline_graph", data)

        mock_manager.get_job_status.assert_called_once_with("job-status-1")

    @patch("api.routes.jobs.OptimizationManager")
    def test_get_optimization_job_status_not_found(self, mock_optimization_manager_cls):
        """
        When the job does not exist, /optimization/{job_id}/status must
        respond with HTTP 404.
        """
        mock_manager = MagicMock()
        mock_manager.get_job_status.return_value = None
        mock_optimization_manager_cls.return_value = mock_manager

        missing_job_id = "unknown-status-job"
        response = self.client.get(f"/jobs/optimization/{missing_job_id}/status")

        self.assertEqual(response.status_code, 404)
        self.assertEqual(
            response.json(),
            schemas.MessageResponse(
                message=f"Optimization job {missing_job_id} not found"
            ).model_dump(),
        )

    # ------------------------------------------------------------------
    # /jobs/validation/status
    # ------------------------------------------------------------------

    @patch("api.routes.jobs.ValidationManager")
    def test_get_validation_statuses_returns_list(self, mock_validation_manager_cls):
        """
        The /jobs/validation/status endpoint should return a list of
        ValidationJobStatus objects as JSON.

        Manager returns InternalValidationJobStatus objects. Route layer
        converts them to API ValidationJobStatus.

        This test validates:
        * HTTP 200 status,
        * response shape (list of objects),
        * selected field values are correctly serialized.
        """
        mock_manager = MagicMock()
        mock_manager.get_all_job_statuses.return_value = [
            InternalValidationJobStatus(
                id="val-job-1",
                start_time=1000,
                elapsed_time=200,
                state=InternalValidationJobState.RUNNING,
                is_valid=None,
                error_message=None,
            ),
            InternalValidationJobStatus(
                id="val-job-2",
                start_time=2000,
                elapsed_time=500,
                state=InternalValidationJobState.ERROR,
                is_valid=False,
                error_message=["no element foo"],
            ),
        ]
        mock_validation_manager_cls.return_value = mock_manager

        response = self.client.get("/jobs/validation/status")

        self.assertEqual(response.status_code, 200)
        data = response.json()

        self.assertIsInstance(data, list)
        self.assertEqual(len(data), 2)

        first, second = data[0], data[1]

        self.assertEqual(first["id"], "val-job-1")
        self.assertEqual(first["state"], "RUNNING")
        self.assertIsNone(first["is_valid"])
        self.assertIsNone(first["error_message"])

        self.assertEqual(second["id"], "val-job-2")
        self.assertEqual(second["state"], "ERROR")
        self.assertFalse(second["is_valid"])
        self.assertEqual(second["error_message"], ["no element foo"])

    # ------------------------------------------------------------------
    # /jobs/validation/{job_id}
    # ------------------------------------------------------------------

    @patch("api.routes.jobs.ValidationManager")
    def test_get_validation_job_summary_found(self, mock_validation_manager_cls):
        """
        When the manager returns an InternalValidationJobSummary, the endpoint
        converts it to API ValidationJobSummary and responds with HTTP 200.
        """
        mock_graph = self._make_mock_graph()
        internal_request = InternalPipelineValidation(
            pipeline_graph=mock_graph,
            parameters={"max-runtime": 10},
        )
        mock_manager = MagicMock()
        mock_manager.get_job_summary.return_value = InternalValidationJobSummary(
            id="val-job-123",
            request=internal_request,
        )
        mock_validation_manager_cls.return_value = mock_manager

        response = self.client.get("/jobs/validation/val-job-123")

        self.assertEqual(response.status_code, 200)
        data = response.json()

        self.assertEqual(data["id"], "val-job-123")
        self.assertIn("request", data)
        self.assertIn("pipeline_graph", data["request"])
        self.assertEqual(data["request"]["parameters"], {"max-runtime": 10})

    @patch("api.routes.jobs.ValidationManager")
    def test_get_validation_job_summary_not_found(self, mock_validation_manager_cls):
        """
        When the manager returns None, the endpoint should return a 404
        with a descriptive MessageResponse payload.
        """
        mock_manager = MagicMock()
        mock_manager.get_job_summary.return_value = None
        mock_validation_manager_cls.return_value = mock_manager

        missing_job_id = "missing-val-job"
        response = self.client.get(f"/jobs/validation/{missing_job_id}")

        self.assertEqual(response.status_code, 404)
        self.assertEqual(
            response.json(),
            schemas.MessageResponse(
                message=f"Validation job {missing_job_id} not found"
            ).model_dump(),
        )

    # ------------------------------------------------------------------
    # /jobs/validation/{job_id}/status
    # ------------------------------------------------------------------

    @patch("api.routes.jobs.ValidationManager")
    def test_get_validation_job_status_found(self, mock_validation_manager_cls):
        """
        When the job exists, /validation/{job_id}/status must return the
        ValidationJobStatus with HTTP 200.

        Manager returns InternalValidationJobStatus. Route layer converts it.
        """
        mock_manager = MagicMock()
        mock_manager.get_job_status.return_value = InternalValidationJobStatus(
            id="val-status-1",
            start_time=123456,
            elapsed_time=1000,
            state=InternalValidationJobState.COMPLETED,
            is_valid=True,
            error_message=None,
        )
        mock_validation_manager_cls.return_value = mock_manager

        response = self.client.get("/jobs/validation/val-status-1/status")

        self.assertEqual(response.status_code, 200)
        data = response.json()

        self.assertEqual(data["id"], "val-status-1")
        self.assertEqual(data["state"], "COMPLETED")
        self.assertTrue(data["is_valid"])
        self.assertIsNone(data["error_message"])

    @patch("api.routes.jobs.ValidationManager")
    def test_get_validation_job_status_not_found(self, mock_validation_manager_cls):
        """
        When the job does not exist, /validation/{job_id}/status must
        respond with HTTP 404 and a MessageResponse.
        """
        mock_manager = MagicMock()
        mock_manager.get_job_status.return_value = None
        mock_validation_manager_cls.return_value = mock_manager

        missing_job_id = "unknown-val-status-job"
        response = self.client.get(f"/jobs/validation/{missing_job_id}/status")

        self.assertEqual(response.status_code, 404)
        self.assertEqual(
            response.json(),
            schemas.MessageResponse(
                message=f"Validation job {missing_job_id} not found"
            ).model_dump(),
        )

    # ------------------------------------------------------------------
    # Router metadata
    # ------------------------------------------------------------------

    def test_operation_ids_are_exposed_as_expected(self):
        """
        Ensure that the router in jobs.py is configured with the expected
        ``operation_id`` values.

        This test does not perform any HTTP calls; instead it inspects
        the FastAPI route definitions.  This is useful to:

        * keep the OpenAPI schema stable,
        * catch accidental renames of operation IDs,
        * slightly increase coverage on routing-related code paths.
        """
        # Collect mapping from path+method to operation_id
        operations = {}
        for route in jobs_router.routes:
            if not isinstance(route, APIRoute):
                # Skip non-HTTP routes such as WebSocketRoute.
                continue
            for method in route.methods:
                operations[(route.path, method)] = route.operation_id

        self.assertIn(("/optimization/status", "GET"), operations)
        self.assertIn(("/optimization/{job_id}", "GET"), operations)
        self.assertIn(("/optimization/{job_id}/status", "GET"), operations)

        self.assertEqual(
            operations[("/optimization/status", "GET")],
            "get_optimization_statuses",
        )
        self.assertEqual(
            operations[("/optimization/{job_id}", "GET")],
            "get_optimization_job_summary",
        )
        self.assertEqual(
            operations[("/optimization/{job_id}/status", "GET")],
            "get_optimization_job_status",
        )

        self.assertIn(("/validation/status", "GET"), operations)
        self.assertIn(("/validation/{job_id}", "GET"), operations)
        self.assertIn(("/validation/{job_id}/status", "GET"), operations)

        self.assertEqual(
            operations[("/validation/status", "GET")],
            "get_validation_statuses",
        )
        self.assertEqual(
            operations[("/validation/{job_id}", "GET")],
            "get_validation_job_summary",
        )
        self.assertEqual(
            operations[("/validation/{job_id}/status", "GET")],
            "get_validation_job_status",
        )

    # ------------------------------------------------------------------
    # Stop test job tests
    # ------------------------------------------------------------------

    @patch("api.routes.jobs.TestsManager")
    def test_stop_test_job_success(self, mock_tests_manager_cls):
        job_id = "46b55660b96011f0948d9b40bdd1b89c"
        mock_manager = MagicMock()
        mock_manager.stop_job.return_value = (True, f"Job {job_id} stopped")
        mock_tests_manager_cls.return_value = mock_manager

        response = self.client.delete(f"/jobs/tests/performance/{job_id}")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"message": f"Job {job_id} stopped"})

        response = self.client.delete(f"/jobs/tests/density/{job_id}")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"message": f"Job {job_id} stopped"})

    @patch("api.routes.jobs.TestsManager")
    def test_stop_test_job_not_found(self, mock_tests_manager_cls):
        job_id = "46b55660b96011f0948d9b40bdd1b89c"
        mock_manager = MagicMock()
        mock_manager.stop_job.return_value = (False, f"Job {job_id} not found")
        mock_tests_manager_cls.return_value = mock_manager

        response = self.client.delete(f"/jobs/tests/performance/{job_id}")
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json(), {"message": f"Job {job_id} not found"})

        response = self.client.delete(f"/jobs/tests/density/{job_id}")
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json(), {"message": f"Job {job_id} not found"})

    @patch("api.routes.jobs.TestsManager")
    def test_stop_test_job_not_running(self, mock_tests_manager_cls):
        job_id = "46b55660b96011f0948d9b40bdd1b89c"
        mock_manager = MagicMock()
        mock_manager.stop_job.return_value = (
            False,
            f"Job {job_id} is not running (state: COMPLETED)",
        )
        mock_tests_manager_cls.return_value = mock_manager

        response = self.client.delete(f"/jobs/tests/performance/{job_id}")
        self.assertEqual(response.status_code, 409)
        self.assertEqual(
            response.json(),
            {"message": f"Job {job_id} is not running (state: COMPLETED)"},
        )

        response = self.client.delete(f"/jobs/tests/density/{job_id}")
        self.assertEqual(response.status_code, 409)
        self.assertEqual(
            response.json(),
            {"message": f"Job {job_id} is not running (state: COMPLETED)"},
        )

    @patch("api.routes.jobs.TestsManager")
    def test_stop_test_job_server_error(self, mock_tests_manager_cls):
        job_id = "46b55660b96011f0948d9b40bdd1b89c"
        mock_manager = MagicMock()
        mock_manager.stop_job.return_value = (False, "Unexpected error occurred")
        mock_tests_manager_cls.return_value = mock_manager

        response = self.client.delete(f"/jobs/tests/performance/{job_id}")
        self.assertEqual(response.status_code, 500)
        self.assertEqual(response.json(), {"message": "Unexpected error occurred"})

        response = self.client.delete(f"/jobs/tests/density/{job_id}")
        self.assertEqual(response.status_code, 500)
        self.assertEqual(response.json(), {"message": "Unexpected error occurred"})

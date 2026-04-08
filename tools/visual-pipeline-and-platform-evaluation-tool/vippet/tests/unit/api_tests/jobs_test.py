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
                details=["Optimization completed successfully"],
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
        self.assertEqual(first["details"], [])

        # Spot-check second job
        self.assertEqual(second["id"], "job-2")
        self.assertEqual(second["type"], "optimize")
        self.assertEqual(second["state"], "COMPLETED")
        self.assertEqual(second["total_fps"], 123.4)
        self.assertEqual(second["optimized_pipeline_description"], "optimized-pipeline")
        self.assertEqual(second["details"], ["Optimization completed successfully"])

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
        self.assertEqual(data["details"], [])

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
                details=[],
                is_valid=None,
            ),
            InternalValidationJobStatus(
                id="val-job-2",
                start_time=2000,
                elapsed_time=500,
                state=InternalValidationJobState.FAILED,
                details=["Pipeline validation failed: no element foo"],
                is_valid=False,
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
        self.assertEqual(first["details"], [])

        self.assertEqual(second["id"], "val-job-2")
        self.assertEqual(second["state"], "FAILED")
        self.assertFalse(second["is_valid"])
        self.assertEqual(
            second["details"], ["Pipeline validation failed: no element foo"]
        )

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
            details=["Pipeline is valid"],
            is_valid=True,
        )
        mock_validation_manager_cls.return_value = mock_manager

        response = self.client.get("/jobs/validation/val-status-1/status")

        self.assertEqual(response.status_code, 200)
        data = response.json()

        self.assertEqual(data["id"], "val-status-1")
        self.assertEqual(data["state"], "COMPLETED")
        self.assertTrue(data["is_valid"])
        self.assertEqual(data["details"], ["Pipeline is valid"])

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

    # ------------------------------------------------------------------
    # /jobs/tests/performance/{job_id}/metadata/{pipeline_id}/{file_index}
    # ------------------------------------------------------------------

    @patch("api.routes.jobs.MetadataManager")
    @patch("api.routes.jobs.TestsManager")
    def test_get_metadata_snapshot_job_not_in_metadata_manager_and_not_in_tests_manager(
        self, mock_tests_manager_cls, mock_metadata_manager_cls
    ):
        """
        When the job is unknown to both MetadataManager and TestsManager the
        endpoint should return 404 with "Performance job … not found".
        """
        mock_metadata_manager = MagicMock()
        mock_metadata_manager.job_exists.return_value = False
        mock_metadata_manager_cls.return_value = mock_metadata_manager

        mock_tests_manager = MagicMock()
        mock_tests_manager.get_job_status.return_value = None
        mock_tests_manager_cls.return_value = mock_tests_manager

        response = self.client.get(
            "/jobs/tests/performance/no-such-job/metadata/pipe-a/0"
        )

        self.assertEqual(response.status_code, 404)
        self.assertEqual(
            response.json(),
            schemas.MessageResponse(
                message="Performance job no-such-job not found"
            ).model_dump(),
        )

    @patch("api.routes.jobs.MetadataManager")
    @patch("api.routes.jobs.TestsManager")
    def test_get_metadata_snapshot_job_exists_but_no_metadata(
        self, mock_tests_manager_cls, mock_metadata_manager_cls
    ):
        """
        When the job exists in TestsManager but MetadataManager has no record
        for it (pipeline has no gvametapublish element), the endpoint should
        return 404 with a "No metadata available" message.
        """
        mock_metadata_manager = MagicMock()
        mock_metadata_manager.job_exists.return_value = False
        mock_metadata_manager_cls.return_value = mock_metadata_manager

        mock_tests_manager = MagicMock()
        mock_tests_manager.get_job_status.return_value = MagicMock()
        mock_tests_manager_cls.return_value = mock_tests_manager

        response = self.client.get(
            "/jobs/tests/performance/job-no-meta/metadata/pipe-a/0"
        )

        self.assertEqual(response.status_code, 404)
        data = response.json()
        self.assertIn("No metadata available", data["message"])
        self.assertIn("job-no-meta", data["message"])

    @patch("api.routes.jobs.MetadataManager")
    def test_get_metadata_snapshot_unknown_pipeline_or_file_index(
        self, mock_metadata_manager_cls
    ):
        """
        When the job is registered in MetadataManager but the given
        pipeline_id / file_index cannot be resolved, the endpoint returns 404.
        """
        mock_metadata_manager = MagicMock()
        mock_metadata_manager.job_exists.return_value = True
        mock_metadata_manager.resolve_file_index.return_value = None
        mock_metadata_manager_cls.return_value = mock_metadata_manager

        response = self.client.get(
            "/jobs/tests/performance/job-1/metadata/missing-pipe/0"
        )

        self.assertEqual(response.status_code, 404)
        data = response.json()
        self.assertIn("missing-pipe", data["message"])
        self.assertIn("job-1", data["message"])

    @patch("api.routes.jobs.MetadataManager")
    def test_get_metadata_snapshot_returns_records(self, mock_metadata_manager_cls):
        """
        The happy path: job exists, pipeline and file_index resolve, records
        are returned by MetadataManager.get_snapshot() and the endpoint
        responds with HTTP 200 and a JSON array.
        """
        records = [{"frame": 1, "timestamp": 100}, {"frame": 2, "timestamp": 200}]
        mock_metadata_manager = MagicMock()
        mock_metadata_manager.job_exists.return_value = True
        mock_metadata_manager.resolve_file_index.return_value = 3
        mock_metadata_manager.get_snapshot.return_value = records
        mock_metadata_manager_cls.return_value = mock_metadata_manager

        response = self.client.get(
            "/jobs/tests/performance/job-1/metadata/pipe-a/0?limit=50"
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), records)
        mock_metadata_manager.resolve_file_index.assert_called_once_with(
            "job-1", "pipe-a", 0
        )
        mock_metadata_manager.get_snapshot.assert_called_once_with(
            "job-1", file_index=3, limit=50
        )

    @patch("api.routes.jobs.MetadataManager")
    def test_get_metadata_snapshot_uses_default_limit(self, mock_metadata_manager_cls):
        """
        When no ``limit`` query parameter is provided the default of 100
        should be forwarded to MetadataManager.get_snapshot().
        """
        mock_metadata_manager = MagicMock()
        mock_metadata_manager.job_exists.return_value = True
        mock_metadata_manager.resolve_file_index.return_value = 0
        mock_metadata_manager.get_snapshot.return_value = []
        mock_metadata_manager_cls.return_value = mock_metadata_manager

        response = self.client.get("/jobs/tests/performance/job-1/metadata/pipe-a/0")

        self.assertEqual(response.status_code, 200)
        mock_metadata_manager.get_snapshot.assert_called_once_with(
            "job-1", file_index=0, limit=100
        )

    @patch("api.routes.jobs.MetadataManager")
    def test_get_metadata_snapshot_returns_empty_list(self, mock_metadata_manager_cls):
        """
        An empty snapshot (no records yet written) should return HTTP 200
        with an empty JSON array, not a 404.
        """
        mock_metadata_manager = MagicMock()
        mock_metadata_manager.job_exists.return_value = True
        mock_metadata_manager.resolve_file_index.return_value = 0
        mock_metadata_manager.get_snapshot.return_value = []
        mock_metadata_manager_cls.return_value = mock_metadata_manager

        response = self.client.get("/jobs/tests/performance/job-1/metadata/pipe-a/0")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), [])

    @patch("api.routes.jobs.MetadataManager")
    def test_get_metadata_snapshot_limit_too_large_is_rejected(
        self, mock_metadata_manager_cls
    ):
        """
        Requesting more records than METADATA_SNAPSHOT_LIMIT (1000) should
        cause FastAPI query validation to reject the request with 422.
        """
        mock_metadata_manager = MagicMock()
        mock_metadata_manager.job_exists.return_value = True
        mock_metadata_manager_cls.return_value = mock_metadata_manager

        response = self.client.get(
            "/jobs/tests/performance/job-1/metadata/pipe-a/0?limit=9999"
        )

        self.assertEqual(response.status_code, 422)

    @patch("api.routes.jobs.MetadataManager")
    def test_get_metadata_snapshot_limit_zero_is_rejected(
        self, mock_metadata_manager_cls
    ):
        """
        A limit of 0 is below the minimum of 1 and should be rejected with 422.
        """
        mock_metadata_manager = MagicMock()
        mock_metadata_manager.job_exists.return_value = True
        mock_metadata_manager_cls.return_value = mock_metadata_manager

        response = self.client.get(
            "/jobs/tests/performance/job-1/metadata/pipe-a/0?limit=0"
        )

        self.assertEqual(response.status_code, 422)

    # ------------------------------------------------------------------
    # /jobs/tests/performance/{job_id}/metadata/{pipeline_id}/{file_index}/stream
    # ------------------------------------------------------------------

    @patch("api.routes.jobs.MetadataManager")
    @patch("api.routes.jobs.TestsManager")
    def test_stream_metadata_job_not_in_metadata_manager_and_not_in_tests_manager(
        self, mock_tests_manager_cls, mock_metadata_manager_cls
    ):
        """
        When the job is unknown to both managers the SSE endpoint returns 404
        with "Performance job … not found".
        """
        mock_metadata_manager = MagicMock()
        mock_metadata_manager.job_exists.return_value = False
        mock_metadata_manager_cls.return_value = mock_metadata_manager

        mock_tests_manager = MagicMock()
        mock_tests_manager.get_job_status.return_value = None
        mock_tests_manager_cls.return_value = mock_tests_manager

        response = self.client.get(
            "/jobs/tests/performance/no-such-job/metadata/pipe-a/0/stream"
        )

        self.assertEqual(response.status_code, 404)
        self.assertEqual(
            response.json(),
            schemas.MessageResponse(
                message="Performance job no-such-job not found"
            ).model_dump(),
        )

    @patch("api.routes.jobs.MetadataManager")
    @patch("api.routes.jobs.TestsManager")
    def test_stream_metadata_job_exists_but_no_metadata(
        self, mock_tests_manager_cls, mock_metadata_manager_cls
    ):
        """
        When the job exists in TestsManager but MetadataManager has no record
        for it (no gvametapublish element), the SSE endpoint returns 404 with
        a "No metadata stream available" message.
        """
        mock_metadata_manager = MagicMock()
        mock_metadata_manager.job_exists.return_value = False
        mock_metadata_manager_cls.return_value = mock_metadata_manager

        mock_tests_manager = MagicMock()
        mock_tests_manager.get_job_status.return_value = MagicMock()
        mock_tests_manager_cls.return_value = mock_tests_manager

        response = self.client.get(
            "/jobs/tests/performance/job-no-meta/metadata/pipe-a/0/stream"
        )

        self.assertEqual(response.status_code, 404)
        data = response.json()
        self.assertIn("No metadata stream available", data["message"])
        self.assertIn("job-no-meta", data["message"])

    @patch("api.routes.jobs.MetadataManager")
    def test_stream_metadata_unknown_pipeline_or_file_index(
        self, mock_metadata_manager_cls
    ):
        """
        When the job exists in MetadataManager but the pipeline_id / file_index
        cannot be resolved, the SSE endpoint returns 404.
        """
        mock_metadata_manager = MagicMock()
        mock_metadata_manager.job_exists.return_value = True
        mock_metadata_manager.resolve_file_index.return_value = None
        mock_metadata_manager_cls.return_value = mock_metadata_manager

        response = self.client.get(
            "/jobs/tests/performance/job-1/metadata/missing-pipe/0/stream"
        )

        self.assertEqual(response.status_code, 404)
        data = response.json()
        self.assertIn("missing-pipe", data["message"])
        self.assertIn("job-1", data["message"])

    @patch("api.routes.jobs.MetadataManager")
    def test_stream_metadata_returns_sse_stream(self, mock_metadata_manager_cls):
        """
        The happy path: job and file_index resolve correctly, MetadataManager
        yields one JSON record then stops.  The SSE response must have
        ``Content-Type: text/event-stream`` and contain a ``data:`` line for
        the record.
        """

        async def _fake_stream(*_args, **_kwargs):
            yield '{"frame": 1}'

        mock_metadata_manager = MagicMock()
        mock_metadata_manager.job_exists.return_value = True
        mock_metadata_manager.resolve_file_index.return_value = 2
        mock_metadata_manager.stream_events = _fake_stream
        mock_metadata_manager_cls.return_value = mock_metadata_manager

        response = self.client.get(
            "/jobs/tests/performance/job-1/metadata/pipe-a/0/stream"
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("text/event-stream", response.headers["content-type"])
        self.assertIn('data: {"frame": 1}', response.text)

    @patch("api.routes.jobs.MetadataManager")
    def test_stream_metadata_forwards_keepalive_comments(
        self, mock_metadata_manager_cls
    ):
        """
        Keepalive comments (lines starting with ``:``) should be passed through
        as-is without wrapping them in a ``data:`` prefix.
        """

        async def _fake_stream(*_args, **_kwargs):
            yield ": keepalive\n\n"

        mock_metadata_manager = MagicMock()
        mock_metadata_manager.job_exists.return_value = True
        mock_metadata_manager.resolve_file_index.return_value = 0
        mock_metadata_manager.stream_events = _fake_stream
        mock_metadata_manager_cls.return_value = mock_metadata_manager

        response = self.client.get(
            "/jobs/tests/performance/job-1/metadata/pipe-a/0/stream"
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn(": keepalive", response.text)
        self.assertNotIn("data: : keepalive", response.text)

    @patch("api.routes.jobs.MetadataManager")
    def test_stream_metadata_empty_stream_returns_200(self, mock_metadata_manager_cls):
        """
        When MetadataManager yields nothing (pipeline already finished),
        the SSE endpoint should still return HTTP 200 with an empty body.
        """

        async def _fake_stream(*_args, **_kwargs):
            return
            yield  # make it an async generator

        mock_metadata_manager = MagicMock()
        mock_metadata_manager.job_exists.return_value = True
        mock_metadata_manager.resolve_file_index.return_value = 0
        mock_metadata_manager.stream_events = _fake_stream
        mock_metadata_manager_cls.return_value = mock_metadata_manager

        response = self.client.get(
            "/jobs/tests/performance/job-1/metadata/pipe-a/0/stream"
        )

        self.assertEqual(response.status_code, 200)

    @patch("api.routes.jobs.MetadataManager")
    def test_stream_metadata_passes_correct_global_index_to_stream_events(
        self, mock_metadata_manager_cls
    ):
        """
        The route must call stream_events with the *global* index returned by
        resolve_file_index, not the per-pipeline local file_index from the URL.
        """
        calls: list[tuple] = []

        async def _fake_stream(job_id, global_index):
            calls.append((job_id, global_index))
            return
            yield

        mock_metadata_manager = MagicMock()
        mock_metadata_manager.job_exists.return_value = True
        mock_metadata_manager.resolve_file_index.return_value = 7
        mock_metadata_manager.stream_events = _fake_stream
        mock_metadata_manager_cls.return_value = mock_metadata_manager

        self.client.get("/jobs/tests/performance/job-1/metadata/pipe-a/0/stream")

        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0], ("job-1", 7))

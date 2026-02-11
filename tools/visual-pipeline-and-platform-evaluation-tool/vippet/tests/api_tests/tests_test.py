import unittest
from unittest.mock import patch, MagicMock

from fastapi import FastAPI
from fastapi.testclient import TestClient

import api.api_schemas as schemas
from api.routes.tests import router as tests_router
from managers.tests_manager import TestsManager
from managers.pipeline_manager import PipelineManager


class TestTestsAPI(unittest.TestCase):
    """
    Integration-style unit tests for the tests HTTP API.

    The tests use FastAPI's TestClient and patch the TestsManager singleton
    so we can precisely control the behavior of the underlying manager without
    touching its real implementation or any background threads.
    """

    @classmethod
    def setUpClass(cls):
        """
        Build a minimal FastAPI app and mount the tests router once for all tests.

        This mirrors the approach used in ``pipelines_test.py`` in order to:
        * exercise the actual path/operation configuration of the router,
        * verify serialization / response models and HTTP codes,
        * keep the tests fast and side-effect free by patching dependencies.
        """
        app = FastAPI()
        # All endpoints in tests.py are mounted under the /tests prefix.
        # This prefix is baked into all request URLs used in this test suite.
        app.include_router(tests_router, prefix="/tests")
        cls.client = TestClient(app)

    def setUp(self):
        """Reset singleton state before each test."""
        TestsManager._instance = None
        PipelineManager._instance = None

    def tearDown(self):
        """Reset singleton state after each test."""
        TestsManager._instance = None
        PipelineManager._instance = None

    # ------------------------------------------------------------------
    # /tests/performance
    # ------------------------------------------------------------------

    @patch("api.routes.tests.TestsManager")
    def test_run_performance_test_returns_job_id(self, mock_tests_manager_cls):
        """
        The /tests/performance endpoint should accept a PerformanceTestSpec
        and return a TestJobResponse with a job_id.

        This test validates:
        * HTTP 202 status (Accepted),
        * response contains job_id field,
        * test_manager.test_performance() is called with the correct spec.
        """
        # Arrange: configure mock to return a job ID
        mock_manager = MagicMock()
        mock_manager.test_performance.return_value = "test-job-123"
        mock_tests_manager_cls.return_value = mock_manager

        # Act: send a performance test request
        request_body = {
            "pipeline_performance_specs": [
                {
                    "id": "pipeline-test123",
                    "streams": 2,
                }
            ],
            "execution_config": {"output_mode": "disabled", "max_runtime": 0},
        }
        response = self.client.post("/tests/performance", json=request_body)

        # Assert: verify response
        self.assertEqual(response.status_code, 202)
        data = response.json()
        self.assertIn("job_id", data)
        self.assertEqual(data["job_id"], "test-job-123")

        # Verify manager was called with correct spec
        mock_manager.test_performance.assert_called_once()
        call_args = mock_manager.test_performance.call_args[0][0]
        self.assertIsInstance(call_args, schemas.PerformanceTestSpec)
        self.assertEqual(len(call_args.pipeline_performance_specs), 1)
        self.assertEqual(call_args.pipeline_performance_specs[0].id, "pipeline-test123")
        self.assertEqual(call_args.pipeline_performance_specs[0].streams, 2)

    @patch("api.routes.tests.TestsManager")
    def test_run_performance_test_with_multiple_pipelines(self, mock_tests_manager_cls):
        """
        The /tests/performance endpoint should accept multiple pipeline specs
        in a single request.
        """
        # Arrange
        mock_manager = MagicMock()
        mock_manager.test_performance.return_value = "multi-job-456"
        mock_tests_manager_cls.return_value = mock_manager

        # Act: send request with multiple pipeline specs
        request_body = {
            "pipeline_performance_specs": [
                {
                    "id": "pipeline-abc123",
                    "streams": 1,
                },
                {
                    "id": "pipeline-def456",
                    "streams": 3,
                },
            ],
            "execution_config": {"output_mode": "disabled", "max_runtime": 0},
        }
        response = self.client.post("/tests/performance", json=request_body)

        # Assert
        self.assertEqual(response.status_code, 202)
        data = response.json()
        self.assertEqual(data["job_id"], "multi-job-456")

        # Verify manager was called with correct spec
        mock_manager.test_performance.assert_called_once()
        call_args = mock_manager.test_performance.call_args[0][0]
        self.assertEqual(len(call_args.pipeline_performance_specs), 2)
        self.assertEqual(call_args.pipeline_performance_specs[0].streams, 1)
        self.assertEqual(call_args.pipeline_performance_specs[1].streams, 3)

    @patch("api.routes.tests.TestsManager")
    def test_run_performance_test_with_invalid_body_returns_422(
        self, mock_tests_manager_cls
    ):
        """
        The /tests/performance endpoint should return 422 if the request body
        is invalid (e.g., missing required fields).
        """
        # Arrange
        mock_manager = MagicMock()
        mock_tests_manager_cls.return_value = mock_manager

        # Act: send request with missing pipeline_performance_specs
        request_body = {}
        response = self.client.post("/tests/performance", json=request_body)

        # Assert: FastAPI validation should reject the request
        self.assertEqual(response.status_code, 422)
        mock_manager.test_performance.assert_not_called()

    @patch("api.routes.tests.TestsManager")
    def test_run_performance_test_with_invalid_streams_returns_422(
        self, mock_tests_manager_cls
    ):
        """
        The /tests/performance endpoint should return 422 if streams value
        is invalid (e.g., negative number).
        """
        # Arrange
        mock_manager = MagicMock()
        mock_tests_manager_cls.return_value = mock_manager

        # Act: send request with negative streams
        request_body = {
            "pipeline_performance_specs": [
                {
                    "id": "pipeline-test789",
                    "streams": -1,
                }
            ],
            "execution_config": {"output_mode": "disabled", "max_runtime": 0},
        }
        response = self.client.post("/tests/performance", json=request_body)

        # Assert: FastAPI validation should reject the request
        self.assertEqual(response.status_code, 422)
        mock_manager.test_performance.assert_not_called()

    @patch("api.routes.tests.TestsManager")
    def test_run_performance_test_with_file_output(self, mock_tests_manager_cls):
        """
        The /tests/performance endpoint should accept execution_config
        with file output mode.
        """
        # Arrange: configure mock to return a job ID
        mock_manager = MagicMock()
        mock_manager.test_performance.return_value = "file-job-456"
        mock_tests_manager_cls.return_value = mock_manager

        # Act: send a performance test request with file output
        request_body = {
            "pipeline_performance_specs": [
                {
                    "id": "pipeline-file123",
                    "streams": 2,
                }
            ],
            "execution_config": {
                "output_mode": "file",
                "max_runtime": 0,
            },
        }
        response = self.client.post("/tests/performance", json=request_body)

        # Assert: verify response
        self.assertEqual(response.status_code, 202)
        data = response.json()
        self.assertIn("job_id", data)
        self.assertEqual(data["job_id"], "file-job-456")

        # Verify manager was called with correct spec including file output
        mock_manager.test_performance.assert_called_once()
        call_args = mock_manager.test_performance.call_args[0][0]
        self.assertIsInstance(call_args, schemas.PerformanceTestSpec)
        self.assertEqual(
            call_args.execution_config.output_mode, schemas.OutputMode.FILE
        )
        self.assertEqual(call_args.execution_config.max_runtime, 0)

    @patch("api.routes.tests.TestsManager")
    def test_run_performance_test_with_live_stream_output(self, mock_tests_manager_cls):
        """
        The /tests/performance endpoint should accept execution_config
        with live_stream output mode.
        """
        # Arrange: configure mock to return a job ID
        mock_manager = MagicMock()
        mock_manager.test_performance.return_value = "stream-job-789"
        mock_tests_manager_cls.return_value = mock_manager

        # Act: send a performance test request with live_stream output
        request_body = {
            "pipeline_performance_specs": [
                {
                    "id": "pipeline-stream123",
                    "streams": 1,
                }
            ],
            "execution_config": {
                "output_mode": "live_stream",
                "max_runtime": 60,
            },
        }
        response = self.client.post("/tests/performance", json=request_body)

        # Assert: verify response
        self.assertEqual(response.status_code, 202)
        data = response.json()
        self.assertEqual(data["job_id"], "stream-job-789")

        # Verify manager was called with correct spec including live_stream output
        mock_manager.test_performance.assert_called_once()
        call_args = mock_manager.test_performance.call_args[0][0]
        self.assertEqual(
            call_args.execution_config.output_mode, schemas.OutputMode.LIVE_STREAM
        )
        self.assertEqual(call_args.execution_config.max_runtime, 60)

    @patch("api.routes.tests.TestsManager")
    def test_run_performance_test_with_max_runtime(self, mock_tests_manager_cls):
        """
        The /tests/performance endpoint should accept execution_config
        with max_runtime for time-limited execution.
        """
        # Arrange: configure mock to return a job ID
        mock_manager = MagicMock()
        mock_manager.test_performance.return_value = "runtime-job-999"
        mock_tests_manager_cls.return_value = mock_manager

        # Act: send a performance test request with max_runtime
        request_body = {
            "pipeline_performance_specs": [
                {
                    "id": "pipeline-runtime123",
                    "streams": 2,
                }
            ],
            "execution_config": {
                "output_mode": "disabled",
                "max_runtime": 120,
            },
        }
        response = self.client.post("/tests/performance", json=request_body)

        # Assert: verify response
        self.assertEqual(response.status_code, 202)
        data = response.json()
        self.assertEqual(data["job_id"], "runtime-job-999")

        # Verify manager was called with correct spec including max_runtime
        mock_manager.test_performance.assert_called_once()
        call_args = mock_manager.test_performance.call_args[0][0]
        self.assertEqual(
            call_args.execution_config.output_mode, schemas.OutputMode.DISABLED
        )
        self.assertEqual(call_args.execution_config.max_runtime, 120)

    # ------------------------------------------------------------------
    # /tests/density
    # ------------------------------------------------------------------

    @patch("api.routes.tests.TestsManager")
    def test_run_density_test_returns_job_id(self, mock_tests_manager_cls):
        """
        The /tests/density endpoint should accept a DensityTestSpec
        and return a TestJobResponse with a job_id.

        This test validates:
        * HTTP 202 status (Accepted),
        * response contains job_id field,
        * test_manager.test_density() is called with the correct spec.
        """
        # Arrange: configure mock to return a job ID
        mock_manager = MagicMock()
        mock_manager.test_density.return_value = "density-job-789"
        mock_tests_manager_cls.return_value = mock_manager

        # Act: send a density test request
        request_body = {
            "fps_floor": 30,
            "pipeline_density_specs": [
                {
                    "id": "pipeline-ghi789",
                    "stream_rate": 100,
                }
            ],
            "execution_config": {"output_mode": "disabled", "max_runtime": 0},
        }
        response = self.client.post("/tests/density", json=request_body)

        # Assert: verify response
        self.assertEqual(response.status_code, 202)
        data = response.json()
        self.assertIn("job_id", data)
        self.assertEqual(data["job_id"], "density-job-789")

        # Verify manager was called with correct spec
        mock_manager.test_density.assert_called_once()
        call_args = mock_manager.test_density.call_args[0][0]
        self.assertIsInstance(call_args, schemas.DensityTestSpec)
        self.assertEqual(call_args.fps_floor, 30)
        self.assertEqual(len(call_args.pipeline_density_specs), 1)
        self.assertEqual(call_args.pipeline_density_specs[0].id, "pipeline-ghi789")
        self.assertEqual(call_args.pipeline_density_specs[0].stream_rate, 100)

    @patch("api.routes.tests.TestsManager")
    def test_run_density_test_with_multiple_pipelines(self, mock_tests_manager_cls):
        """
        The /tests/density endpoint should accept multiple pipeline specs
        in a single request.
        """
        # Arrange
        mock_manager = MagicMock()
        mock_manager.test_density.return_value = "density-multi-999"
        mock_tests_manager_cls.return_value = mock_manager

        # Act: send request with multiple pipeline specs
        request_body = {
            "fps_floor": 25,
            "pipeline_density_specs": [
                {
                    "id": "pipeline-jkl012",
                    "stream_rate": 50,
                },
                {
                    "id": "pipeline-mno345",
                    "stream_rate": 50,
                },
            ],
            "execution_config": {"output_mode": "disabled", "max_runtime": 0},
        }
        response = self.client.post("/tests/density", json=request_body)

        # Assert
        self.assertEqual(response.status_code, 202)
        data = response.json()
        self.assertEqual(data["job_id"], "density-multi-999")

        # Verify manager was called with correct spec
        mock_manager.test_density.assert_called_once()
        call_args = mock_manager.test_density.call_args[0][0]
        self.assertEqual(call_args.fps_floor, 25)
        self.assertEqual(len(call_args.pipeline_density_specs), 2)
        self.assertEqual(call_args.pipeline_density_specs[0].stream_rate, 50)
        self.assertEqual(call_args.pipeline_density_specs[1].stream_rate, 50)

    @patch("api.routes.tests.TestsManager")
    def test_run_density_test_with_invalid_body_returns_422(
        self, mock_tests_manager_cls
    ):
        """
        The /tests/density endpoint should return 422 if the request body
        is invalid (e.g., missing required fields).
        """
        # Arrange
        mock_manager = MagicMock()
        mock_tests_manager_cls.return_value = mock_manager

        # Act: send request with missing fps_floor
        request_body = {
            "pipeline_density_specs": [
                {
                    "id": "pipeline-pqr678",
                    "stream_rate": 100,
                }
            ]
        }
        response = self.client.post("/tests/density", json=request_body)

        # Assert: FastAPI validation should reject the request
        self.assertEqual(response.status_code, 422)
        mock_manager.test_density.assert_not_called()

    @patch("api.routes.tests.TestsManager")
    def test_run_density_test_with_invalid_fps_floor_returns_422(
        self, mock_tests_manager_cls
    ):
        """
        The /tests/density endpoint should return 422 if fps_floor value
        is invalid (e.g., negative number).
        """
        # Arrange
        mock_manager = MagicMock()
        mock_tests_manager_cls.return_value = mock_manager

        # Act: send request with negative fps_floor
        request_body = {
            "fps_floor": -10,
            "pipeline_density_specs": [
                {
                    "id": "pipeline-stu901",
                    "stream_rate": 100,
                }
            ],
            "execution_config": {"output_mode": "disabled", "max_runtime": 0},
        }
        response = self.client.post("/tests/density", json=request_body)

        # Assert: FastAPI validation should reject the request
        self.assertEqual(response.status_code, 422)
        mock_manager.test_density.assert_not_called()

    @patch("api.routes.tests.TestsManager")
    def test_run_density_test_with_invalid_stream_rate_returns_422(
        self, mock_tests_manager_cls
    ):
        """
        The /tests/density endpoint should return 422 if stream_rate value
        is invalid (e.g., negative number).
        """
        # Arrange
        mock_manager = MagicMock()
        mock_tests_manager_cls.return_value = mock_manager

        # Act: send request with negative stream_rate
        request_body = {
            "fps_floor": 30,
            "pipeline_density_specs": [
                {
                    "id": "pipeline-vwx234",
                    "stream_rate": -50,
                }
            ],
            "execution_config": {"output_mode": "disabled", "max_runtime": 0},
        }
        response = self.client.post("/tests/density", json=request_body)

        # Assert: FastAPI validation should reject the request
        self.assertEqual(response.status_code, 422)
        mock_manager.test_density.assert_not_called()

    @patch("api.routes.tests.TestsManager")
    def test_run_density_test_with_file_output(self, mock_tests_manager_cls):
        """
        The /tests/density endpoint should accept file output mode.
        """
        # Arrange: configure mock to return a job ID
        mock_manager = MagicMock()
        mock_manager.test_density.return_value = "density-file-job"
        mock_tests_manager_cls.return_value = mock_manager

        # Act: send a density test request with file output
        request_body = {
            "fps_floor": 30,
            "pipeline_density_specs": [
                {
                    "id": "pipeline-density-file",
                    "stream_rate": 100,
                }
            ],
            "execution_config": {"output_mode": "file", "max_runtime": 0},
        }
        response = self.client.post("/tests/density", json=request_body)

        # Assert: verify response
        self.assertEqual(response.status_code, 202)
        data = response.json()
        self.assertIn("job_id", data)
        self.assertEqual(data["job_id"], "density-file-job")

        # Verify manager was called with correct spec including file output
        mock_manager.test_density.assert_called_once()
        call_args = mock_manager.test_density.call_args[0][0]
        self.assertIsInstance(call_args, schemas.DensityTestSpec)
        self.assertEqual(
            call_args.execution_config.output_mode, schemas.OutputMode.FILE
        )


if __name__ == "__main__":
    unittest.main()

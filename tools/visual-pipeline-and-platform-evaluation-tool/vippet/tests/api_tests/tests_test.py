import unittest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from unittest.mock import patch

import api.api_schemas as schemas
from api.routes.tests import router as tests_router


class TestTestsAPI(unittest.TestCase):
    """
    Integration-style unit tests for the tests HTTP API.

    The tests use FastAPI's TestClient and patch the global
    ``test_manager`` object exposed by ``api.routes.tests`` so we can
    precisely control the behavior of the underlying manager without
    touching its real implementation or any background threads.

    The overall design mirrors tests/api_tests/pipelines_test.py:

    * we mount only the router we want to test on a lightweight FastAPI app,
    * we exercise the real path configuration and response models,
    * we always validate both HTTP status codes and JSON payloads.
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

    # ------------------------------------------------------------------
    # /tests/performance
    # ------------------------------------------------------------------

    @patch("api.routes.tests.test_manager")
    def test_run_performance_test_returns_job_id(self, mock_test_manager):
        """
        The /tests/performance endpoint should accept a PerformanceTestSpec
        and return a TestJobResponse with a job_id.

        This test validates:
        * HTTP 202 status (Accepted),
        * response contains job_id field,
        * test_manager.test_performance() is called with the correct spec.
        """
        # Arrange: configure mock to return a job ID
        mock_test_manager.test_performance.return_value = "test-job-123"

        # Act: send a performance test request
        request_body = {
            "pipeline_performance_specs": [
                {
                    "id": "pipeline-test123",
                    "streams": 2,
                }
            ],
            "video_output": {"enabled": False},
        }
        response = self.client.post("/tests/performance", json=request_body)

        # Assert: verify response
        self.assertEqual(response.status_code, 202)
        data = response.json()
        self.assertIn("job_id", data)
        self.assertEqual(data["job_id"], "test-job-123")

        # Verify manager was called with correct spec
        mock_test_manager.test_performance.assert_called_once()
        call_args = mock_test_manager.test_performance.call_args[0][0]
        self.assertIsInstance(call_args, schemas.PerformanceTestSpec)
        self.assertEqual(len(call_args.pipeline_performance_specs), 1)
        self.assertEqual(call_args.pipeline_performance_specs[0].id, "pipeline-test123")
        self.assertEqual(call_args.pipeline_performance_specs[0].streams, 2)

    @patch("api.routes.tests.test_manager")
    def test_run_performance_test_with_multiple_pipelines(self, mock_test_manager):
        """
        The /tests/performance endpoint should accept multiple pipeline specs
        in a single request.
        """
        # Arrange
        mock_test_manager.test_performance.return_value = "multi-job-456"

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
            "video_output": {"enabled": False},
        }
        response = self.client.post("/tests/performance", json=request_body)

        # Assert
        self.assertEqual(response.status_code, 202)
        data = response.json()
        self.assertEqual(data["job_id"], "multi-job-456")

        # Verify manager was called with correct spec
        mock_test_manager.test_performance.assert_called_once()
        call_args = mock_test_manager.test_performance.call_args[0][0]
        self.assertEqual(len(call_args.pipeline_performance_specs), 2)
        self.assertEqual(call_args.pipeline_performance_specs[0].streams, 1)
        self.assertEqual(call_args.pipeline_performance_specs[1].streams, 3)

    @patch("api.routes.tests.test_manager")
    def test_run_performance_test_with_invalid_body_returns_422(
        self, mock_test_manager
    ):
        """
        The /tests/performance endpoint should return 422 if the request body
        is invalid (e.g., missing required fields).
        """
        # Act: send request with missing pipeline_performance_specs
        request_body = {}
        response = self.client.post("/tests/performance", json=request_body)

        # Assert: FastAPI validation should reject the request
        self.assertEqual(response.status_code, 422)
        mock_test_manager.test_performance.assert_not_called()

    @patch("api.routes.tests.test_manager")
    def test_run_performance_test_with_invalid_streams_returns_422(
        self, mock_test_manager
    ):
        """
        The /tests/performance endpoint should return 422 if streams value
        is invalid (e.g., negative number).
        """
        # Act: send request with negative streams
        request_body = {
            "pipeline_performance_specs": [
                {
                    "id": "pipeline-test789",
                    "streams": -1,
                }
            ],
            "video_output": {"enabled": False},
        }
        response = self.client.post("/tests/performance", json=request_body)

        # Assert: FastAPI validation should reject the request
        self.assertEqual(response.status_code, 422)
        mock_test_manager.test_performance.assert_not_called()

    @patch("api.routes.tests.test_manager")
    def test_run_performance_test_with_gpu_encoder(self, mock_test_manager):
        """
        The /tests/performance endpoint should accept video output configuration
        with GPU encoder device.
        """
        # Arrange: configure mock to return a job ID
        mock_test_manager.test_performance.return_value = "gpu-job-456"

        # Act: send a performance test request with GPU encoder
        request_body = {
            "pipeline_performance_specs": [
                {
                    "id": "pipeline-gpu123",
                    "streams": 2,
                }
            ],
            "video_output": {
                "enabled": True,
                "encoder_device": {
                    "device_name": "GPU",
                    "gpu_id": 0,
                },
            },
        }
        response = self.client.post("/tests/performance", json=request_body)

        # Assert: verify response
        self.assertEqual(response.status_code, 202)
        data = response.json()
        self.assertIn("job_id", data)
        self.assertEqual(data["job_id"], "gpu-job-456")

        # Verify manager was called with correct spec including video output
        mock_test_manager.test_performance.assert_called_once()
        call_args = mock_test_manager.test_performance.call_args[0][0]
        self.assertIsInstance(call_args, schemas.PerformanceTestSpec)

        # Verify video output configuration
        self.assertTrue(call_args.video_output.enabled)
        self.assertEqual(call_args.video_output.encoder_device.device_name, "GPU")
        self.assertEqual(call_args.video_output.encoder_device.gpu_id, 0)

    # ------------------------------------------------------------------
    # /tests/density
    # ------------------------------------------------------------------

    @patch("api.routes.tests.test_manager")
    def test_run_density_test_returns_job_id(self, mock_test_manager):
        """
        The /tests/density endpoint should accept a DensityTestSpec
        and return a TestJobResponse with a job_id.

        This test validates:
        * HTTP 202 status (Accepted),
        * response contains job_id field,
        * test_manager.test_density() is called with the correct spec.
        """
        # Arrange: configure mock to return a job ID
        mock_test_manager.test_density.return_value = "density-job-789"

        # Act: send a density test request
        request_body = {
            "fps_floor": 30,
            "pipeline_density_specs": [
                {
                    "id": "pipeline-ghi789",
                    "stream_rate": 100,
                }
            ],
            "video_output": {"enabled": False},
        }
        response = self.client.post("/tests/density", json=request_body)

        # Assert: verify response
        self.assertEqual(response.status_code, 202)
        data = response.json()
        self.assertIn("job_id", data)
        self.assertEqual(data["job_id"], "density-job-789")

        # Verify manager was called with correct spec
        mock_test_manager.test_density.assert_called_once()
        call_args = mock_test_manager.test_density.call_args[0][0]
        self.assertIsInstance(call_args, schemas.DensityTestSpec)
        self.assertEqual(call_args.fps_floor, 30)
        self.assertEqual(len(call_args.pipeline_density_specs), 1)
        self.assertEqual(call_args.pipeline_density_specs[0].id, "pipeline-ghi789")
        self.assertEqual(call_args.pipeline_density_specs[0].stream_rate, 100)

    @patch("api.routes.tests.test_manager")
    def test_run_density_test_with_multiple_pipelines(self, mock_test_manager):
        """
        The /tests/density endpoint should accept multiple pipeline specs
        in a single request.
        """
        # Arrange
        mock_test_manager.test_density.return_value = "density-multi-999"

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
                    "stream_rate": 75,
                },
            ],
            "video_output": {"enabled": False},
        }
        response = self.client.post("/tests/density", json=request_body)

        # Assert
        self.assertEqual(response.status_code, 202)
        data = response.json()
        self.assertEqual(data["job_id"], "density-multi-999")

        # Verify manager was called with correct spec
        mock_test_manager.test_density.assert_called_once()
        call_args = mock_test_manager.test_density.call_args[0][0]
        self.assertEqual(call_args.fps_floor, 25)
        self.assertEqual(len(call_args.pipeline_density_specs), 2)
        self.assertEqual(call_args.pipeline_density_specs[0].stream_rate, 50)
        self.assertEqual(call_args.pipeline_density_specs[1].stream_rate, 75)

    @patch("api.routes.tests.test_manager")
    def test_run_density_test_with_invalid_body_returns_422(self, mock_test_manager):
        """
        The /tests/density endpoint should return 422 if the request body
        is invalid (e.g., missing required fields).
        """
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
        mock_test_manager.test_density.assert_not_called()

    @patch("api.routes.tests.test_manager")
    def test_run_density_test_with_invalid_fps_floor_returns_422(
        self, mock_test_manager
    ):
        """
        The /tests/density endpoint should return 422 if fps_floor value
        is invalid (e.g., negative number).
        """
        # Act: send request with negative fps_floor
        request_body = {
            "fps_floor": -10,
            "pipeline_density_specs": [
                {
                    "id": "pipeline-stu901",
                    "stream_rate": 100,
                }
            ],
            "video_output": {"enabled": False},
        }
        response = self.client.post("/tests/density", json=request_body)

        # Assert: FastAPI validation should reject the request
        self.assertEqual(response.status_code, 422)
        mock_test_manager.test_density.assert_not_called()

    @patch("api.routes.tests.test_manager")
    def test_run_density_test_with_invalid_stream_rate_returns_422(
        self, mock_test_manager
    ):
        """
        The /tests/density endpoint should return 422 if stream_rate value
        is invalid (e.g., negative number).
        """
        # Act: send request with negative stream_rate
        request_body = {
            "fps_floor": 30,
            "pipeline_density_specs": [
                {
                    "id": "pipeline-vwx234",
                    "stream_rate": -50,
                }
            ],
            "video_output": {"enabled": False},
        }
        response = self.client.post("/tests/density", json=request_body)

        # Assert: FastAPI validation should reject the request
        self.assertEqual(response.status_code, 422)
        mock_test_manager.test_density.assert_not_called()


if __name__ == "__main__":
    unittest.main()

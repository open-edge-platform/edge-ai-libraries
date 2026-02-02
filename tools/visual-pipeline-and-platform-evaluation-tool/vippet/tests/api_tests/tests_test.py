import unittest
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

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
    # /tests/performance - Variant Reference
    # ------------------------------------------------------------------

    @patch("api.routes.tests.test_manager")
    def test_run_performance_test_with_variant_reference_returns_job_id(
        self, mock_test_manager
    ):
        """
        The /tests/performance endpoint should accept a PerformanceTestSpec
        with variant reference and return a TestJobResponse with a job_id.

        This test validates:
        * HTTP 202 status (Accepted),
        * response contains job_id field,
        * test_manager.test_performance() is called with the correct spec.
        """
        # Arrange: configure mock to return a job ID
        mock_test_manager.test_performance.return_value = "test-job-123"

        # Act: send a performance test request with variant reference
        request_body = {
            "pipeline_performance_specs": [
                {
                    "pipeline": {
                        "source": "variant",
                        "pipeline_id": "pipeline-test123",
                        "variant_id": "variant-abc123",
                    },
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
        mock_test_manager.test_performance.assert_called_once()
        call_args = mock_test_manager.test_performance.call_args[0][0]
        self.assertIsInstance(call_args, schemas.PerformanceTestSpec)
        self.assertEqual(len(call_args.pipeline_performance_specs), 1)

        # Verify the pipeline is a VariantReference
        pipeline_spec = call_args.pipeline_performance_specs[0]
        self.assertIsInstance(pipeline_spec.pipeline, schemas.VariantReference)
        self.assertEqual(pipeline_spec.pipeline.pipeline_id, "pipeline-test123")
        self.assertEqual(pipeline_spec.pipeline.variant_id, "variant-abc123")
        self.assertEqual(pipeline_spec.streams, 2)

    @patch("api.routes.tests.test_manager")
    def test_run_performance_test_with_inline_graph_returns_job_id(
        self, mock_test_manager
    ):
        """
        The /tests/performance endpoint should accept a PerformanceTestSpec
        with inline graph and return a TestJobResponse with a job_id.
        """
        # Arrange: configure mock to return a job ID
        mock_test_manager.test_performance.return_value = "graph-job-456"

        # Act: send a performance test request with inline graph
        request_body = {
            "pipeline_performance_specs": [
                {
                    "pipeline": {
                        "source": "graph",
                        "pipeline_graph": {
                            "nodes": [
                                {
                                    "id": "0",
                                    "type": "filesrc",
                                    "data": {"location": "/videos/test.mp4"},
                                },
                                {"id": "1", "type": "decodebin", "data": {}},
                                {"id": "2", "type": "fakesink", "data": {}},
                            ],
                            "edges": [
                                {"id": "0", "source": "0", "target": "1"},
                                {"id": "1", "source": "1", "target": "2"},
                            ],
                        },
                    },
                    "streams": 4,
                }
            ],
            "execution_config": {"output_mode": "disabled", "max_runtime": 0},
        }
        response = self.client.post("/tests/performance", json=request_body)

        # Assert: verify response
        self.assertEqual(response.status_code, 202)
        data = response.json()
        self.assertIn("job_id", data)
        self.assertEqual(data["job_id"], "graph-job-456")

        # Verify manager was called with correct spec
        mock_test_manager.test_performance.assert_called_once()
        call_args = mock_test_manager.test_performance.call_args[0][0]
        self.assertIsInstance(call_args, schemas.PerformanceTestSpec)

        # Verify the pipeline is a GraphInline
        pipeline_spec = call_args.pipeline_performance_specs[0]
        self.assertIsInstance(pipeline_spec.pipeline, schemas.GraphInline)
        self.assertIsNotNone(pipeline_spec.pipeline.pipeline_graph)
        self.assertEqual(pipeline_spec.streams, 4)

    @patch("api.routes.tests.test_manager")
    def test_run_performance_test_with_multiple_pipelines(self, mock_test_manager):
        """
        The /tests/performance endpoint should accept multiple pipeline specs
        in a single request with mixed sources (variant + inline graph).
        """
        # Arrange
        mock_test_manager.test_performance.return_value = "multi-job-456"

        # Act: send request with multiple pipeline specs (mixed sources)
        request_body = {
            "pipeline_performance_specs": [
                {
                    "pipeline": {
                        "source": "variant",
                        "pipeline_id": "pipeline-abc123",
                        "variant_id": "variant-cpu",
                    },
                    "streams": 1,
                },
                {
                    "pipeline": {
                        "source": "graph",
                        "pipeline_graph": {
                            "nodes": [
                                {
                                    "id": "0",
                                    "type": "filesrc",
                                    "data": {"location": "/videos/test.mp4"},
                                },
                                {"id": "1", "type": "fakesink", "data": {}},
                            ],
                            "edges": [{"id": "0", "source": "0", "target": "1"}],
                        },
                    },
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
        mock_test_manager.test_performance.assert_called_once()
        call_args = mock_test_manager.test_performance.call_args[0][0]
        self.assertEqual(len(call_args.pipeline_performance_specs), 2)

        # First spec should be variant reference
        self.assertIsInstance(
            call_args.pipeline_performance_specs[0].pipeline, schemas.VariantReference
        )
        self.assertEqual(call_args.pipeline_performance_specs[0].streams, 1)

        # Second spec should be inline graph
        self.assertIsInstance(
            call_args.pipeline_performance_specs[1].pipeline, schemas.GraphInline
        )
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
                    "pipeline": {
                        "source": "variant",
                        "pipeline_id": "pipeline-test789",
                        "variant_id": "variant-cpu",
                    },
                    "streams": -1,
                }
            ],
            "execution_config": {"output_mode": "disabled", "max_runtime": 0},
        }
        response = self.client.post("/tests/performance", json=request_body)

        # Assert: FastAPI validation should reject the request
        self.assertEqual(response.status_code, 422)
        mock_test_manager.test_performance.assert_not_called()

    @patch("api.routes.tests.test_manager")
    def test_run_performance_test_with_invalid_source_returns_422(
        self, mock_test_manager
    ):
        """
        The /tests/performance endpoint should return 422 if pipeline source
        is invalid (not 'variant' or 'graph').
        """
        # Act: send request with invalid source
        request_body = {
            "pipeline_performance_specs": [
                {
                    "pipeline": {
                        "source": "invalid_source",
                        "pipeline_id": "pipeline-test",
                    },
                    "streams": 1,
                }
            ],
            "execution_config": {"output_mode": "disabled", "max_runtime": 0},
        }
        response = self.client.post("/tests/performance", json=request_body)

        # Assert: FastAPI validation should reject the request
        self.assertEqual(response.status_code, 422)
        mock_test_manager.test_performance.assert_not_called()

    @patch("api.routes.tests.test_manager")
    def test_run_performance_test_with_file_output(self, mock_test_manager):
        """
        The /tests/performance endpoint should accept execution_config
        with file output mode.
        """
        # Arrange: configure mock to return a job ID
        mock_test_manager.test_performance.return_value = "file-job-456"

        # Act: send a performance test request with file output
        request_body = {
            "pipeline_performance_specs": [
                {
                    "pipeline": {
                        "source": "variant",
                        "pipeline_id": "pipeline-file123",
                        "variant_id": "variant-cpu",
                    },
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
        mock_test_manager.test_performance.assert_called_once()
        call_args = mock_test_manager.test_performance.call_args[0][0]
        self.assertIsInstance(call_args, schemas.PerformanceTestSpec)
        self.assertEqual(
            call_args.execution_config.output_mode, schemas.OutputMode.FILE
        )
        self.assertEqual(call_args.execution_config.max_runtime, 0)

    @patch("api.routes.tests.test_manager")
    def test_run_performance_test_with_live_stream_output(self, mock_test_manager):
        """
        The /tests/performance endpoint should accept execution_config
        with live_stream output mode.
        """
        # Arrange: configure mock to return a job ID
        mock_test_manager.test_performance.return_value = "stream-job-789"

        # Act: send a performance test request with live_stream output
        request_body = {
            "pipeline_performance_specs": [
                {
                    "pipeline": {
                        "source": "variant",
                        "pipeline_id": "pipeline-stream123",
                        "variant_id": "variant-gpu",
                    },
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
        mock_test_manager.test_performance.assert_called_once()
        call_args = mock_test_manager.test_performance.call_args[0][0]
        self.assertEqual(
            call_args.execution_config.output_mode, schemas.OutputMode.LIVE_STREAM
        )
        self.assertEqual(call_args.execution_config.max_runtime, 60)

    @patch("api.routes.tests.test_manager")
    def test_run_performance_test_with_max_runtime(self, mock_test_manager):
        """
        The /tests/performance endpoint should accept execution_config
        with max_runtime for time-limited execution.
        """
        # Arrange: configure mock to return a job ID
        mock_test_manager.test_performance.return_value = "runtime-job-999"

        # Act: send a performance test request with max_runtime
        request_body = {
            "pipeline_performance_specs": [
                {
                    "pipeline": {
                        "source": "variant",
                        "pipeline_id": "pipeline-runtime123",
                        "variant_id": "variant-npu",
                    },
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
        mock_test_manager.test_performance.assert_called_once()
        call_args = mock_test_manager.test_performance.call_args[0][0]
        self.assertEqual(
            call_args.execution_config.output_mode, schemas.OutputMode.DISABLED
        )
        self.assertEqual(call_args.execution_config.max_runtime, 120)

    @patch("api.routes.tests.test_manager")
    def test_run_performance_test_manager_raises_value_error_returns_400(
        self, mock_test_manager
    ):
        """
        The /tests/performance endpoint should return 400 if test_manager
        raises ValueError (e.g., variant not found).
        """
        # Arrange: configure mock to raise ValueError
        mock_test_manager.test_performance.side_effect = ValueError(
            "Variant 'variant-unknown' not found in pipeline 'pipeline-abc'."
        )

        # Act: send a valid request
        request_body = {
            "pipeline_performance_specs": [
                {
                    "pipeline": {
                        "source": "variant",
                        "pipeline_id": "pipeline-abc",
                        "variant_id": "variant-unknown",
                    },
                    "streams": 1,
                }
            ],
            "execution_config": {"output_mode": "disabled", "max_runtime": 0},
        }
        response = self.client.post("/tests/performance", json=request_body)

        # Assert: should return 400 with error message
        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertIn("message", data)
        self.assertIn("not found", data["message"])

    @patch("api.routes.tests.test_manager")
    def test_run_performance_test_manager_raises_exception_returns_500(
        self, mock_test_manager
    ):
        """
        The /tests/performance endpoint should return 500 if test_manager
        raises an unexpected exception.
        """
        # Arrange: configure mock to raise RuntimeError
        mock_test_manager.test_performance.side_effect = RuntimeError(
            "Unexpected error"
        )

        # Act: send a valid request
        request_body = {
            "pipeline_performance_specs": [
                {
                    "pipeline": {
                        "source": "variant",
                        "pipeline_id": "pipeline-abc",
                        "variant_id": "variant-cpu",
                    },
                    "streams": 1,
                }
            ],
            "execution_config": {"output_mode": "disabled", "max_runtime": 0},
        }
        response = self.client.post("/tests/performance", json=request_body)

        # Assert: should return 500 with error message
        self.assertEqual(response.status_code, 500)
        data = response.json()
        self.assertIn("message", data)

    # ------------------------------------------------------------------
    # /tests/density - Variant Reference
    # ------------------------------------------------------------------

    @patch("api.routes.tests.test_manager")
    def test_run_density_test_with_variant_reference_returns_job_id(
        self, mock_test_manager
    ):
        """
        The /tests/density endpoint should accept a DensityTestSpec
        with variant reference and return a TestJobResponse with a job_id.

        This test validates:
        * HTTP 202 status (Accepted),
        * response contains job_id field,
        * test_manager.test_density() is called with the correct spec.
        """
        # Arrange: configure mock to return a job ID
        mock_test_manager.test_density.return_value = "density-job-789"

        # Act: send a density test request with variant reference
        request_body = {
            "fps_floor": 30,
            "pipeline_density_specs": [
                {
                    "pipeline": {
                        "source": "variant",
                        "pipeline_id": "pipeline-ghi789",
                        "variant_id": "variant-cpu",
                    },
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
        mock_test_manager.test_density.assert_called_once()
        call_args = mock_test_manager.test_density.call_args[0][0]
        self.assertIsInstance(call_args, schemas.DensityTestSpec)
        self.assertEqual(call_args.fps_floor, 30)
        self.assertEqual(len(call_args.pipeline_density_specs), 1)

        # Verify the pipeline is a VariantReference
        pipeline_spec = call_args.pipeline_density_specs[0]
        self.assertIsInstance(pipeline_spec.pipeline, schemas.VariantReference)
        self.assertEqual(pipeline_spec.pipeline.pipeline_id, "pipeline-ghi789")
        self.assertEqual(pipeline_spec.pipeline.variant_id, "variant-cpu")
        self.assertEqual(pipeline_spec.stream_rate, 100)

    @patch("api.routes.tests.test_manager")
    def test_run_density_test_with_inline_graph_returns_job_id(self, mock_test_manager):
        """
        The /tests/density endpoint should accept a DensityTestSpec
        with inline graph and return a TestJobResponse with a job_id.
        """
        # Arrange: configure mock to return a job ID
        mock_test_manager.test_density.return_value = "density-graph-job"

        # Act: send a density test request with inline graph
        request_body = {
            "fps_floor": 25,
            "pipeline_density_specs": [
                {
                    "pipeline": {
                        "source": "graph",
                        "pipeline_graph": {
                            "nodes": [
                                {
                                    "id": "0",
                                    "type": "filesrc",
                                    "data": {"location": "/videos/test.mp4"},
                                },
                                {"id": "1", "type": "decodebin", "data": {}},
                                {"id": "2", "type": "fakesink", "data": {}},
                            ],
                            "edges": [
                                {"id": "0", "source": "0", "target": "1"},
                                {"id": "1", "source": "1", "target": "2"},
                            ],
                        },
                    },
                    "stream_rate": 100,
                }
            ],
            "execution_config": {"output_mode": "disabled", "max_runtime": 0},
        }
        response = self.client.post("/tests/density", json=request_body)

        # Assert: verify response
        self.assertEqual(response.status_code, 202)
        data = response.json()
        self.assertEqual(data["job_id"], "density-graph-job")

        # Verify the pipeline is a GraphInline
        call_args = mock_test_manager.test_density.call_args[0][0]
        pipeline_spec = call_args.pipeline_density_specs[0]
        self.assertIsInstance(pipeline_spec.pipeline, schemas.GraphInline)
        self.assertIsNotNone(pipeline_spec.pipeline.pipeline_graph)

    @patch("api.routes.tests.test_manager")
    def test_run_density_test_with_multiple_pipelines(self, mock_test_manager):
        """
        The /tests/density endpoint should accept multiple pipeline specs
        in a single request with stream_rate values summing to 100.
        """
        # Arrange
        mock_test_manager.test_density.return_value = "density-multi-999"

        # Act: send request with multiple pipeline specs
        request_body = {
            "fps_floor": 25,
            "pipeline_density_specs": [
                {
                    "pipeline": {
                        "source": "variant",
                        "pipeline_id": "pipeline-jkl012",
                        "variant_id": "variant-cpu",
                    },
                    "stream_rate": 50,
                },
                {
                    "pipeline": {
                        "source": "variant",
                        "pipeline_id": "pipeline-mno345",
                        "variant_id": "variant-gpu",
                    },
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
        mock_test_manager.test_density.assert_called_once()
        call_args = mock_test_manager.test_density.call_args[0][0]
        self.assertEqual(call_args.fps_floor, 25)
        self.assertEqual(len(call_args.pipeline_density_specs), 2)
        self.assertEqual(call_args.pipeline_density_specs[0].stream_rate, 50)
        self.assertEqual(call_args.pipeline_density_specs[1].stream_rate, 50)

    @patch("api.routes.tests.test_manager")
    def test_run_density_test_with_mixed_sources(self, mock_test_manager):
        """
        The /tests/density endpoint should accept mixed pipeline sources
        (variant reference + inline graph) in a single request.
        """
        # Arrange
        mock_test_manager.test_density.return_value = "density-mixed-job"

        # Act: send request with mixed pipeline sources
        request_body = {
            "fps_floor": 30,
            "pipeline_density_specs": [
                {
                    "pipeline": {
                        "source": "variant",
                        "pipeline_id": "pipeline-abc",
                        "variant_id": "variant-cpu",
                    },
                    "stream_rate": 60,
                },
                {
                    "pipeline": {
                        "source": "graph",
                        "pipeline_graph": {
                            "nodes": [
                                {
                                    "id": "0",
                                    "type": "filesrc",
                                    "data": {"location": "/videos/test.mp4"},
                                },
                                {"id": "1", "type": "fakesink", "data": {}},
                            ],
                            "edges": [{"id": "0", "source": "0", "target": "1"}],
                        },
                    },
                    "stream_rate": 40,
                },
            ],
            "execution_config": {"output_mode": "disabled", "max_runtime": 0},
        }
        response = self.client.post("/tests/density", json=request_body)

        # Assert
        self.assertEqual(response.status_code, 202)
        data = response.json()
        self.assertEqual(data["job_id"], "density-mixed-job")

        # Verify mixed sources
        call_args = mock_test_manager.test_density.call_args[0][0]
        self.assertIsInstance(
            call_args.pipeline_density_specs[0].pipeline, schemas.VariantReference
        )
        self.assertIsInstance(
            call_args.pipeline_density_specs[1].pipeline, schemas.GraphInline
        )

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
                    "pipeline": {
                        "source": "variant",
                        "pipeline_id": "pipeline-pqr678",
                        "variant_id": "variant-cpu",
                    },
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
                    "pipeline": {
                        "source": "variant",
                        "pipeline_id": "pipeline-stu901",
                        "variant_id": "variant-cpu",
                    },
                    "stream_rate": 100,
                }
            ],
            "execution_config": {"output_mode": "disabled", "max_runtime": 0},
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
                    "pipeline": {
                        "source": "variant",
                        "pipeline_id": "pipeline-vwx234",
                        "variant_id": "variant-cpu",
                    },
                    "stream_rate": -50,
                }
            ],
            "execution_config": {"output_mode": "disabled", "max_runtime": 0},
        }
        response = self.client.post("/tests/density", json=request_body)

        # Assert: FastAPI validation should reject the request
        self.assertEqual(response.status_code, 422)
        mock_test_manager.test_density.assert_not_called()

    @patch("api.routes.tests.test_manager")
    def test_run_density_test_with_file_output(self, mock_test_manager):
        """
        The /tests/density endpoint should accept file output mode.
        """
        # Arrange: configure mock to return a job ID
        mock_test_manager.test_density.return_value = "density-file-job"

        # Act: send a density test request with file output
        request_body = {
            "fps_floor": 30,
            "pipeline_density_specs": [
                {
                    "pipeline": {
                        "source": "variant",
                        "pipeline_id": "pipeline-density-file",
                        "variant_id": "variant-cpu",
                    },
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
        mock_test_manager.test_density.assert_called_once()
        call_args = mock_test_manager.test_density.call_args[0][0]
        self.assertIsInstance(call_args, schemas.DensityTestSpec)
        self.assertEqual(
            call_args.execution_config.output_mode, schemas.OutputMode.FILE
        )

    @patch("api.routes.tests.test_manager")
    def test_run_density_test_manager_raises_value_error_returns_400(
        self, mock_test_manager
    ):
        """
        The /tests/density endpoint should return 400 if test_manager
        raises ValueError (e.g., stream_rate doesn't sum to 100).
        """
        # Arrange: configure mock to raise ValueError
        mock_test_manager.test_density.side_effect = ValueError(
            "Pipeline stream_rate ratios must sum to 100%, got 110%"
        )

        # Act: send a valid request
        request_body = {
            "fps_floor": 30,
            "pipeline_density_specs": [
                {
                    "pipeline": {
                        "source": "variant",
                        "pipeline_id": "pipeline-abc",
                        "variant_id": "variant-cpu",
                    },
                    "stream_rate": 60,
                },
                {
                    "pipeline": {
                        "source": "variant",
                        "pipeline_id": "pipeline-def",
                        "variant_id": "variant-gpu",
                    },
                    "stream_rate": 50,
                },
            ],
            "execution_config": {"output_mode": "disabled", "max_runtime": 0},
        }
        response = self.client.post("/tests/density", json=request_body)

        # Assert: should return 400 with error message
        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertIn("message", data)
        self.assertIn("100%", data["message"])

    @patch("api.routes.tests.test_manager")
    def test_run_density_test_manager_raises_exception_returns_500(
        self, mock_test_manager
    ):
        """
        The /tests/density endpoint should return 500 if test_manager
        raises an unexpected exception.
        """
        # Arrange: configure mock to raise RuntimeError
        mock_test_manager.test_density.side_effect = RuntimeError("Unexpected error")

        # Act: send a valid request
        request_body = {
            "fps_floor": 30,
            "pipeline_density_specs": [
                {
                    "pipeline": {
                        "source": "variant",
                        "pipeline_id": "pipeline-abc",
                        "variant_id": "variant-cpu",
                    },
                    "stream_rate": 100,
                }
            ],
            "execution_config": {"output_mode": "disabled", "max_runtime": 0},
        }
        response = self.client.post("/tests/density", json=request_body)

        # Assert: should return 500 with error message
        self.assertEqual(response.status_code, 500)
        data = response.json()
        self.assertIn("message", data)

    # ------------------------------------------------------------------
    # Schema validation tests
    # ------------------------------------------------------------------

    def test_variant_reference_source_discriminator(self):
        """
        VariantReference should have source='variant' as discriminator.
        """
        ref = schemas.VariantReference(
            pipeline_id="pipeline-abc", variant_id="variant-123"
        )
        self.assertEqual(ref.source, "variant")
        self.assertEqual(ref.pipeline_id, "pipeline-abc")
        self.assertEqual(ref.variant_id, "variant-123")

    def test_graph_inline_source_discriminator(self):
        """
        GraphInline should have source='graph' as discriminator.
        """
        graph = schemas.PipelineGraph(
            nodes=[
                schemas.Node(id="0", type="filesrc", data={"location": "/test.mp4"}),
                schemas.Node(id="1", type="fakesink", data={}),
            ],
            edges=[schemas.Edge(id="0", source="0", target="1")],
        )
        inline = schemas.GraphInline(pipeline_graph=graph)
        self.assertEqual(inline.source, "graph")
        self.assertIsNotNone(inline.pipeline_graph)

    def test_pipeline_performance_spec_with_variant_reference(self):
        """
        PipelinePerformanceSpec should accept VariantReference.
        """
        ref = schemas.VariantReference(
            pipeline_id="pipeline-abc", variant_id="variant-123"
        )
        spec = schemas.PipelinePerformanceSpec(pipeline=ref, streams=4)
        self.assertIsInstance(spec.pipeline, schemas.VariantReference)
        self.assertEqual(spec.streams, 4)

    def test_pipeline_performance_spec_with_graph_inline(self):
        """
        PipelinePerformanceSpec should accept GraphInline.
        """
        graph = schemas.PipelineGraph(
            nodes=[
                schemas.Node(id="0", type="filesrc", data={"location": "/test.mp4"}),
                schemas.Node(id="1", type="fakesink", data={}),
            ],
            edges=[schemas.Edge(id="0", source="0", target="1")],
        )
        inline = schemas.GraphInline(pipeline_graph=graph)
        spec = schemas.PipelinePerformanceSpec(pipeline=inline, streams=2)
        self.assertIsInstance(spec.pipeline, schemas.GraphInline)
        self.assertEqual(spec.streams, 2)

    def test_pipeline_density_spec_with_variant_reference(self):
        """
        PipelineDensitySpec should accept VariantReference.
        """
        ref = schemas.VariantReference(
            pipeline_id="pipeline-abc", variant_id="variant-123"
        )
        spec = schemas.PipelineDensitySpec(pipeline=ref, stream_rate=50)
        self.assertIsInstance(spec.pipeline, schemas.VariantReference)
        self.assertEqual(spec.stream_rate, 50)

    def test_pipeline_density_spec_with_graph_inline(self):
        """
        PipelineDensitySpec should accept GraphInline.
        """
        graph = schemas.PipelineGraph(
            nodes=[
                schemas.Node(id="0", type="filesrc", data={"location": "/test.mp4"}),
                schemas.Node(id="1", type="fakesink", data={}),
            ],
            edges=[schemas.Edge(id="0", source="0", target="1")],
        )
        inline = schemas.GraphInline(pipeline_graph=graph)
        spec = schemas.PipelineDensitySpec(pipeline=inline, stream_rate=100)
        self.assertIsInstance(spec.pipeline, schemas.GraphInline)
        self.assertEqual(spec.stream_rate, 100)

    def test_pipeline_stream_spec_variant_path_format(self):
        """
        PipelineStreamSpec should accept variant path format for ID.
        """
        spec = schemas.PipelineStreamSpec(
            id="/pipelines/pipeline-abc/variants/variant-123", streams=4
        )
        self.assertTrue(spec.id.startswith("/pipelines/"))
        self.assertIn("/variants/", spec.id)
        self.assertEqual(spec.streams, 4)

    def test_pipeline_stream_spec_graph_hash_format(self):
        """
        PipelineStreamSpec should accept __graph-{hash} format for ID.
        """
        spec = schemas.PipelineStreamSpec(id="__graph-abcd1234efgh5678", streams=2)
        self.assertTrue(spec.id.startswith("__graph-"))
        self.assertEqual(spec.streams, 2)

    def test_execution_config_defaults(self):
        """
        ExecutionConfig should have correct default values.
        """
        config = schemas.ExecutionConfig()
        self.assertEqual(config.output_mode, schemas.OutputMode.DISABLED)
        self.assertEqual(config.max_runtime, 0.0)

    def test_execution_config_file_mode(self):
        """
        ExecutionConfig should accept file output mode.
        """
        config = schemas.ExecutionConfig(
            output_mode=schemas.OutputMode.FILE, max_runtime=0
        )
        self.assertEqual(config.output_mode, schemas.OutputMode.FILE)

    def test_execution_config_live_stream_mode(self):
        """
        ExecutionConfig should accept live_stream output mode.
        """
        config = schemas.ExecutionConfig(
            output_mode=schemas.OutputMode.LIVE_STREAM, max_runtime=60
        )
        self.assertEqual(config.output_mode, schemas.OutputMode.LIVE_STREAM)
        self.assertEqual(config.max_runtime, 60)


if __name__ == "__main__":
    unittest.main()

import unittest
from unittest.mock import patch, MagicMock

from fastapi import FastAPI
from fastapi.testclient import TestClient

import api.api_schemas as schemas
from api.routes.tests import router as tests_router
from internal_types import InternalPerformanceTestSpec, InternalDensityTestSpec
from managers.tests_manager import TestsManager
from managers.pipeline_manager import PipelineManager


def create_mock_pipeline(pipeline_id: str, name: str = "Test Pipeline"):
    """Helper to create a mock Pipeline object."""
    mock_pipeline = MagicMock()
    mock_pipeline.id = pipeline_id
    mock_pipeline.name = name
    return mock_pipeline


def create_mock_variant(variant_id: str):
    """Helper to create a mock Variant object with pipeline_graph."""
    mock_variant = MagicMock()
    mock_variant.id = variant_id
    mock_variant.pipeline_graph = MagicMock()
    mock_variant.pipeline_graph.model_dump.return_value = {
        "nodes": [
            {"id": "0", "type": "fakesrc", "data": {}},
            {"id": "1", "type": "fakesink", "data": {}},
        ],
        "edges": [{"id": "0", "source": "0", "target": "1"}],
    }
    return mock_variant


class TestTestsAPI(unittest.TestCase):
    """
    Integration-style unit tests for the tests HTTP API.

    The tests use FastAPI's TestClient and patch the TestsManager and
    PipelineManager singletons so we can precisely control the behavior
    of the underlying managers without touching their real implementations
    or any background threads.

    Note: Since the route layer now converts API types to internal types,
    we need to mock PipelineManager for variant resolution and TestsManager
    for job creation.
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
    # /tests/performance - Variant Reference
    # ------------------------------------------------------------------

    @patch("api.routes.tests.PipelineManager")
    @patch("api.routes.tests.TestsManager")
    def test_run_performance_test_returns_job_id(
        self, mock_tests_manager_cls, mock_pipeline_manager_cls
    ):
        """
        The /tests/performance endpoint should accept a PerformanceTestSpec
        with variant reference and return a TestJobResponse with a job_id.

        This test validates:
        * HTTP 202 status (Accepted),
        * response contains job_id field,
        * test_manager.test_performance() is called with InternalPerformanceTestSpec.
        """
        # Arrange: configure mocks
        mock_pipeline_manager = MagicMock()
        mock_pipeline_manager.get_pipeline_by_id.return_value = create_mock_pipeline(
            "pipeline-test123", "Test Pipeline"
        )
        mock_pipeline_manager.get_variant_by_ids.return_value = create_mock_variant(
            "variant-abc123"
        )
        mock_pipeline_manager_cls.return_value = mock_pipeline_manager

        mock_tests_manager = MagicMock()
        mock_tests_manager.test_performance.return_value = "test-job-123"
        mock_tests_manager_cls.return_value = mock_tests_manager

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

        # Verify manager was called with InternalPerformanceTestSpec
        mock_tests_manager.test_performance.assert_called_once()
        call_args = mock_tests_manager.test_performance.call_args[0][0]
        self.assertIsInstance(call_args, InternalPerformanceTestSpec)
        self.assertEqual(len(call_args.pipeline_performance_specs), 1)

        # Verify the internal spec has resolved pipeline information
        internal_spec = call_args.pipeline_performance_specs[0]
        self.assertEqual(
            internal_spec.pipeline_id,
            "/pipelines/pipeline-test123/variants/variant-abc123",
        )
        self.assertEqual(internal_spec.pipeline_name, "Test Pipeline")
        self.assertEqual(internal_spec.streams, 2)

        # Verify original_request is stored
        self.assertIn("pipeline_performance_specs", call_args.original_request)

    @patch("api.routes.tests.PipelineManager")
    @patch("api.routes.tests.TestsManager")
    def test_run_performance_test_with_inline_graph_returns_job_id(
        self, mock_tests_manager_cls, mock_pipeline_manager_cls
    ):
        """
        The /tests/performance endpoint should accept a PerformanceTestSpec
        with inline graph (no graph_id) and return a TestJobResponse with a job_id.
        """
        # Arrange: configure mocks (PipelineManager not needed for inline graphs)
        mock_pipeline_manager_cls.return_value = MagicMock()

        mock_tests_manager = MagicMock()
        mock_tests_manager.test_performance.return_value = "graph-job-456"
        mock_tests_manager_cls.return_value = mock_tests_manager

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

        # Verify manager was called with InternalPerformanceTestSpec
        mock_tests_manager.test_performance.assert_called_once()
        call_args = mock_tests_manager.test_performance.call_args[0][0]
        self.assertIsInstance(call_args, InternalPerformanceTestSpec)

        # Verify the internal spec has generated hash-based ID (starts with __graph-)
        internal_spec = call_args.pipeline_performance_specs[0]
        self.assertTrue(internal_spec.pipeline_id.startswith("__graph-"))
        self.assertEqual(internal_spec.streams, 4)

    @patch("api.routes.tests.PipelineManager")
    @patch("api.routes.tests.TestsManager")
    def test_run_performance_test_with_inline_graph_custom_graph_id(
        self, mock_tests_manager_cls, mock_pipeline_manager_cls
    ):
        """
        The /tests/performance endpoint should accept inline graph with
        custom graph_id and use it as pipeline_id.
        """
        # Arrange
        mock_pipeline_manager_cls.return_value = MagicMock()

        mock_tests_manager = MagicMock()
        mock_tests_manager.test_performance.return_value = "custom-id-job"
        mock_tests_manager_cls.return_value = mock_tests_manager

        # Act: send request with custom graph_id
        request_body = {
            "pipeline_performance_specs": [
                {
                    "pipeline": {
                        "source": "graph",
                        "graph_id": "my-custom-pipeline",
                        "pipeline_graph": {
                            "nodes": [
                                {"id": "0", "type": "filesrc", "data": {}},
                                {"id": "1", "type": "fakesink", "data": {}},
                            ],
                            "edges": [{"id": "0", "source": "0", "target": "1"}],
                        },
                    },
                    "streams": 2,
                }
            ],
            "execution_config": {"output_mode": "disabled", "max_runtime": 0},
        }
        response = self.client.post("/tests/performance", json=request_body)

        # Assert
        self.assertEqual(response.status_code, 202)

        # Verify custom graph_id is used as pipeline_id
        call_args = mock_tests_manager.test_performance.call_args[0][0]
        internal_spec = call_args.pipeline_performance_specs[0]
        self.assertEqual(internal_spec.pipeline_id, "my-custom-pipeline")
        self.assertEqual(internal_spec.pipeline_name, "my-custom-pipeline")

    @patch("api.routes.tests.PipelineManager")
    @patch("api.routes.tests.TestsManager")
    def test_run_performance_test_with_empty_graph_id_returns_400(
        self, mock_tests_manager_cls, mock_pipeline_manager_cls
    ):
        """
        The /tests/performance endpoint should return 400 if graph_id
        is empty after trim.
        """
        # Arrange
        mock_pipeline_manager_cls.return_value = MagicMock()
        mock_tests_manager_cls.return_value = MagicMock()

        # Act: send request with empty graph_id (whitespace only)
        request_body = {
            "pipeline_performance_specs": [
                {
                    "pipeline": {
                        "source": "graph",
                        "graph_id": "   ",
                        "pipeline_graph": {
                            "nodes": [{"id": "0", "type": "fakesrc", "data": {}}],
                            "edges": [],
                        },
                    },
                    "streams": 1,
                }
            ],
            "execution_config": {"output_mode": "disabled", "max_runtime": 0},
        }
        response = self.client.post("/tests/performance", json=request_body)

        # Assert
        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertIn("message", data)
        self.assertIn("empty", data["message"].lower())

    @patch("api.routes.tests.PipelineManager")
    @patch("api.routes.tests.TestsManager")
    def test_run_performance_test_with_invalid_graph_id_chars_returns_400(
        self, mock_tests_manager_cls, mock_pipeline_manager_cls
    ):
        """
        The /tests/performance endpoint should return 400 if graph_id
        contains characters that are not URL-safe.
        """
        # Arrange
        mock_pipeline_manager_cls.return_value = MagicMock()
        mock_tests_manager_cls.return_value = MagicMock()

        # Act: send request with invalid graph_id (contains uppercase and spaces)
        request_body = {
            "pipeline_performance_specs": [
                {
                    "pipeline": {
                        "source": "graph",
                        "graph_id": "My Pipeline ID",
                        "pipeline_graph": {
                            "nodes": [{"id": "0", "type": "fakesrc", "data": {}}],
                            "edges": [],
                        },
                    },
                    "streams": 1,
                }
            ],
            "execution_config": {"output_mode": "disabled", "max_runtime": 0},
        }
        response = self.client.post("/tests/performance", json=request_body)

        # Assert
        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertIn("message", data)
        self.assertIn("URL", data["message"])

    @patch("api.routes.tests.PipelineManager")
    @patch("api.routes.tests.TestsManager")
    def test_run_performance_test_with_multiple_pipelines(
        self, mock_tests_manager_cls, mock_pipeline_manager_cls
    ):
        """
        The /tests/performance endpoint should accept multiple pipeline specs
        in a single request with mixed sources (variant + inline graph).
        """
        # Arrange
        mock_pipeline_manager = MagicMock()
        mock_pipeline_manager.get_pipeline_by_id.return_value = create_mock_pipeline(
            "pipeline-abc123", "Pipeline ABC"
        )
        mock_pipeline_manager.get_variant_by_ids.return_value = create_mock_variant(
            "variant-cpu"
        )
        mock_pipeline_manager_cls.return_value = mock_pipeline_manager

        mock_tests_manager = MagicMock()
        mock_tests_manager.test_performance.return_value = "multi-job-456"
        mock_tests_manager_cls.return_value = mock_tests_manager

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
        mock_tests_manager.test_performance.assert_called_once()
        call_args = mock_tests_manager.test_performance.call_args[0][0]
        self.assertEqual(len(call_args.pipeline_performance_specs), 2)

        # First spec should be variant reference format
        self.assertTrue(
            call_args.pipeline_performance_specs[0].pipeline_id.startswith(
                "/pipelines/"
            )
        )
        self.assertEqual(call_args.pipeline_performance_specs[0].streams, 1)

        # Second spec should be inline graph format
        self.assertTrue(
            call_args.pipeline_performance_specs[1].pipeline_id.startswith("__graph-")
        )
        self.assertEqual(call_args.pipeline_performance_specs[1].streams, 3)

    @patch("api.routes.tests.PipelineManager")
    @patch("api.routes.tests.TestsManager")
    def test_run_performance_test_with_invalid_body_returns_422(
        self, mock_tests_manager_cls, mock_pipeline_manager_cls
    ):
        """
        The /tests/performance endpoint should return 422 if the request body
        is invalid (e.g., missing required fields).
        """
        # Arrange
        mock_pipeline_manager_cls.return_value = MagicMock()
        mock_tests_manager = MagicMock()
        mock_tests_manager_cls.return_value = mock_tests_manager

        # Act: send request with missing pipeline_performance_specs
        request_body = {}
        response = self.client.post("/tests/performance", json=request_body)

        # Assert: FastAPI validation should reject the request
        self.assertEqual(response.status_code, 422)
        mock_tests_manager.test_performance.assert_not_called()

    @patch("api.routes.tests.PipelineManager")
    @patch("api.routes.tests.TestsManager")
    def test_run_performance_test_with_invalid_streams_returns_422(
        self, mock_tests_manager_cls, mock_pipeline_manager_cls
    ):
        """
        The /tests/performance endpoint should return 422 if streams value
        is invalid (e.g., negative number).
        """
        # Arrange
        mock_pipeline_manager_cls.return_value = MagicMock()
        mock_tests_manager = MagicMock()
        mock_tests_manager_cls.return_value = mock_tests_manager

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
        mock_tests_manager.test_performance.assert_not_called()

    @patch("api.routes.tests.PipelineManager")
    @patch("api.routes.tests.TestsManager")
    def test_run_performance_test_with_invalid_source_returns_422(
        self, mock_tests_manager_cls, mock_pipeline_manager_cls
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

    @patch("api.routes.tests.PipelineManager")
    @patch("api.routes.tests.TestsManager")
    def test_run_performance_test_with_file_output(
        self, mock_tests_manager_cls, mock_pipeline_manager_cls
    ):
        """
        The /tests/performance endpoint should accept execution_config
        with file output mode.
        """
        # Arrange: configure mocks
        mock_pipeline_manager = MagicMock()
        mock_pipeline_manager.get_pipeline_by_id.return_value = create_mock_pipeline(
            "pipeline-file123", "File Pipeline"
        )
        mock_pipeline_manager.get_variant_by_ids.return_value = create_mock_variant(
            "variant-cpu"
        )
        mock_pipeline_manager_cls.return_value = mock_pipeline_manager

        mock_tests_manager = MagicMock()
        mock_tests_manager.test_performance.return_value = "file-job-456"
        mock_tests_manager_cls.return_value = mock_tests_manager

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
        mock_tests_manager.test_performance.assert_called_once()
        call_args = mock_tests_manager.test_performance.call_args[0][0]
        self.assertIsInstance(call_args, InternalPerformanceTestSpec)
        from internal_types import InternalOutputMode

        self.assertEqual(
            call_args.execution_config.output_mode, InternalOutputMode.FILE
        )
        self.assertEqual(call_args.execution_config.max_runtime, 0)

    @patch("api.routes.tests.PipelineManager")
    @patch("api.routes.tests.TestsManager")
    def test_run_performance_test_with_live_stream_output(
        self, mock_tests_manager_cls, mock_pipeline_manager_cls
    ):
        """
        The /tests/performance endpoint should accept execution_config
        with live_stream output mode.
        """
        # Arrange: configure mocks
        mock_pipeline_manager = MagicMock()
        mock_pipeline_manager.get_pipeline_by_id.return_value = create_mock_pipeline(
            "pipeline-stream123", "Stream Pipeline"
        )
        mock_pipeline_manager.get_variant_by_ids.return_value = create_mock_variant(
            "variant-gpu"
        )
        mock_pipeline_manager_cls.return_value = mock_pipeline_manager

        mock_tests_manager = MagicMock()
        mock_tests_manager.test_performance.return_value = "stream-job-789"
        mock_tests_manager_cls.return_value = mock_tests_manager

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
        mock_tests_manager.test_performance.assert_called_once()
        call_args = mock_tests_manager.test_performance.call_args[0][0]
        from internal_types import InternalOutputMode

        self.assertEqual(
            call_args.execution_config.output_mode, InternalOutputMode.LIVE_STREAM
        )
        self.assertEqual(call_args.execution_config.max_runtime, 60)

    @patch("api.routes.tests.PipelineManager")
    @patch("api.routes.tests.TestsManager")
    def test_run_performance_test_with_max_runtime(
        self, mock_tests_manager_cls, mock_pipeline_manager_cls
    ):
        """
        The /tests/performance endpoint should accept execution_config
        with max_runtime for time-limited execution.
        """
        # Arrange: configure mocks
        mock_pipeline_manager = MagicMock()
        mock_pipeline_manager.get_pipeline_by_id.return_value = create_mock_pipeline(
            "pipeline-runtime123", "Runtime Pipeline"
        )
        mock_pipeline_manager.get_variant_by_ids.return_value = create_mock_variant(
            "variant-npu"
        )
        mock_pipeline_manager_cls.return_value = mock_pipeline_manager

        mock_tests_manager = MagicMock()
        mock_tests_manager.test_performance.return_value = "runtime-job-999"
        mock_tests_manager_cls.return_value = mock_tests_manager

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
        mock_tests_manager.test_performance.assert_called_once()
        call_args = mock_tests_manager.test_performance.call_args[0][0]
        from internal_types import InternalOutputMode

        self.assertEqual(
            call_args.execution_config.output_mode, InternalOutputMode.DISABLED
        )
        self.assertEqual(call_args.execution_config.max_runtime, 120)

    @patch("api.routes.tests.PipelineManager")
    @patch("api.routes.tests.TestsManager")
    def test_run_performance_test_variant_not_found_returns_400(
        self, mock_tests_manager_cls, mock_pipeline_manager_cls
    ):
        """
        The /tests/performance endpoint should return 400 if the referenced
        variant does not exist.
        """
        # Arrange: configure mock to raise ValueError for variant not found
        mock_pipeline_manager = MagicMock()
        mock_pipeline_manager.get_pipeline_by_id.return_value = create_mock_pipeline(
            "pipeline-abc", "Pipeline ABC"
        )
        mock_pipeline_manager.get_variant_by_ids.side_effect = ValueError(
            "Variant 'variant-unknown' not found in pipeline 'pipeline-abc'."
        )
        mock_pipeline_manager_cls.return_value = mock_pipeline_manager

        mock_tests_manager_cls.return_value = MagicMock()

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

    @patch("api.routes.tests.PipelineManager")
    @patch("api.routes.tests.TestsManager")
    def test_run_performance_test_manager_raises_exception_returns_500(
        self, mock_tests_manager_cls, mock_pipeline_manager_cls
    ):
        """
        The /tests/performance endpoint should return 500 if test_manager
        raises an unexpected exception.
        """
        # Arrange: configure mocks
        mock_pipeline_manager = MagicMock()
        mock_pipeline_manager.get_pipeline_by_id.return_value = create_mock_pipeline(
            "pipeline-abc", "Pipeline ABC"
        )
        mock_pipeline_manager.get_variant_by_ids.return_value = create_mock_variant(
            "variant-cpu"
        )
        mock_pipeline_manager_cls.return_value = mock_pipeline_manager

        mock_tests_manager = MagicMock()
        mock_tests_manager.test_performance.side_effect = RuntimeError(
            "Unexpected error"
        )
        mock_tests_manager_cls.return_value = mock_tests_manager

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

    @patch("api.routes.tests.PipelineManager")
    @patch("api.routes.tests.TestsManager")
    def test_run_performance_test_empty_specs_returns_400(
        self, mock_tests_manager_cls, mock_pipeline_manager_cls
    ):
        """
        The /tests/performance endpoint should return 400 if
        pipeline_performance_specs is empty.
        """
        # Arrange
        mock_pipeline_manager_cls.return_value = MagicMock()
        mock_tests_manager_cls.return_value = MagicMock()

        # Act: send request with empty pipeline_performance_specs
        request_body = {
            "pipeline_performance_specs": [],
            "execution_config": {"output_mode": "disabled", "max_runtime": 0},
        }
        response = self.client.post("/tests/performance", json=request_body)

        # Assert: should return 400 (validation in route layer)
        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertIn("message", data)
        self.assertIn("cannot be empty", data["message"])

    @patch("api.routes.tests.PipelineManager")
    @patch("api.routes.tests.TestsManager")
    def test_run_performance_test_duplicate_pipeline_ids_returns_400(
        self, mock_tests_manager_cls, mock_pipeline_manager_cls
    ):
        """
        The /tests/performance endpoint should return 400 if there are
        duplicate pipeline_ids after resolution.
        """
        # Arrange: configure mocks to return same resolved ID
        mock_pipeline_manager = MagicMock()
        mock_pipeline_manager.get_pipeline_by_id.return_value = create_mock_pipeline(
            "pipeline-abc", "Pipeline ABC"
        )
        mock_pipeline_manager.get_variant_by_ids.return_value = create_mock_variant(
            "variant-cpu"
        )
        mock_pipeline_manager_cls.return_value = mock_pipeline_manager

        mock_tests_manager_cls.return_value = MagicMock()

        # Act: send request with duplicate pipeline references
        request_body = {
            "pipeline_performance_specs": [
                {
                    "pipeline": {
                        "source": "variant",
                        "pipeline_id": "pipeline-abc",
                        "variant_id": "variant-cpu",
                    },
                    "streams": 1,
                },
                {
                    "pipeline": {
                        "source": "variant",
                        "pipeline_id": "pipeline-abc",
                        "variant_id": "variant-cpu",
                    },
                    "streams": 2,
                },
            ],
            "execution_config": {"output_mode": "disabled", "max_runtime": 0},
        }
        response = self.client.post("/tests/performance", json=request_body)

        # Assert: should return 400 for duplicate IDs
        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertIn("message", data)
        self.assertIn("Duplicate", data["message"])

    # ------------------------------------------------------------------
    # /tests/density - Variant Reference
    # ------------------------------------------------------------------

    @patch("api.routes.tests.PipelineManager")
    @patch("api.routes.tests.TestsManager")
    def test_run_density_test_returns_job_id(
        self, mock_tests_manager_cls, mock_pipeline_manager_cls
    ):
        """
        The /tests/density endpoint should accept a DensityTestSpec
        with variant reference and return a TestJobResponse with a job_id.

        This test validates:
        * HTTP 202 status (Accepted),
        * response contains job_id field,
        * test_manager.test_density() is called with InternalDensityTestSpec.
        """
        # Arrange: configure mocks
        mock_pipeline_manager = MagicMock()
        mock_pipeline_manager.get_pipeline_by_id.return_value = create_mock_pipeline(
            "pipeline-ghi789", "GHI Pipeline"
        )
        mock_pipeline_manager.get_variant_by_ids.return_value = create_mock_variant(
            "variant-cpu"
        )
        mock_pipeline_manager_cls.return_value = mock_pipeline_manager

        mock_tests_manager = MagicMock()
        mock_tests_manager.test_density.return_value = "density-job-789"
        mock_tests_manager_cls.return_value = mock_tests_manager

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

        # Verify manager was called with InternalDensityTestSpec
        mock_tests_manager.test_density.assert_called_once()
        call_args = mock_tests_manager.test_density.call_args[0][0]
        self.assertIsInstance(call_args, InternalDensityTestSpec)
        self.assertEqual(call_args.fps_floor, 30)
        self.assertEqual(len(call_args.pipeline_density_specs), 1)

        # Verify the internal spec has resolved pipeline information
        internal_spec = call_args.pipeline_density_specs[0]
        self.assertEqual(
            internal_spec.pipeline_id, "/pipelines/pipeline-ghi789/variants/variant-cpu"
        )
        self.assertEqual(internal_spec.pipeline_name, "GHI Pipeline")
        self.assertEqual(internal_spec.stream_rate, 100)

        # Verify original_request is stored
        self.assertIn("pipeline_density_specs", call_args.original_request)
        self.assertEqual(call_args.original_request["fps_floor"], 30)

    @patch("api.routes.tests.PipelineManager")
    @patch("api.routes.tests.TestsManager")
    def test_run_density_test_with_inline_graph_returns_job_id(
        self, mock_tests_manager_cls, mock_pipeline_manager_cls
    ):
        """
        The /tests/density endpoint should accept a DensityTestSpec
        with inline graph (no graph_id) and return a TestJobResponse with a job_id.
        """
        # Arrange: configure mocks
        mock_pipeline_manager_cls.return_value = MagicMock()

        mock_tests_manager = MagicMock()
        mock_tests_manager.test_density.return_value = "density-graph-job"
        mock_tests_manager_cls.return_value = mock_tests_manager

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

        # Verify the internal spec has inline graph format ID
        call_args = mock_tests_manager.test_density.call_args[0][0]
        internal_spec = call_args.pipeline_density_specs[0]
        self.assertTrue(internal_spec.pipeline_id.startswith("__graph-"))

    @patch("api.routes.tests.PipelineManager")
    @patch("api.routes.tests.TestsManager")
    def test_run_density_test_with_inline_graph_custom_graph_id(
        self, mock_tests_manager_cls, mock_pipeline_manager_cls
    ):
        """
        The /tests/density endpoint should accept inline graph with
        custom graph_id and use it as pipeline_id.
        """
        # Arrange
        mock_pipeline_manager_cls.return_value = MagicMock()

        mock_tests_manager = MagicMock()
        mock_tests_manager.test_density.return_value = "density-custom-id"
        mock_tests_manager_cls.return_value = mock_tests_manager

        # Act: send request with custom graph_id
        request_body = {
            "fps_floor": 30,
            "pipeline_density_specs": [
                {
                    "pipeline": {
                        "source": "graph",
                        "graph_id": "my-density-test",
                        "pipeline_graph": {
                            "nodes": [
                                {"id": "0", "type": "filesrc", "data": {}},
                                {"id": "1", "type": "fakesink", "data": {}},
                            ],
                            "edges": [{"id": "0", "source": "0", "target": "1"}],
                        },
                    },
                    "stream_rate": 100,
                }
            ],
            "execution_config": {"output_mode": "disabled", "max_runtime": 0},
        }
        response = self.client.post("/tests/density", json=request_body)

        # Assert
        self.assertEqual(response.status_code, 202)

        # Verify custom graph_id is used
        call_args = mock_tests_manager.test_density.call_args[0][0]
        internal_spec = call_args.pipeline_density_specs[0]
        self.assertEqual(internal_spec.pipeline_id, "my-density-test")

    @patch("api.routes.tests.PipelineManager")
    @patch("api.routes.tests.TestsManager")
    def test_run_density_test_with_empty_graph_id_returns_400(
        self, mock_tests_manager_cls, mock_pipeline_manager_cls
    ):
        """
        The /tests/density endpoint should return 400 if graph_id is empty.
        """
        # Arrange
        mock_pipeline_manager_cls.return_value = MagicMock()
        mock_tests_manager_cls.return_value = MagicMock()

        # Act: send request with empty graph_id
        request_body = {
            "fps_floor": 30,
            "pipeline_density_specs": [
                {
                    "pipeline": {
                        "source": "graph",
                        "graph_id": "",
                        "pipeline_graph": {
                            "nodes": [{"id": "0", "type": "fakesrc", "data": {}}],
                            "edges": [],
                        },
                    },
                    "stream_rate": 100,
                }
            ],
            "execution_config": {"output_mode": "disabled", "max_runtime": 0},
        }
        response = self.client.post("/tests/density", json=request_body)

        # Assert
        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertIn("empty", data["message"].lower())

    @patch("api.routes.tests.PipelineManager")
    @patch("api.routes.tests.TestsManager")
    def test_run_density_test_with_invalid_graph_id_chars_returns_400(
        self, mock_tests_manager_cls, mock_pipeline_manager_cls
    ):
        """
        The /tests/density endpoint should return 400 if graph_id
        contains invalid characters.
        """
        # Arrange
        mock_pipeline_manager_cls.return_value = MagicMock()
        mock_tests_manager_cls.return_value = MagicMock()

        # Act: send request with special characters
        request_body = {
            "fps_floor": 30,
            "pipeline_density_specs": [
                {
                    "pipeline": {
                        "source": "graph",
                        "graph_id": "test@pipeline#123",
                        "pipeline_graph": {
                            "nodes": [{"id": "0", "type": "fakesrc", "data": {}}],
                            "edges": [],
                        },
                    },
                    "stream_rate": 100,
                }
            ],
            "execution_config": {"output_mode": "disabled", "max_runtime": 0},
        }
        response = self.client.post("/tests/density", json=request_body)

        # Assert
        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertIn("URL", data["message"])

    @patch("api.routes.tests.PipelineManager")
    @patch("api.routes.tests.TestsManager")
    def test_run_density_test_with_multiple_pipelines(
        self, mock_tests_manager_cls, mock_pipeline_manager_cls
    ):
        """
        The /tests/density endpoint should accept multiple pipeline specs
        in a single request with stream_rate values summing to 100.
        """
        # Arrange
        mock_pipeline_manager = MagicMock()

        def get_pipeline_side_effect(pid):
            if pid == "pipeline-jkl012":
                return create_mock_pipeline(pid, "JKL Pipeline")
            elif pid == "pipeline-mno345":
                return create_mock_pipeline(pid, "MNO Pipeline")
            raise ValueError(f"Pipeline {pid} not found")

        mock_pipeline_manager.get_pipeline_by_id.side_effect = get_pipeline_side_effect
        mock_pipeline_manager.get_variant_by_ids.return_value = create_mock_variant(
            "variant-cpu"
        )
        mock_pipeline_manager_cls.return_value = mock_pipeline_manager

        mock_tests_manager = MagicMock()
        mock_tests_manager.test_density.return_value = "density-multi-999"
        mock_tests_manager_cls.return_value = mock_tests_manager

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
        mock_tests_manager.test_density.assert_called_once()
        call_args = mock_tests_manager.test_density.call_args[0][0]
        self.assertEqual(call_args.fps_floor, 25)
        self.assertEqual(len(call_args.pipeline_density_specs), 2)
        self.assertEqual(call_args.pipeline_density_specs[0].stream_rate, 50)
        self.assertEqual(call_args.pipeline_density_specs[1].stream_rate, 50)

    @patch("api.routes.tests.PipelineManager")
    @patch("api.routes.tests.TestsManager")
    def test_run_density_test_with_mixed_sources(
        self, mock_tests_manager_cls, mock_pipeline_manager_cls
    ):
        """
        The /tests/density endpoint should accept mixed pipeline sources
        (variant reference + inline graph) in a single request.
        """
        # Arrange
        mock_pipeline_manager = MagicMock()
        mock_pipeline_manager.get_pipeline_by_id.return_value = create_mock_pipeline(
            "pipeline-abc", "ABC Pipeline"
        )
        mock_pipeline_manager.get_variant_by_ids.return_value = create_mock_variant(
            "variant-cpu"
        )
        mock_pipeline_manager_cls.return_value = mock_pipeline_manager

        mock_tests_manager = MagicMock()
        mock_tests_manager.test_density.return_value = "density-mixed-job"
        mock_tests_manager_cls.return_value = mock_tests_manager

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

        # Verify mixed sources in internal spec
        call_args = mock_tests_manager.test_density.call_args[0][0]
        self.assertTrue(
            call_args.pipeline_density_specs[0].pipeline_id.startswith("/pipelines/")
        )
        self.assertTrue(
            call_args.pipeline_density_specs[1].pipeline_id.startswith("__graph-")
        )

    @patch("api.routes.tests.PipelineManager")
    @patch("api.routes.tests.TestsManager")
    def test_run_density_test_with_invalid_body_returns_422(
        self, mock_tests_manager_cls, mock_pipeline_manager_cls
    ):
        """
        The /tests/density endpoint should return 422 if the request body
        is invalid (e.g., missing required fields).
        """
        # Arrange
        mock_pipeline_manager_cls.return_value = MagicMock()
        mock_tests_manager = MagicMock()
        mock_tests_manager_cls.return_value = mock_tests_manager

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
        mock_tests_manager.test_density.assert_not_called()

    @patch("api.routes.tests.PipelineManager")
    @patch("api.routes.tests.TestsManager")
    def test_run_density_test_with_invalid_fps_floor_returns_422(
        self, mock_tests_manager_cls, mock_pipeline_manager_cls
    ):
        """
        The /tests/density endpoint should return 422 if fps_floor value
        is invalid (e.g., negative number).
        """
        # Arrange
        mock_pipeline_manager_cls.return_value = MagicMock()
        mock_tests_manager = MagicMock()
        mock_tests_manager_cls.return_value = mock_tests_manager

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
        mock_tests_manager.test_density.assert_not_called()

    @patch("api.routes.tests.PipelineManager")
    @patch("api.routes.tests.TestsManager")
    def test_run_density_test_with_invalid_stream_rate_returns_422(
        self, mock_tests_manager_cls, mock_pipeline_manager_cls
    ):
        """
        The /tests/density endpoint should return 422 if stream_rate value
        is invalid (e.g., negative number).
        """
        # Arrange
        mock_pipeline_manager_cls.return_value = MagicMock()
        mock_tests_manager = MagicMock()
        mock_tests_manager_cls.return_value = mock_tests_manager

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
        mock_tests_manager.test_density.assert_not_called()

    @patch("api.routes.tests.PipelineManager")
    @patch("api.routes.tests.TestsManager")
    def test_run_density_test_with_file_output(
        self, mock_tests_manager_cls, mock_pipeline_manager_cls
    ):
        """
        The /tests/density endpoint should accept file output mode.
        """
        # Arrange: configure mocks
        mock_pipeline_manager = MagicMock()
        mock_pipeline_manager.get_pipeline_by_id.return_value = create_mock_pipeline(
            "pipeline-density-file", "Density File Pipeline"
        )
        mock_pipeline_manager.get_variant_by_ids.return_value = create_mock_variant(
            "variant-cpu"
        )
        mock_pipeline_manager_cls.return_value = mock_pipeline_manager

        mock_tests_manager = MagicMock()
        mock_tests_manager.test_density.return_value = "density-file-job"
        mock_tests_manager_cls.return_value = mock_tests_manager

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
        mock_tests_manager.test_density.assert_called_once()
        call_args = mock_tests_manager.test_density.call_args[0][0]
        self.assertIsInstance(call_args, InternalDensityTestSpec)
        from internal_types import InternalOutputMode

        self.assertEqual(
            call_args.execution_config.output_mode, InternalOutputMode.FILE
        )

    @patch("api.routes.tests.PipelineManager")
    @patch("api.routes.tests.TestsManager")
    def test_run_density_test_variant_not_found_returns_400(
        self, mock_tests_manager_cls, mock_pipeline_manager_cls
    ):
        """
        The /tests/density endpoint should return 400 if the referenced
        variant does not exist.
        """
        # Arrange: configure mock to raise ValueError
        mock_pipeline_manager = MagicMock()
        mock_pipeline_manager.get_pipeline_by_id.return_value = create_mock_pipeline(
            "pipeline-abc", "Pipeline ABC"
        )
        mock_pipeline_manager.get_variant_by_ids.side_effect = ValueError(
            "Variant 'variant-unknown' not found in pipeline 'pipeline-abc'."
        )
        mock_pipeline_manager_cls.return_value = mock_pipeline_manager

        mock_tests_manager_cls.return_value = MagicMock()

        # Act: send a valid request
        request_body = {
            "fps_floor": 30,
            "pipeline_density_specs": [
                {
                    "pipeline": {
                        "source": "variant",
                        "pipeline_id": "pipeline-abc",
                        "variant_id": "variant-unknown",
                    },
                    "stream_rate": 100,
                }
            ],
            "execution_config": {"output_mode": "disabled", "max_runtime": 0},
        }
        response = self.client.post("/tests/density", json=request_body)

        # Assert: should return 400 with error message
        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertIn("message", data)
        self.assertIn("not found", data["message"])

    @patch("api.routes.tests.PipelineManager")
    @patch("api.routes.tests.TestsManager")
    def test_run_density_test_manager_raises_exception_returns_500(
        self, mock_tests_manager_cls, mock_pipeline_manager_cls
    ):
        """
        The /tests/density endpoint should return 500 if test_manager
        raises an unexpected exception.
        """
        # Arrange: configure mocks
        mock_pipeline_manager = MagicMock()
        mock_pipeline_manager.get_pipeline_by_id.return_value = create_mock_pipeline(
            "pipeline-abc", "Pipeline ABC"
        )
        mock_pipeline_manager.get_variant_by_ids.return_value = create_mock_variant(
            "variant-cpu"
        )
        mock_pipeline_manager_cls.return_value = mock_pipeline_manager

        mock_tests_manager = MagicMock()
        mock_tests_manager.test_density.side_effect = RuntimeError("Unexpected error")
        mock_tests_manager_cls.return_value = mock_tests_manager

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

    @patch("api.routes.tests.PipelineManager")
    @patch("api.routes.tests.TestsManager")
    def test_run_density_test_empty_specs_returns_400(
        self, mock_tests_manager_cls, mock_pipeline_manager_cls
    ):
        """
        The /tests/density endpoint should return 400 if
        pipeline_density_specs is empty.
        """
        # Arrange
        mock_pipeline_manager_cls.return_value = MagicMock()
        mock_tests_manager_cls.return_value = MagicMock()

        # Act: send request with empty pipeline_density_specs
        request_body = {
            "fps_floor": 30,
            "pipeline_density_specs": [],
            "execution_config": {"output_mode": "disabled", "max_runtime": 0},
        }
        response = self.client.post("/tests/density", json=request_body)

        # Assert: should return 400 (validation in route layer)
        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertIn("message", data)
        self.assertIn("cannot be empty", data["message"])

    @patch("api.routes.tests.PipelineManager")
    @patch("api.routes.tests.TestsManager")
    def test_run_density_test_duplicate_pipeline_ids_returns_400(
        self, mock_tests_manager_cls, mock_pipeline_manager_cls
    ):
        """
        The /tests/density endpoint should return 400 if there are
        duplicate pipeline_ids after resolution.
        """
        # Arrange: configure mocks to return same resolved ID
        mock_pipeline_manager = MagicMock()
        mock_pipeline_manager.get_pipeline_by_id.return_value = create_mock_pipeline(
            "pipeline-abc", "Pipeline ABC"
        )
        mock_pipeline_manager.get_variant_by_ids.return_value = create_mock_variant(
            "variant-cpu"
        )
        mock_pipeline_manager_cls.return_value = mock_pipeline_manager

        mock_tests_manager_cls.return_value = MagicMock()

        # Act: send request with duplicate pipeline references
        request_body = {
            "fps_floor": 30,
            "pipeline_density_specs": [
                {
                    "pipeline": {
                        "source": "variant",
                        "pipeline_id": "pipeline-abc",
                        "variant_id": "variant-cpu",
                    },
                    "stream_rate": 50,
                },
                {
                    "pipeline": {
                        "source": "variant",
                        "pipeline_id": "pipeline-abc",
                        "variant_id": "variant-cpu",
                    },
                    "stream_rate": 50,
                },
            ],
            "execution_config": {"output_mode": "disabled", "max_runtime": 0},
        }
        response = self.client.post("/tests/density", json=request_body)

        # Assert: should return 400 for duplicate IDs
        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertIn("message", data)
        self.assertIn("Duplicate", data["message"])

    # ------------------------------------------------------------------
    # /tests/performance - Pipeline Description Source
    # ------------------------------------------------------------------

    @patch("api.routes.tests.PipelineManager")
    @patch("api.routes.tests.TestsManager")
    def test_run_performance_test_with_pipeline_description_returns_job_id(
        self, mock_tests_manager_cls, mock_pipeline_manager_cls
    ):
        """
        The /tests/performance endpoint should accept a PerformanceTestSpec
        with pipeline description source and return a TestJobResponse with job_id.
        Uses Graph.from_pipeline_description to create graph from description.
        """
        # Arrange: configure mocks (PipelineManager not needed for description source)
        mock_pipeline_manager_cls.return_value = MagicMock()

        mock_tests_manager = MagicMock()
        mock_tests_manager.test_performance.return_value = "description-job-123"
        mock_tests_manager_cls.return_value = mock_tests_manager

        # Act: send a performance test request with pipeline description
        request_body = {
            "pipeline_performance_specs": [
                {
                    "pipeline": {
                        "source": "description",
                        "pipeline_description": "videotestsrc ! videoconvert ! fakesink",
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
        self.assertEqual(data["job_id"], "description-job-123")

        # Verify manager was called with InternalPerformanceTestSpec
        mock_tests_manager.test_performance.assert_called_once()
        call_args = mock_tests_manager.test_performance.call_args[0][0]
        self.assertIsInstance(call_args, InternalPerformanceTestSpec)

        # Verify the internal spec has generated hash-based ID (starts with __description-)
        internal_spec = call_args.pipeline_performance_specs[0]
        self.assertTrue(internal_spec.pipeline_id.startswith("__description-"))
        self.assertEqual(internal_spec.streams, 2)

        # Verify pipeline_graph was created from description
        self.assertIsNotNone(internal_spec.pipeline_graph)
        self.assertGreater(len(internal_spec.pipeline_graph.nodes), 0)

    @patch("api.routes.tests.PipelineManager")
    @patch("api.routes.tests.TestsManager")
    def test_run_performance_test_with_pipeline_description_custom_id(
        self, mock_tests_manager_cls, mock_pipeline_manager_cls
    ):
        """
        The /tests/performance endpoint should accept pipeline description
        with custom description_id and use it as pipeline_id.
        """
        # Arrange
        mock_pipeline_manager_cls.return_value = MagicMock()

        mock_tests_manager = MagicMock()
        mock_tests_manager.test_performance.return_value = "custom-desc-job"
        mock_tests_manager_cls.return_value = mock_tests_manager

        # Act: send request with custom description_id
        request_body = {
            "pipeline_performance_specs": [
                {
                    "pipeline": {
                        "source": "description",
                        "description_id": "my-test-description",
                        "pipeline_description": "videotestsrc ! fakesink",
                    },
                    "streams": 1,
                }
            ],
            "execution_config": {"output_mode": "disabled", "max_runtime": 0},
        }
        response = self.client.post("/tests/performance", json=request_body)

        # Assert
        self.assertEqual(response.status_code, 202)

        # Verify custom description_id is used as pipeline_id
        call_args = mock_tests_manager.test_performance.call_args[0][0]
        internal_spec = call_args.pipeline_performance_specs[0]
        self.assertEqual(internal_spec.pipeline_id, "my-test-description")
        self.assertEqual(internal_spec.pipeline_name, "my-test-description")

    @patch("api.routes.tests.PipelineManager")
    @patch("api.routes.tests.TestsManager")
    def test_run_performance_test_with_empty_description_id_returns_400(
        self, mock_tests_manager_cls, mock_pipeline_manager_cls
    ):
        """
        The /tests/performance endpoint should return 400 if description_id
        is empty after trim.
        """
        # Arrange
        mock_pipeline_manager_cls.return_value = MagicMock()
        mock_tests_manager_cls.return_value = MagicMock()

        # Act: send request with empty description_id
        request_body = {
            "pipeline_performance_specs": [
                {
                    "pipeline": {
                        "source": "description",
                        "description_id": "   ",
                        "pipeline_description": "videotestsrc ! fakesink",
                    },
                    "streams": 1,
                }
            ],
            "execution_config": {"output_mode": "disabled", "max_runtime": 0},
        }
        response = self.client.post("/tests/performance", json=request_body)

        # Assert
        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertIn("message", data)
        self.assertIn("empty", data["message"].lower())

    @patch("api.routes.tests.PipelineManager")
    @patch("api.routes.tests.TestsManager")
    def test_run_performance_test_with_invalid_description_id_chars_returns_400(
        self, mock_tests_manager_cls, mock_pipeline_manager_cls
    ):
        """
        The /tests/performance endpoint should return 400 if description_id
        contains invalid URL characters.
        """
        # Arrange
        mock_pipeline_manager_cls.return_value = MagicMock()
        mock_tests_manager_cls.return_value = MagicMock()

        # Act: send request with invalid description_id
        request_body = {
            "pipeline_performance_specs": [
                {
                    "pipeline": {
                        "source": "description",
                        "description_id": "My Description ID",
                        "pipeline_description": "videotestsrc ! fakesink",
                    },
                    "streams": 1,
                }
            ],
            "execution_config": {"output_mode": "disabled", "max_runtime": 0},
        }
        response = self.client.post("/tests/performance", json=request_body)

        # Assert
        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertIn("message", data)
        self.assertIn("URL", data["message"])

    @patch("api.routes.tests.PipelineManager")
    @patch("api.routes.tests.TestsManager")
    def test_run_performance_test_with_empty_pipeline_description_returns_422(
        self, mock_tests_manager_cls, mock_pipeline_manager_cls
    ):
        """
        The /tests/performance endpoint should return 422 if pipeline_description
        is empty (pydantic validation).
        """
        # Act: send request with empty pipeline_description
        request_body = {
            "pipeline_performance_specs": [
                {
                    "pipeline": {
                        "source": "description",
                        "pipeline_description": "",
                    },
                    "streams": 1,
                }
            ],
            "execution_config": {"output_mode": "disabled", "max_runtime": 0},
        }
        response = self.client.post("/tests/performance", json=request_body)

        # Assert: FastAPI validation should reject the request
        self.assertEqual(response.status_code, 422)

    # ------------------------------------------------------------------
    # /tests/density - Pipeline Description Source
    # ------------------------------------------------------------------

    @patch("api.routes.tests.PipelineManager")
    @patch("api.routes.tests.TestsManager")
    def test_run_density_test_with_pipeline_description_returns_job_id(
        self, mock_tests_manager_cls, mock_pipeline_manager_cls
    ):
        """
        The /tests/density endpoint should accept a DensityTestSpec
        with pipeline description source and return a TestJobResponse with job_id.
        Uses Graph.from_pipeline_description to create graph from description.
        """
        # Arrange: configure mocks
        mock_pipeline_manager_cls.return_value = MagicMock()

        mock_tests_manager = MagicMock()
        mock_tests_manager.test_density.return_value = "density-desc-job"
        mock_tests_manager_cls.return_value = mock_tests_manager

        # Act: send a density test request with pipeline description
        request_body = {
            "fps_floor": 30,
            "pipeline_density_specs": [
                {
                    "pipeline": {
                        "source": "description",
                        "pipeline_description": "videotestsrc ! queue ! fakesink",
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
        self.assertEqual(data["job_id"], "density-desc-job")

        # Verify the internal spec has description format ID
        call_args = mock_tests_manager.test_density.call_args[0][0]
        internal_spec = call_args.pipeline_density_specs[0]
        self.assertTrue(internal_spec.pipeline_id.startswith("__description-"))

        # Verify pipeline_graph was created from description
        self.assertIsNotNone(internal_spec.pipeline_graph)

    @patch("api.routes.tests.PipelineManager")
    @patch("api.routes.tests.TestsManager")
    def test_run_density_test_with_pipeline_description_custom_id(
        self, mock_tests_manager_cls, mock_pipeline_manager_cls
    ):
        """
        The /tests/density endpoint should accept pipeline description
        with custom description_id and use it as pipeline_id.
        """
        # Arrange
        mock_pipeline_manager_cls.return_value = MagicMock()

        mock_tests_manager = MagicMock()
        mock_tests_manager.test_density.return_value = "density-custom-desc"
        mock_tests_manager_cls.return_value = mock_tests_manager

        # Act: send request with custom description_id
        request_body = {
            "fps_floor": 30,
            "pipeline_density_specs": [
                {
                    "pipeline": {
                        "source": "description",
                        "description_id": "my-density-description",
                        "pipeline_description": "videotestsrc ! fakesink",
                    },
                    "stream_rate": 100,
                }
            ],
            "execution_config": {"output_mode": "disabled", "max_runtime": 0},
        }
        response = self.client.post("/tests/density", json=request_body)

        # Assert
        self.assertEqual(response.status_code, 202)

        # Verify custom description_id is used
        call_args = mock_tests_manager.test_density.call_args[0][0]
        internal_spec = call_args.pipeline_density_specs[0]
        self.assertEqual(internal_spec.pipeline_id, "my-density-description")

    @patch("api.routes.tests.PipelineManager")
    @patch("api.routes.tests.TestsManager")
    def test_run_density_test_with_empty_description_id_returns_400(
        self, mock_tests_manager_cls, mock_pipeline_manager_cls
    ):
        """
        The /tests/density endpoint should return 400 if description_id
        is empty after trim.
        """
        # Arrange
        mock_pipeline_manager_cls.return_value = MagicMock()
        mock_tests_manager_cls.return_value = MagicMock()

        # Act: send request with empty description_id
        request_body = {
            "fps_floor": 30,
            "pipeline_density_specs": [
                {
                    "pipeline": {
                        "source": "description",
                        "description_id": "",
                        "pipeline_description": "videotestsrc ! fakesink",
                    },
                    "stream_rate": 100,
                }
            ],
            "execution_config": {"output_mode": "disabled", "max_runtime": 0},
        }
        response = self.client.post("/tests/density", json=request_body)

        # Assert
        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertIn("empty", data["message"].lower())

    @patch("api.routes.tests.PipelineManager")
    @patch("api.routes.tests.TestsManager")
    def test_run_density_test_with_invalid_description_id_chars_returns_400(
        self, mock_tests_manager_cls, mock_pipeline_manager_cls
    ):
        """
        The /tests/density endpoint should return 400 if description_id
        contains invalid URL characters.
        """
        # Arrange
        mock_pipeline_manager_cls.return_value = MagicMock()
        mock_tests_manager_cls.return_value = MagicMock()

        # Act: send request with invalid description_id
        request_body = {
            "fps_floor": 30,
            "pipeline_density_specs": [
                {
                    "pipeline": {
                        "source": "description",
                        "description_id": "test@desc#123",
                        "pipeline_description": "videotestsrc ! fakesink",
                    },
                    "stream_rate": 100,
                }
            ],
            "execution_config": {"output_mode": "disabled", "max_runtime": 0},
        }
        response = self.client.post("/tests/density", json=request_body)

        # Assert
        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertIn("URL", data["message"])

    @patch("api.routes.tests.PipelineManager")
    @patch("api.routes.tests.TestsManager")
    def test_run_performance_test_with_mixed_sources_including_description(
        self, mock_tests_manager_cls, mock_pipeline_manager_cls
    ):
        """
        The /tests/performance endpoint should accept mixed pipeline sources
        including variant, inline graph, and pipeline description.
        """
        # Arrange
        mock_pipeline_manager = MagicMock()
        mock_pipeline_manager.get_pipeline_by_id.return_value = create_mock_pipeline(
            "pipeline-abc", "ABC Pipeline"
        )
        mock_pipeline_manager.get_variant_by_ids.return_value = create_mock_variant(
            "variant-cpu"
        )
        mock_pipeline_manager_cls.return_value = mock_pipeline_manager

        mock_tests_manager = MagicMock()
        mock_tests_manager.test_performance.return_value = "mixed-job-789"
        mock_tests_manager_cls.return_value = mock_tests_manager

        # Act: send request with all three source types
        request_body = {
            "pipeline_performance_specs": [
                {
                    "pipeline": {
                        "source": "variant",
                        "pipeline_id": "pipeline-abc",
                        "variant_id": "variant-cpu",
                    },
                    "streams": 1,
                },
                {
                    "pipeline": {
                        "source": "graph",
                        "pipeline_graph": {
                            "nodes": [
                                {"id": "0", "type": "filesrc", "data": {}},
                                {"id": "1", "type": "fakesink", "data": {}},
                            ],
                            "edges": [{"id": "0", "source": "0", "target": "1"}],
                        },
                    },
                    "streams": 2,
                },
                {
                    "pipeline": {
                        "source": "description",
                        "pipeline_description": "videotestsrc ! fakesink",
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
        self.assertEqual(data["job_id"], "mixed-job-789")

        # Verify all three sources are converted correctly
        call_args = mock_tests_manager.test_performance.call_args[0][0]
        self.assertEqual(len(call_args.pipeline_performance_specs), 3)

        # First spec should be variant reference format
        self.assertTrue(
            call_args.pipeline_performance_specs[0].pipeline_id.startswith(
                "/pipelines/"
            )
        )
        # Second spec should be inline graph format
        self.assertTrue(
            call_args.pipeline_performance_specs[1].pipeline_id.startswith("__graph-")
        )
        # Third spec should be description format
        self.assertTrue(
            call_args.pipeline_performance_specs[2].pipeline_id.startswith(
                "__description-"
            )
        )

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

    def test_graph_inline_with_graph_id(self):
        """
        GraphInline should accept optional graph_id field.
        """
        graph = schemas.PipelineGraph(
            nodes=[
                schemas.Node(id="0", type="filesrc", data={"location": "/test.mp4"}),
                schemas.Node(id="1", type="fakesink", data={}),
            ],
            edges=[schemas.Edge(id="0", source="0", target="1")],
        )
        inline = schemas.GraphInline(graph_id="my-custom-id", pipeline_graph=graph)
        self.assertEqual(inline.source, "graph")
        self.assertEqual(inline.graph_id, "my-custom-id")
        self.assertIsNotNone(inline.pipeline_graph)

    def test_graph_inline_without_graph_id(self):
        """
        GraphInline should work without graph_id (defaults to None).
        """
        graph = schemas.PipelineGraph(
            nodes=[
                schemas.Node(id="0", type="filesrc", data={}),
            ],
            edges=[],
        )
        inline = schemas.GraphInline(pipeline_graph=graph)
        self.assertEqual(inline.source, "graph")
        self.assertIsNone(inline.graph_id)

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

    def test_pipeline_description_source_discriminator(self):
        """
        PipelineDescriptionSource should have source='description' as discriminator.
        """
        desc = schemas.PipelineDescriptionSource(
            pipeline_description="videotestsrc ! fakesink"
        )
        self.assertEqual(desc.source, "description")
        self.assertEqual(desc.pipeline_description, "videotestsrc ! fakesink")
        self.assertIsNone(desc.description_id)

    def test_pipeline_description_source_with_description_id(self):
        """
        PipelineDescriptionSource should accept optional description_id field.
        """
        desc = schemas.PipelineDescriptionSource(
            description_id="my-custom-desc",
            pipeline_description="videotestsrc ! fakesink",
        )
        self.assertEqual(desc.source, "description")
        self.assertEqual(desc.description_id, "my-custom-desc")
        self.assertEqual(desc.pipeline_description, "videotestsrc ! fakesink")

    def test_pipeline_performance_spec_with_description_source(self):
        """
        PipelinePerformanceSpec should accept PipelineDescriptionSource.
        """
        desc = schemas.PipelineDescriptionSource(
            pipeline_description="videotestsrc ! videoconvert ! fakesink"
        )
        spec = schemas.PipelinePerformanceSpec(pipeline=desc, streams=3)
        self.assertIsInstance(spec.pipeline, schemas.PipelineDescriptionSource)
        self.assertEqual(spec.streams, 3)

    def test_pipeline_density_spec_with_description_source(self):
        """
        PipelineDensitySpec should accept PipelineDescriptionSource.
        """
        desc = schemas.PipelineDescriptionSource(
            pipeline_description="videotestsrc ! fakesink"
        )
        spec = schemas.PipelineDensitySpec(pipeline=desc, stream_rate=100)
        self.assertIsInstance(spec.pipeline, schemas.PipelineDescriptionSource)
        self.assertEqual(spec.stream_rate, 100)

    def test_pipeline_stream_spec_description_hash_format(self):
        """
        PipelineStreamSpec should accept __description-{hash} format for ID.
        """
        spec = schemas.PipelineStreamSpec(
            id="__description-abcd1234efgh5678", streams=2
        )
        self.assertTrue(spec.id.startswith("__description-"))
        self.assertEqual(spec.streams, 2)


if __name__ == "__main__":
    unittest.main()

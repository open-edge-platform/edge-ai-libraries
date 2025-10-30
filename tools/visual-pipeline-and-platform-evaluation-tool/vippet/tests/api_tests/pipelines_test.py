import unittest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from unittest.mock import patch

import api.api_schemas as schemas
from api.routes.pipelines import router as pipelines_router


class TestPipelinesAPI(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        """Set up test client once for all tests."""
        app = FastAPI()
        app.include_router(pipelines_router, prefix="/pipelines")
        cls.client = TestClient(app)

    @patch("api.routes.pipelines.pipeline_manager")
    def test_get_pipelines_returns_list(self, mock_pipeline_manager):
        mock_pipeline_manager.get_pipelines.return_value = [
            schemas.Pipeline(
                name="predefined-pipelines",
                version="SmartNVRPipeline",
                description="Smart Network Video Recorder (NVR) Proxy Pipeline",
                type=schemas.PipelineType.GSTREAMER,
                launch_config={
                    "nodes": [
                        {
                            "id": "0",
                            "type": "filesrc",
                            "data": {"location": "/tmp/license-plate-detection.mp4"},
                        }
                    ],
                    "edges": [{"id": "0", "source": "0", "target": "1"}],
                },
                parameters=None,
            ),
            schemas.Pipeline(
                name="user-defined-pipelines",
                version="TestPipeline",
                description="Test Pipeline Description",
                type=schemas.PipelineType.GSTREAMER,
                launch_config={
                    "nodes": [
                        {
                            "id": "0",
                            "type": "filesrc",
                            "data": {"location": "/tmp/license-plate-detection.mp4"},
                        }
                    ],
                    "edges": [{"id": "0", "source": "0", "target": "1"}],
                },
                parameters=None,
            ),
        ]

        response = self.client.get("/pipelines")

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIsInstance(data, list)
        self.assertEqual(len(data), 2)

        # Check the contents of the first pipeline
        first_pipeline = data[0]
        self.assertEqual(first_pipeline["name"], "predefined-pipelines")
        self.assertEqual(first_pipeline["version"], "SmartNVRPipeline")
        self.assertEqual(
            first_pipeline["description"],
            "Smart Network Video Recorder (NVR) Proxy Pipeline",
        )
        self.assertEqual(first_pipeline["type"], schemas.PipelineType.GSTREAMER)
        self.assertIn("launch_config", first_pipeline)
        self.assertIsNone(first_pipeline["parameters"])

        # Check the contents of the second pipeline
        second_pipeline = data[1]
        self.assertEqual(second_pipeline["name"], "user-defined-pipelines")
        self.assertEqual(second_pipeline["version"], "TestPipeline")
        self.assertEqual(second_pipeline["description"], "Test Pipeline Description")
        self.assertEqual(second_pipeline["type"], schemas.PipelineType.GSTREAMER)
        self.assertIn("launch_config", second_pipeline)
        self.assertIsNone(second_pipeline["parameters"])

    @patch("api.routes.pipelines.pipeline_manager")
    def test_create_pipeline_valid(self, mock_pipeline_manager):
        mock_pipeline_manager.add_pipeline.return_value = None

        new_pipeline = {
            "name": "user-defined-pipelines",
            "version": "test-pipeline",
            "description": "A custom test pipeline",
            "type": schemas.PipelineType.GSTREAMER,
            "launch_string": "filesrc location=/tmp/test.mp4 ! decodebin ! autovideosink",
            "parameters": None,
        }

        response = self.client.post("/pipelines", json=new_pipeline)

        self.assertEqual(response.status_code, 201)
        self.assertIn("Location", response.headers)
        self.assertEqual(
            response.headers["Location"],
            "/pipelines/user-defined-pipelines/test-pipeline",
        )
        self.assertEqual(response.json(), {"message": "Pipeline created"})

    @patch("api.routes.pipelines.pipeline_manager")
    def test_create_pipeline_duplicate(self, mock_pipeline_manager):
        mock_pipeline_manager.add_pipeline.side_effect = ValueError(
            "Pipeline with name 'user-defined-pipelines' and version 'test-pipeline' already exists."
        )

        duplicate_pipeline = {
            "name": "user-defined-pipelines",
            "version": "test-pipeline",
            "description": "A custom test pipeline",
            "type": schemas.PipelineType.GSTREAMER,
            "launch_string": "filesrc location=/tmp/test.mp4 ! decodebin ! autovideosink",
            "parameters": None,
        }

        response = self.client.post("/pipelines", json=duplicate_pipeline)

        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.json(),
            {
                "detail": "Pipeline with name 'user-defined-pipelines' and version 'test-pipeline' already exists."
            },
        )

    @patch("api.routes.pipelines.pipeline_manager")
    def test_create_pipeline_server_error(self, mock_pipeline_manager):
        mock_pipeline_manager.add_pipeline.side_effect = Exception("Unexpected error")

        new_pipeline = {
            "name": "user-defined-pipelines",
            "version": "test-pipeline",
            "description": "A custom test pipeline",
            "type": schemas.PipelineType.GSTREAMER,
            "launch_string": "filesrc location=/tmp/test.mp4 ! decodebin ! autovideosink",
            "parameters": None,
        }

        response = self.client.post("/pipelines", json=new_pipeline)

        self.assertEqual(response.status_code, 500)
        self.assertEqual(
            response.json(),
            {"detail": "Failed to create pipeline: Unexpected error"},
        )

    @patch("api.routes.pipelines.pipeline_manager")
    def test_get_pipeline_by_name_and_version_found(self, mock_pipeline_manager):
        mock_pipeline_manager.get_pipeline_by_name_and_version.return_value = (
            schemas.Pipeline(
                name="user-defined-pipelines",
                version="test-pipeline",
                description="A custom test pipeline",
                type=schemas.PipelineType.GSTREAMER,
                launch_config={
                    "nodes": [
                        {
                            "id": "0",
                            "type": "filesrc",
                            "data": {"location": "/tmp/license-plate-detection.mp4"},
                        }
                    ],
                    "edges": [{"id": "0", "source": "0", "target": "1"}],
                },
                parameters=None,
            )
        )

        response = self.client.get("/pipelines/user-defined-pipelines/test-pipeline")

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["name"], "user-defined-pipelines")
        self.assertEqual(data["version"], "test-pipeline")
        self.assertEqual(data["description"], "A custom test pipeline")
        self.assertEqual(data["type"], schemas.PipelineType.GSTREAMER)
        self.assertIn("launch_config", data)
        self.assertIsNone(data["parameters"])

    @patch("api.routes.pipelines.pipeline_manager")
    def test_get_pipeline_by_name_and_version_not_found(self, mock_pipeline_manager):
        mock_pipeline_manager.get_pipeline_by_name_and_version.side_effect = ValueError(
            "Pipeline with name 'user-defined-pipelines' and version 'nonexistent' not found."
        )

        response = self.client.get("/pipelines/user-defined-pipelines/nonexistent")

        self.assertEqual(response.status_code, 404)
        self.assertEqual(
            response.json(),
            {
                "detail": "Pipeline with name 'user-defined-pipelines' and version 'nonexistent' not found."
            },
        )

    @patch("api.routes.pipelines.pipeline_manager")
    def test_get_pipeline_by_name_and_version_server_error(self, mock_pipeline_manager):
        mock_pipeline_manager.get_pipeline_by_name_and_version.side_effect = Exception(
            "Unexpected error"
        )

        response = self.client.get("/pipelines/user-defined-pipelines/test-pipeline")

        self.assertEqual(response.status_code, 500)
        self.assertEqual(
            response.json(),
            {"detail": "Unexpected error: Unexpected error"},
        )

import unittest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from unittest.mock import patch

import api.api_schemas as schemas
from api.routes.pipelines import router as pipelines_router


class TestPipelinesAPI(unittest.TestCase):
    test_graph = """
    {
        "nodes": [
            {
                "id": "0",
                "type": "filesrc",
                "data": {
                    "location": "/tmp/license-plate-detection.mp4"
                }
            },
            {
                "id": "1",
                "type": "autovideosink",
                "data": {}
            }
        ],
        "edges": [
            {
                "id": "0",
                "source": "0",
                "target": "1"
            }
        ]
    }
    """

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
                id="pipeline-abc123",
                name="predefined-pipelines",
                version=1,
                description="Smart Network Video Recorder (NVR) Proxy Pipeline",
                source=schemas.PipelineSource.PREDEFINED,
                type=schemas.PipelineType.GSTREAMER,
                pipeline_graph=schemas.PipelineGraph.model_validate_json(
                    self.test_graph
                ),
                parameters=None,
            ),
            schemas.Pipeline(
                id="pipeline-def456",
                name="user-defined-pipelines",
                version=1,
                description="Test Pipeline Description",
                source=schemas.PipelineSource.USER_CREATED,
                type=schemas.PipelineType.GSTREAMER,
                pipeline_graph=schemas.PipelineGraph.model_validate_json(
                    self.test_graph
                ),
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
        self.assertEqual(first_pipeline["id"], "pipeline-abc123")
        self.assertEqual(first_pipeline["name"], "predefined-pipelines")
        self.assertEqual(first_pipeline["version"], 1)
        self.assertEqual(
            first_pipeline["description"],
            "Smart Network Video Recorder (NVR) Proxy Pipeline",
        )
        self.assertEqual(first_pipeline["type"], schemas.PipelineType.GSTREAMER)
        self.assertIn("pipeline_graph", first_pipeline)
        self.assertIsNone(first_pipeline["parameters"])

        # Check the contents of the second pipeline
        second_pipeline = data[1]
        self.assertEqual(second_pipeline["id"], "pipeline-def456")
        self.assertEqual(second_pipeline["name"], "user-defined-pipelines")
        self.assertEqual(second_pipeline["version"], 1)
        self.assertEqual(second_pipeline["description"], "Test Pipeline Description")
        self.assertEqual(second_pipeline["type"], schemas.PipelineType.GSTREAMER)
        self.assertIn("pipeline_graph", second_pipeline)
        self.assertIsNone(second_pipeline["parameters"])

    @patch("api.routes.pipelines.pipeline_manager")
    def test_create_pipeline_valid(self, mock_pipeline_manager):
        # Mock the return value to include the pipeline with ID
        mock_pipeline = schemas.Pipeline(
            id="pipeline-newtest",
            name="user-defined-pipelines",
            version=1,
            description="A custom test pipeline",
            source=schemas.PipelineSource.USER_CREATED,
            type=schemas.PipelineType.GSTREAMER,
            pipeline_graph=schemas.PipelineGraph.model_validate_json(self.test_graph),
            parameters=None,
        )
        mock_pipeline_manager.add_pipeline.return_value = mock_pipeline

        new_pipeline = {
            "name": "user-defined-pipelines",
            "version": 1,
            "description": "A custom test pipeline",
            "type": schemas.PipelineType.GSTREAMER,
            "pipeline_description": "filesrc location=/tmp/test.mp4 ! decodebin ! autovideosink",
            "parameters": None,
        }

        response = self.client.post("/pipelines", json=new_pipeline)

        self.assertEqual(response.status_code, 201)
        self.assertEqual(
            response.json(),
            schemas.PipelineCreationResponse(id="pipeline-newtest").model_dump(),
        )

    @patch("api.routes.pipelines.pipeline_manager")
    def test_create_pipeline_duplicate(self, mock_pipeline_manager):
        mock_pipeline_manager.add_pipeline.side_effect = ValueError(
            "Pipeline already exists."
        )

        duplicate_pipeline = {
            "name": "user-defined-pipelines",
            "version": 1,
            "description": "A custom test pipeline",
            "type": schemas.PipelineType.GSTREAMER,
            "pipeline_description": "filesrc location=/tmp/test.mp4 ! decodebin ! autovideosink",
            "parameters": None,
        }

        response = self.client.post("/pipelines", json=duplicate_pipeline)

        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.json(),
            schemas.MessageResponse(message="Pipeline already exists.").model_dump(),
        )

    @patch("api.routes.pipelines.pipeline_manager")
    def test_create_pipeline_server_error(self, mock_pipeline_manager):
        mock_pipeline_manager.add_pipeline.side_effect = Exception("Unexpected error")

        new_pipeline = {
            "name": "user-defined-pipelines",
            "version": 1,
            "description": "A custom test pipeline",
            "type": schemas.PipelineType.GSTREAMER,
            "pipeline_description": "filesrc location=/tmp/test.mp4 ! decodebin ! autovideosink",
            "parameters": None,
        }

        response = self.client.post("/pipelines", json=new_pipeline)

        self.assertEqual(response.status_code, 500)
        self.assertEqual(
            response.json(),
            schemas.MessageResponse(
                message="Failed to create pipeline: Unexpected error"
            ).model_dump(),
        )

    @patch("api.routes.pipelines.pipeline_manager")
    def test_get_pipeline_by_id_found(self, mock_pipeline_manager):
        mock_pipeline_manager.get_pipeline_by_id.return_value = schemas.Pipeline(
            id="pipeline-ghi789",
            name="user-defined-pipelines",
            version=1,
            description="A custom test pipeline",
            source=schemas.PipelineSource.USER_CREATED,
            type=schemas.PipelineType.GSTREAMER,
            pipeline_graph=schemas.PipelineGraph.model_validate_json(self.test_graph),
            parameters=None,
        )

        response = self.client.get("/pipelines/pipeline-ghi789")

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["id"], "pipeline-ghi789")
        self.assertEqual(data["name"], "user-defined-pipelines")
        self.assertEqual(data["version"], 1)
        self.assertEqual(data["description"], "A custom test pipeline")
        self.assertEqual(data["type"], schemas.PipelineType.GSTREAMER)
        self.assertIn("pipeline_graph", data)
        self.assertIsNone(data["parameters"])

    @patch("api.routes.pipelines.pipeline_manager")
    def test_get_pipeline_by_id_not_found(self, mock_pipeline_manager):
        mock_pipeline_manager.get_pipeline_by_id.side_effect = ValueError(
            "Pipeline with id 'nonexistent-id' not found."
        )

        response = self.client.get("/pipelines/nonexistent-id")

        self.assertEqual(response.status_code, 404)
        self.assertEqual(
            response.json(),
            schemas.MessageResponse(
                message="Pipeline with id 'nonexistent-id' not found."
            ).model_dump(),
        )

    @patch("api.routes.pipelines.pipeline_manager")
    def test_get_pipeline_by_id_server_error(self, mock_pipeline_manager):
        mock_pipeline_manager.get_pipeline_by_id.side_effect = Exception(
            "Unexpected error"
        )

        response = self.client.get("/pipelines/pipeline-test123")

        self.assertEqual(response.status_code, 500)
        self.assertEqual(
            response.json(),
            schemas.MessageResponse(
                message="Unexpected error: Unexpected error"
            ).model_dump(),
        )

    @patch("api.routes.pipelines.pipeline_manager")
    def test_update_pipeline_description(self, mock_pipeline_manager):
        updated_pipeline = schemas.Pipeline(
            id="pipeline-ghi789",
            name="updated-name",
            version=1,
            description="Updated description",
            source=schemas.PipelineSource.USER_CREATED,
            type=schemas.PipelineType.GSTREAMER,
            pipeline_graph=schemas.PipelineGraph.model_validate_json(self.test_graph),
            parameters=None,
        )
        mock_pipeline_manager.update_pipeline.return_value = updated_pipeline

        payload = {"name": "updated-name", "description": "Updated description"}
        response = self.client.patch("/pipelines/pipeline-ghi789", json=payload)

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["id"], "pipeline-ghi789")
        self.assertEqual(data["name"], "updated-name")
        self.assertEqual(data["description"], "Updated description")
        mock_pipeline_manager.update_pipeline.assert_called_once_with(
            pipeline_id="pipeline-ghi789",
            name="updated-name",
            description="Updated description",
            pipeline_graph=None,
            parameters=None,
        )

    @patch("api.routes.pipelines.pipeline_manager")
    def test_update_pipeline_pipeline_graph(self, mock_pipeline_manager):
        updated_pipeline = schemas.Pipeline(
            id="pipeline-ghi789",
            name="user-defined-pipelines",
            version=1,
            description="A custom test pipeline",
            source=schemas.PipelineSource.USER_CREATED,
            type=schemas.PipelineType.GSTREAMER,
            pipeline_graph=schemas.PipelineGraph.model_validate_json(self.test_graph),
            parameters=None,
        )
        mock_pipeline_manager.update_pipeline.return_value = updated_pipeline

        payload = {
            "pipeline_graph": schemas.PipelineGraph.model_validate_json(
                self.test_graph
            ).model_dump()
        }
        response = self.client.patch("/pipelines/pipeline-ghi789", json=payload)

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["id"], "pipeline-ghi789")
        mock_pipeline_manager.update_pipeline.assert_called_once_with(
            pipeline_id="pipeline-ghi789",
            name=None,
            description=None,
            pipeline_graph=schemas.PipelineGraph.model_validate_json(self.test_graph),
            parameters=None,
        )

    @patch("api.routes.pipelines.pipeline_manager")
    def test_update_pipeline_empty_payload(self, mock_pipeline_manager):
        response = self.client.patch("/pipelines/pipeline-ghi789", json={})

        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.json(),
            schemas.MessageResponse(
                message="At least one of 'name', 'description', 'parameters' or 'pipeline_graph' must be provided."
            ).model_dump(),
        )
        mock_pipeline_manager.update_pipeline.assert_not_called()

    @patch("api.routes.pipelines.pipeline_manager")
    def test_update_pipeline_empty_name_rejected(self, mock_pipeline_manager):
        payload = {"name": ""}
        response = self.client.patch("/pipelines/pipeline-ghi789", json=payload)

        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.json(),
            schemas.MessageResponse(
                message="Field 'name' must not be empty."
            ).model_dump(),
        )
        mock_pipeline_manager.update_pipeline.assert_not_called()

    @patch("api.routes.pipelines.pipeline_manager")
    def test_update_pipeline_empty_description_rejected(self, mock_pipeline_manager):
        payload = {"description": "   "}
        response = self.client.patch("/pipelines/pipeline-ghi789", json=payload)

        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.json(),
            schemas.MessageResponse(
                message="Field 'description' must not be empty."
            ).model_dump(),
        )
        mock_pipeline_manager.update_pipeline.assert_not_called()

    @patch("api.routes.pipelines.pipeline_manager")
    def test_update_pipeline_empty_pipeline_graph_rejected(self, mock_pipeline_manager):
        payload = {"pipeline_graph": {"nodes": [], "edges": []}}
        response = self.client.patch("/pipelines/pipeline-ghi789", json=payload)

        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.json(),
            schemas.MessageResponse(
                message="Field 'pipeline_graph' must contain at least one node and one edge."
            ).model_dump(),
        )
        mock_pipeline_manager.update_pipeline.assert_not_called()

    @patch("api.routes.pipelines.pipeline_manager")
    def test_update_pipeline_not_found(self, mock_pipeline_manager):
        mock_pipeline_manager.update_pipeline.side_effect = ValueError(
            "Pipeline with id 'nonexistent-id' not found."
        )

        payload = {"description": "Updated description"}
        response = self.client.patch("/pipelines/nonexistent-id", json=payload)

        self.assertEqual(response.status_code, 404)
        self.assertEqual(
            response.json(),
            schemas.MessageResponse(
                message="Pipeline with id 'nonexistent-id' not found."
            ).model_dump(),
        )

    @patch("api.routes.pipelines.pipeline_manager")
    def test_update_pipeline_server_error(self, mock_pipeline_manager):
        mock_pipeline_manager.update_pipeline.side_effect = Exception(
            "Unexpected error"
        )

        payload = {"description": "Updated description"}
        response = self.client.patch("/pipelines/pipeline-ghi789", json=payload)

        self.assertEqual(response.status_code, 500)
        self.assertEqual(
            response.json(),
            schemas.MessageResponse(
                message="Unexpected error: Unexpected error"
            ).model_dump(),
        )

    # ------------------------------------------------------------------
    # /pipelines/validate
    # ------------------------------------------------------------------

    @patch("api.routes.pipelines.validation_manager")
    def test_validate_pipeline_accepts_request_and_returns_job_id(
        self, mock_validation_manager
    ):
        """
        The /pipelines/validate endpoint should:

        * accept a PipelineValidation request body,
        * delegate to validation_manager.run_validation,
        * return HTTP 202 with a ValidationJobResponse payload.
        """
        mock_validation_manager.run_validation.return_value = "val-job-123"

        body = {
            "pipeline_graph": schemas.PipelineGraph.model_validate_json(
                self.test_graph
            ).model_dump(),
            # Explicitly omit 'parameters' to ensure it is treated as optional.
        }

        response = self.client.post("/pipelines/validate", json=body)

        self.assertEqual(response.status_code, 202)
        self.assertEqual(
            response.json(),
            schemas.ValidationJobResponse(job_id="val-job-123").model_dump(),
        )

        # Ensure the manager was called exactly once with a PipelineValidation object.
        args, kwargs = mock_validation_manager.run_validation.call_args
        self.assertEqual(len(args), 1)
        validation_request = args[0]
        self.assertIsInstance(validation_request, schemas.PipelineValidation)
        self.assertIsNotNone(validation_request.pipeline_graph)
        self.assertIsNone(validation_request.parameters)

    @patch("api.routes.pipelines.validation_manager")
    def test_validate_pipeline_returns_400_on_value_error(
        self, mock_validation_manager
    ):
        """
        When ValidationManager.run_validation raises ValueError (e.g. invalid
        max-runtime), the endpoint must return HTTP 400 with a
        MessageResponse payload.
        """
        mock_validation_manager.run_validation.side_effect = ValueError(
            "Parameter 'max-runtime' must be greater than or equal to 1."
        )

        body = {
            "pipeline_graph": schemas.PipelineGraph.model_validate_json(
                self.test_graph
            ).model_dump(),
            "parameters": {"max-runtime": 0},
        }

        response = self.client.post("/pipelines/validate", json=body)

        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.json(),
            schemas.MessageResponse(
                message="Parameter 'max-runtime' must be greater than or equal to 1."
            ).model_dump(),
        )

        self.assertTrue(mock_validation_manager.run_validation.called)

    @patch("api.routes.pipelines.validation_manager")
    def test_validate_pipeline_returns_500_on_unexpected_error(
        self, mock_validation_manager
    ):
        """
        Any unexpected exception raised by ValidationManager.run_validation
        should be translated to HTTP 500 with a generic MessageResponse.
        """
        mock_validation_manager.run_validation.side_effect = RuntimeError("boom!")

        body = {
            "pipeline_graph": schemas.PipelineGraph.model_validate_json(
                self.test_graph
            ).model_dump(),
        }

        response = self.client.post("/pipelines/validate", json=body)

        self.assertEqual(response.status_code, 500)
        self.assertEqual(
            response.json(),
            schemas.MessageResponse(message="Unexpected error: boom!").model_dump(),
        )

        self.assertTrue(mock_validation_manager.run_validation.called)


if __name__ == "__main__":
    unittest.main()

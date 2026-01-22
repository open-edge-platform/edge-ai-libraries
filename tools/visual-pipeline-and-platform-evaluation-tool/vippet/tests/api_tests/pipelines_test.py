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
                pipeline_graph_simple=schemas.PipelineGraph.model_validate_json(
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
                pipeline_graph_simple=schemas.PipelineGraph.model_validate_json(
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
            pipeline_graph_simple=schemas.PipelineGraph.model_validate_json(
                self.test_graph
            ),
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
            pipeline_graph_simple=schemas.PipelineGraph.model_validate_json(
                self.test_graph
            ),
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
            pipeline_graph_simple=schemas.PipelineGraph.model_validate_json(
                self.test_graph
            ),
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
            pipeline_graph_simple=None,
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
            pipeline_graph_simple=schemas.PipelineGraph.model_validate_json(
                self.test_graph
            ),
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
            pipeline_graph_simple=None,
            parameters=None,
        )

    @patch("api.routes.pipelines.pipeline_manager")
    def test_update_pipeline_empty_payload(self, mock_pipeline_manager):
        response = self.client.patch("/pipelines/pipeline-ghi789", json={})

        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.json(),
            schemas.MessageResponse(
                message="At least one of 'name', 'description', 'parameters', 'pipeline_graph' or 'pipeline_graph_simple' must be provided."
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
    def test_update_pipeline_empty_pipeline_graph_simple_rejected(
        self, mock_pipeline_manager
    ):
        """
        Test that updating with empty pipeline_graph_simple is rejected with 400.

        This validates the endpoint check for at least one node and one edge
        in the simple view graph.
        """
        payload = {"pipeline_graph_simple": {"nodes": [], "edges": []}}
        response = self.client.patch("/pipelines/pipeline-ghi789", json=payload)

        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.json(),
            schemas.MessageResponse(
                message="Field 'pipeline_graph_simple' must contain at least one node and one edge."
            ).model_dump(),
        )
        mock_pipeline_manager.update_pipeline.assert_not_called()

    @patch("api.routes.pipelines.pipeline_manager")
    def test_update_pipeline_both_graphs_provided_rejected(self, mock_pipeline_manager):
        """
        Test that providing both pipeline_graph and pipeline_graph_simple is rejected.

        This validates the mutual exclusivity requirement - only one graph type
        should be provided at a time.
        """
        payload = {
            "pipeline_graph": schemas.PipelineGraph.model_validate_json(
                self.test_graph
            ).model_dump(),
            "pipeline_graph_simple": schemas.PipelineGraph.model_validate_json(
                self.test_graph
            ).model_dump(),
        }
        response = self.client.patch("/pipelines/pipeline-ghi789", json=payload)

        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.json(),
            schemas.MessageResponse(
                message="Cannot update both 'pipeline_graph' and 'pipeline_graph_simple' at the same time. Please provide only one."
            ).model_dump(),
        )
        mock_pipeline_manager.update_pipeline.assert_not_called()

    @patch("api.routes.pipelines.pipeline_manager")
    def test_update_pipeline_simple_view_success(self, mock_pipeline_manager):
        """
        Test successful update using pipeline_graph_simple.

        This validates that when only pipeline_graph_simple is provided,
        the endpoint correctly passes it to the manager and returns the
        updated pipeline with both views.
        """
        updated_pipeline = schemas.Pipeline(
            id="pipeline-ghi789",
            name="user-defined-pipelines",
            version=1,
            description="A custom test pipeline",
            source=schemas.PipelineSource.USER_CREATED,
            type=schemas.PipelineType.GSTREAMER,
            pipeline_graph=schemas.PipelineGraph.model_validate_json(self.test_graph),
            pipeline_graph_simple=schemas.PipelineGraph.model_validate_json(
                self.test_graph
            ),
            parameters=None,
        )
        mock_pipeline_manager.update_pipeline.return_value = updated_pipeline

        payload = {
            "pipeline_graph_simple": schemas.PipelineGraph.model_validate_json(
                self.test_graph
            ).model_dump()
        }
        response = self.client.patch("/pipelines/pipeline-ghi789", json=payload)

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["id"], "pipeline-ghi789")
        # Verify both graph views are present in response
        self.assertIn("pipeline_graph", data)
        self.assertIn("pipeline_graph_simple", data)
        mock_pipeline_manager.update_pipeline.assert_called_once_with(
            pipeline_id="pipeline-ghi789",
            name=None,
            description=None,
            pipeline_graph=None,
            pipeline_graph_simple=schemas.PipelineGraph.model_validate_json(
                self.test_graph
            ),
            parameters=None,
        )

    @patch("api.routes.pipelines.pipeline_manager")
    def test_update_pipeline_simple_view_structural_change_rejected(
        self, mock_pipeline_manager
    ):
        """
        Test that structural changes in simple view are rejected with 400.

        This validates that the manager correctly detects and rejects
        unsupported operations like adding/removing nodes or edges in
        simple view, and the endpoint returns appropriate error message.
        """
        mock_pipeline_manager.update_pipeline.side_effect = ValueError(
            "Node additions are not supported in simple view. Added nodes: 5. "
            "Please use advanced view to add new nodes."
        )

        payload = {
            "pipeline_graph_simple": schemas.PipelineGraph.model_validate_json(
                self.test_graph
            ).model_dump()
        }
        response = self.client.patch("/pipelines/pipeline-ghi789", json=payload)

        self.assertEqual(response.status_code, 400)
        self.assertIn("Node additions are not supported", response.json()["message"])

    @patch("api.routes.pipelines.pipeline_manager")
    def test_update_pipeline_simple_view_edge_change_rejected(
        self, mock_pipeline_manager
    ):
        """
        Test that edge changes in simple view are rejected with 400.

        This validates that when a user tries to modify edges in simple view,
        the manager correctly rejects it and the endpoint returns appropriate
        error message.
        """
        mock_pipeline_manager.update_pipeline.side_effect = ValueError(
            "Edge modifications are not supported in simple view. Modified edges: "
            "id=1 changed from (0 -> 2) to (0 -> 3). Please use advanced view to "
            "modify graph structure."
        )

        payload = {
            "pipeline_graph_simple": schemas.PipelineGraph.model_validate_json(
                self.test_graph
            ).model_dump()
        }
        response = self.client.patch("/pipelines/pipeline-ghi789", json=payload)

        self.assertEqual(response.status_code, 400)
        self.assertIn(
            "Edge modifications are not supported", response.json()["message"]
        )

    @patch("api.routes.pipelines.pipeline_manager")
    def test_update_pipeline_advanced_view_success(self, mock_pipeline_manager):
        """
        Test successful update using pipeline_graph (advanced view).

        This validates that when pipeline_graph is provided, the endpoint
        correctly passes it to the manager, which generates a new simple view,
        and returns the updated pipeline with both views.
        """
        updated_pipeline = schemas.Pipeline(
            id="pipeline-ghi789",
            name="user-defined-pipelines",
            version=1,
            description="Updated with new advanced graph",
            source=schemas.PipelineSource.USER_CREATED,
            type=schemas.PipelineType.GSTREAMER,
            pipeline_graph=schemas.PipelineGraph.model_validate_json(self.test_graph),
            pipeline_graph_simple=schemas.PipelineGraph.model_validate_json(
                self.test_graph
            ),
            parameters=None,
        )
        mock_pipeline_manager.update_pipeline.return_value = updated_pipeline

        payload = {
            "description": "Updated with new advanced graph",
            "pipeline_graph": schemas.PipelineGraph.model_validate_json(
                self.test_graph
            ).model_dump(),
        }
        response = self.client.patch("/pipelines/pipeline-ghi789", json=payload)

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["id"], "pipeline-ghi789")
        self.assertEqual(data["description"], "Updated with new advanced graph")
        # Verify both graph views are present in response
        self.assertIn("pipeline_graph", data)
        self.assertIn("pipeline_graph_simple", data)
        mock_pipeline_manager.update_pipeline.assert_called_once()

    @patch("api.routes.pipelines.pipeline_manager")
    def test_update_pipeline_validation_error_returns_400(self, mock_pipeline_manager):
        """
        Test that validation errors from manager result in 400 response.

        This validates that when the manager raises ValueError for validation
        issues (not "not found"), the endpoint returns 400 with the error message.
        """
        mock_pipeline_manager.update_pipeline.side_effect = ValueError(
            "Invalid graph: circular graph detected or no start nodes found"
        )

        payload = {
            "pipeline_graph": schemas.PipelineGraph.model_validate_json(
                self.test_graph
            ).model_dump()
        }
        response = self.client.patch("/pipelines/pipeline-ghi789", json=payload)

        self.assertEqual(response.status_code, 400)
        self.assertIn("Invalid graph", response.json()["message"])

    @patch("api.routes.pipelines.pipeline_manager")
    def test_get_pipelines_includes_both_views(self, mock_pipeline_manager):
        """
        Test that GET /pipelines returns pipelines with both graph views.

        This validates that the list endpoint includes both pipeline_graph
        (advanced view) and pipeline_graph_simple (simple view) for each pipeline.
        """
        mock_pipeline_manager.get_pipelines.return_value = [
            schemas.Pipeline(
                id="pipeline-abc123",
                name="test-pipeline",
                version=1,
                description="Test pipeline with both views",
                source=schemas.PipelineSource.USER_CREATED,
                type=schemas.PipelineType.GSTREAMER,
                pipeline_graph=schemas.PipelineGraph.model_validate_json(
                    self.test_graph
                ),
                pipeline_graph_simple=schemas.PipelineGraph.model_validate_json(
                    self.test_graph
                ),
                parameters=None,
            ),
        ]

        response = self.client.get("/pipelines")

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIsInstance(data, list)
        self.assertEqual(len(data), 1)

        # Verify both graph views are present
        pipeline = data[0]
        self.assertIn("pipeline_graph", pipeline)
        self.assertIn("pipeline_graph_simple", pipeline)
        self.assertIsNotNone(pipeline["pipeline_graph"])
        self.assertIsNotNone(pipeline["pipeline_graph_simple"])

    @patch("api.routes.pipelines.pipeline_manager")
    def test_get_pipeline_by_id_includes_both_views(self, mock_pipeline_manager):
        """
        Test that GET /pipelines/{id} returns pipeline with both graph views.

        This validates that the single pipeline endpoint includes both
        pipeline_graph (advanced view) and pipeline_graph_simple (simple view).
        """
        mock_pipeline_manager.get_pipeline_by_id.return_value = schemas.Pipeline(
            id="pipeline-ghi789",
            name="test-pipeline",
            version=1,
            description="Test pipeline with both views",
            source=schemas.PipelineSource.USER_CREATED,
            type=schemas.PipelineType.GSTREAMER,
            pipeline_graph=schemas.PipelineGraph.model_validate_json(self.test_graph),
            pipeline_graph_simple=schemas.PipelineGraph.model_validate_json(
                self.test_graph
            ),
            parameters=None,
        )

        response = self.client.get("/pipelines/pipeline-ghi789")

        self.assertEqual(response.status_code, 200)
        data = response.json()

        # Verify both graph views are present
        self.assertIn("pipeline_graph", data)
        self.assertIn("pipeline_graph_simple", data)
        self.assertIsNotNone(data["pipeline_graph"])
        self.assertIsNotNone(data["pipeline_graph_simple"])

    @patch("api.routes.pipelines.pipeline_manager")
    def test_create_pipeline_generates_both_views(self, mock_pipeline_manager):
        """
        Test that POST /pipelines creates pipeline with both graph views.

        This validates that when a pipeline is created from a GStreamer
        pipeline string, the manager generates both advanced and simple
        views, and the ID is returned in the response.
        """
        mock_pipeline = schemas.Pipeline(
            id="pipeline-newtest",
            name="new-pipeline",
            version=1,
            description="New pipeline with both views",
            source=schemas.PipelineSource.USER_CREATED,
            type=schemas.PipelineType.GSTREAMER,
            pipeline_graph=schemas.PipelineGraph.model_validate_json(self.test_graph),
            pipeline_graph_simple=schemas.PipelineGraph.model_validate_json(
                self.test_graph
            ),
            parameters=None,
        )
        mock_pipeline_manager.add_pipeline.return_value = mock_pipeline

        new_pipeline = {
            "name": "new-pipeline",
            "version": 1,
            "description": "New pipeline with both views",
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
        # Verify add_pipeline was called (which should generate both views)
        mock_pipeline_manager.add_pipeline.assert_called_once()

    @patch("api.routes.pipelines.pipeline_manager")
    def test_update_pipeline_property_changes_only_in_simple_view(
        self, mock_pipeline_manager
    ):
        """
        Test that property-only changes in simple view are accepted.

        This validates that when only node properties are modified in simple view
        (no structural changes), the update succeeds and both views are returned.
        """
        # Create a modified test graph with changed property
        modified_graph_json = """
        {
            "nodes": [
                {
                    "id": "0",
                    "type": "filesrc",
                    "data": {
                        "location": "/tmp/different-file.mp4"
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

        updated_pipeline = schemas.Pipeline(
            id="pipeline-ghi789",
            name="user-defined-pipelines",
            version=1,
            description="Pipeline with property changes",
            source=schemas.PipelineSource.USER_CREATED,
            type=schemas.PipelineType.GSTREAMER,
            pipeline_graph=schemas.PipelineGraph.model_validate_json(
                modified_graph_json
            ),
            pipeline_graph_simple=schemas.PipelineGraph.model_validate_json(
                modified_graph_json
            ),
            parameters=None,
        )
        mock_pipeline_manager.update_pipeline.return_value = updated_pipeline

        payload = {
            "pipeline_graph_simple": schemas.PipelineGraph.model_validate_json(
                modified_graph_json
            ).model_dump()
        }
        response = self.client.patch("/pipelines/pipeline-ghi789", json=payload)

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["id"], "pipeline-ghi789")
        # Verify the property change was applied
        self.assertEqual(
            data["pipeline_graph"]["nodes"][0]["data"]["location"],
            "/tmp/different-file.mp4",
        )

    @patch("api.routes.pipelines.pipeline_manager")
    def test_update_pipeline_combined_fields_with_simple_view(
        self, mock_pipeline_manager
    ):
        """
        Test updating multiple fields including simple view at once.

        This validates that name, description, and pipeline_graph_simple
        can be updated together in a single request.
        """
        updated_pipeline = schemas.Pipeline(
            id="pipeline-ghi789",
            name="updated-pipeline-name",
            version=1,
            description="Updated description with simple view",
            source=schemas.PipelineSource.USER_CREATED,
            type=schemas.PipelineType.GSTREAMER,
            pipeline_graph=schemas.PipelineGraph.model_validate_json(self.test_graph),
            pipeline_graph_simple=schemas.PipelineGraph.model_validate_json(
                self.test_graph
            ),
            parameters=None,
        )
        mock_pipeline_manager.update_pipeline.return_value = updated_pipeline

        payload = {
            "name": "updated-pipeline-name",
            "description": "Updated description with simple view",
            "pipeline_graph_simple": schemas.PipelineGraph.model_validate_json(
                self.test_graph
            ).model_dump(),
        }
        response = self.client.patch("/pipelines/pipeline-ghi789", json=payload)

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["name"], "updated-pipeline-name")
        self.assertEqual(data["description"], "Updated description with simple view")
        mock_pipeline_manager.update_pipeline.assert_called_once_with(
            pipeline_id="pipeline-ghi789",
            name="updated-pipeline-name",
            description="Updated description with simple view",
            pipeline_graph=None,
            pipeline_graph_simple=schemas.PipelineGraph.model_validate_json(
                self.test_graph
            ),
            parameters=None,
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

import unittest
from datetime import datetime, timezone
from typing import Optional
from fastapi import FastAPI
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock

import api.api_schemas as schemas
from api.routes.pipelines import router as pipelines_router


# Helper to generate test timestamp as datetime
def _get_test_timestamp() -> datetime:
    return datetime(2026, 2, 5, 14, 30, 45, 123000, tzinfo=timezone.utc)


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

    def _create_test_variant(
        self,
        variant_id: str = "variant-abc123",
        name: str = "CPU",
        read_only: bool = False,
    ) -> schemas.Variant:
        """Helper to create a test variant with standard graph."""
        timestamp = _get_test_timestamp()
        return schemas.Variant(
            id=variant_id,
            name=name,
            read_only=read_only,
            pipeline_graph=schemas.PipelineGraph.model_validate_json(self.test_graph),
            pipeline_graph_simple=schemas.PipelineGraph.model_validate_json(
                self.test_graph
            ),
            created_at=timestamp,
            modified_at=timestamp,
        )

    def _create_test_pipeline(
        self,
        pipeline_id: str = "pipeline-abc123",
        name: str = "test-pipeline",
        description: str = "Test Pipeline Description",
        source: schemas.PipelineSource = schemas.PipelineSource.USER_CREATED,
        tags: Optional[list] = None,
        variants: Optional[list] = None,
        thumbnail: Optional[str] = None,
    ) -> schemas.Pipeline:
        """Helper to create a test pipeline with standard structure."""
        if tags is None:
            tags = []
        if variants is None:
            variants = [self._create_test_variant()]
        timestamp = _get_test_timestamp()
        return schemas.Pipeline(
            id=pipeline_id,
            name=name,
            description=description,
            source=source,
            tags=tags,
            variants=variants,
            thumbnail=thumbnail,
            created_at=timestamp,
            modified_at=timestamp,
        )

    @patch("api.routes.pipelines.PipelineManager")
    def test_get_pipelines_returns_list(self, mock_pipeline_manager_cls):
        mock_manager = MagicMock()
        mock_manager.get_pipelines.return_value = [
            self._create_test_pipeline(
                pipeline_id="pipeline-abc123",
                name="predefined-pipelines",
                description="Smart Network Video Recorder (NVR) Proxy Pipeline",
                source=schemas.PipelineSource.PREDEFINED,
                variants=[self._create_test_variant(read_only=True)],
            ),
            self._create_test_pipeline(
                pipeline_id="pipeline-def456",
                name="user-defined-pipelines",
                description="Test Pipeline Description",
                source=schemas.PipelineSource.USER_CREATED,
            ),
        ]
        mock_pipeline_manager_cls.return_value = mock_manager

        response = self.client.get("/pipelines")

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIsInstance(data, list)
        self.assertEqual(len(data), 2)

        # Check the contents of the first pipeline
        first_pipeline = data[0]
        self.assertEqual(first_pipeline["id"], "pipeline-abc123")
        self.assertEqual(first_pipeline["name"], "predefined-pipelines")
        self.assertEqual(
            first_pipeline["description"],
            "Smart Network Video Recorder (NVR) Proxy Pipeline",
        )
        self.assertIn("variants", first_pipeline)
        self.assertEqual(len(first_pipeline["variants"]), 1)

        # Verify timestamps are present (serialized as ISO strings by Pydantic)
        self.assertIn("created_at", first_pipeline)
        self.assertIn("modified_at", first_pipeline)

        # Verify variant timestamps
        self.assertIn("created_at", first_pipeline["variants"][0])
        self.assertIn("modified_at", first_pipeline["variants"][0])

        # Check the contents of the second pipeline
        second_pipeline = data[1]
        self.assertEqual(second_pipeline["id"], "pipeline-def456")
        self.assertEqual(second_pipeline["name"], "user-defined-pipelines")
        self.assertEqual(second_pipeline["description"], "Test Pipeline Description")
        self.assertIn("variants", second_pipeline)

    @patch("api.routes.pipelines.PipelineManager")
    def test_create_pipeline_valid(self, mock_pipeline_manager_cls):
        # Mock the return value to include the pipeline with ID
        mock_pipeline = self._create_test_pipeline(
            pipeline_id="pipeline-newtest",
            name="user-defined-pipelines",
            description="A custom test pipeline",
        )
        mock_manager = MagicMock()
        mock_manager.add_pipeline.return_value = mock_pipeline
        mock_pipeline_manager_cls.return_value = mock_manager

        timestamp = _get_test_timestamp()
        new_pipeline = {
            "name": "user-defined-pipelines",
            "description": "A custom test pipeline",
            "tags": [],
            "variants": [
                {
                    "id": "variant-1",
                    "name": "CPU",
                    "read_only": False,
                    "pipeline_graph": schemas.PipelineGraph.model_validate_json(
                        self.test_graph
                    ).model_dump(),
                    "pipeline_graph_simple": schemas.PipelineGraph.model_validate_json(
                        self.test_graph
                    ).model_dump(),
                    "created_at": timestamp.isoformat(),
                    "modified_at": timestamp.isoformat(),
                }
            ],
        }

        response = self.client.post("/pipelines", json=new_pipeline)

        self.assertEqual(response.status_code, 201)
        self.assertEqual(
            response.json(),
            schemas.PipelineCreationResponse(id="pipeline-newtest").model_dump(),
        )

    @patch("api.routes.pipelines.PipelineManager")
    def test_create_pipeline_duplicate(self, mock_pipeline_manager_cls):
        mock_manager = MagicMock()
        mock_manager.add_pipeline.side_effect = ValueError("Pipeline already exists.")
        mock_pipeline_manager_cls.return_value = mock_manager

        timestamp = _get_test_timestamp()
        duplicate_pipeline = {
            "name": "user-defined-pipelines",
            "description": "A custom test pipeline",
            "tags": [],
            "variants": [
                {
                    "id": "variant-1",
                    "name": "CPU",
                    "read_only": False,
                    "pipeline_graph": schemas.PipelineGraph.model_validate_json(
                        self.test_graph
                    ).model_dump(),
                    "pipeline_graph_simple": schemas.PipelineGraph.model_validate_json(
                        self.test_graph
                    ).model_dump(),
                    "created_at": timestamp.isoformat(),
                    "modified_at": timestamp.isoformat(),
                }
            ],
        }

        response = self.client.post("/pipelines", json=duplicate_pipeline)

        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.json(),
            schemas.MessageResponse(message="Pipeline already exists.").model_dump(),
        )

    @patch("api.routes.pipelines.PipelineManager")
    def test_create_pipeline_server_error(self, mock_pipeline_manager_cls):
        mock_manager = MagicMock()
        mock_manager.add_pipeline.side_effect = Exception("Unexpected error")
        mock_pipeline_manager_cls.return_value = mock_manager

        timestamp = _get_test_timestamp()
        new_pipeline = {
            "name": "user-defined-pipelines",
            "description": "A custom test pipeline",
            "tags": [],
            "variants": [
                {
                    "id": "variant-1",
                    "name": "CPU",
                    "read_only": False,
                    "pipeline_graph": schemas.PipelineGraph.model_validate_json(
                        self.test_graph
                    ).model_dump(),
                    "pipeline_graph_simple": schemas.PipelineGraph.model_validate_json(
                        self.test_graph
                    ).model_dump(),
                    "created_at": timestamp.isoformat(),
                    "modified_at": timestamp.isoformat(),
                }
            ],
        }

        response = self.client.post("/pipelines", json=new_pipeline)

        self.assertEqual(response.status_code, 500)
        self.assertEqual(
            response.json(),
            schemas.MessageResponse(
                message="Failed to create pipeline: Unexpected error"
            ).model_dump(),
        )

    @patch("api.routes.pipelines.PipelineManager")
    def test_get_pipeline_by_id_found(self, mock_pipeline_manager_cls):
        mock_manager = MagicMock()
        mock_manager.get_pipeline_by_id.return_value = self._create_test_pipeline(
            pipeline_id="pipeline-ghi789",
            name="user-defined-pipelines",
            description="A custom test pipeline",
        )
        mock_pipeline_manager_cls.return_value = mock_manager

        response = self.client.get("/pipelines/pipeline-ghi789")

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["id"], "pipeline-ghi789")
        self.assertEqual(data["name"], "user-defined-pipelines")
        self.assertEqual(data["description"], "A custom test pipeline")
        self.assertIn("variants", data)
        self.assertEqual(len(data["variants"]), 1)

        # Verify timestamps are present
        self.assertIn("created_at", data)
        self.assertIn("modified_at", data)

    @patch("api.routes.pipelines.PipelineManager")
    def test_get_pipeline_by_id_not_found(self, mock_pipeline_manager_cls):
        mock_manager = MagicMock()
        mock_manager.get_pipeline_by_id.side_effect = ValueError(
            "Pipeline with id 'nonexistent-id' not found."
        )
        mock_pipeline_manager_cls.return_value = mock_manager

        response = self.client.get("/pipelines/nonexistent-id")

        self.assertEqual(response.status_code, 404)
        self.assertEqual(
            response.json(),
            schemas.MessageResponse(
                message="Pipeline with id 'nonexistent-id' not found."
            ).model_dump(),
        )

    @patch("api.routes.pipelines.PipelineManager")
    def test_get_pipeline_by_id_server_error(self, mock_pipeline_manager_cls):
        mock_manager = MagicMock()
        mock_manager.get_pipeline_by_id.side_effect = Exception("Unexpected error")
        mock_pipeline_manager_cls.return_value = mock_manager

        response = self.client.get("/pipelines/pipeline-test123")

        self.assertEqual(response.status_code, 500)
        self.assertEqual(
            response.json(),
            schemas.MessageResponse(
                message="Unexpected error: Unexpected error"
            ).model_dump(),
        )

    @patch("api.routes.pipelines.PipelineManager")
    def test_update_pipeline_description(self, mock_pipeline_manager_cls):
        updated_pipeline = self._create_test_pipeline(
            pipeline_id="pipeline-ghi789",
            name="updated-name",
            description="Updated description",
        )
        mock_manager = MagicMock()
        mock_manager.update_pipeline.return_value = updated_pipeline
        mock_pipeline_manager_cls.return_value = mock_manager

        payload = {"name": "updated-name", "description": "Updated description"}
        response = self.client.patch("/pipelines/pipeline-ghi789", json=payload)

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["id"], "pipeline-ghi789")
        self.assertEqual(data["name"], "updated-name")
        self.assertEqual(data["description"], "Updated description")
        mock_manager.update_pipeline.assert_called_once_with(
            pipeline_id="pipeline-ghi789",
            name="updated-name",
            description="Updated description",
            tags=None,
        )

    @patch("api.routes.pipelines.PipelineManager")
    def test_update_pipeline_pipeline_graph(self, mock_pipeline_manager_cls):
        updated_pipeline = self._create_test_pipeline(
            pipeline_id="pipeline-ghi789",
            name="test-pipeline",
            description="Test description",
            tags=["tag1", "tag2"],
        )
        mock_manager = MagicMock()
        mock_manager.update_pipeline.return_value = updated_pipeline
        mock_pipeline_manager_cls.return_value = mock_manager

        payload = {"tags": ["tag1", "tag2"]}
        response = self.client.patch("/pipelines/pipeline-ghi789", json=payload)

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["tags"], ["tag1", "tag2"])
        mock_manager.update_pipeline.assert_called_once_with(
            pipeline_id="pipeline-ghi789",
            name=None,
            description=None,
            tags=["tag1", "tag2"],
        )

    @patch("api.routes.pipelines.PipelineManager")
    def test_update_pipeline_empty_payload(self, mock_pipeline_manager_cls):
        """Test that empty payload is rejected by Pydantic validation with 422."""
        response = self.client.patch("/pipelines/pipeline-ghi789", json={})

        # Pydantic validation returns 422
        self.assertEqual(response.status_code, 422)
        # Manager should not be called
        mock_pipeline_manager_cls.return_value.update_pipeline.assert_not_called()

    @patch("api.routes.pipelines.PipelineManager")
    def test_update_pipeline_empty_name_rejected(self, mock_pipeline_manager_cls):
        """Test that empty name is rejected by Pydantic validation with 422."""
        payload = {"name": ""}
        response = self.client.patch("/pipelines/pipeline-ghi789", json=payload)

        # Pydantic validation returns 422
        self.assertEqual(response.status_code, 422)
        # Manager should not be called
        mock_pipeline_manager_cls.return_value.update_pipeline.assert_not_called()

    @patch("api.routes.pipelines.PipelineManager")
    def test_update_pipeline_whitespace_name_rejected(self, mock_pipeline_manager_cls):
        """Test that whitespace-only name is rejected by Pydantic validation with 422."""
        payload = {"name": "   "}
        response = self.client.patch("/pipelines/pipeline-ghi789", json=payload)

        # Pydantic validation returns 422
        self.assertEqual(response.status_code, 422)
        # Manager should not be called
        mock_pipeline_manager_cls.return_value.update_pipeline.assert_not_called()

    @patch("api.routes.pipelines.PipelineManager")
    def test_update_pipeline_empty_description_rejected(
        self, mock_pipeline_manager_cls
    ):
        """Test that whitespace-only description is rejected by Pydantic validation with 422."""
        payload = {"description": "   "}
        response = self.client.patch("/pipelines/pipeline-ghi789", json=payload)

        # Pydantic validation returns 422
        self.assertEqual(response.status_code, 422)
        # Manager should not be called
        mock_pipeline_manager_cls.return_value.update_pipeline.assert_not_called()

    @patch("api.routes.pipelines.PipelineManager")
    def test_update_pipeline_not_found(self, mock_pipeline_manager_cls):
        mock_pipeline_manager_cls.return_value.update_pipeline.side_effect = ValueError(
            "Pipeline with id 'pipeline-ghi789' not found."
        )

        payload = {"name": "new-name"}
        response = self.client.patch("/pipelines/pipeline-ghi789", json=payload)

        self.assertEqual(response.status_code, 404)
        self.assertIn("not found", response.json()["message"])

    @patch("api.routes.pipelines.PipelineManager")
    def test_delete_pipeline_success(self, mock_pipeline_manager_cls):
        mock_pipeline_manager_cls.return_value.delete_pipeline_by_id.return_value = None

        response = self.client.delete("/pipelines/pipeline-ghi789")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            schemas.MessageResponse(message="Pipeline deleted").model_dump(),
        )

    @patch("api.routes.pipelines.PipelineManager")
    def test_delete_pipeline_not_found(self, mock_pipeline_manager_cls):
        mock_pipeline_manager_cls.return_value.delete_pipeline_by_id.side_effect = (
            ValueError("Pipeline with id 'nonexistent-id' not found.")
        )

        response = self.client.delete("/pipelines/nonexistent-id")

        self.assertEqual(response.status_code, 404)
        self.assertIn("not found", response.json()["message"])

    @patch("api.routes.pipelines.PipelineManager")
    def test_delete_predefined_pipeline_rejected(self, mock_pipeline_manager_cls):
        """Test that deleting a PREDEFINED pipeline is rejected with 400."""
        mock_pipeline_manager_cls.return_value.delete_pipeline_by_id.side_effect = (
            ValueError("Cannot delete PREDEFINED pipeline 'pipeline-abc123'.")
        )

        response = self.client.delete("/pipelines/pipeline-abc123")

        self.assertEqual(response.status_code, 400)
        self.assertIn("PREDEFINED", response.json()["message"])

    # ------------------------------------------------------------------
    # Variant endpoints tests
    # ------------------------------------------------------------------

    @patch("api.routes.pipelines.PipelineManager")
    def test_create_variant_success(self, mock_pipeline_manager_cls):
        """Test successful variant creation."""
        new_variant = self._create_test_variant(variant_id="variant-new123", name="GPU")
        mock_pipeline_manager_cls.return_value.add_variant.return_value = new_variant

        payload = {
            "name": "GPU",
            "pipeline_graph": schemas.PipelineGraph.model_validate_json(
                self.test_graph
            ).model_dump(),
            "pipeline_graph_simple": schemas.PipelineGraph.model_validate_json(
                self.test_graph
            ).model_dump(),
        }

        response = self.client.post("/pipelines/pipeline-abc123/variants", json=payload)

        self.assertEqual(response.status_code, 201)
        data = response.json()
        self.assertEqual(data["id"], "variant-new123")
        self.assertEqual(data["name"], "GPU")
        self.assertEqual(data["read_only"], False)
        mock_pipeline_manager_cls.return_value.add_variant.assert_called_once()

    @patch("api.routes.pipelines.PipelineManager")
    def test_create_variant_pipeline_not_found(self, mock_pipeline_manager_cls):
        """Test variant creation when pipeline does not exist."""
        mock_pipeline_manager_cls.return_value.add_variant.side_effect = ValueError(
            "Pipeline with id 'nonexistent' not found."
        )

        payload = {
            "name": "GPU",
            "pipeline_graph": schemas.PipelineGraph.model_validate_json(
                self.test_graph
            ).model_dump(),
            "pipeline_graph_simple": schemas.PipelineGraph.model_validate_json(
                self.test_graph
            ).model_dump(),
        }

        response = self.client.post("/pipelines/nonexistent/variants", json=payload)

        self.assertEqual(response.status_code, 404)
        self.assertIn("not found", response.json()["message"])

    @patch("api.routes.pipelines.PipelineManager")
    def test_delete_variant_success(self, mock_pipeline_manager_cls):
        """Test successful variant deletion."""
        mock_pipeline_manager_cls.return_value.delete_variant.return_value = None

        response = self.client.delete("/pipelines/pipeline-abc123/variants/variant-123")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            schemas.MessageResponse(message="Variant deleted").model_dump(),
        )
        mock_pipeline_manager_cls.return_value.delete_variant.assert_called_once_with(
            "pipeline-abc123", "variant-123"
        )

    @patch("api.routes.pipelines.PipelineManager")
    def test_delete_variant_not_found(self, mock_pipeline_manager_cls):
        """Test variant deletion when variant does not exist."""
        mock_pipeline_manager_cls.return_value.delete_variant.side_effect = ValueError(
            "Variant 'variant-123' not found in pipeline 'pipeline-abc123'."
        )

        response = self.client.delete("/pipelines/pipeline-abc123/variants/variant-123")

        self.assertEqual(response.status_code, 404)
        self.assertIn("not found", response.json()["message"])

    @patch("api.routes.pipelines.PipelineManager")
    def test_delete_variant_read_only_rejected(self, mock_pipeline_manager_cls):
        """Test that deleting a read-only variant is rejected."""
        mock_pipeline_manager_cls.return_value.delete_variant.side_effect = ValueError(
            "Cannot delete read-only variant 'variant-123'."
        )

        response = self.client.delete("/pipelines/pipeline-abc123/variants/variant-123")

        self.assertEqual(response.status_code, 400)
        self.assertIn("read-only", response.json()["message"])

    @patch("api.routes.pipelines.PipelineManager")
    def test_delete_variant_last_variant_rejected(self, mock_pipeline_manager_cls):
        """Test that deleting the last variant is rejected."""
        mock_pipeline_manager_cls.return_value.delete_variant.side_effect = ValueError(
            "Cannot delete variant 'variant-123' as it is the last variant in pipeline 'pipeline-abc123'."
        )

        response = self.client.delete("/pipelines/pipeline-abc123/variants/variant-123")

        self.assertEqual(response.status_code, 400)
        self.assertIn("last variant", response.json()["message"])

    @patch("api.routes.pipelines.PipelineManager")
    def test_update_variant_name_success(self, mock_pipeline_manager_cls):
        """Test successful variant name update."""
        updated_variant = self._create_test_variant(
            variant_id="variant-123", name="GPU-optimized"
        )
        mock_pipeline_manager_cls.return_value.update_variant.return_value = (
            updated_variant
        )

        payload = {"name": "GPU-optimized"}

        response = self.client.patch(
            "/pipelines/pipeline-abc123/variants/variant-123", json=payload
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["name"], "GPU-optimized")
        mock_pipeline_manager_cls.return_value.update_variant.assert_called_once_with(
            pipeline_id="pipeline-abc123",
            variant_id="variant-123",
            name="GPU-optimized",
            pipeline_graph=None,
            pipeline_graph_simple=None,
        )

    @patch("api.routes.pipelines.PipelineManager")
    def test_update_variant_pipeline_graph_success(self, mock_pipeline_manager_cls):
        """Test successful variant pipeline_graph update."""
        updated_variant = self._create_test_variant(variant_id="variant-123")
        mock_pipeline_manager_cls.return_value.update_variant.return_value = (
            updated_variant
        )

        payload = {
            "pipeline_graph": schemas.PipelineGraph.model_validate_json(
                self.test_graph
            ).model_dump()
        }

        response = self.client.patch(
            "/pipelines/pipeline-abc123/variants/variant-123", json=payload
        )

        self.assertEqual(response.status_code, 200)
        mock_pipeline_manager_cls.return_value.update_variant.assert_called_once()

    @patch("api.routes.pipelines.PipelineManager")
    def test_update_variant_read_only_rejected(self, mock_pipeline_manager_cls):
        """Test that updating a read-only variant is rejected."""
        mock_pipeline_manager_cls.return_value.update_variant.side_effect = ValueError(
            "Cannot update read-only variant 'variant-123'."
        )

        payload = {"name": "new-name"}

        response = self.client.patch(
            "/pipelines/pipeline-abc123/variants/variant-123", json=payload
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("read-only", response.json()["message"])

    @patch("api.routes.pipelines.PipelineManager")
    def test_update_variant_not_found(self, mock_pipeline_manager_cls):
        """Test variant update when variant does not exist."""
        mock_pipeline_manager_cls.return_value.update_variant.side_effect = ValueError(
            "Variant 'variant-123' not found in pipeline 'pipeline-abc123'."
        )

        payload = {"name": "new-name"}

        response = self.client.patch(
            "/pipelines/pipeline-abc123/variants/variant-123", json=payload
        )

        self.assertEqual(response.status_code, 404)
        self.assertIn("not found", response.json()["message"])

    @patch("api.routes.pipelines.PipelineManager")
    def test_update_variant_both_graphs_rejected(self, mock_pipeline_manager_cls):
        """Test that providing both pipeline_graph and pipeline_graph_simple is rejected.

        This validation is done by the VariantUpdate pydantic model.
        """
        payload = {
            "pipeline_graph": schemas.PipelineGraph.model_validate_json(
                self.test_graph
            ).model_dump(),
            "pipeline_graph_simple": schemas.PipelineGraph.model_validate_json(
                self.test_graph
            ).model_dump(),
        }

        response = self.client.patch(
            "/pipelines/pipeline-abc123/variants/variant-123", json=payload
        )

        # Pydantic validation returns 422
        self.assertEqual(response.status_code, 422)
        mock_pipeline_manager_cls.return_value.update_variant.assert_not_called()

    # ------------------------------------------------------------------
    # Optimize variant endpoint tests
    # ------------------------------------------------------------------

    @patch("api.routes.pipelines.OptimizationManager")
    @patch("api.routes.pipelines.PipelineManager")
    def test_optimize_variant_success(
        self, mock_pipeline_manager_cls, mock_optimization_manager_cls
    ):
        """Test successful variant optimization."""
        mock_variant = self._create_test_variant(variant_id="variant-123")
        mock_pipeline_manager_cls.return_value.get_variant_by_ids.return_value = (
            mock_variant
        )
        mock_optimization_manager_cls.return_value.run_optimization.return_value = (
            "opt-job-123"
        )

        payload = {"type": "preprocess", "parameters": None}

        response = self.client.post(
            "/pipelines/pipeline-abc123/variants/variant-123/optimize", json=payload
        )

        self.assertEqual(response.status_code, 202)
        self.assertEqual(response.json()["job_id"], "opt-job-123")
        mock_pipeline_manager_cls.return_value.get_variant_by_ids.assert_called_once_with(
            "pipeline-abc123", "variant-123"
        )
        mock_optimization_manager_cls.return_value.run_optimization.assert_called_once()

    @patch("api.routes.pipelines.OptimizationManager")
    @patch("api.routes.pipelines.PipelineManager")
    def test_optimize_variant_pipeline_not_found(
        self, mock_pipeline_manager_cls, mock_optimization_manager_cls
    ):
        """Test variant optimization when pipeline does not exist."""
        mock_pipeline_manager_cls.return_value.get_variant_by_ids.side_effect = (
            ValueError("Pipeline with id 'nonexistent' not found.")
        )

        payload = {"type": "preprocess", "parameters": None}

        response = self.client.post(
            "/pipelines/nonexistent/variants/variant-123/optimize", json=payload
        )

        self.assertEqual(response.status_code, 404)
        self.assertIn("not found", response.json()["message"])
        mock_optimization_manager_cls.return_value.run_optimization.assert_not_called()

    @patch("api.routes.pipelines.OptimizationManager")
    @patch("api.routes.pipelines.PipelineManager")
    def test_optimize_variant_variant_not_found(
        self, mock_pipeline_manager_cls, mock_optimization_manager_cls
    ):
        """Test variant optimization when variant does not exist."""
        mock_pipeline_manager_cls.return_value.get_variant_by_ids.side_effect = (
            ValueError(
                "Variant 'nonexistent-variant' not found in pipeline 'pipeline-abc123'."
            )
        )

        payload = {"type": "preprocess", "parameters": None}

        response = self.client.post(
            "/pipelines/pipeline-abc123/variants/nonexistent-variant/optimize",
            json=payload,
        )

        self.assertEqual(response.status_code, 404)
        self.assertIn("not found", response.json()["message"])
        mock_optimization_manager_cls.return_value.run_optimization.assert_not_called()

    # ------------------------------------------------------------------
    # /pipelines/validate
    # ------------------------------------------------------------------

    @patch("api.routes.pipelines.ValidationManager")
    def test_validate_pipeline_accepts_request_and_returns_job_id(
        self, mock_validation_manager_cls
    ):
        """
        The /pipelines/validate endpoint should:

        * accept a PipelineValidation request body,
        * delegate to validation_manager.run_validation,
        * return HTTP 202 with a ValidationJobResponse payload.
        """
        mock_manager = MagicMock()
        mock_manager.run_validation.return_value = "val-job-123"
        mock_validation_manager_cls.return_value = mock_manager

        body = {
            "pipeline_graph": schemas.PipelineGraph.model_validate_json(
                self.test_graph
            ).model_dump(),
        }

        response = self.client.post("/pipelines/validate", json=body)

        self.assertEqual(response.status_code, 202)
        self.assertEqual(
            response.json(),
            schemas.ValidationJobResponse(job_id="val-job-123").model_dump(),
        )

        # Ensure the manager was called exactly once with a PipelineValidation object.
        args, kwargs = mock_manager.run_validation.call_args
        self.assertEqual(len(args), 1)
        validation_request = args[0]
        self.assertIsInstance(validation_request, schemas.PipelineValidation)

    @patch("api.routes.pipelines.ValidationManager")
    def test_validate_pipeline_returns_400_on_value_error(
        self, mock_validation_manager_cls
    ):
        """
        When ValidationManager.run_validation raises ValueError (e.g. invalid
        max-runtime), the endpoint must return HTTP 400 with a
        MessageResponse payload.
        """
        mock_manager = MagicMock()
        mock_manager.run_validation.side_effect = ValueError(
            "Parameter 'max-runtime' must be greater than or equal to 1."
        )
        mock_validation_manager_cls.return_value = mock_manager

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

    @patch("api.routes.pipelines.ValidationManager")
    def test_validate_pipeline_returns_500_on_unexpected_error(
        self, mock_validation_manager_cls
    ):
        """
        Any unexpected exception raised by ValidationManager.run_validation
        should be translated to HTTP 500 with a generic MessageResponse.
        """
        mock_manager = MagicMock()
        mock_manager.run_validation.side_effect = RuntimeError("boom!")
        mock_validation_manager_cls.return_value = mock_manager

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

        self.assertTrue(mock_manager.run_validation.called)

    # ------------------------------------------------------------------
    # Pipeline with variants structure tests
    # ------------------------------------------------------------------

    @patch("api.routes.pipelines.PipelineManager")
    def test_get_pipelines_includes_variants(self, mock_pipeline_manager_cls):
        """Test that GET /pipelines returns pipelines with variants."""
        mock_pipeline_manager_cls.return_value.get_pipelines.return_value = [
            self._create_test_pipeline(
                pipeline_id="pipeline-abc123",
                name="test-pipeline",
                description="Test pipeline with variants",
                variants=[
                    self._create_test_variant(variant_id="variant-1", name="CPU"),
                    self._create_test_variant(variant_id="variant-2", name="GPU"),
                ],
            ),
        ]

        response = self.client.get("/pipelines")

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIsInstance(data, list)
        self.assertEqual(len(data), 1)

        # Verify variants are present
        pipeline = data[0]
        self.assertIn("variants", pipeline)
        self.assertEqual(len(pipeline["variants"]), 2)
        self.assertEqual(pipeline["variants"][0]["name"], "CPU")
        self.assertEqual(pipeline["variants"][1]["name"], "GPU")

        # Verify variant timestamps
        for variant in pipeline["variants"]:
            self.assertIn("created_at", variant)
            self.assertIn("modified_at", variant)

    @patch("api.routes.pipelines.PipelineManager")
    def test_get_pipeline_by_id_includes_variants(self, mock_pipeline_manager_cls):
        """Test that GET /pipelines/{id} returns pipeline with variants."""
        mock_pipeline_manager_cls.return_value.get_pipeline_by_id.return_value = (
            self._create_test_pipeline(
                pipeline_id="pipeline-ghi789",
                name="test-pipeline",
                description="Test pipeline with variants",
                variants=[
                    self._create_test_variant(variant_id="variant-1", name="CPU"),
                ],
            )
        )

        response = self.client.get("/pipelines/pipeline-ghi789")

        self.assertEqual(response.status_code, 200)
        data = response.json()

        # Verify variants are present
        self.assertIn("variants", data)
        self.assertEqual(len(data["variants"]), 1)
        variant = data["variants"][0]
        self.assertEqual(variant["id"], "variant-1")
        self.assertEqual(variant["name"], "CPU")
        self.assertIn("pipeline_graph", variant)
        self.assertIn("pipeline_graph_simple", variant)

    # ------------------------------------------------------------------
    # Convert graph endpoints tests
    # ------------------------------------------------------------------

    @patch("api.routes.pipelines.PipelineManager")
    def test_convert_advanced_to_simple_success(self, mock_pipeline_manager_cls):
        """Test successful conversion from advanced to simple graph."""
        from graph import Graph

        mock_manager = MagicMock()

        # Mock the conversion method to return a simple graph
        simple_graph_dict = {
            "nodes": [
                {"id": "0", "type": "filesrc", "data": {"location": "test.mp4"}},
                {"id": "1", "type": "autovideosink", "data": {}},
            ],
            "edges": [{"id": "0", "source": "0", "target": "1"}],
        }
        mock_simple_graph = Graph.from_dict(simple_graph_dict)
        mock_manager.validate_and_convert_advanced_to_simple.return_value = (
            mock_simple_graph
        )

        mock_pipeline_manager_cls.return_value = mock_manager

        payload = schemas.PipelineGraph.model_validate_json(
            self.test_graph
        ).model_dump()

        response = self.client.post(
            "/pipelines/pipeline-abc123/variants/variant-123/convert-to-simple",
            json=payload,
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("nodes", data)
        self.assertIn("edges", data)
        mock_manager.validate_and_convert_advanced_to_simple.assert_called_once()

    @patch("api.routes.pipelines.PipelineManager")
    def test_convert_advanced_to_simple_pipeline_not_found(
        self, mock_pipeline_manager_cls
    ):
        """Test conversion when pipeline not found."""
        mock_manager = MagicMock()
        mock_manager.validate_and_convert_advanced_to_simple.side_effect = ValueError(
            "Pipeline with id 'nonexistent' not found."
        )
        mock_pipeline_manager_cls.return_value = mock_manager

        payload = schemas.PipelineGraph.model_validate_json(
            self.test_graph
        ).model_dump()

        response = self.client.post(
            "/pipelines/nonexistent/variants/variant-123/convert-to-simple",
            json=payload,
        )

        self.assertEqual(response.status_code, 404)
        self.assertIn("not found", response.json()["message"])

    @patch("api.routes.pipelines.PipelineManager")
    def test_convert_advanced_to_simple_invalid_graph(self, mock_pipeline_manager_cls):
        """Test conversion with invalid graph."""
        mock_manager = MagicMock()
        mock_manager.validate_and_convert_advanced_to_simple.side_effect = ValueError(
            "Invalid pipeline_graph: cannot convert to valid GStreamer pipeline string."
        )
        mock_pipeline_manager_cls.return_value = mock_manager

        payload = schemas.PipelineGraph.model_validate_json(
            self.test_graph
        ).model_dump()

        response = self.client.post(
            "/pipelines/pipeline-abc123/variants/variant-123/convert-to-simple",
            json=payload,
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("Invalid", response.json()["message"])

    @patch("api.routes.pipelines.PipelineManager")
    def test_convert_simple_to_advanced_success(self, mock_pipeline_manager_cls):
        """Test successful conversion from simple to advanced graph."""
        from graph import Graph

        mock_variant = self._create_test_variant()
        mock_manager = MagicMock()
        mock_manager.get_variant_by_ids.return_value = mock_variant

        # Mock the conversion method to return an advanced graph
        advanced_graph_dict = {
            "nodes": [
                {"id": "0", "type": "filesrc", "data": {"location": "test.mp4"}},
                {"id": "1", "type": "queue", "data": {}},
                {"id": "2", "type": "autovideosink", "data": {}},
            ],
            "edges": [
                {"id": "0", "source": "0", "target": "1"},
                {"id": "1", "source": "1", "target": "2"},
            ],
        }
        mock_advanced_graph = Graph.from_dict(advanced_graph_dict)
        mock_manager.validate_and_convert_simple_to_advanced.return_value = (
            mock_advanced_graph
        )

        mock_pipeline_manager_cls.return_value = mock_manager

        payload = schemas.PipelineGraph.model_validate_json(
            self.test_graph
        ).model_dump()

        response = self.client.post(
            "/pipelines/pipeline-abc123/variants/variant-123/convert-to-advanced",
            json=payload,
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("nodes", data)
        self.assertIn("edges", data)
        mock_manager.get_variant_by_ids.assert_called_once_with(
            "pipeline-abc123", "variant-123"
        )

    @patch("api.routes.pipelines.PipelineManager")
    def test_convert_simple_to_advanced_pipeline_not_found(
        self, mock_pipeline_manager_cls
    ):
        """Test conversion when pipeline not found."""
        mock_manager = MagicMock()
        mock_manager.get_variant_by_ids.side_effect = ValueError(
            "Pipeline with id 'nonexistent' not found."
        )
        mock_pipeline_manager_cls.return_value = mock_manager

        payload = schemas.PipelineGraph.model_validate_json(
            self.test_graph
        ).model_dump()

        response = self.client.post(
            "/pipelines/nonexistent/variants/variant-123/convert-to-advanced",
            json=payload,
        )

        self.assertEqual(response.status_code, 404)
        self.assertIn("not found", response.json()["message"])

    @patch("api.routes.pipelines.PipelineManager")
    def test_convert_simple_to_advanced_structural_change_rejected(
        self, mock_pipeline_manager_cls
    ):
        """Test conversion with structural changes is rejected."""
        mock_variant = self._create_test_variant()
        mock_manager = MagicMock()
        mock_manager.get_variant_by_ids.return_value = mock_variant
        mock_manager.validate_and_convert_simple_to_advanced.side_effect = ValueError(
            "Invalid pipeline_graph_simple: Node additions are not supported."
        )
        mock_pipeline_manager_cls.return_value = mock_manager

        payload = schemas.PipelineGraph.model_validate_json(
            self.test_graph
        ).model_dump()

        response = self.client.post(
            "/pipelines/pipeline-abc123/variants/variant-123/convert-to-advanced",
            json=payload,
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("Invalid", response.json()["message"])


class TestPipelineThumbnailRedaction(unittest.TestCase):
    """Test that Pipeline.thumbnail is redacted when converting to string."""

    def test_pipeline_thumbnail_redacted_in_repr(self):
        """Test that thumbnail is not shown in repr() output."""
        timestamp = _get_test_timestamp()
        graph = schemas.PipelineGraph(
            nodes=[schemas.Node(id="0", type="fakesrc", data={})],
            edges=[],
        )
        variant = schemas.Variant(
            id="variant-1",
            name="CPU",
            read_only=False,
            pipeline_graph=graph,
            pipeline_graph_simple=graph,
            created_at=timestamp,
            modified_at=timestamp,
        )
        pipeline = schemas.Pipeline(
            id="test-pipeline",
            name="Test",
            description="Test description",
            source=schemas.PipelineSource.PREDEFINED,
            tags=[],
            variants=[variant],
            thumbnail="data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==",
            created_at=timestamp,
            modified_at=timestamp,
        )

        # Convert to repr string
        repr_str = repr(pipeline)

        # Thumbnail should NOT appear in repr output (redacted with repr=False)
        self.assertNotIn("iVBORw0KGgo", repr_str)
        # But other fields should be present
        self.assertIn("test-pipeline", repr_str)
        self.assertIn("Test", repr_str)

    def test_pipeline_thumbnail_present_in_dict(self):
        """Test that thumbnail IS present when converting to dict/json."""
        timestamp = _get_test_timestamp()
        graph = schemas.PipelineGraph(
            nodes=[schemas.Node(id="0", type="fakesrc", data={})],
            edges=[],
        )
        variant = schemas.Variant(
            id="variant-1",
            name="CPU",
            read_only=False,
            pipeline_graph=graph,
            pipeline_graph_simple=graph,
            created_at=timestamp,
            modified_at=timestamp,
        )
        thumbnail_data = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
        pipeline = schemas.Pipeline(
            id="test-pipeline",
            name="Test",
            description="Test description",
            source=schemas.PipelineSource.PREDEFINED,
            tags=[],
            variants=[variant],
            thumbnail=thumbnail_data,
            created_at=timestamp,
            modified_at=timestamp,
        )

        # Convert to dict (as used by API)
        pipeline_dict = pipeline.model_dump()

        # Thumbnail should be present in dict output
        self.assertEqual(pipeline_dict["thumbnail"], thumbnail_data)

    def test_pipeline_thumbnail_null_for_user_created(self):
        """Test that thumbnail is null for user-created pipelines."""
        timestamp = _get_test_timestamp()
        graph = schemas.PipelineGraph(
            nodes=[schemas.Node(id="0", type="fakesrc", data={})],
            edges=[],
        )
        variant = schemas.Variant(
            id="variant-1",
            name="CPU",
            read_only=False,
            pipeline_graph=graph,
            pipeline_graph_simple=graph,
            created_at=timestamp,
            modified_at=timestamp,
        )
        pipeline = schemas.Pipeline(
            id="test-pipeline",
            name="Test",
            description="Test description",
            source=schemas.PipelineSource.USER_CREATED,
            tags=[],
            variants=[variant],
            thumbnail=None,
            created_at=timestamp,
            modified_at=timestamp,
        )

        # Convert to dict
        pipeline_dict = pipeline.model_dump()

        # Thumbnail should be None for user-created pipelines
        self.assertIsNone(pipeline_dict["thumbnail"])


if __name__ == "__main__":
    unittest.main()

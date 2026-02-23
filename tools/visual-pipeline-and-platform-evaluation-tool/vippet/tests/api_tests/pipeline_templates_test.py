import unittest
from datetime import datetime, timezone
from typing import Optional
from fastapi import FastAPI
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock

import api.api_schemas as schemas
from api.routes.pipeline_templates import router as pipeline_templates_router


# Helper to generate test timestamp as datetime
def _get_test_timestamp() -> datetime:
    return datetime(2026, 2, 5, 14, 30, 45, 123000, tzinfo=timezone.utc)


class TestPipelineTemplatesAPI(unittest.TestCase):
    test_graph = """
    {
        "nodes": [
            {
                "id": "0",
                "type": "filesrc",
                "data": {
                    "location": ""
                }
            },
            {
                "id": "1",
                "type": "gvadetect",
                "data": {
                    "model": ""
                }
            },
            {
                "id": "2",
                "type": "gvaclassify",
                "data": {
                    "model": ""
                }
            },
            {
                "id": "3",
                "type": "autovideosink",
                "data": {}
            }
        ],
        "edges": [
            {
                "id": "0",
                "source": "0",
                "target": "1"
            },
            {
                "id": "1",
                "source": "1",
                "target": "2"
            },
            {
                "id": "2",
                "source": "2",
                "target": "3"
            }
        ]
    }
    """

    @classmethod
    def setUpClass(cls):
        """Set up test client once for all tests."""
        app = FastAPI()
        app.include_router(pipeline_templates_router, prefix="/pipeline-templates")
        cls.client = TestClient(app)

    def _create_test_variant(
        self,
        variant_id: str = "cpu",
        name: str = "CPU",
        read_only: bool = True,
    ) -> schemas.Variant:
        """Helper to create a test template variant (read-only by default)."""
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

    def _create_test_template(
        self,
        pipeline_id: str = "detect-only",
        name: str = "Detect Only",
        description: str = "Template pipeline with a single object detection model.",
        tags: Optional[list] = None,
        variants: Optional[list] = None,
    ) -> schemas.Pipeline:
        """Helper to create a test pipeline template."""
        if tags is None:
            tags = ["template", "detection"]
        if variants is None:
            variants = [self._create_test_variant()]
        timestamp = _get_test_timestamp()
        return schemas.Pipeline(
            id=pipeline_id,
            name=name,
            description=description,
            source=schemas.PipelineSource.TEMPLATE,
            tags=tags,
            variants=variants,
            thumbnail=None,
            created_at=timestamp,
            modified_at=timestamp,
        )

    # ------------------------------------------------------------------ #
    #  GET /pipeline-templates                                             #
    # ------------------------------------------------------------------ #

    @patch("api.routes.pipeline_templates.PipelineTemplateManager")
    def test_get_pipeline_templates_returns_list(self, mock_manager_cls):
        """Test GET /pipeline-templates returns 200 with a list of templates."""
        mock_manager = MagicMock()
        mock_manager.get_templates.return_value = [
            self._create_test_template(
                pipeline_id="detect-only",
                name="Detect Only",
                description="Template pipeline with a single object detection model.",
                tags=["template", "detection"],
            ),
            self._create_test_template(
                pipeline_id="detect-classify",
                name="Detect and Classify",
                description="Template pipeline with detection and classification.",
                tags=["template", "detection", "classification"],
                variants=[
                    self._create_test_variant(variant_id="cpu", name="CPU"),
                    self._create_test_variant(variant_id="gpu", name="GPU"),
                ],
            ),
        ]
        mock_manager_cls.return_value = mock_manager

        response = self.client.get("/pipeline-templates")

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIsInstance(data, list)
        self.assertEqual(len(data), 2)

        # Check the first template
        first = data[0]
        self.assertEqual(first["id"], "detect-only")
        self.assertEqual(first["name"], "Detect Only")
        self.assertEqual(
            first["description"],
            "Template pipeline with a single object detection model.",
        )
        self.assertEqual(first["source"], schemas.PipelineSource.TEMPLATE.value)
        self.assertIn("template", first["tags"])
        self.assertIsNone(first["thumbnail"])
        self.assertIn("variants", first)
        self.assertEqual(len(first["variants"]), 1)
        self.assertTrue(first["variants"][0]["read_only"])

        # Check timestamps are present
        self.assertIn("created_at", first)
        self.assertIn("modified_at", first)
        self.assertIn("created_at", first["variants"][0])
        self.assertIn("modified_at", first["variants"][0])

        # Check the second template
        second = data[1]
        self.assertEqual(second["id"], "detect-classify")
        self.assertEqual(len(second["variants"]), 2)

    @patch("api.routes.pipeline_templates.PipelineTemplateManager")
    def test_get_pipeline_templates_returns_empty_list(self, mock_manager_cls):
        """Test GET /pipeline-templates returns 200 with an empty list when no templates exist."""
        mock_manager = MagicMock()
        mock_manager.get_templates.return_value = []
        mock_manager_cls.return_value = mock_manager

        response = self.client.get("/pipeline-templates")

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIsInstance(data, list)
        self.assertEqual(len(data), 0)

    @patch("api.routes.pipeline_templates.PipelineTemplateManager")
    def test_get_pipeline_templates_server_error(self, mock_manager_cls):
        """Test GET /pipeline-templates returns 500 on unexpected error."""
        mock_manager = MagicMock()
        mock_manager.get_templates.side_effect = Exception("Unexpected error")
        mock_manager_cls.return_value = mock_manager

        response = self.client.get("/pipeline-templates")

        self.assertEqual(response.status_code, 500)
        self.assertEqual(
            response.json(),
            schemas.MessageResponse(
                message="Unexpected error while listing pipeline templates."
            ).model_dump(),
        )

    # ------------------------------------------------------------------ #
    #  GET /pipeline-templates/{template_id}                               #
    # ------------------------------------------------------------------ #

    @patch("api.routes.pipeline_templates.PipelineTemplateManager")
    def test_get_pipeline_template_by_id_returns_template(self, mock_manager_cls):
        """Test GET /pipeline-templates/{template_id} returns 200 with the matching template."""
        template = self._create_test_template(
            pipeline_id="detect-only",
            name="Detect Only",
            description="Template pipeline with a single object detection model.",
            tags=["template", "detection"],
        )
        mock_manager = MagicMock()
        mock_manager.get_template_by_id.return_value = template
        mock_manager_cls.return_value = mock_manager

        response = self.client.get("/pipeline-templates/detect-only")

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["id"], "detect-only")
        self.assertEqual(data["name"], "Detect Only")
        self.assertEqual(
            data["description"],
            "Template pipeline with a single object detection model.",
        )
        self.assertEqual(data["source"], schemas.PipelineSource.TEMPLATE.value)
        self.assertIn("template", data["tags"])
        self.assertIsNone(data["thumbnail"])
        self.assertIn("variants", data)
        self.assertEqual(len(data["variants"]), 1)
        self.assertTrue(data["variants"][0]["read_only"])
        self.assertEqual(data["variants"][0]["id"], "cpu")

        # Check timestamps are present
        self.assertIn("created_at", data)
        self.assertIn("modified_at", data)

        mock_manager.get_template_by_id.assert_called_once_with("detect-only")

    @patch("api.routes.pipeline_templates.PipelineTemplateManager")
    def test_get_pipeline_template_by_id_not_found(self, mock_manager_cls):
        """Test GET /pipeline-templates/{template_id} returns 404 when template does not exist."""
        mock_manager = MagicMock()
        mock_manager.get_template_by_id.side_effect = ValueError(
            "Template 'nonexistent' not found."
        )
        mock_manager_cls.return_value = mock_manager

        response = self.client.get("/pipeline-templates/nonexistent")

        self.assertEqual(response.status_code, 404)
        self.assertEqual(
            response.json(),
            schemas.MessageResponse(
                message="Template 'nonexistent' not found."
            ).model_dump(),
        )

    @patch("api.routes.pipeline_templates.PipelineTemplateManager")
    def test_get_pipeline_template_by_id_server_error(self, mock_manager_cls):
        """Test GET /pipeline-templates/{template_id} returns 500 on unexpected error."""
        mock_manager = MagicMock()
        mock_manager.get_template_by_id.side_effect = Exception("Unexpected error")
        mock_manager_cls.return_value = mock_manager

        response = self.client.get("/pipeline-templates/detect-only")

        self.assertEqual(response.status_code, 500)
        self.assertEqual(
            response.json(),
            schemas.MessageResponse(
                message="Unexpected error while retrieving pipeline template."
            ).model_dump(),
        )

    @patch("api.routes.pipeline_templates.PipelineTemplateManager")
    def test_get_pipeline_template_by_id_all_variants_read_only(self, mock_manager_cls):
        """Test that all variants in a returned template have read_only=True."""
        template = self._create_test_template(
            pipeline_id="multi-variant",
            name="Multi Variant",
            description="Template with multiple hardware variants.",
            tags=["template"],
            variants=[
                self._create_test_variant(variant_id="cpu", name="CPU", read_only=True),
                self._create_test_variant(variant_id="gpu", name="GPU", read_only=True),
                self._create_test_variant(variant_id="npu", name="NPU", read_only=True),
            ],
        )
        mock_manager = MagicMock()
        mock_manager.get_template_by_id.return_value = template
        mock_manager_cls.return_value = mock_manager

        response = self.client.get("/pipeline-templates/multi-variant")

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(len(data["variants"]), 3)
        for variant in data["variants"]:
            self.assertTrue(variant["read_only"])

    @patch("api.routes.pipeline_templates.PipelineTemplateManager")
    def test_get_pipeline_templates_thumbnail_is_null(self, mock_manager_cls):
        """Test that templates always have a null thumbnail."""
        mock_manager = MagicMock()
        mock_manager.get_templates.return_value = [self._create_test_template()]
        mock_manager_cls.return_value = mock_manager

        response = self.client.get("/pipeline-templates")

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIsNone(data[0]["thumbnail"])

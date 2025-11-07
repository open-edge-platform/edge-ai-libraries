import unittest

from managers.pipeline_manager import PipelineManager
from api.api_schemas import PipelineType, PipelineDefinition


class TestPipelineManager(unittest.TestCase):
    def test_add_pipeline_valid(self):
        manager = PipelineManager()
        initial_count = len(manager.get_pipelines())

        new_pipeline = PipelineDefinition(
            name="user-defined-pipelines",
            version="test-pipeline",
            description="A test pipeline",
            type=PipelineType.GSTREAMER,
            pipeline_description="filesrc location=/tmp/dummy-video.mp4 ! decodebin3 ! autovideosink",
            parameters=None,
        )

        manager.add_pipeline(new_pipeline)
        pipelines = manager.get_pipelines()
        self.assertEqual(len(pipelines), initial_count + 1)

        # Verify the added pipeline
        added_pipeline = manager.get_pipeline_by_name_and_version(
            "user-defined-pipelines", "test-pipeline"
        )
        self.assertEqual(added_pipeline.name, "user-defined-pipelines")
        self.assertEqual(added_pipeline.version, "test-pipeline")

    def test_add_pipeline_duplicate(self):
        manager = PipelineManager()

        new_pipeline = PipelineDefinition(
            name="user-defined-pipelines",
            version="test-pipeline",
            description="A test pipeline",
            type=PipelineType.GSTREAMER,
            pipeline_description="filesrc location=/tmp/dummy-video.mp4 ! decodebin3 ! autovideosink",
            parameters=None,
        )

        manager.add_pipeline(new_pipeline)

        # Attempt to add the same pipeline again should raise ValueError
        with self.assertRaises(ValueError) as context:
            manager.add_pipeline(new_pipeline)

        self.assertIn(
            "Pipeline with name 'user-defined-pipelines' and version 'test-pipeline' already exists.",
            str(context.exception),
        )

    def test_get_pipeline_by_name_and_version_not_found(self):
        manager = PipelineManager()

        with self.assertRaises(ValueError) as context:
            manager.get_pipeline_by_name_and_version(
                "user-defined-pipelines", "nonexistent-pipeline"
            )

        self.assertIn(
            "Pipeline with name 'user-defined-pipelines' and version 'nonexistent-pipeline' not found.",
            str(context.exception),
        )

    def test_load_predefined_pipelines(self):
        manager = PipelineManager()
        pipelines = manager.get_pipelines()
        self.assertIsInstance(pipelines, list)
        self.assertEqual(len(pipelines), 2)

        self.assertEqual(pipelines[0].name, "predefined_pipelines")
        self.assertEqual(pipelines[0].version, "SimpleVideoStructurizationPipeline")
        self.assertEqual(
            pipelines[0].description, "Simple Video Structurization (D-T-C)"
        )
        self.assertIsNotNone(pipelines[0].pipeline_graph)

        self.assertEqual(pipelines[1].name, "predefined_pipelines")
        self.assertEqual(pipelines[1].version, "SmartNVRPipeline")
        self.assertEqual(
            pipelines[1].description,
            "Smart Network Video Recorder (NVR) Proxy Pipeline",
        )
        self.assertIsNotNone(pipelines[1].pipeline_graph)

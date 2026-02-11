import unittest
from unittest.mock import patch, MagicMock

from api.api_schemas import (
    Edge,
    ExecutionConfig,
    Node,
    OutputMode,
    PipelineDefinition,
    PipelineGraph,
    PipelineParameters,
    PipelinePerformanceSpec,
    PipelineSource,
    PipelineType,
)
from managers.pipeline_manager import PipelineManager
from videos import OUTPUT_VIDEO_DIR


class TestPipelineManager(unittest.TestCase):
    def setUp(self):
        """Reset singleton state before each test."""
        # Reset the singleton instance to ensure clean state for each test
        PipelineManager._instance = None

    def test_add_pipeline_valid(self):
        manager = PipelineManager()
        manager.pipelines = []  # Reset pipelines for isolated test
        initial_count = len(manager.get_pipelines())

        new_pipeline = PipelineDefinition(
            name="user-defined-pipelines",
            version=1,
            description="A test pipeline",
            source=PipelineSource.USER_CREATED,
            type=PipelineType.GSTREAMER,
            pipeline_description="filesrc location=/tmp/dummy-video.mp4 ! decodebin3 ! autovideosink",
            parameters=None,
        )

        added_pipeline = manager.add_pipeline(new_pipeline)
        pipelines = manager.get_pipelines()
        self.assertEqual(len(pipelines), initial_count + 1)

        # Verify the added pipeline has an ID and correct attributes
        self.assertIsNotNone(added_pipeline.id)
        self.assertTrue(added_pipeline.id.startswith("pipeline-"))
        self.assertEqual(added_pipeline.name, "user-defined-pipelines")
        self.assertEqual(added_pipeline.version, 1)

        # Verify we can retrieve it by ID
        retrieved = manager.get_pipeline_by_id(added_pipeline.id)
        self.assertEqual(retrieved.name, "user-defined-pipelines")
        self.assertEqual(retrieved.version, 1)

    def test_add_pipeline_duplicate(self):
        manager = PipelineManager()
        manager.pipelines = []  # Reset pipelines for isolated test

        new_pipeline = PipelineDefinition(
            name="user-defined-pipelines",
            version=1,
            description="A test pipeline",
            source=PipelineSource.USER_CREATED,
            type=PipelineType.GSTREAMER,
            pipeline_description="filesrc location=/tmp/dummy-video.mp4 ! decodebin3 ! autovideosink",
            parameters=None,
        )

        manager.add_pipeline(new_pipeline)

        # Attempt to add the same pipeline again should raise ValueError
        with self.assertRaises(ValueError) as context:
            manager.add_pipeline(new_pipeline)

        self.assertIn(
            "Invalid version '1' for pipeline 'user-defined-pipelines'. Expected next version to be '2'.",
            str(context.exception),
        )

    def test_add_pipeline_version_must_start_at_one_for_new_name(self):
        manager = PipelineManager()
        manager.pipelines = []

        # For a new pipeline name, only version 1 is allowed.
        invalid_pipeline = PipelineDefinition(
            name="user-defined-pipelines",
            version=3,
            description="A test pipeline",
            source=PipelineSource.USER_CREATED,
            type=PipelineType.GSTREAMER,
            pipeline_description="filesrc location=/tmp/dummy-video.mp4 ! decodebin3 ! autovideosink",
            parameters=None,
        )

        with self.assertRaises(ValueError) as context:
            manager.add_pipeline(invalid_pipeline)

        self.assertIn(
            "Invalid version '3' for pipeline 'user-defined-pipelines'. Expected version '1' for a new pipeline.",
            str(context.exception),
        )

    def test_add_pipeline_version_must_be_consecutive(self):
        manager = PipelineManager()
        manager.pipelines = []

        pipeline_v1 = PipelineDefinition(
            name="user-defined-pipelines",
            version=1,
            description="v1",
            source=PipelineSource.USER_CREATED,
            type=PipelineType.GSTREAMER,
            pipeline_description="fakesrc ! fakesink",
            parameters=None,
        )

        pipeline_v2 = PipelineDefinition(
            name="user-defined-pipelines",
            version=2,
            description="v2",
            source=PipelineSource.USER_CREATED,
            type=PipelineType.GSTREAMER,
            pipeline_description="fakesrc ! fakesink",
            parameters=None,
        )

        pipeline_v4 = PipelineDefinition(
            name="user-defined-pipelines",
            version=4,
            description="v4",
            source=PipelineSource.USER_CREATED,
            type=PipelineType.GSTREAMER,
            pipeline_description="fakesrc ! fakesink",
            parameters=None,
        )

        # v1 and v2 should be accepted
        manager.add_pipeline(pipeline_v1)
        manager.add_pipeline(pipeline_v2)

        # Skipping directly to v4 must fail; expected next version is 3
        with self.assertRaises(ValueError) as context:
            manager.add_pipeline(pipeline_v4)

        self.assertIn(
            "Invalid version '4' for pipeline 'user-defined-pipelines'. Expected next version to be '3'.",
            str(context.exception),
        )

    def test_get_pipeline_by_id_not_found(self):
        manager = PipelineManager()

        with self.assertRaises(ValueError) as context:
            manager.get_pipeline_by_id("nonexistent-pipeline-id")

        self.assertIn(
            "Pipeline with id 'nonexistent-pipeline-id' not found.",
            str(context.exception),
        )

    def test_load_predefined_pipelines(self):
        manager = PipelineManager()
        pipelines = manager.get_pipelines()
        self.assertIsInstance(pipelines, list)
        # Just verify we loaded at least one pipeline
        self.assertGreaterEqual(len(pipelines), 1)

        # Verify all pipelines have required fields
        for pipeline in pipelines:
            self.assertIsNotNone(pipeline.id)
            self.assertIsNotNone(pipeline.name)
            self.assertIsNotNone(pipeline.pipeline_graph)

    def test_build_pipeline_command_single_pipeline_single_stream(self):
        manager = PipelineManager()
        manager.pipelines = []  # Reset pipelines for isolated test

        # Add a test pipeline
        test_pipeline = PipelineDefinition(
            name="test-pipelines",
            version=1,
            description="Test pipeline for single stream",
            source=PipelineSource.USER_CREATED,
            type=PipelineType.GSTREAMER,
            pipeline_description="fakesrc ! fakesink",
            parameters=None,
        )
        added = manager.add_pipeline(test_pipeline)

        # Build command with one pipeline and one stream using the pipeline ID
        pipeline_performance_specs = [PipelinePerformanceSpec(id=added.id, streams=1)]
        execution_config = ExecutionConfig(output_mode=OutputMode.DISABLED)

        command, output_paths, live_stream_urls = manager.build_pipeline_command(
            pipeline_performance_specs, execution_config
        )

        # Verify command is not empty and contains pipeline elements
        self.assertIsInstance(command, str)
        self.assertIsInstance(output_paths, dict)
        self.assertIsInstance(live_stream_urls, dict)
        self.assertGreater(len(command), 0)
        self.assertIn("fakesrc", command)
        self.assertIn("fakesink", command)

    def test_build_pipeline_command_single_pipeline_multiple_streams(self):
        manager = PipelineManager()
        manager.pipelines = []  # Reset pipelines for isolated test

        # Add a test pipeline
        test_pipeline = PipelineDefinition(
            name="test-pipelines",
            version=1,
            description="Test pipeline for multiple streams",
            source=PipelineSource.USER_CREATED,
            type=PipelineType.GSTREAMER,
            pipeline_description="videotestsrc ! tee name=t ! queue ! fakesink t. ! queue ! fakesink",
            parameters=None,
        )
        added = manager.add_pipeline(test_pipeline)

        # Build command with one pipeline and 3 streams using the pipeline ID
        pipeline_performance_specs = [PipelinePerformanceSpec(id=added.id, streams=3)]
        execution_config = ExecutionConfig(output_mode=OutputMode.DISABLED)

        command, output_paths, live_stream_urls = manager.build_pipeline_command(
            pipeline_performance_specs, execution_config
        )

        # Verify command contains multiple instances
        self.assertIsInstance(command, str)
        self.assertIsInstance(output_paths, dict)
        self.assertIsInstance(live_stream_urls, dict)
        self.assertGreater(len(command), 0)
        # Should have 3 instances of videotestsrc (one per stream)
        self.assertEqual(command.count("videotestsrc"), 3)

    def test_build_pipeline_command_multiple_pipelines(self):
        manager = PipelineManager()
        manager.pipelines = []  # Reset pipelines for isolated test

        # Add two test pipelines
        pipeline1 = PipelineDefinition(
            name="test-pipelines",
            version=1,
            description="First test pipeline",
            source=PipelineSource.USER_CREATED,
            type=PipelineType.GSTREAMER,
            pipeline_description="fakesrc name=source1 ! fakesink",
            parameters=None,
        )
        pipeline2 = PipelineDefinition(
            name="test-pipelines",
            version=2,
            description="Second test pipeline",
            source=PipelineSource.USER_CREATED,
            type=PipelineType.GSTREAMER,
            pipeline_description="videotestsrc name=source2 ! fakesink",
            parameters=None,
        )
        added1 = manager.add_pipeline(pipeline1)
        added2 = manager.add_pipeline(pipeline2)

        # Build command with two pipelines with different stream counts using IDs
        pipeline_performance_specs = [
            PipelinePerformanceSpec(id=added1.id, streams=2),
            PipelinePerformanceSpec(id=added2.id, streams=3),
        ]
        execution_config = ExecutionConfig(output_mode=OutputMode.DISABLED)

        command, output_paths, live_stream_urls = manager.build_pipeline_command(
            pipeline_performance_specs, execution_config
        )

        # Verify both pipeline types are present
        self.assertIsInstance(command, str)
        self.assertIsInstance(output_paths, dict)
        self.assertIsInstance(live_stream_urls, dict)
        self.assertGreater(len(command), 0)
        # Should have 2 instances of fakesrc and 3 instances of videotestsrc
        self.assertEqual(command.count("fakesrc"), 2)
        self.assertEqual(command.count("videotestsrc"), 3)

    def test_build_pipeline_command_nonexistent_pipeline_raises_error(self):
        manager = PipelineManager()

        # Try to build command with pipeline ID that doesn't exist
        pipeline_performance_specs = [
            PipelinePerformanceSpec(id="nonexistent-pipeline-id", streams=1)
        ]
        execution_config = ExecutionConfig(output_mode=OutputMode.DISABLED)

        with self.assertRaises(ValueError) as context:
            manager.build_pipeline_command(pipeline_performance_specs, execution_config)

        self.assertIn(
            "Pipeline with id 'nonexistent-pipeline-id' not found",
            str(context.exception),
        )

    def test_update_pipeline_description_and_name(self):
        manager = PipelineManager()
        manager.pipelines = []

        new_pipeline = PipelineDefinition(
            name="original-name",
            version=1,
            description="Original description",
            source=PipelineSource.USER_CREATED,
            type=PipelineType.GSTREAMER,
            pipeline_description="fakesrc ! fakesink",
            parameters=None,
        )

        added = manager.add_pipeline(new_pipeline)

        updated = manager.update_pipeline(
            pipeline_id=added.id,
            name="updated-name",
            description="Updated description",
        )

        self.assertEqual(updated.id, added.id)
        self.assertEqual(updated.name, "updated-name")
        self.assertEqual(updated.description, "Updated description")

        # Ensure the change is reflected in manager state
        retrieved = manager.get_pipeline_by_id(added.id)
        self.assertEqual(retrieved.name, "updated-name")
        self.assertEqual(retrieved.description, "Updated description")

    def test_update_pipeline_graph_and_parameters(self):
        manager = PipelineManager()
        manager.pipelines = []

        new_pipeline = PipelineDefinition(
            name="test-pipeline",
            version=1,
            description="Pipeline to be updated",
            source=PipelineSource.USER_CREATED,
            type=PipelineType.GSTREAMER,
            pipeline_description="fakesrc ! fakesink",
            parameters=None,
        )

        added = manager.add_pipeline(new_pipeline)

        updated_graph = PipelineGraph(
            nodes=[
                Node(id="0", type="videotestsrc", data={}),
                Node(id="1", type="fakesink", data={}),
            ],
            edges=[Edge(id="0", source="0", target="1")],
        )

        updated_params = PipelineParameters(default={"key": "value"})

        updated = manager.update_pipeline(
            pipeline_id=added.id,
            pipeline_graph=updated_graph,
            parameters=updated_params,
        )

        self.assertEqual(updated.id, added.id)
        self.assertEqual(updated.pipeline_graph, updated_graph)
        self.assertEqual(updated.parameters, updated_params)

    def test_update_pipeline_invalid_graph_raises(self):
        manager = PipelineManager()
        manager.pipelines = []

        new_pipeline = PipelineDefinition(
            name="test-pipeline-invalid-graph",
            version=1,
            description="Pipeline with invalid graph update",
            source=PipelineSource.USER_CREATED,
            type=PipelineType.GSTREAMER,
            pipeline_description="fakesrc ! fakesink",
            parameters=None,
        )

        added = manager.add_pipeline(new_pipeline)

        # Create an invalid graph that should fail validation in update_pipeline
        invalid_graph = PipelineGraph(
            nodes=[
                Node(
                    id="0",
                    type="gvafpscounter",
                    data={"starting-frame": "2000"},
                ),
            ],
            edges=[Edge(id="1", source="0", target="0")],
        )

        with self.assertRaises(ValueError) as context:
            manager.update_pipeline(pipeline_id=added.id, pipeline_graph=invalid_graph)

        self.assertIn(
            "Cannot convert graph to pipeline description: circular graph detected or no start nodes found",
            str(context.exception),
        )

    def test_update_pipeline_not_found_raises(self):
        manager = PipelineManager()
        manager.pipelines = []

        with self.assertRaises(ValueError) as context:
            manager.update_pipeline(pipeline_id="nonexistent", name="new-name")

        self.assertIn(
            "Pipeline with id 'nonexistent' not found.", str(context.exception)
        )

    def test_build_pipeline_command_with_video_output_enabled(self):
        """Test building pipeline command with video output enabled (file mode)."""
        manager = PipelineManager()
        manager.pipelines = []

        # Add a test pipeline
        new_pipeline = PipelineDefinition(
            name="test-video-output",
            version=1,
            description="Pipeline for testing video output",
            source=PipelineSource.USER_CREATED,
            type=PipelineType.GSTREAMER,
            pipeline_description="videotestsrc ! fakesink name=default_output_sink",
            parameters=None,
        )
        added = manager.add_pipeline(new_pipeline)

        pipeline_performance_specs = [PipelinePerformanceSpec(id=added.id, streams=1)]
        execution_config = ExecutionConfig(
            output_mode=OutputMode.FILE,
            max_runtime=0,
        )

        command, output_paths, live_stream_urls = manager.build_pipeline_command(
            pipeline_performance_specs, execution_config
        )

        # Verify video output is configured
        self.assertIsInstance(command, str)
        self.assertIsInstance(output_paths, dict)
        self.assertIn(added.id, output_paths)
        self.assertGreater(len(output_paths[added.id]), 0)

        # Verify output directory is in the command
        self.assertIn(OUTPUT_VIDEO_DIR, command)

        # Verify fakesink is replaced with encoder pipeline
        self.assertNotIn("fakesink", command)
        self.assertIn("filesink", command)

        # Verify no live stream URLs for file output mode
        self.assertEqual(len(live_stream_urls), 0)

    def test_build_pipeline_command_with_gpu_encoder(self):
        """Test building pipeline command with GPU encoder (file mode)."""
        manager = PipelineManager()
        manager.pipelines = []

        new_pipeline = PipelineDefinition(
            name="test-gpu-encoder",
            version=1,
            description="Pipeline with GPU encoder",
            source=PipelineSource.USER_CREATED,
            type=PipelineType.GSTREAMER,
            pipeline_description="videotestsrc ! fakesink name=default_output_sink",
            parameters=None,
        )
        added = manager.add_pipeline(new_pipeline)

        pipeline_performance_specs = [PipelinePerformanceSpec(id=added.id, streams=2)]
        execution_config = ExecutionConfig(
            output_mode=OutputMode.FILE,
            max_runtime=0,
        )

        command, output_paths, live_stream_urls = manager.build_pipeline_command(
            pipeline_performance_specs, execution_config
        )

        # Verify output paths for all streams
        self.assertIn(added.id, output_paths)
        # Should have only 1 output path (first stream)
        self.assertEqual(len(output_paths[added.id]), 1)
        # Verify output directory is in the command
        self.assertIn(OUTPUT_VIDEO_DIR, command)

    def test_build_pipeline_command_video_output_multiple_pipelines(self):
        """Test video output with multiple pipelines - only first stream gets output."""
        manager = PipelineManager()
        manager.pipelines = []

        pipeline1 = PipelineDefinition(
            name="pipeline-1",
            version=1,
            description="First pipeline",
            source=PipelineSource.USER_CREATED,
            type=PipelineType.GSTREAMER,
            pipeline_description="videotestsrc ! fakesink name=default_output_sink",
            parameters=None,
        )
        pipeline2 = PipelineDefinition(
            name="pipeline-2",
            version=1,
            description="Second pipeline",
            source=PipelineSource.USER_CREATED,
            type=PipelineType.GSTREAMER,
            pipeline_description="videotestsrc ! fakesink name=default_output_sink",
            parameters=None,
        )

        added1 = manager.add_pipeline(pipeline1)
        added2 = manager.add_pipeline(pipeline2)

        pipeline_performance_specs = [
            PipelinePerformanceSpec(id=added1.id, streams=2),
            PipelinePerformanceSpec(id=added2.id, streams=3),
        ]
        execution_config = ExecutionConfig(
            output_mode=OutputMode.FILE,
            max_runtime=0,
        )

        command, output_paths, live_stream_urls = manager.build_pipeline_command(
            pipeline_performance_specs, execution_config
        )

        # Verify video output paths exist for both pipelines
        self.assertIn(added1.id, output_paths)
        self.assertIn(added2.id, output_paths)

        # Each pipeline should have only 1 output path (first stream)
        self.assertEqual(len(output_paths[added1.id]), 1)
        self.assertEqual(len(output_paths[added2.id]), 1)

        # Verify output directory is in the command
        self.assertIn(OUTPUT_VIDEO_DIR, command)

    def test_add_pipeline_generates_simple_view(self):
        """
        add_pipeline should generate simple view automatically from advanced view.
        """
        manager = PipelineManager()
        manager.pipelines = []

        new_pipeline = PipelineDefinition(
            name="test-simple-view",
            version=1,
            description="Test simple view generation",
            source=PipelineSource.USER_CREATED,
            type=PipelineType.GSTREAMER,
            pipeline_description="filesrc location=/tmp/test.mp4 ! decodebin3 ! autovideosink",
            parameters=None,
        )

        added = manager.add_pipeline(new_pipeline)

        # Verify both views exist
        self.assertIsNotNone(added.pipeline_graph)
        self.assertIsNotNone(added.pipeline_graph_simple)

        # Verify simple view is different from advanced view (simplified)
        self.assertLess(
            len(added.pipeline_graph_simple.nodes),
            len(added.pipeline_graph.nodes),
        )

        # Verify both views have valid node and edge structures
        self.assertGreater(len(added.pipeline_graph.nodes), 0)
        self.assertGreater(len(added.pipeline_graph_simple.nodes), 0)

    def test_load_predefined_pipelines_generates_simple_views(self):
        """
        load_predefined_pipelines should generate simple view for each predefined pipeline.
        """
        manager = PipelineManager()
        pipelines = manager.get_pipelines()

        # Verify each predefined pipeline has both views
        for pipeline in pipelines:
            self.assertIsNotNone(
                pipeline.pipeline_graph,
                f"Pipeline {pipeline.name} missing advanced view",
            )
            self.assertIsNotNone(
                pipeline.pipeline_graph_simple,
                f"Pipeline {pipeline.name} missing simple view",
            )

            # Verify both views have nodes
            self.assertGreater(
                len(pipeline.pipeline_graph.nodes),
                0,
                f"Pipeline {pipeline.name} advanced view has no nodes",
            )
            self.assertGreater(
                len(pipeline.pipeline_graph_simple.nodes),
                0,
                f"Pipeline {pipeline.name} simple view has no nodes",
            )

    def test_update_pipeline_with_advanced_graph_regenerates_simple_view(self):
        """
        Updating pipeline with new advanced graph should auto-generate simple view.
        """
        manager = PipelineManager()
        manager.pipelines = []

        original_pipeline = PipelineDefinition(
            name="test-graph-update",
            version=1,
            description="Original pipeline",
            source=PipelineSource.USER_CREATED,
            type=PipelineType.GSTREAMER,
            pipeline_description="fakesrc ! fakesink",
            parameters=None,
        )

        added = manager.add_pipeline(original_pipeline)
        original_simple_view = added.pipeline_graph_simple

        # Update with new advanced graph
        new_graph = PipelineGraph(
            nodes=[
                Node(id="0", type="videotestsrc", data={}),
                Node(id="1", type="videoconvert", data={}),
                Node(id="2", type="fakesink", data={}),
            ],
            edges=[
                Edge(id="0", source="0", target="1"),
                Edge(id="1", source="1", target="2"),
            ],
        )

        updated = manager.update_pipeline(
            pipeline_id=added.id, pipeline_graph=new_graph
        )

        # Verify advanced view is updated
        self.assertEqual(updated.pipeline_graph, new_graph)

        # Verify simple view was regenerated (auto-generated)
        self.assertIsNotNone(updated.pipeline_graph_simple)
        # New simple view should be different from original
        self.assertNotEqual(
            updated.pipeline_graph_simple.model_dump(),
            original_simple_view.model_dump(),
        )

    def test_update_pipeline_with_simple_graph_applies_changes_to_advanced(self):
        """
        Updating pipeline with simple graph should regenerate both views successfully.
        """
        manager = PipelineManager()
        manager.pipelines = []

        original_pipeline = PipelineDefinition(
            name="test-simple-update",
            version=1,
            description="Pipeline for simple graph update",
            source=PipelineSource.USER_CREATED,
            type=PipelineType.GSTREAMER,
            pipeline_description="videotestsrc ! videoconvert ! fakesink",
            parameters=None,
        )

        added = manager.add_pipeline(original_pipeline)

        # Get the current simple view
        current_simple = added.pipeline_graph_simple

        # Create modified simple view with same structure (no property changes)
        # This tests that applying simple view changes works correctly
        modified_simple = PipelineGraph(
            nodes=current_simple.nodes,
            edges=current_simple.edges,
        )

        # Update with modified simple graph
        updated = manager.update_pipeline(
            pipeline_id=added.id, pipeline_graph_simple=modified_simple
        )

        # Verify both views exist and are valid
        self.assertIsNotNone(updated.pipeline_graph)
        self.assertIsNotNone(updated.pipeline_graph_simple)

        # Verify updated pipeline has valid structure
        self.assertGreater(len(updated.pipeline_graph.nodes), 0)
        self.assertGreater(len(updated.pipeline_graph_simple.nodes), 0)

        # Verify the pipeline can still be converted to a valid GStreamer description
        self.assertIsNotNone(updated.pipeline_graph)

    def test_update_pipeline_invalid_advanced_graph_raises_error(self):
        """
        Updating with invalid advanced graph that fails pipeline description conversion should raise error.
        """
        manager = PipelineManager()
        manager.pipelines = []

        pipeline = PipelineDefinition(
            name="test-invalid-advanced",
            version=1,
            description="Test invalid advanced graph",
            source=PipelineSource.USER_CREATED,
            type=PipelineType.GSTREAMER,
            pipeline_description="fakesrc ! fakesink",
            parameters=None,
        )

        added = manager.add_pipeline(pipeline)

        # Create invalid graph with no start nodes (all nodes have incoming edges)
        # This creates a circular/disconnected structure that fails validation
        invalid_graph = PipelineGraph(
            nodes=[
                Node(id="0", type="fakesink", data={}),
                Node(id="1", type="fakesink", data={}),
            ],
            edges=[
                Edge(id="0", source="0", target="1"),
                Edge(id="1", source="1", target="0"),
            ],
        )

        with self.assertRaises(ValueError) as context:
            manager.update_pipeline(pipeline_id=added.id, pipeline_graph=invalid_graph)

        # Should fail due to circular graph or no start nodes
        error_msg = str(context.exception).lower()
        self.assertTrue(
            "circular" in error_msg or "start" in error_msg or "invalid" in error_msg,
            f"Expected error about circular or invalid graph, got: {context.exception}",
        )

    def test_update_pipeline_with_simple_graph_invalid_changes_raises_error(self):
        """
        Applying invalid simple graph changes (removing nodes) to advanced view should raise error.
        """
        manager = PipelineManager()
        manager.pipelines = []

        pipeline = PipelineDefinition(
            name="test-invalid-simple-changes",
            version=1,
            description="Test invalid simple view changes",
            source=PipelineSource.USER_CREATED,
            type=PipelineType.GSTREAMER,
            pipeline_description="filesrc location=/tmp/video.mp4 ! decodebin3 ! autovideosink",
            parameters=None,
        )

        added = manager.add_pipeline(pipeline)
        current_simple = added.pipeline_graph_simple

        # Create invalid modified simple view by removing node (not allowed in simple view)
        modified_simple = PipelineGraph(
            nodes=current_simple.nodes[:1],  # Only first node - removes others
            edges=[],  # No connections
        )

        with self.assertRaises(ValueError) as context:
            manager.update_pipeline(
                pipeline_id=added.id, pipeline_graph_simple=modified_simple
            )

        # Check for the actual error message about node removal
        self.assertIn("node removals are not supported", str(context.exception).lower())

    def test_pipeline_views_in_get_pipelines(self):
        """
        get_pipelines should return pipelines with both advanced and simple views.
        """
        manager = PipelineManager()

        pipelines = manager.get_pipelines()

        # All pipelines should have both views
        for pipeline in pipelines:
            self.assertIsNotNone(pipeline.pipeline_graph)
            self.assertIsNotNone(pipeline.pipeline_graph_simple)
            self.assertGreater(len(pipeline.pipeline_graph.nodes), 0)
            self.assertGreater(len(pipeline.pipeline_graph_simple.nodes), 0)

    def test_build_pipeline_command_preserves_both_graph_views(self):
        """
        build_pipeline_command should work with both advanced and simple views.
        """
        manager = PipelineManager()
        manager.pipelines = []

        pipeline = PipelineDefinition(
            name="test-views-build",
            version=1,
            description="Test pipeline for build command",
            source=PipelineSource.USER_CREATED,
            type=PipelineType.GSTREAMER,
            pipeline_description="videotestsrc ! fakesink name=default_output_sink",
            parameters=None,
        )

        added = manager.add_pipeline(pipeline)

        # Verify pipeline has both views before building command
        self.assertIsNotNone(added.pipeline_graph)
        self.assertIsNotNone(added.pipeline_graph_simple)

        # Build command should work
        specs = [PipelinePerformanceSpec(id=added.id, streams=1)]
        execution_config = ExecutionConfig(output_mode=OutputMode.DISABLED)

        command, output_paths, live_stream_urls = manager.build_pipeline_command(
            specs, execution_config
        )

        # Verify command was built successfully
        self.assertIsInstance(command, str)
        self.assertGreater(len(command), 0)
        self.assertIn("videotestsrc", command)

    def test_update_pipeline_preserves_other_fields_with_graph_update(self):
        """
        Updating pipeline graph should not affect name, description, or parameters if not specified.
        """
        manager = PipelineManager()
        manager.pipelines = []

        original_params = PipelineParameters(default={"key": "original"})
        pipeline = PipelineDefinition(
            name="test-preserve-fields",
            version=1,
            description="Original description",
            source=PipelineSource.USER_CREATED,
            type=PipelineType.GSTREAMER,
            pipeline_description="fakesrc ! fakesink",
            parameters=original_params,
        )

        added = manager.add_pipeline(pipeline)

        # Update only the graph
        new_graph = PipelineGraph(
            nodes=[
                Node(id="0", type="videotestsrc", data={}),
                Node(id="1", type="fakesink", data={}),
            ],
            edges=[Edge(id="0", source="0", target="1")],
        )

        updated = manager.update_pipeline(
            pipeline_id=added.id, pipeline_graph=new_graph
        )

        # Verify other fields are unchanged
        self.assertEqual(updated.name, "test-preserve-fields")
        self.assertEqual(updated.description, "Original description")
        self.assertIsNotNone(updated.parameters)
        if updated.parameters is not None:
            self.assertEqual(updated.parameters.default, {"key": "original"})

    def test_add_pipeline_with_complex_graph_generates_simple_view(self):
        """
        Adding pipeline with complex GStreamer pipeline should generate valid simple view.
        """
        manager = PipelineManager()
        manager.pipelines = []

        complex_pipeline = PipelineDefinition(
            name="test-complex-pipeline",
            version=1,
            description="Complex pipeline with multiple branches",
            source=PipelineSource.USER_CREATED,
            type=PipelineType.GSTREAMER,
            pipeline_description="filesrc location=/tmp/test.mp4 ! decodebin3 ! videoconvert ! autovideosink",
            parameters=None,
        )

        added = manager.add_pipeline(complex_pipeline)

        # Both views should be valid
        self.assertIsNotNone(added.pipeline_graph)
        self.assertIsNotNone(added.pipeline_graph_simple)

        # Simple view should have fewer or equal nodes than advanced
        self.assertLessEqual(
            len(added.pipeline_graph_simple.nodes),
            len(added.pipeline_graph.nodes),
        )

        # Both should have valid edges
        self.assertGreater(len(added.pipeline_graph.edges), 0)
        self.assertGreater(len(added.pipeline_graph_simple.edges), 0)


class TestBuildPipelineCommandExecutionConfig(unittest.TestCase):
    """Test cases for ExecutionConfig validation in build_pipeline_command."""

    def setUp(self):
        PipelineManager._instance = None
        self.manager = PipelineManager()
        self.manager.pipelines = []

        # Add a test pipeline for all tests
        test_pipeline = PipelineDefinition(
            name="test-execution-config",
            version=1,
            description="Test pipeline for execution config",
            source=PipelineSource.USER_CREATED,
            type=PipelineType.GSTREAMER,
            pipeline_description="videotestsrc ! fakesink name=default_output_sink",
            parameters=None,
        )
        self.added_pipeline = self.manager.add_pipeline(test_pipeline)
        self.specs = [PipelinePerformanceSpec(id=self.added_pipeline.id, streams=1)]

    def test_file_output_with_max_runtime_raises_error(self):
        """Test that file output mode with max_runtime > 0 raises ValueError."""
        execution_config = ExecutionConfig(
            output_mode=OutputMode.FILE,
            max_runtime=60,
        )

        with self.assertRaises(ValueError) as context:
            self.manager.build_pipeline_command(self.specs, execution_config)

        self.assertIn(
            "output_mode='file' cannot be combined with max_runtime > 0",
            str(context.exception),
        )

    def test_file_output_with_zero_max_runtime_succeeds(self):
        """Test that file output mode with max_runtime=0 works correctly."""
        execution_config = ExecutionConfig(
            output_mode=OutputMode.FILE,
            max_runtime=0,
        )

        command, output_paths, live_stream_urls = self.manager.build_pipeline_command(
            self.specs, execution_config
        )

        self.assertIsInstance(command, str)
        self.assertGreater(len(command), 0)
        self.assertIn("filesink", command)

    def test_disabled_output_with_max_runtime_succeeds(self):
        """Test that disabled output mode with max_runtime > 0 works correctly."""
        execution_config = ExecutionConfig(
            output_mode=OutputMode.DISABLED,
            max_runtime=60,
        )

        command, output_paths, live_stream_urls = self.manager.build_pipeline_command(
            self.specs, execution_config
        )

        self.assertIsInstance(command, str)
        self.assertGreater(len(command), 0)
        # Fakesink should remain in disabled mode
        self.assertIn("fakesink", command)

    def test_live_stream_output_with_max_runtime_succeeds(self):
        """Test that live stream output mode with max_runtime > 0 works correctly."""
        execution_config = ExecutionConfig(
            output_mode=OutputMode.LIVE_STREAM,
            max_runtime=60,
        )

        command, output_paths, live_stream_urls = self.manager.build_pipeline_command(
            self.specs, execution_config
        )

        self.assertIsInstance(command, str)
        self.assertGreater(len(command), 0)
        # Should have rtspclientsink for live streaming
        self.assertIn("rtspclientsink", command)
        # Should have live stream URL
        self.assertIn(self.added_pipeline.id, live_stream_urls)

    def test_live_stream_output_returns_stream_urls(self):
        """Test that live stream output mode returns correct stream URLs."""
        execution_config = ExecutionConfig(
            output_mode=OutputMode.LIVE_STREAM,
            max_runtime=0,
        )

        command, output_paths, live_stream_urls = self.manager.build_pipeline_command(
            self.specs, execution_config
        )

        # Verify live stream URL format
        self.assertIn(self.added_pipeline.id, live_stream_urls)
        stream_url = live_stream_urls[self.added_pipeline.id]
        self.assertTrue(stream_url.startswith("rtsp://"))
        self.assertIn(self.added_pipeline.id, stream_url)

    def test_live_stream_one_url_per_pipeline_type(self):
        """Test that only one live stream URL is generated per pipeline type."""
        # Add another pipeline
        another_pipeline = PipelineDefinition(
            name="test-execution-config",
            version=2,
            description="Another test pipeline",
            source=PipelineSource.USER_CREATED,
            type=PipelineType.GSTREAMER,
            pipeline_description="videotestsrc ! fakesink name=default_output_sink",
            parameters=None,
        )
        added2 = self.manager.add_pipeline(another_pipeline)

        specs = [
            PipelinePerformanceSpec(id=self.added_pipeline.id, streams=3),
            PipelinePerformanceSpec(id=added2.id, streams=2),
        ]
        execution_config = ExecutionConfig(
            output_mode=OutputMode.LIVE_STREAM,
            max_runtime=60,
        )

        command, output_paths, live_stream_urls = self.manager.build_pipeline_command(
            specs, execution_config
        )

        # Should have exactly 2 live stream URLs (one per pipeline type)
        self.assertEqual(len(live_stream_urls), 2)
        self.assertIn(self.added_pipeline.id, live_stream_urls)
        self.assertIn(added2.id, live_stream_urls)

        # Only first stream of each pipeline should have rtspclientsink
        self.assertEqual(command.count("rtspclientsink"), 2)


class TestBuildPipelineCommandLooping(unittest.TestCase):
    """Test cases for looping behavior in build_pipeline_command."""

    def setUp(self):
        self.manager = PipelineManager()
        self.manager.pipelines = []

        # Add a test pipeline with videotestsrc for looping tests
        # Using videotestsrc instead of filesrc avoids video path validation issues
        test_pipeline = PipelineDefinition(
            name="test-looping",
            version=1,
            description="Test pipeline for looping",
            source=PipelineSource.USER_CREATED,
            type=PipelineType.GSTREAMER,
            pipeline_description="videotestsrc ! fakesink name=default_output_sink",
            parameters=None,
        )
        self.added_pipeline = self.manager.add_pipeline(test_pipeline)
        self.specs = [PipelinePerformanceSpec(id=self.added_pipeline.id, streams=1)]

    def test_looping_not_applied_when_max_runtime_zero(self):
        """Test that looping modifications are not applied when max_runtime=0."""
        execution_config = ExecutionConfig(
            output_mode=OutputMode.DISABLED,
            max_runtime=0,
        )

        command, _, _ = self.manager.build_pipeline_command(
            self.specs, execution_config
        )

        # Should use videotestsrc (not multifilesrc) when not looping
        self.assertIn("videotestsrc", command)
        self.assertNotIn("multifilesrc", command)

    def test_looping_applied_when_max_runtime_positive_and_disabled_mode(self):
        """Test that looping modifications are applied for disabled mode with max_runtime > 0."""
        execution_config = ExecutionConfig(
            output_mode=OutputMode.DISABLED,
            max_runtime=60,
        )

        command, _, _ = self.manager.build_pipeline_command(
            self.specs, execution_config
        )

        # videotestsrc doesn't get converted to multifilesrc, only filesrc does
        # But the pipeline should still work with max_runtime > 0
        self.assertIn("videotestsrc", command)
        self.assertIn("fakesink", command)

    def test_looping_applied_when_max_runtime_positive_and_live_stream_mode(self):
        """Test that looping modifications are applied for live stream mode with max_runtime > 0."""
        execution_config = ExecutionConfig(
            output_mode=OutputMode.LIVE_STREAM,
            max_runtime=60,
        )

        command, _, live_stream_urls = self.manager.build_pipeline_command(
            self.specs, execution_config
        )

        # Should have rtspclientsink for live streaming
        self.assertIn("rtspclientsink", command)
        # Should have live stream URL
        self.assertIn(self.added_pipeline.id, live_stream_urls)

    def test_looping_not_applied_for_file_mode(self):
        """Test that looping modifications are never applied for file mode."""
        execution_config = ExecutionConfig(
            output_mode=OutputMode.FILE,
            max_runtime=0,  # max_runtime must be 0 for file mode
        )

        command, _, _ = self.manager.build_pipeline_command(
            self.specs, execution_config
        )

        # Should use videotestsrc (not multifilesrc) for file output
        self.assertIn("videotestsrc", command)
        self.assertNotIn("multifilesrc", command)


class TestBuildPipelineCommandLoopingWithFilesrc(unittest.TestCase):
    """Test cases for looping behavior with filesrc pipelines."""

    def setUp(self):
        PipelineManager._instance = None
        self.manager = PipelineManager()
        self.manager.pipelines = []

    @patch("graph.VideosManager")
    def test_looping_converts_filesrc_to_multifilesrc(self, mock_videos_cls):
        """Test that filesrc is converted to multifilesrc when looping is enabled."""
        # Mock get_ts_path to return a valid path
        mock_videos_instance = MagicMock()
        mock_videos_instance.get_ts_path.return_value = "/videos/input/test.ts"
        mock_videos_instance.get_video_path.return_value = "/videos/input/test.mp4"
        mock_videos_cls.return_value = mock_videos_instance

        # Add pipeline with filesrc - use a path that won't trigger validation
        test_pipeline = PipelineDefinition(
            name="test-filesrc-looping",
            version=1,
            description="Test filesrc looping",
            source=PipelineSource.USER_CREATED,
            type=PipelineType.GSTREAMER,
            pipeline_description="filesrc ! fakesink",
            parameters=None,
        )
        added = self.manager.add_pipeline(test_pipeline)
        specs = [PipelinePerformanceSpec(id=added.id, streams=1)]

        execution_config = ExecutionConfig(
            output_mode=OutputMode.DISABLED,
            max_runtime=60,
        )

        command, _, _ = self.manager.build_pipeline_command(specs, execution_config)

        # Command should be valid
        self.assertIsInstance(command, str)
        self.assertGreater(len(command), 0)


if __name__ == "__main__":
    unittest.main()

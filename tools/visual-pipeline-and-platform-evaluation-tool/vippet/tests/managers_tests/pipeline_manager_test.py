import unittest
from unittest.mock import patch

from api.api_schemas import (
    Edge,
    ExecutionConfig,
    Node,
    OutputMode,
    PipelineDefinition,
    PipelineGraph,
    PipelinePerformanceSpec,
    PipelineSource,
    Variant,
    VariantReference,
    GraphInline,
)
from managers.pipeline_manager import PipelineManager
from videos import OUTPUT_VIDEO_DIR


def create_simple_graph() -> PipelineGraph:
    """Helper to create a simple valid pipeline graph."""
    return PipelineGraph(
        nodes=[
            Node(id="0", type="fakesrc", data={}),
            Node(id="1", type="fakesink", data={}),
        ],
        edges=[Edge(id="0", source="0", target="1")],
    )


def create_variant(name: str = "CPU", read_only: bool = False) -> Variant:
    """Helper to create a valid variant for testing."""
    graph = create_simple_graph()
    return Variant(
        id="variant-test",
        name=name,
        read_only=read_only,
        pipeline_graph=graph,
        pipeline_graph_simple=graph,
    )


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
            description="A test pipeline",
            source=PipelineSource.USER_CREATED,
            tags=["test"],
            variants=[create_variant()],
        )

        added_pipeline = manager.add_pipeline(new_pipeline)
        pipelines = manager.get_pipelines()
        self.assertEqual(len(pipelines), initial_count + 1)

        # Verify the added pipeline has an ID and correct attributes
        self.assertIsNotNone(added_pipeline.id)
        self.assertGreater(len(added_pipeline.id), 0)
        # ID should be a slugified version of the name
        self.assertEqual(added_pipeline.id, "user-defined-pipelines")
        self.assertEqual(added_pipeline.name, "user-defined-pipelines")
        self.assertEqual(len(added_pipeline.variants), 1)

        # Verify we can retrieve it by ID
        retrieved = manager.get_pipeline_by_id(added_pipeline.id)
        self.assertEqual(retrieved.name, "user-defined-pipelines")

    def test_add_pipeline_with_multiple_variants(self):
        """Test adding a pipeline with multiple variants."""
        manager = PipelineManager()
        manager.pipelines = []

        new_pipeline = PipelineDefinition(
            name="multi-variant-pipeline",
            description="Pipeline with CPU and GPU variants",
            source=PipelineSource.USER_CREATED,
            tags=["multi", "test"],
            variants=[
                create_variant(name="CPU"),
                create_variant(name="GPU"),
            ],
        )

        added_pipeline = manager.add_pipeline(new_pipeline)
        self.assertEqual(len(added_pipeline.variants), 2)
        variant_names = [v.name for v in added_pipeline.variants]
        self.assertIn("CPU", variant_names)
        self.assertIn("GPU", variant_names)

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

        # Check that predefined pipelines have variants
        for pipeline in pipelines:
            if pipeline.source == PipelineSource.PREDEFINED:
                self.assertGreater(len(pipeline.variants), 0)
                # Verify each variant has required fields
                for variant in pipeline.variants:
                    self.assertIsNotNone(variant.id)
                    self.assertIsNotNone(variant.name)
                    self.assertIsNotNone(variant.pipeline_graph)
                    self.assertIsNotNone(variant.pipeline_graph_simple)
                    # Predefined variants should be read-only
                    self.assertTrue(variant.read_only)

    def test_build_pipeline_command_single_pipeline_single_stream(self):
        manager = PipelineManager()
        manager.pipelines = []  # Reset pipelines for isolated test

        # Add a test pipeline with a variant
        test_pipeline = PipelineDefinition(
            name="test-pipelines",
            description="Test pipeline for single stream",
            source=PipelineSource.USER_CREATED,
            tags=[],
            variants=[create_variant()],
        )
        added = manager.add_pipeline(test_pipeline)
        variant_id = added.variants[0].id

        # Build command using VariantReference
        pipeline_performance_specs = [
            PipelinePerformanceSpec(
                pipeline=VariantReference(
                    pipeline_id=added.id,
                    variant_id=variant_id,
                ),
                streams=1,
            )
        ]
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

    def test_build_pipeline_command_with_inline_graph(self):
        """Test building pipeline command with inline graph instead of variant reference."""
        manager = PipelineManager()
        manager.pipelines = []

        inline_graph = create_simple_graph()

        # Build command using GraphInline
        pipeline_performance_specs = [
            PipelinePerformanceSpec(
                pipeline=GraphInline(pipeline_graph=inline_graph),
                streams=1,
            )
        ]
        execution_config = ExecutionConfig(output_mode=OutputMode.DISABLED)

        command, output_paths, live_stream_urls = manager.build_pipeline_command(
            pipeline_performance_specs, execution_config
        )

        self.assertIsInstance(command, str)
        self.assertGreater(len(command), 0)
        self.assertIn("fakesrc", command)

        # Verify output_paths key uses __graph- prefix for inline graphs
        for key in output_paths.keys():
            self.assertTrue(key.startswith("__graph-"))

    def test_build_pipeline_command_single_pipeline_multiple_streams(self):
        manager = PipelineManager()
        manager.pipelines = []  # Reset pipelines for isolated test

        # Create variant with tee element
        tee_graph = PipelineGraph(
            nodes=[
                Node(id="0", type="videotestsrc", data={}),
                Node(id="1", type="tee", data={"name": "t"}),
                Node(id="2", type="queue", data={}),
                Node(id="3", type="fakesink", data={}),
            ],
            edges=[
                Edge(id="0", source="0", target="1"),
                Edge(id="1", source="1", target="2"),
                Edge(id="2", source="2", target="3"),
            ],
        )
        variant = Variant(
            id="variant-tee",
            name="CPU",
            read_only=False,
            pipeline_graph=tee_graph,
            pipeline_graph_simple=tee_graph,
        )

        test_pipeline = PipelineDefinition(
            name="test-pipelines",
            description="Test pipeline for multiple streams",
            source=PipelineSource.USER_CREATED,
            tags=[],
            variants=[variant],
        )
        added = manager.add_pipeline(test_pipeline)

        # Build command with 3 streams
        pipeline_performance_specs = [
            PipelinePerformanceSpec(
                pipeline=VariantReference(
                    pipeline_id=added.id,
                    variant_id=added.variants[0].id,
                ),
                streams=3,
            )
        ]
        execution_config = ExecutionConfig(output_mode=OutputMode.DISABLED)

        command, output_paths, live_stream_urls = manager.build_pipeline_command(
            pipeline_performance_specs, execution_config
        )

        # Verify command contains multiple instances
        self.assertIsInstance(command, str)
        self.assertGreater(len(command), 0)
        # Should have 3 instances of videotestsrc (one per stream)
        self.assertEqual(command.count("videotestsrc"), 3)

    def test_build_pipeline_command_multiple_pipelines(self):
        manager = PipelineManager()
        manager.pipelines = []  # Reset pipelines for isolated test

        # Add two test pipelines with different element types
        graph1 = PipelineGraph(
            nodes=[
                Node(id="0", type="fakesrc", data={"name": "source1"}),
                Node(id="1", type="fakesink", data={}),
            ],
            edges=[Edge(id="0", source="0", target="1")],
        )
        graph2 = PipelineGraph(
            nodes=[
                Node(id="0", type="videotestsrc", data={"name": "source2"}),
                Node(id="1", type="fakesink", data={}),
            ],
            edges=[Edge(id="0", source="0", target="1")],
        )

        pipeline1 = PipelineDefinition(
            name="pipeline-1",
            description="First test pipeline",
            source=PipelineSource.USER_CREATED,
            tags=[],
            variants=[
                Variant(
                    id="v1",
                    name="CPU",
                    read_only=False,
                    pipeline_graph=graph1,
                    pipeline_graph_simple=graph1,
                )
            ],
        )
        pipeline2 = PipelineDefinition(
            name="pipeline-2",
            description="Second test pipeline",
            source=PipelineSource.USER_CREATED,
            tags=[],
            variants=[
                Variant(
                    id="v2",
                    name="CPU",
                    read_only=False,
                    pipeline_graph=graph2,
                    pipeline_graph_simple=graph2,
                )
            ],
        )
        added1 = manager.add_pipeline(pipeline1)
        added2 = manager.add_pipeline(pipeline2)

        # Build command with two pipelines
        pipeline_performance_specs = [
            PipelinePerformanceSpec(
                pipeline=VariantReference(
                    pipeline_id=added1.id,
                    variant_id=added1.variants[0].id,
                ),
                streams=2,
            ),
            PipelinePerformanceSpec(
                pipeline=VariantReference(
                    pipeline_id=added2.id,
                    variant_id=added2.variants[0].id,
                ),
                streams=3,
            ),
        ]
        execution_config = ExecutionConfig(output_mode=OutputMode.DISABLED)

        command, output_paths, live_stream_urls = manager.build_pipeline_command(
            pipeline_performance_specs, execution_config
        )

        # Verify both pipeline types are present
        self.assertIsInstance(command, str)
        self.assertGreater(len(command), 0)
        # Should have 2 instances of fakesrc and 3 instances of videotestsrc
        self.assertEqual(command.count("fakesrc"), 2)
        self.assertEqual(command.count("videotestsrc"), 3)

    def test_build_pipeline_command_nonexistent_variant_raises_error(self):
        manager = PipelineManager()
        manager.pipelines = []

        # Add a pipeline but reference wrong variant
        test_pipeline = PipelineDefinition(
            name="test-pipeline",
            description="Test",
            source=PipelineSource.USER_CREATED,
            tags=[],
            variants=[create_variant()],
        )
        added = manager.add_pipeline(test_pipeline)

        pipeline_performance_specs = [
            PipelinePerformanceSpec(
                pipeline=VariantReference(
                    pipeline_id=added.id,
                    variant_id="nonexistent-variant-id",
                ),
                streams=1,
            )
        ]
        execution_config = ExecutionConfig(output_mode=OutputMode.DISABLED)

        with self.assertRaises(ValueError) as context:
            manager.build_pipeline_command(pipeline_performance_specs, execution_config)

        self.assertIn("not found", str(context.exception))

    def test_update_pipeline_description_and_name(self):
        manager = PipelineManager()
        manager.pipelines = []

        new_pipeline = PipelineDefinition(
            name="original-name",
            description="Original description",
            source=PipelineSource.USER_CREATED,
            tags=["original"],
            variants=[create_variant()],
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

    def test_update_pipeline_tags(self):
        """Test updating pipeline tags."""
        manager = PipelineManager()
        manager.pipelines = []

        new_pipeline = PipelineDefinition(
            name="test-tags",
            description="Test",
            source=PipelineSource.USER_CREATED,
            tags=["original"],
            variants=[create_variant()],
        )

        added = manager.add_pipeline(new_pipeline)

        updated = manager.update_pipeline(
            pipeline_id=added.id,
            tags=["updated", "new-tag"],
        )

        self.assertEqual(updated.tags, ["updated", "new-tag"])

    def test_update_pipeline_not_found_raises(self):
        manager = PipelineManager()
        manager.pipelines = []

        with self.assertRaises(ValueError) as context:
            manager.update_pipeline(pipeline_id="nonexistent", name="new-name")

        self.assertIn(
            "Pipeline with id 'nonexistent' not found.", str(context.exception)
        )

    def test_delete_pipeline_user_created(self):
        """Test deleting user-created pipeline succeeds."""
        manager = PipelineManager()
        manager.pipelines = []

        new_pipeline = PipelineDefinition(
            name="to-delete",
            description="Test",
            source=PipelineSource.USER_CREATED,
            tags=[],
            variants=[create_variant()],
        )
        added = manager.add_pipeline(new_pipeline)

        # Delete should succeed
        manager.delete_pipeline_by_id(added.id)

        # Verify pipeline is removed
        with self.assertRaises(ValueError):
            manager.get_pipeline_by_id(added.id)

    def test_delete_pipeline_predefined_raises_error(self):
        """Test that deleting a PREDEFINED pipeline raises error."""
        manager = PipelineManager()

        # Find a predefined pipeline
        predefined = None
        for p in manager.get_pipelines():
            if p.source == PipelineSource.PREDEFINED:
                predefined = p
                break

        assert predefined is not None  # Type narrowing for pyright

        with self.assertRaises(ValueError) as context:
            manager.delete_pipeline_by_id(predefined.id)

        self.assertIn("PREDEFINED", str(context.exception))

    def test_build_pipeline_command_with_video_output_enabled(self):
        """Test building pipeline command with video output enabled (file mode)."""
        manager = PipelineManager()
        manager.pipelines = []

        graph = PipelineGraph(
            nodes=[
                Node(id="0", type="videotestsrc", data={}),
                Node(id="1", type="fakesink", data={}),
            ],
            edges=[Edge(id="0", source="0", target="1")],
        )
        new_pipeline = PipelineDefinition(
            name="test-video-output",
            description="Pipeline for testing video output",
            source=PipelineSource.USER_CREATED,
            tags=[],
            variants=[
                Variant(
                    id="v1",
                    name="CPU",
                    read_only=False,
                    pipeline_graph=graph,
                    pipeline_graph_simple=graph,
                )
            ],
        )
        added = manager.add_pipeline(new_pipeline)
        pipeline_id = f"/pipelines/{added.id}/variants/{added.variants[0].id}"

        pipeline_performance_specs = [
            PipelinePerformanceSpec(
                pipeline=VariantReference(
                    pipeline_id=added.id,
                    variant_id=added.variants[0].id,
                ),
                streams=1,
            )
        ]
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
        self.assertIn(pipeline_id, output_paths)
        self.assertGreater(len(output_paths[pipeline_id]), 0)

        # Verify output directory is in the command
        self.assertIn(OUTPUT_VIDEO_DIR, command)

        # Verify fakesink is replaced with encoder pipeline
        self.assertNotIn("fakesink", command)
        self.assertIn("filesink", command)

        # Verify no live stream URLs for file output mode
        self.assertEqual(len(live_stream_urls), 0)

    def test_pipeline_id_format_variant_reference(self):
        """Test that variant reference produces correct pipeline ID format."""
        manager = PipelineManager()
        manager.pipelines = []

        new_pipeline = PipelineDefinition(
            name="test-id-format",
            description="Test",
            source=PipelineSource.USER_CREATED,
            tags=[],
            variants=[create_variant()],
        )
        added = manager.add_pipeline(new_pipeline)

        pipeline_performance_specs = [
            PipelinePerformanceSpec(
                pipeline=VariantReference(
                    pipeline_id=added.id,
                    variant_id=added.variants[0].id,
                ),
                streams=1,
            )
        ]
        execution_config = ExecutionConfig(output_mode=OutputMode.DISABLED)

        _, output_paths, _ = manager.build_pipeline_command(
            pipeline_performance_specs, execution_config
        )

        # Verify pipeline ID format for variant reference
        expected_id = f"/pipelines/{added.id}/variants/{added.variants[0].id}"
        self.assertIn(expected_id, output_paths.keys())


class TestVariantCRUD(unittest.TestCase):
    """Test cases for variant CRUD operations."""

    def test_add_variant_to_pipeline(self):
        """Test adding a new variant to an existing pipeline."""
        manager = PipelineManager()
        manager.pipelines = []

        # Create pipeline with one variant
        new_pipeline = PipelineDefinition(
            name="test-add-variant",
            description="Test",
            source=PipelineSource.USER_CREATED,
            tags=[],
            variants=[create_variant(name="CPU")],
        )
        added = manager.add_pipeline(new_pipeline)
        self.assertEqual(len(added.variants), 1)

        # Add another variant
        new_graph = PipelineGraph(
            nodes=[
                Node(id="0", type="videotestsrc", data={}),
                Node(id="1", type="fakesink", data={}),
            ],
            edges=[Edge(id="0", source="0", target="1")],
        )

        new_variant = manager.add_variant(
            pipeline_id=added.id,
            name="GPU",
            pipeline_graph=new_graph,
            pipeline_graph_simple=new_graph,
        )

        # Verify variant was added
        self.assertIsNotNone(new_variant.id)
        self.assertGreater(len(new_variant.id), 0)
        # ID should be a slugified version of the name
        self.assertEqual(new_variant.id, "gpu")
        self.assertEqual(new_variant.name, "GPU")
        self.assertFalse(new_variant.read_only)

        # Verify pipeline now has two variants
        retrieved = manager.get_pipeline_by_id(added.id)
        self.assertEqual(len(retrieved.variants), 2)

    def test_add_variant_to_nonexistent_pipeline(self):
        """Test that adding variant to nonexistent pipeline raises error."""
        manager = PipelineManager()
        manager.pipelines = []

        with self.assertRaises(ValueError) as context:
            manager.add_variant(
                pipeline_id="nonexistent",
                name="GPU",
                pipeline_graph=create_simple_graph(),
                pipeline_graph_simple=create_simple_graph(),
            )

        self.assertIn("not found", str(context.exception))

    def test_delete_variant(self):
        """Test deleting a variant from a pipeline."""
        manager = PipelineManager()
        manager.pipelines = []

        # Create pipeline with two variants
        new_pipeline = PipelineDefinition(
            name="test-delete-variant",
            description="Test",
            source=PipelineSource.USER_CREATED,
            tags=[],
            variants=[
                create_variant(name="CPU"),
                create_variant(name="GPU"),
            ],
        )
        added = manager.add_pipeline(new_pipeline)
        self.assertEqual(len(added.variants), 2)

        # Delete second variant
        variant_to_delete = added.variants[1].id
        manager.delete_variant(added.id, variant_to_delete)

        # Verify variant was deleted
        retrieved = manager.get_pipeline_by_id(added.id)
        self.assertEqual(len(retrieved.variants), 1)

    def test_delete_last_variant_raises_error(self):
        """Test that deleting the last variant raises error."""
        manager = PipelineManager()
        manager.pipelines = []

        new_pipeline = PipelineDefinition(
            name="test-last-variant",
            description="Test",
            source=PipelineSource.USER_CREATED,
            tags=[],
            variants=[create_variant()],
        )
        added = manager.add_pipeline(new_pipeline)

        with self.assertRaises(ValueError) as context:
            manager.delete_variant(added.id, added.variants[0].id)

        self.assertIn("last variant", str(context.exception))

    def test_delete_nonexistent_variant_raises_error(self):
        """Test that deleting a nonexistent variant raises error."""
        manager = PipelineManager()
        manager.pipelines = []

        new_pipeline = PipelineDefinition(
            name="test-nonexistent",
            description="Test",
            source=PipelineSource.USER_CREATED,
            tags=[],
            variants=[create_variant()],
        )
        added = manager.add_pipeline(new_pipeline)

        with self.assertRaises(ValueError) as context:
            manager.delete_variant(added.id, "nonexistent-variant")

        self.assertIn("not found", str(context.exception))

    def test_update_variant_name(self):
        """Test updating variant name."""
        manager = PipelineManager()
        manager.pipelines = []

        new_pipeline = PipelineDefinition(
            name="test-update-variant",
            description="Test",
            source=PipelineSource.USER_CREATED,
            tags=[],
            variants=[create_variant(name="CPU")],
        )
        added = manager.add_pipeline(new_pipeline)

        updated = manager.update_variant(
            pipeline_id=added.id,
            variant_id=added.variants[0].id,
            name="GPU-optimized",
        )

        self.assertEqual(updated.name, "GPU-optimized")

    def test_update_variant_pipeline_graph(self):
        """Test updating variant with new pipeline graph."""
        manager = PipelineManager()
        manager.pipelines = []

        new_pipeline = PipelineDefinition(
            name="test-update-graph",
            description="Test",
            source=PipelineSource.USER_CREATED,
            tags=[],
            variants=[create_variant()],
        )
        added = manager.add_pipeline(new_pipeline)

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

        updated = manager.update_variant(
            pipeline_id=added.id,
            variant_id=added.variants[0].id,
            pipeline_graph=new_graph,
        )

        # Verify graph was updated
        self.assertEqual(len(updated.pipeline_graph.nodes), 3)
        # Verify simple view was auto-generated
        self.assertIsNotNone(updated.pipeline_graph_simple)

    def test_update_variant_both_graphs_raises_error(self):
        """Test that providing both graph types raises error."""
        manager = PipelineManager()
        manager.pipelines = []

        new_pipeline = PipelineDefinition(
            name="test-both-graphs",
            description="Test",
            source=PipelineSource.USER_CREATED,
            tags=[],
            variants=[create_variant()],
        )
        added = manager.add_pipeline(new_pipeline)

        graph = create_simple_graph()

        with self.assertRaises(ValueError) as context:
            manager.update_variant(
                pipeline_id=added.id,
                variant_id=added.variants[0].id,
                pipeline_graph=graph,
                pipeline_graph_simple=graph,
            )

        self.assertIn("Cannot update both", str(context.exception))


class TestBuildPipelineCommandExecutionConfig(unittest.TestCase):
    """Test cases for ExecutionConfig validation in build_pipeline_command."""

    def setUp(self):
        PipelineManager._instance = None
        self.manager = PipelineManager()
        self.manager.pipelines = []

        # Add a test pipeline for all tests
        graph = PipelineGraph(
            nodes=[
                Node(id="0", type="videotestsrc", data={}),
                Node(id="1", type="fakesink", data={}),
            ],
            edges=[Edge(id="0", source="0", target="1")],
        )
        test_pipeline = PipelineDefinition(
            name="test-execution-config",
            description="Test pipeline for execution config",
            source=PipelineSource.USER_CREATED,
            tags=[],
            variants=[
                Variant(
                    id="v1",
                    name="CPU",
                    read_only=False,
                    pipeline_graph=graph,
                    pipeline_graph_simple=graph,
                )
            ],
        )
        self.added_pipeline = self.manager.add_pipeline(test_pipeline)
        self.specs = [
            PipelinePerformanceSpec(
                pipeline=VariantReference(
                    pipeline_id=self.added_pipeline.id,
                    variant_id=self.added_pipeline.variants[0].id,
                ),
                streams=1,
            )
        ]

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
        pipeline_id = f"/pipelines/{self.added_pipeline.id}/variants/{self.added_pipeline.variants[0].id}"
        self.assertIn(pipeline_id, live_stream_urls)

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
        pipeline_id = f"/pipelines/{self.added_pipeline.id}/variants/{self.added_pipeline.variants[0].id}"
        self.assertIn(pipeline_id, live_stream_urls)
        stream_url = live_stream_urls[pipeline_id]
        self.assertTrue(stream_url.startswith("rtsp://"))

    def test_live_stream_one_url_per_pipeline(self):
        """Test that only one live stream URL is generated per pipeline."""
        # Add another pipeline
        graph = PipelineGraph(
            nodes=[
                Node(id="0", type="videotestsrc", data={}),
                Node(id="1", type="fakesink", data={}),
            ],
            edges=[Edge(id="0", source="0", target="1")],
        )
        another_pipeline = PipelineDefinition(
            name="test-execution-config-2",
            description="Another test pipeline",
            source=PipelineSource.USER_CREATED,
            tags=[],
            variants=[
                Variant(
                    id="v2",
                    name="CPU",
                    read_only=False,
                    pipeline_graph=graph,
                    pipeline_graph_simple=graph,
                )
            ],
        )
        added2 = self.manager.add_pipeline(another_pipeline)

        specs = [
            PipelinePerformanceSpec(
                pipeline=VariantReference(
                    pipeline_id=self.added_pipeline.id,
                    variant_id=self.added_pipeline.variants[0].id,
                ),
                streams=3,
            ),
            PipelinePerformanceSpec(
                pipeline=VariantReference(
                    pipeline_id=added2.id,
                    variant_id=added2.variants[0].id,
                ),
                streams=2,
            ),
        ]
        execution_config = ExecutionConfig(
            output_mode=OutputMode.LIVE_STREAM,
            max_runtime=60,
        )

        command, output_paths, live_stream_urls = self.manager.build_pipeline_command(
            specs, execution_config
        )

        # Should have exactly 2 live stream URLs (one per pipeline)
        self.assertEqual(len(live_stream_urls), 2)

        # Only first stream of each pipeline should have rtspclientsink
        self.assertEqual(command.count("rtspclientsink"), 2)


class TestBuildPipelineCommandLooping(unittest.TestCase):
    """Test cases for looping behavior in build_pipeline_command."""

    def setUp(self):
        self.manager = PipelineManager()
        self.manager.pipelines = []

        # Add a test pipeline with videotestsrc for looping tests
        graph = PipelineGraph(
            nodes=[
                Node(id="0", type="videotestsrc", data={}),
                Node(id="1", type="fakesink", data={}),
            ],
            edges=[Edge(id="0", source="0", target="1")],
        )
        test_pipeline = PipelineDefinition(
            name="test-looping",
            description="Test pipeline for looping",
            source=PipelineSource.USER_CREATED,
            tags=[],
            variants=[
                Variant(
                    id="v1",
                    name="CPU",
                    read_only=False,
                    pipeline_graph=graph,
                    pipeline_graph_simple=graph,
                )
            ],
        )
        self.added_pipeline = self.manager.add_pipeline(test_pipeline)
        self.specs = [
            PipelinePerformanceSpec(
                pipeline=VariantReference(
                    pipeline_id=self.added_pipeline.id,
                    variant_id=self.added_pipeline.variants[0].id,
                ),
                streams=1,
            )
        ]

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
        pipeline_id = f"/pipelines/{self.added_pipeline.id}/variants/{self.added_pipeline.variants[0].id}"
        self.assertIn(pipeline_id, live_stream_urls)

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


# Mock pipeline configs for testing predefined pipelines
MOCK_PIPELINE_CONFIGS = [
    {
        "name": "object-detection",
        "definition": "Object detection pipeline for testing",
        "tags": ["detection", "test"],
        "variants": [
            {
                "name": "CPU",
                "pipeline_description": "filesrc location=/videos/test.mp4 ! decodebin ! fakesink",
            },
            {
                "name": "GPU",
                "pipeline_description": "filesrc location=/videos/test.mp4 ! decodebin ! fakesink",
            },
        ],
    },
    {
        "name": "classification",
        "definition": "Classification pipeline for testing",
        "tags": ["classification", "test"],
        "variants": [
            {
                "name": "CPU",
                "pipeline_description": "filesrc location=/videos/test.mp4 ! decodebin ! fakesink",
            },
            {
                "name": "GPU",
                "pipeline_description": "filesrc location=/videos/test.mp4 ! decodebin ! fakesink",
            },
            {
                "name": "NPU",
                "pipeline_description": "filesrc location=/videos/test.mp4 ! decodebin ! fakesink",
            },
        ],
    },
]


def mock_pipeline_loader_list():
    """Return mock list of pipeline config paths."""
    return [f"config_{i}.yaml" for i in range(len(MOCK_PIPELINE_CONFIGS))]


def mock_pipeline_loader_config(config_path: str):
    """Return mock pipeline config based on path."""
    index = int(config_path.split("_")[1].split(".")[0])
    return MOCK_PIPELINE_CONFIGS[index]


class TestPredefinedPipelinesStructure(unittest.TestCase):
    """Test cases for predefined pipelines structure after migration to variants."""

    def setUp(self):
        """Reset singleton state before each test."""
        PipelineManager._instance = None

    def tearDown(self):
        """Reset singleton state after each test."""
        PipelineManager._instance = None

    @patch("managers.pipeline_manager.PipelineLoader")
    def test_predefined_pipelines_have_correct_structure(self, mock_loader_cls):
        """Verify predefined pipelines have correct structure with variants."""
        # Setup mock
        mock_loader_cls.list.return_value = mock_pipeline_loader_list()
        mock_loader_cls.config.side_effect = mock_pipeline_loader_config

        manager = PipelineManager()
        pipelines = manager.get_pipelines()

        predefined_count = 0
        for pipeline in pipelines:
            if pipeline.source == PipelineSource.PREDEFINED:
                predefined_count += 1

                # Verify basic fields
                self.assertIsNotNone(pipeline.id)
                self.assertIsNotNone(pipeline.name)
                self.assertIsNotNone(pipeline.description)

                # Verify variants
                self.assertGreater(len(pipeline.variants), 0)

                for variant in pipeline.variants:
                    # Verify variant fields
                    self.assertIsNotNone(variant.id)
                    self.assertGreater(len(variant.id), 0)
                    self.assertIsNotNone(variant.name)
                    self.assertIn(variant.name, ["CPU", "GPU", "NPU"])
                    # ID should be a slugified version of the name (lowercase)
                    self.assertIn(variant.id, ["cpu", "gpu", "npu"])
                    self.assertTrue(variant.read_only)
                    self.assertIsNotNone(variant.pipeline_graph)
                    self.assertIsNotNone(variant.pipeline_graph_simple)

                    # Verify graphs have content
                    self.assertGreater(len(variant.pipeline_graph.nodes), 0)
                    self.assertGreater(len(variant.pipeline_graph_simple.nodes), 0)

        self.assertGreater(predefined_count, 0)
        self.assertEqual(predefined_count, len(MOCK_PIPELINE_CONFIGS))

    @patch("managers.pipeline_manager.PipelineLoader")
    def test_predefined_pipelines_have_multiple_variants(self, mock_loader_cls):
        """Verify predefined pipelines have multiple variants (CPU/GPU/NPU)."""
        # Setup mock
        mock_loader_cls.list.return_value = mock_pipeline_loader_list()
        mock_loader_cls.config.side_effect = mock_pipeline_loader_config

        manager = PipelineManager()
        pipelines = manager.get_pipelines()

        multi_variant_count = 0
        predefined_count = 0
        for pipeline in pipelines:
            if pipeline.source == PipelineSource.PREDEFINED:
                predefined_count += 1
                if len(pipeline.variants) > 1:
                    multi_variant_count += 1

        # Most predefined pipelines should have multiple variants
        self.assertGreater(multi_variant_count, 0)
        # All our mock configs have multiple variants
        self.assertEqual(multi_variant_count, predefined_count)


class TestDeletePredefinedPipeline(unittest.TestCase):
    """Test cases for deleting predefined pipelines."""

    def setUp(self):
        """Reset singleton state before each test."""
        PipelineManager._instance = None

    def tearDown(self):
        """Reset singleton state after each test."""
        PipelineManager._instance = None

    @patch("managers.pipeline_manager.PipelineLoader")
    def test_delete_predefined_pipeline_raises_error(self, mock_loader_cls):
        """Test that deleting a PREDEFINED pipeline raises error."""
        # Setup mock
        mock_loader_cls.list.return_value = mock_pipeline_loader_list()
        mock_loader_cls.config.side_effect = mock_pipeline_loader_config

        manager = PipelineManager()

        # Find a predefined pipeline
        predefined = None
        for p in manager.get_pipelines():
            if p.source == PipelineSource.PREDEFINED:
                predefined = p
                break

        assert predefined is not None  # Type narrowing for pyright

        with self.assertRaises(ValueError) as context:
            manager.delete_pipeline_by_id(predefined.id)

        self.assertIn("PREDEFINED", str(context.exception))


class TestDeleteReadOnlyVariant(unittest.TestCase):
    """Test cases for deleting read-only variants."""

    def setUp(self):
        """Reset singleton state before each test."""
        PipelineManager._instance = None

    def tearDown(self):
        """Reset singleton state after each test."""
        PipelineManager._instance = None

    @patch("managers.pipeline_manager.PipelineLoader")
    def test_delete_readonly_variant_raises_error(self, mock_loader_cls):
        """Test that deleting a read-only variant raises error."""
        # Setup mock
        mock_loader_cls.list.return_value = mock_pipeline_loader_list()
        mock_loader_cls.config.side_effect = mock_pipeline_loader_config

        manager = PipelineManager()

        # Find a predefined pipeline with read-only variants
        predefined = None
        for p in manager.get_pipelines():
            if p.source == PipelineSource.PREDEFINED and len(p.variants) > 0:
                predefined = p
                break

        assert predefined is not None  # Type narrowing for pyright

        readonly_variant = predefined.variants[0]
        self.assertTrue(readonly_variant.read_only)

        with self.assertRaises(ValueError) as context:
            manager.delete_variant(predefined.id, readonly_variant.id)

        self.assertIn("read-only", str(context.exception))


class TestUpdateReadOnlyVariant(unittest.TestCase):
    """Test cases for updating read-only variants."""

    def setUp(self):
        """Reset singleton state before each test."""
        PipelineManager._instance = None

    def tearDown(self):
        """Reset singleton state after each test."""
        PipelineManager._instance = None

    @patch("managers.pipeline_manager.PipelineLoader")
    def test_update_readonly_variant_raises_error(self, mock_loader_cls):
        """Test that updating a read-only variant raises error."""
        # Setup mock
        mock_loader_cls.list.return_value = mock_pipeline_loader_list()
        mock_loader_cls.config.side_effect = mock_pipeline_loader_config

        manager = PipelineManager()

        # Find a predefined pipeline with read-only variants
        predefined = None
        for p in manager.get_pipelines():
            if p.source == PipelineSource.PREDEFINED and len(p.variants) > 0:
                predefined = p
                break

        assert predefined is not None  # Type narrowing for pyright

        readonly_variant = predefined.variants[0]

        with self.assertRaises(ValueError) as context:
            manager.update_variant(
                pipeline_id=predefined.id,
                variant_id=readonly_variant.id,
                name="new-name",
            )

        self.assertIn("read-only", str(context.exception))

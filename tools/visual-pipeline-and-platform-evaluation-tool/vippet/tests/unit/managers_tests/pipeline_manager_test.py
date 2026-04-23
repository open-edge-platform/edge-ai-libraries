import unittest
from datetime import datetime, timezone
from unittest.mock import patch

from graph import Graph
from internal_types import (
    InternalExecutionConfig,
    InternalMetadataMode,
    InternalOutputMode,
    InternalPipelineDefinition,
    InternalPipelinePerformanceSpec,
    InternalPipelineSource,
    InternalVariantCreate,
)
from managers.pipeline_manager import PipelineManager, METADATA_DIR
from videos import OUTPUT_VIDEO_DIR


def create_simple_graph() -> Graph:
    """Helper to create a simple valid pipeline graph as Graph object."""
    return Graph.from_dict(
        {
            "nodes": [
                {"id": "0", "type": "fakesrc", "data": {}},
                {
                    "id": "1",
                    "type": "fakesink",
                    "data": {"name": "default_output_sink"},
                },
            ],
            "edges": [{"id": "0", "source": "0", "target": "1"}],
        }
    )


def create_gvametapublish_graph(publish_nodes: int = 1) -> Graph:
    """Helper to create a pipeline graph with gvametapublish nodes for metadata tests.

    Builds a linear chain: fakesrc → gvametapublish(1) … gvametapublish(N) → fakesink.

    Args:
        publish_nodes: Number of gvametapublish nodes to include (default 1).
    """
    nodes: list[dict] = [{"id": "0", "type": "fakesrc", "data": {}}]
    edges: list[dict] = []
    for i in range(publish_nodes):
        node_id = str(1 + i)
        nodes.append({"id": node_id, "type": "gvametapublish", "data": {}})
        edges.append({"id": str(i), "source": str(i), "target": node_id})
    sink_id = str(1 + publish_nodes)
    nodes.append(
        {"id": sink_id, "type": "fakesink", "data": {"name": "default_output_sink"}}
    )
    edges.append(
        {"id": str(publish_nodes), "source": str(publish_nodes), "target": sink_id}
    )
    return Graph.from_dict({"nodes": nodes, "edges": edges})


def create_variant_create(name: str = "CPU") -> InternalVariantCreate:
    """Helper to create a valid InternalVariantCreate for testing."""
    graph = create_simple_graph()
    return InternalVariantCreate(
        name=name,
        pipeline_graph=graph,
        pipeline_graph_simple=graph,
    )


def create_internal_execution_config(
    output_mode: InternalOutputMode = InternalOutputMode.DISABLED,
    max_runtime: float = 0,
    metadata_mode: InternalMetadataMode = InternalMetadataMode.DISABLED,
) -> InternalExecutionConfig:
    """Helper to create InternalExecutionConfig for testing."""
    return InternalExecutionConfig(
        output_mode=output_mode,
        max_runtime=max_runtime,
        metadata_mode=metadata_mode,
    )


def create_internal_performance_spec(
    pipeline_id: str,
    pipeline_name: str,
    streams: int = 1,
    graph: Graph | None = None,
) -> InternalPipelinePerformanceSpec:
    """Helper to create InternalPipelinePerformanceSpec for testing."""
    if graph is None:
        graph = create_simple_graph()
    return InternalPipelinePerformanceSpec(
        pipeline_id=pipeline_id,
        pipeline_name=pipeline_name,
        pipeline_graph=graph,
        streams=streams,
    )


def create_pipeline_definition(
    name: str = "test-pipeline",
    description: str = "A test pipeline",
    tags: list[str] | None = None,
    variants: list[InternalVariantCreate] | None = None,
) -> InternalPipelineDefinition:
    """Helper to create an InternalPipelineDefinition for testing."""
    if tags is None:
        tags = []
    if variants is None:
        variants = [create_variant_create()]
    return InternalPipelineDefinition(
        name=name,
        description=description,
        source=InternalPipelineSource.USER_CREATED,
        tags=tags,
        variants=variants,
    )


class TestPipelineManager(unittest.TestCase):
    def setUp(self):
        """Reset singleton state before each test."""
        PipelineManager._instance = None
        self.job_id = "test-job-123"

    def test_add_pipeline_valid(self):
        manager = PipelineManager()
        manager.pipelines = []
        initial_count = len(manager.get_pipelines())

        new_pipeline = create_pipeline_definition(
            name="user-defined-pipelines",
            description="A test pipeline",
            tags=["test"],
            variants=[create_variant_create()],
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

        # Verify variant ID was generated from variant name
        variant = added_pipeline.variants[0]
        self.assertEqual(variant.id, "cpu")  # slugified from "CPU"
        self.assertFalse(variant.read_only)  # User-created variants are never read-only

        # Verify timestamps are datetime objects with UTC timezone
        self.assertIsInstance(added_pipeline.created_at, datetime)
        self.assertIsInstance(added_pipeline.modified_at, datetime)
        self.assertEqual(added_pipeline.created_at.tzinfo, timezone.utc)
        self.assertEqual(added_pipeline.modified_at.tzinfo, timezone.utc)
        self.assertEqual(added_pipeline.created_at, added_pipeline.modified_at)

        # Verify variant timestamps
        self.assertIsInstance(variant.created_at, datetime)
        self.assertIsInstance(variant.modified_at, datetime)
        self.assertEqual(variant.created_at.tzinfo, timezone.utc)

        # Verify thumbnail is None for user-created pipeline
        self.assertIsNone(added_pipeline.thumbnail)

        # Verify we can retrieve it by ID
        retrieved = manager.get_pipeline_by_id(added_pipeline.id)
        self.assertEqual(retrieved.name, "user-defined-pipelines")

    def test_add_pipeline_with_multiple_variants(self):
        """Test adding a pipeline with multiple variants."""
        manager = PipelineManager()
        manager.pipelines = []

        new_pipeline = create_pipeline_definition(
            name="multi-variant-pipeline",
            description="Pipeline with CPU and GPU variants",
            tags=["multi", "test"],
            variants=[
                create_variant_create(name="CPU"),
                create_variant_create(name="GPU"),
            ],
        )

        added_pipeline = manager.add_pipeline(new_pipeline)
        self.assertEqual(len(added_pipeline.variants), 2)
        variant_names = [v.name for v in added_pipeline.variants]
        self.assertIn("CPU", variant_names)
        self.assertIn("GPU", variant_names)

        # Verify variant IDs were generated from names
        variant_ids = [v.id for v in added_pipeline.variants]
        self.assertIn("cpu", variant_ids)
        self.assertIn("gpu", variant_ids)

        # Verify all variants have read_only=False
        for variant in added_pipeline.variants:
            self.assertFalse(variant.read_only)

    def test_get_pipeline_by_id_not_found(self):
        manager = PipelineManager()

        with self.assertRaises(ValueError) as context:
            manager.get_pipeline_by_id("nonexistent-pipeline-id")

        self.assertIn(
            "Pipeline with id 'nonexistent-pipeline-id' not found.",
            str(context.exception),
        )

    def test_get_variant_by_ids_success(self):
        """Test successful retrieval of variant by pipeline and variant IDs."""
        manager = PipelineManager()
        manager.pipelines = []

        # Add a test pipeline with a variant
        new_pipeline = create_pipeline_definition(
            name="test-variant-lookup",
            description="Test pipeline for variant lookup",
            variants=[create_variant_create(name="CPU")],
        )
        added = manager.add_pipeline(new_pipeline)
        variant_id = added.variants[0].id

        # Retrieve variant by IDs
        variant = manager.get_variant_by_ids(added.id, variant_id)

        self.assertIsNotNone(variant)
        self.assertEqual(variant.id, variant_id)
        self.assertEqual(variant.name, "CPU")

    def test_get_variant_by_ids_pipeline_not_found(self):
        """Test get_variant_by_ids raises error when pipeline not found."""
        manager = PipelineManager()
        manager.pipelines = []

        with self.assertRaises(ValueError) as context:
            manager.get_variant_by_ids("nonexistent-pipeline", "some-variant")

        self.assertIn(
            "Pipeline with id 'nonexistent-pipeline' not found.",
            str(context.exception),
        )

    def test_get_variant_by_ids_variant_not_found(self):
        """Test get_variant_by_ids raises error when variant not found."""
        manager = PipelineManager()
        manager.pipelines = []

        new_pipeline = create_pipeline_definition(
            name="test-variant-lookup",
            description="Test pipeline",
        )
        added = manager.add_pipeline(new_pipeline)

        with self.assertRaises(ValueError) as context:
            manager.get_variant_by_ids(added.id, "nonexistent-variant")

        self.assertIn(
            f"Variant 'nonexistent-variant' not found in pipeline '{added.id}'.",
            str(context.exception),
        )

    def test_get_variant_by_ids_returns_copy(self):
        """Test that get_variant_by_ids returns a copy, not the original."""
        manager = PipelineManager()
        manager.pipelines = []

        new_pipeline = create_pipeline_definition(
            name="test-variant-copy",
            description="Test pipeline",
            variants=[create_variant_create(name="CPU")],
        )
        added = manager.add_pipeline(new_pipeline)
        variant_id = added.variants[0].id

        # Get variant and modify it
        variant = manager.get_variant_by_ids(added.id, variant_id)
        variant.name = "MODIFIED"

        # Original should be unchanged
        original_variant = manager.get_variant_by_ids(added.id, variant_id)
        self.assertEqual(original_variant.name, "CPU")

    def test_load_predefined_pipelines(self):
        manager = PipelineManager()
        pipelines = manager.get_pipelines()
        self.assertIsInstance(pipelines, list)
        self.assertGreaterEqual(len(pipelines), 1)

        # Check that predefined pipelines have variants
        for pipeline in pipelines:
            if pipeline.source == InternalPipelineSource.PREDEFINED:
                self.assertGreater(len(pipeline.variants), 0)
                for variant in pipeline.variants:
                    self.assertIsNotNone(variant.id)
                    self.assertIsNotNone(variant.name)
                    self.assertIsNotNone(variant.pipeline_graph)
                    self.assertIsNotNone(variant.pipeline_graph_simple)
                    self.assertTrue(variant.read_only)
                    self.assertIsInstance(variant.created_at, datetime)
                    self.assertIsInstance(variant.modified_at, datetime)

    def test_build_pipeline_command_single_pipeline_single_stream(self):
        manager = PipelineManager()
        manager.pipelines = []

        # Build command using internal types directly
        pipeline_id = "/pipelines/test-pipelines/variants/cpu"
        pipeline_performance_specs = [
            create_internal_performance_spec(
                pipeline_id=pipeline_id,
                pipeline_name="test-pipelines",
                streams=1,
            )
        ]
        execution_config = create_internal_execution_config()

        pipeline_cmd = manager.build_pipeline_command(
            pipeline_performance_specs, execution_config, self.job_id
        )

        # Verify command is not empty and contains pipeline elements
        self.assertIsInstance(pipeline_cmd.command, str)
        self.assertIsInstance(pipeline_cmd.video_output_paths, dict)
        self.assertIsInstance(pipeline_cmd.live_stream_urls, dict)
        self.assertIsInstance(pipeline_cmd.metadata_file_paths, dict)
        self.assertGreater(len(pipeline_cmd.command), 0)
        self.assertIn("fakesrc", pipeline_cmd.command)
        self.assertIn("fakesink", pipeline_cmd.command)

    def test_build_pipeline_command_with_inline_graph(self):
        """Test building pipeline command with inline graph format."""
        manager = PipelineManager()
        manager.pipelines = []

        # Build command using inline graph format (synthetic ID)
        pipeline_performance_specs = [
            create_internal_performance_spec(
                pipeline_id="__graph-1234567890abcdef",
                pipeline_name="__graph-1234567890abcdef",
                streams=1,
            )
        ]
        execution_config = create_internal_execution_config()

        pipeline_cmd = manager.build_pipeline_command(
            pipeline_performance_specs, execution_config, self.job_id
        )

        self.assertGreater(len(pipeline_cmd.command), 0)
        self.assertIn("fakesrc", pipeline_cmd.command)

        # Verify output_paths key uses __graph- prefix for inline graphs
        for key in pipeline_cmd.video_output_paths.keys():
            self.assertTrue(key.startswith("__graph-"))

    def test_build_pipeline_command_single_pipeline_multiple_streams(self):
        manager = PipelineManager()
        manager.pipelines = []

        # Create Graph object with tee element
        tee_graph = Graph.from_dict(
            {
                "nodes": [
                    {"id": "0", "type": "videotestsrc", "data": {}},
                    {"id": "1", "type": "tee", "data": {"name": "t"}},
                    {"id": "2", "type": "queue", "data": {}},
                    {
                        "id": "3",
                        "type": "fakesink",
                        "data": {"name": "default_output_sink"},
                    },
                ],
                "edges": [
                    {"id": "0", "source": "0", "target": "1"},
                    {"id": "1", "source": "1", "target": "2"},
                    {"id": "2", "source": "2", "target": "3"},
                ],
            }
        )

        # Build command with 3 streams
        pipeline_performance_specs = [
            InternalPipelinePerformanceSpec(
                pipeline_id="/pipelines/test-pipelines/variants/cpu",
                pipeline_name="test-pipelines",
                pipeline_graph=tee_graph,
                streams=3,
            )
        ]
        execution_config = create_internal_execution_config()

        pipeline_cmd = manager.build_pipeline_command(
            pipeline_performance_specs, execution_config, self.job_id
        )

        # Verify command contains multiple instances
        self.assertGreater(len(pipeline_cmd.command), 0)
        # Should have 3 instances of videotestsrc (one per stream)
        self.assertEqual(pipeline_cmd.command.count("videotestsrc"), 3)

    def test_build_pipeline_command_multiple_pipelines(self):
        manager = PipelineManager()
        manager.pipelines = []

        # Create two different Graph objects
        graph1 = Graph.from_dict(
            {
                "nodes": [
                    {"id": "0", "type": "fakesrc", "data": {"name": "source1"}},
                    {
                        "id": "1",
                        "type": "fakesink",
                        "data": {"name": "default_output_sink"},
                    },
                ],
                "edges": [{"id": "0", "source": "0", "target": "1"}],
            }
        )
        graph2 = Graph.from_dict(
            {
                "nodes": [
                    {"id": "0", "type": "videotestsrc", "data": {"name": "source2"}},
                    {
                        "id": "1",
                        "type": "fakesink",
                        "data": {"name": "default_output_sink"},
                    },
                ],
                "edges": [{"id": "0", "source": "0", "target": "1"}],
            }
        )

        # Build command with two pipelines
        pipeline_performance_specs = [
            InternalPipelinePerformanceSpec(
                pipeline_id="/pipelines/pipeline-1/variants/cpu",
                pipeline_name="pipeline-1",
                pipeline_graph=graph1,
                streams=2,
            ),
            InternalPipelinePerformanceSpec(
                pipeline_id="/pipelines/pipeline-2/variants/cpu",
                pipeline_name="pipeline-2",
                pipeline_graph=graph2,
                streams=3,
            ),
        ]
        execution_config = create_internal_execution_config()

        pipeline_cmd = manager.build_pipeline_command(
            pipeline_performance_specs, execution_config, self.job_id
        )

        # Verify both pipeline types are present
        self.assertIsInstance(pipeline_cmd.command, str)
        # Should have 2 instances of fakesrc and 3 instances of videotestsrc
        self.assertEqual(pipeline_cmd.command.count("fakesrc"), 2)
        self.assertEqual(pipeline_cmd.command.count("videotestsrc"), 3)

    def test_update_pipeline_description_and_name(self):
        manager = PipelineManager()
        manager.pipelines = []

        new_pipeline = create_pipeline_definition(
            name="original-name",
            description="Original description",
            tags=["original"],
        )

        added = manager.add_pipeline(new_pipeline)
        original_modified_at = added.modified_at

        import time

        time.sleep(0.01)

        updated = manager.update_pipeline(
            pipeline_id=added.id,
            name="updated-name",
            description="Updated description",
        )

        self.assertEqual(updated.id, added.id)
        self.assertEqual(updated.name, "updated-name")
        self.assertEqual(updated.description, "Updated description")
        self.assertGreater(updated.modified_at, original_modified_at)
        self.assertIsInstance(updated.modified_at, datetime)
        self.assertEqual(updated.created_at, added.created_at)

        retrieved = manager.get_pipeline_by_id(added.id)
        self.assertEqual(retrieved.name, "updated-name")
        self.assertEqual(retrieved.description, "Updated description")

    def test_update_pipeline_tags(self):
        """Test updating pipeline tags."""
        manager = PipelineManager()
        manager.pipelines = []

        new_pipeline = create_pipeline_definition(
            name="test-tags",
            description="Test",
            tags=["original"],
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

        new_pipeline = create_pipeline_definition(
            name="to-delete",
            description="Test",
        )
        added = manager.add_pipeline(new_pipeline)

        manager.delete_pipeline_by_id(added.id)

        with self.assertRaises(ValueError):
            manager.get_pipeline_by_id(added.id)

    def test_delete_pipeline_predefined_raises_error(self):
        """Test that deleting a PREDEFINED pipeline raises error."""
        manager = PipelineManager()

        predefined = None
        for p in manager.get_pipelines():
            if p.source == InternalPipelineSource.PREDEFINED:
                predefined = p
                break

        assert predefined is not None

        with self.assertRaises(ValueError) as context:
            manager.delete_pipeline_by_id(predefined.id)

        self.assertIn("PREDEFINED", str(context.exception))

    def test_build_pipeline_command_with_video_output_enabled(self):
        """Test building pipeline command with video output enabled (file mode)."""
        manager = PipelineManager()
        manager.pipelines = []

        graph = Graph.from_dict(
            {
                "nodes": [
                    {"id": "0", "type": "videotestsrc", "data": {}},
                    {
                        "id": "1",
                        "type": "fakesink",
                        "data": {"name": "default_output_sink"},
                    },
                ],
                "edges": [{"id": "0", "source": "0", "target": "1"}],
            }
        )

        pipeline_id = "/pipelines/test-video-output/variants/cpu"
        pipeline_performance_specs = [
            InternalPipelinePerformanceSpec(
                pipeline_id=pipeline_id,
                pipeline_name="test-video-output",
                pipeline_graph=graph,
                streams=1,
            )
        ]
        execution_config = create_internal_execution_config(
            output_mode=InternalOutputMode.FILE,
            max_runtime=0,
            metadata_mode=InternalMetadataMode.DISABLED,
        )

        pipeline_cmd = manager.build_pipeline_command(
            pipeline_performance_specs, execution_config, self.job_id
        )

        # Verify video output is configured
        self.assertIsInstance(pipeline_cmd.command, str)
        self.assertIsInstance(pipeline_cmd.video_output_paths, dict)
        self.assertGreater(len(pipeline_cmd.video_output_paths[pipeline_id]), 0)

        # Verify output directory is in the command
        self.assertIn(OUTPUT_VIDEO_DIR, pipeline_cmd.command)

        # Verify fakesink is replaced with encoder pipeline
        self.assertNotIn("fakesink", pipeline_cmd.command)
        self.assertIn("filesink", pipeline_cmd.command)

        # Verify no live stream URLs for file output mode
        self.assertEqual(len(pipeline_cmd.live_stream_urls), 0)

    def test_pipeline_id_format_variant_reference(self):
        """Test that variant reference format produces correct pipeline ID."""
        manager = PipelineManager()
        manager.pipelines = []

        pipeline_id = "/pipelines/test-id-format/variants/cpu"
        pipeline_performance_specs = [
            create_internal_performance_spec(
                pipeline_id=pipeline_id,
                pipeline_name="test-id-format",
                streams=1,
            )
        ]
        execution_config = create_internal_execution_config()

        pipeline_cmd = manager.build_pipeline_command(
            pipeline_performance_specs, execution_config, self.job_id
        )

        # Verify pipeline ID format for variant reference
        self.assertIn(pipeline_id, pipeline_cmd.video_output_paths.keys())


class TestBuildPipelineCommandStreamIdentifiers(unittest.TestCase):
    """Tests for per-stream source/sink naming done by build_pipeline_command.

    These tests verify that:
      * every stream gets unique source/sink GStreamer element names,
      * tee-branch sinks are not renamed,
      * when the main-output placeholder is replaced by an encoder
        subpipeline, the final terminal sink still carries the
        stream-unique `name` property so external tracers
        (latency_tracer) can correlate measurements to a specific stream.
    """

    def setUp(self):
        PipelineManager._instance = None
        self.job_id = "test-job-stream-ids"

    def test_single_stream_gets_named_source_and_sink(self):
        """For a single stream the command contains exactly one source/sink name pair."""
        manager = PipelineManager()
        manager.pipelines = []

        graph = Graph.from_dict(
            {
                "nodes": [
                    {"id": "0", "type": "fakesrc", "data": {}},
                    {
                        "id": "1",
                        "type": "fakesink",
                        "data": {"name": "default_output_sink"},
                    },
                ],
                "edges": [{"id": "0", "source": "0", "target": "1"}],
            }
        )

        specs = [
            InternalPipelinePerformanceSpec(
                pipeline_id="/pipelines/p/variants/cpu",
                pipeline_name="p",
                pipeline_graph=graph,
                streams=1,
            )
        ]
        execution_config = InternalExecutionConfig(
            output_mode=InternalOutputMode.DISABLED,
            max_runtime=0,
            metadata_mode=InternalMetadataMode.DISABLED,
        )

        pipeline_cmd = manager.build_pipeline_command(
            specs, execution_config, self.job_id
        )

        # `unify_all_element_names` appends `_{pipeline_index}_{stream_index}`
        # so the final names include those indices.
        self.assertIn("name=src_p0_s0_0_0", pipeline_cmd.command)
        self.assertIn("name=sink_p0_s0_0_0", pipeline_cmd.command)

    def test_multiple_streams_have_unique_source_and_sink_names(self):
        """All streams of a single pipeline get distinct source/sink names."""
        manager = PipelineManager()
        manager.pipelines = []

        graph = Graph.from_dict(
            {
                "nodes": [
                    {"id": "0", "type": "videotestsrc", "data": {}},
                    {
                        "id": "1",
                        "type": "fakesink",
                        "data": {"name": "default_output_sink"},
                    },
                ],
                "edges": [{"id": "0", "source": "0", "target": "1"}],
            }
        )

        specs = [
            InternalPipelinePerformanceSpec(
                pipeline_id="/pipelines/multi/variants/cpu",
                pipeline_name="multi",
                pipeline_graph=graph,
                streams=3,
            )
        ]
        execution_config = InternalExecutionConfig(
            output_mode=InternalOutputMode.DISABLED,
            max_runtime=0,
            metadata_mode=InternalMetadataMode.DISABLED,
        )

        pipeline_cmd = manager.build_pipeline_command(
            specs, execution_config, self.job_id
        )

        # Exactly one occurrence per stream of the expected source and sink names.
        for stream_index in range(3):
            self.assertEqual(
                pipeline_cmd.command.count(
                    f"name=src_p0_s{stream_index}_0_{stream_index}"
                ),
                1,
            )
            self.assertEqual(
                pipeline_cmd.command.count(
                    f"name=sink_p0_s{stream_index}_0_{stream_index}"
                ),
                1,
            )

    def test_multiple_pipelines_produce_unique_stream_ids(self):
        """Different pipelines use different pipeline_index, giving disjoint names."""
        manager = PipelineManager()
        manager.pipelines = []

        g1 = Graph.from_dict(
            {
                "nodes": [
                    {"id": "0", "type": "fakesrc", "data": {}},
                    {
                        "id": "1",
                        "type": "fakesink",
                        "data": {"name": "default_output_sink"},
                    },
                ],
                "edges": [{"id": "0", "source": "0", "target": "1"}],
            }
        )
        g2 = Graph.from_dict(
            {
                "nodes": [
                    {"id": "0", "type": "videotestsrc", "data": {}},
                    {
                        "id": "1",
                        "type": "fakesink",
                        "data": {"name": "default_output_sink"},
                    },
                ],
                "edges": [{"id": "0", "source": "0", "target": "1"}],
            }
        )

        specs = [
            InternalPipelinePerformanceSpec(
                pipeline_id="/pipelines/p1/variants/cpu",
                pipeline_name="p1",
                pipeline_graph=g1,
                streams=2,
            ),
            InternalPipelinePerformanceSpec(
                pipeline_id="/pipelines/p2/variants/cpu",
                pipeline_name="p2",
                pipeline_graph=g2,
                streams=2,
            ),
        ]
        execution_config = InternalExecutionConfig(
            output_mode=InternalOutputMode.DISABLED,
            max_runtime=0,
            metadata_mode=InternalMetadataMode.DISABLED,
        )

        pipeline_cmd = manager.build_pipeline_command(
            specs, execution_config, self.job_id
        )

        # pipeline_index 0 produces src_p0_*, pipeline_index 1 produces src_p1_*.
        # Each index/stream combination must appear exactly once.
        expected = [
            "name=src_p0_s0_0_0",
            "name=src_p0_s1_0_1",
            "name=src_p1_s0_1_0",
            "name=src_p1_s1_1_1",
            "name=sink_p0_s0_0_0",
            "name=sink_p0_s1_0_1",
            "name=sink_p1_s0_1_0",
            "name=sink_p1_s1_1_1",
        ]
        for token in expected:
            self.assertEqual(
                pipeline_cmd.command.count(token), 1, f"Missing or duplicate: {token}"
            )

    def test_tee_branch_sink_is_not_given_stream_sink_name(self):
        """Tee-branch sinks are not renamed — only the main-branch sink is."""
        manager = PipelineManager()
        manager.pipelines = []

        # Main branch goes through the first outgoing edge of the tee.
        # The second outgoing edge leads to a separately-named fakesink that
        # must keep its original name (suffixed by unify_all_element_names).
        graph = Graph.from_dict(
            {
                "nodes": [
                    {"id": "0", "type": "videotestsrc", "data": {}},
                    {"id": "1", "type": "tee", "data": {"name": "t"}},
                    {"id": "2", "type": "queue", "data": {}},
                    {
                        "id": "3",
                        "type": "fakesink",
                        "data": {"name": "default_output_sink"},
                    },
                    {"id": "4", "type": "queue", "data": {}},
                    {
                        "id": "5",
                        "type": "fakesink",
                        "data": {"name": "branch_sink"},
                    },
                ],
                "edges": [
                    {"id": "0", "source": "0", "target": "1"},
                    {"id": "1", "source": "1", "target": "2"},
                    {"id": "2", "source": "2", "target": "3"},
                    {"id": "3", "source": "1", "target": "4"},
                    {"id": "4", "source": "4", "target": "5"},
                ],
            }
        )

        specs = [
            InternalPipelinePerformanceSpec(
                pipeline_id="/pipelines/tee/variants/cpu",
                pipeline_name="tee",
                pipeline_graph=graph,
                streams=1,
            )
        ]
        execution_config = InternalExecutionConfig(
            output_mode=InternalOutputMode.DISABLED,
            max_runtime=0,
            metadata_mode=InternalMetadataMode.DISABLED,
        )

        pipeline_cmd = manager.build_pipeline_command(
            specs, execution_config, self.job_id
        )

        # Main-branch sink uses the new stream sink name.
        self.assertIn("name=sink_p0_s0_0_0", pipeline_cmd.command)
        # Tee-branch sink keeps its original name (suffixed by unify_all_element_names).
        self.assertIn("name=branch_sink_0_0", pipeline_cmd.command)
        # The tee-branch sink is NOT renamed to a stream sink name.
        self.assertNotIn("name=sink_p0_s0_0_0 name=branch_sink", pipeline_cmd.command)

    def test_sink_name_is_injected_into_output_subpipeline_for_stream_zero(self):
        """When the placeholder is replaced by filesink, the sink name is appended."""
        manager = PipelineManager()
        manager.pipelines = []

        graph = Graph.from_dict(
            {
                "nodes": [
                    {"id": "0", "type": "videotestsrc", "data": {}},
                    {
                        "id": "1",
                        "type": "fakesink",
                        "data": {"name": "default_output_sink"},
                    },
                ],
                "edges": [{"id": "0", "source": "0", "target": "1"}],
            }
        )

        specs = [
            InternalPipelinePerformanceSpec(
                pipeline_id="/pipelines/with-output/variants/cpu",
                pipeline_name="with-output",
                pipeline_graph=graph,
                streams=1,
            )
        ]
        execution_config = InternalExecutionConfig(
            output_mode=InternalOutputMode.FILE,
            max_runtime=0,
            metadata_mode=InternalMetadataMode.DISABLED,
        )

        pipeline_cmd = manager.build_pipeline_command(
            specs, execution_config, self.job_id
        )

        # With file output, the fakesink is replaced by encoder + filesink.
        # The stream-unique sink name must still appear in the expanded
        # subpipeline so latency_tracer can correlate rows to this stream.
        self.assertIn("filesink", pipeline_cmd.command)
        self.assertIn("name=sink_p0_s0_0_0", pipeline_cmd.command)

    def test_default_output_sink_marker_is_preserved_for_stream_zero(self):
        """`default_output_sink` still triggers placeholder conversion (no interference)."""
        manager = PipelineManager()
        manager.pipelines = []

        # A second fakesink with an unrelated name must not trip placeholder
        # selection: only the one with name=default_output_sink is promoted.
        graph = Graph.from_dict(
            {
                "nodes": [
                    {"id": "0", "type": "videotestsrc", "data": {}},
                    {"id": "1", "type": "tee", "data": {"name": "t"}},
                    {"id": "2", "type": "queue", "data": {}},
                    {
                        "id": "3",
                        "type": "fakesink",
                        "data": {"name": "default_output_sink"},
                    },
                    {"id": "4", "type": "queue", "data": {}},
                    {
                        "id": "5",
                        "type": "fakesink",
                        "data": {"name": "branch_sink"},
                    },
                ],
                "edges": [
                    {"id": "0", "source": "0", "target": "1"},
                    {"id": "1", "source": "1", "target": "2"},
                    {"id": "2", "source": "2", "target": "3"},
                    {"id": "3", "source": "1", "target": "4"},
                    {"id": "4", "source": "4", "target": "5"},
                ],
            }
        )

        specs = [
            InternalPipelinePerformanceSpec(
                pipeline_id="/pipelines/default-marker/variants/cpu",
                pipeline_name="default-marker",
                pipeline_graph=graph,
                streams=1,
            )
        ]
        execution_config = InternalExecutionConfig(
            output_mode=InternalOutputMode.FILE,
            max_runtime=0,
            metadata_mode=InternalMetadataMode.DISABLED,
        )

        pipeline_cmd = manager.build_pipeline_command(
            specs, execution_config, self.job_id
        )

        # The default_output_sink fakesink was converted to the encoder output
        # subpipeline, so it must not remain in the final command.
        self.assertNotIn("default_output_sink", pipeline_cmd.command)
        # The branch sink survives and keeps its original name intact.
        self.assertIn("name=branch_sink_0_0", pipeline_cmd.command)
        # And the encoder terminal sink carries the stream sink name.
        self.assertIn("name=sink_p0_s0_0_0", pipeline_cmd.command)

    def test_recorder_pipeline_with_main_output_on_tee_branch(self):
        """
        Recorder-style pipelines place an intermediate splitmuxsink on
        the tee's first (inline) branch and the user-facing output
        (default_output_sink) on a subsequent tee branch. The stream
        sink name must be assigned to the main output sink (expanded
        from OUTPUT_PLACEHOLDER), NOT to the intermediate splitmuxsink.
        Emitting the same name twice would produce a GStreamer
        "elements don't share a common ancestor" linking error.
        """
        manager = PipelineManager()
        manager.pipelines = []

        graph = Graph.from_dict(
            {
                "nodes": [
                    {"id": "0", "type": "videotestsrc", "data": {}},
                    {"id": "1", "type": "tee", "data": {"name": "t"}},
                    # Inline branch: intermediate recorder sink (must NOT
                    # receive the stream sink name).
                    {"id": "2", "type": "queue", "data": {}},
                    {
                        "id": "3",
                        "type": "splitmuxsink",
                        "data": {"location": "recording.mp4"},
                    },
                    # Second branch: user-facing output (becomes the main
                    # sink after placeholder expansion).
                    {"id": "4", "type": "queue", "data": {}},
                    {
                        "id": "5",
                        "type": "fakesink",
                        "data": {"name": "default_output_sink"},
                    },
                ],
                "edges": [
                    {"id": "0", "source": "0", "target": "1"},
                    {"id": "1", "source": "1", "target": "2"},
                    {"id": "2", "source": "2", "target": "3"},
                    {"id": "3", "source": "1", "target": "4"},
                    {"id": "4", "source": "4", "target": "5"},
                ],
            }
        )

        specs = [
            InternalPipelinePerformanceSpec(
                pipeline_id="/pipelines/recorder/variants/cpu",
                pipeline_name="recorder",
                pipeline_graph=graph,
                streams=1,
            )
        ]
        execution_config = InternalExecutionConfig(
            output_mode=InternalOutputMode.FILE,
            max_runtime=0,
            metadata_mode=InternalMetadataMode.DISABLED,
        )

        pipeline_cmd = manager.build_pipeline_command(
            specs, execution_config, self.job_id
        )

        # The stream sink name appears EXACTLY ONCE — on the expanded
        # output subpipeline's filesink, not on the intermediate
        # splitmuxsink.
        self.assertEqual(pipeline_cmd.command.count("name=sink_p0_s0_0_0"), 1)

        # The splitmuxsink element is still present but does not carry the
        # stream sink name.
        self.assertIn("splitmuxsink", pipeline_cmd.command)
        # Sanity: filesink (from the expanded output subpipeline) is
        # present and immediately followed by the stream sink name.
        self.assertIn("filesink", pipeline_cmd.command)

    def test_recorder_pipeline_with_multiple_streams_names_correct_sinks(self):
        """
        Multi-stream recorder pipelines:

        Stream 0 uses OUTPUT_PLACEHOLDER → sink_p0_s0 is injected into the
        expanded encoder subpipeline.

        Stream 1 (and beyond) does NOT have OUTPUT_PLACEHOLDER. The
        `default_output_sink`-named fakesink on a non-first tee branch
        must be selected as the main sink, not the intermediate
        splitmuxsink on the inline branch.
        """
        manager = PipelineManager()
        manager.pipelines = []

        graph = Graph.from_dict(
            {
                "nodes": [
                    {"id": "0", "type": "videotestsrc", "data": {}},
                    {"id": "1", "type": "tee", "data": {"name": "t"}},
                    # Inline branch: intermediate recorder sink.
                    {"id": "2", "type": "queue", "data": {}},
                    {
                        "id": "3",
                        "type": "splitmuxsink",
                        "data": {"location": "recording.mp4"},
                    },
                    # Second tee branch: user-facing output marked with
                    # default_output_sink.
                    {"id": "4", "type": "queue", "data": {}},
                    {
                        "id": "5",
                        "type": "fakesink",
                        "data": {"name": "default_output_sink"},
                    },
                ],
                "edges": [
                    {"id": "0", "source": "0", "target": "1"},
                    {"id": "1", "source": "1", "target": "2"},
                    {"id": "2", "source": "2", "target": "3"},
                    {"id": "3", "source": "1", "target": "4"},
                    {"id": "4", "source": "4", "target": "5"},
                ],
            }
        )

        specs = [
            InternalPipelinePerformanceSpec(
                pipeline_id="/pipelines/recorder-multi/variants/cpu",
                pipeline_name="recorder-multi",
                pipeline_graph=graph,
                streams=2,
            )
        ]
        execution_config = InternalExecutionConfig(
            output_mode=InternalOutputMode.FILE,
            max_runtime=0,
            metadata_mode=InternalMetadataMode.DISABLED,
        )

        pipeline_cmd = manager.build_pipeline_command(
            specs, execution_config, self.job_id
        )

        # --- Stream 0: placeholder replaced → encoder subpipeline with
        #     `filesink ... name=sink_p0_s0_0_0`.
        self.assertEqual(pipeline_cmd.command.count("name=sink_p0_s0_0_0"), 1)

        # --- Stream 1: no placeholder. The default_output_sink fakesink on
        #     the second tee branch must receive `name=sink_p0_s1_0_1`.
        #     The intermediate splitmuxsink on the inline branch must NOT.
        self.assertEqual(pipeline_cmd.command.count("name=sink_p0_s1_0_1"), 1)

        # The `default_output_sink` marker itself must no longer be present
        # in the final command for stream 1 (it has been renamed).
        self.assertNotIn("name=default_output_sink_0_1", pipeline_cmd.command)

        # Quick structural assertion: for stream 1, the sink name comes
        # after a fakesink (not a splitmuxsink).
        # Find the substring and check the preceding element type.
        stream1_sink_marker = "name=sink_p0_s1_0_1"
        idx = pipeline_cmd.command.find(stream1_sink_marker)
        self.assertGreater(idx, 0)
        # The element directly preceding this `name=...` token should be a
        # fakesink (the user-facing output), not a splitmuxsink.
        preceding_segment = pipeline_cmd.command[:idx]
        # Find the last `!` boundary before this `name=` token.
        last_separator = preceding_segment.rfind("!")
        element_chunk = preceding_segment[last_separator + 1 :]
        self.assertIn("fakesink", element_chunk)
        self.assertNotIn("splitmuxsink", element_chunk)


class TestVariantCRUD(unittest.TestCase):
    """Test cases for variant CRUD operations."""

    def setUp(self):
        PipelineManager._instance = None

    def test_add_variant_to_pipeline(self):
        """Test adding a new variant to an existing pipeline."""
        manager = PipelineManager()
        manager.pipelines = []

        new_pipeline = create_pipeline_definition(
            name="test-add-variant",
            description="Test",
            variants=[create_variant_create(name="CPU")],
        )
        added = manager.add_pipeline(new_pipeline)
        self.assertEqual(len(added.variants), 1)
        original_pipeline_modified_at = added.modified_at

        import time

        time.sleep(0.01)

        new_graph = Graph.from_dict(
            {
                "nodes": [
                    {"id": "0", "type": "videotestsrc", "data": {}},
                    {
                        "id": "1",
                        "type": "fakesink",
                        "data": {"name": "default_output_sink"},
                    },
                ],
                "edges": [{"id": "0", "source": "0", "target": "1"}],
            }
        )

        new_variant = manager.add_variant(
            pipeline_id=added.id,
            name="GPU",
            pipeline_graph=new_graph,
            pipeline_graph_simple=new_graph,
        )

        self.assertIsNotNone(new_variant.id)
        self.assertGreater(len(new_variant.id), 0)
        self.assertEqual(new_variant.id, "gpu")
        self.assertEqual(new_variant.name, "GPU")
        self.assertFalse(new_variant.read_only)

        self.assertIsInstance(new_variant.created_at, datetime)
        self.assertIsInstance(new_variant.modified_at, datetime)
        self.assertEqual(new_variant.created_at.tzinfo, timezone.utc)
        self.assertEqual(new_variant.created_at, new_variant.modified_at)

        retrieved = manager.get_pipeline_by_id(added.id)
        self.assertEqual(len(retrieved.variants), 2)
        self.assertGreater(retrieved.modified_at, original_pipeline_modified_at)

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

        new_pipeline = create_pipeline_definition(
            name="test-delete-variant",
            description="Test",
            variants=[
                create_variant_create(name="CPU"),
                create_variant_create(name="GPU"),
            ],
        )
        added = manager.add_pipeline(new_pipeline)
        self.assertEqual(len(added.variants), 2)
        original_modified_at = added.modified_at

        import time

        time.sleep(0.01)

        variant_to_delete = added.variants[1].id
        manager.delete_variant(added.id, variant_to_delete)

        retrieved = manager.get_pipeline_by_id(added.id)
        self.assertEqual(len(retrieved.variants), 1)
        self.assertGreater(retrieved.modified_at, original_modified_at)

        with self.assertRaises(ValueError) as context:
            manager.get_variant_by_ids(added.id, variant_to_delete)
        self.assertIn("not found", str(context.exception))

    def test_delete_last_variant_raises_error(self):
        """Test that deleting the last variant raises error."""
        manager = PipelineManager()
        manager.pipelines = []

        new_pipeline = create_pipeline_definition(
            name="test-last-variant",
            description="Test",
        )
        added = manager.add_pipeline(new_pipeline)

        with self.assertRaises(ValueError) as context:
            manager.delete_variant(added.id, added.variants[0].id)

        self.assertIn("last variant", str(context.exception))

    def test_delete_nonexistent_variant_raises_error(self):
        """Test that deleting a nonexistent variant raises error."""
        manager = PipelineManager()
        manager.pipelines = []

        new_pipeline = create_pipeline_definition(
            name="test-nonexistent",
            description="Test",
        )
        added = manager.add_pipeline(new_pipeline)

        with self.assertRaises(ValueError) as context:
            manager.delete_variant(added.id, "nonexistent-variant")

        self.assertIn("not found", str(context.exception))

    def test_update_variant_name(self):
        """Test updating variant name."""
        manager = PipelineManager()
        manager.pipelines = []

        new_pipeline = create_pipeline_definition(
            name="test-update-variant",
            description="Test",
            variants=[create_variant_create(name="CPU")],
        )
        added = manager.add_pipeline(new_pipeline)
        original_variant_modified_at = added.variants[0].modified_at
        original_pipeline_modified_at = added.modified_at

        import time

        time.sleep(0.01)

        updated = manager.update_variant(
            pipeline_id=added.id,
            variant_id=added.variants[0].id,
            name="GPU-optimized",
        )

        self.assertEqual(updated.name, "GPU-optimized")
        self.assertGreater(updated.modified_at, original_variant_modified_at)
        self.assertIsInstance(updated.modified_at, datetime)
        self.assertEqual(updated.created_at, added.variants[0].created_at)

        retrieved = manager.get_pipeline_by_id(added.id)
        self.assertGreater(retrieved.modified_at, original_pipeline_modified_at)

    def test_update_variant_pipeline_graph(self):
        """Test updating variant with new pipeline graph."""
        manager = PipelineManager()
        manager.pipelines = []

        new_pipeline = create_pipeline_definition(
            name="test-update-graph",
            description="Test",
        )
        added = manager.add_pipeline(new_pipeline)

        new_graph = Graph.from_dict(
            {
                "nodes": [
                    {"id": "0", "type": "videotestsrc", "data": {}},
                    {"id": "1", "type": "videoconvert", "data": {}},
                    {
                        "id": "2",
                        "type": "fakesink",
                        "data": {"name": "default_output_sink"},
                    },
                ],
                "edges": [
                    {"id": "0", "source": "0", "target": "1"},
                    {"id": "1", "source": "1", "target": "2"},
                ],
            }
        )

        updated = manager.update_variant(
            pipeline_id=added.id,
            variant_id=added.variants[0].id,
            pipeline_graph=new_graph,
        )

        self.assertEqual(len(updated.pipeline_graph.nodes), 3)
        self.assertIsNotNone(updated.pipeline_graph_simple)

    def test_update_variant_both_graphs_raises_error(self):
        """Test that providing both graph types raises error."""
        manager = PipelineManager()
        manager.pipelines = []

        new_pipeline = create_pipeline_definition(
            name="test-both-graphs",
            description="Test",
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


class TestGraphConversionMethods(unittest.TestCase):
    """Test cases for graph conversion private methods."""

    def setUp(self):
        PipelineManager._instance = None

    def test_validate_and_convert_advanced_to_simple_success(self):
        """Test successful conversion from advanced to simple graph."""
        manager = PipelineManager()
        manager.pipelines = []

        # Create an advanced graph with some hidden elements (use videotestsrc, not filesrc)
        advanced_graph = Graph.from_dict(
            {
                "nodes": [
                    {"id": "0", "type": "videotestsrc", "data": {}},
                    {"id": "1", "type": "queue", "data": {}},
                    {"id": "2", "type": "fakesink", "data": {}},
                ],
                "edges": [
                    {"id": "0", "source": "0", "target": "1"},
                    {"id": "1", "source": "1", "target": "2"},
                ],
            }
        )

        # Convert to simple
        simple_graph = manager.validate_and_convert_advanced_to_simple(advanced_graph)

        # Verify simple graph has fewer nodes (queue should be hidden)
        self.assertIsInstance(simple_graph, Graph)
        self.assertLessEqual(len(simple_graph.nodes), len(advanced_graph.nodes))

    def test_validate_and_convert_advanced_to_simple_empty_nodes_raises_error(self):
        """Test that empty nodes in advanced graph raises error."""
        manager = PipelineManager()
        manager.pipelines = []

        # Create empty graph
        empty_graph = Graph(nodes=[], edges=[])

        with self.assertRaises(ValueError) as context:
            manager.validate_and_convert_advanced_to_simple(empty_graph)

        self.assertIn("at least one node and one edge", str(context.exception))

    def test_validate_and_convert_simple_to_advanced_success(self):
        """Test successful conversion from simple to advanced graph."""
        manager = PipelineManager()
        manager.pipelines = []

        # Create variant with both graphs (use videotestsrc, not filesrc)
        graph = Graph.from_dict(
            {
                "nodes": [
                    {"id": "0", "type": "videotestsrc", "data": {"pattern": "0"}},
                    {"id": "1", "type": "queue", "data": {}},
                    {"id": "2", "type": "fakesink", "data": {}},
                ],
                "edges": [
                    {"id": "0", "source": "0", "target": "1"},
                    {"id": "1", "source": "1", "target": "2"},
                ],
            }
        )
        simple_graph = Graph.from_dict(
            {
                "nodes": [
                    {"id": "0", "type": "videotestsrc", "data": {"pattern": "0"}},
                    {"id": "2", "type": "fakesink", "data": {}},
                ],
                "edges": [
                    {"id": "0", "source": "0", "target": "2"},
                ],
            }
        )

        new_pipeline = create_pipeline_definition(
            name="test-conversion",
            description="Test",
            variants=[
                InternalVariantCreate(
                    name="CPU",
                    pipeline_graph=graph,
                    pipeline_graph_simple=simple_graph,
                )
            ],
        )
        added = manager.add_pipeline(new_pipeline)
        variant = added.variants[0]

        # Modify simple graph (change property)
        modified_simple_graph = Graph.from_dict(
            {
                "nodes": [
                    {"id": "0", "type": "videotestsrc", "data": {"pattern": "1"}},
                    {"id": "2", "type": "fakesink", "data": {}},
                ],
                "edges": [
                    {"id": "0", "source": "0", "target": "2"},
                ],
            }
        )

        # Convert to advanced
        advanced_graph = manager.validate_and_convert_simple_to_advanced(
            variant, modified_simple_graph
        )

        # Verify advanced graph has the new property
        self.assertIsInstance(advanced_graph, Graph)
        videotestsrc_node = next(
            n for n in advanced_graph.nodes if n.type == "videotestsrc"
        )
        self.assertEqual(videotestsrc_node.data["pattern"], "1")

    def test_validate_and_convert_simple_to_advanced_structural_change_raises_error(
        self,
    ):
        """Test that structural changes in simple graph raise error."""
        manager = PipelineManager()
        manager.pipelines = []

        graph = Graph.from_dict(
            {
                "nodes": [
                    {"id": "0", "type": "videotestsrc", "data": {}},
                    {"id": "1", "type": "fakesink", "data": {}},
                ],
                "edges": [
                    {"id": "0", "source": "0", "target": "1"},
                ],
            }
        )

        new_pipeline = create_pipeline_definition(
            name="test-conversion",
            description="Test",
            variants=[
                InternalVariantCreate(
                    name="CPU",
                    pipeline_graph=graph,
                    pipeline_graph_simple=graph,
                )
            ],
        )
        added = manager.add_pipeline(new_pipeline)
        variant = added.variants[0]

        # Try to add a node in simple graph (structural change)
        modified_simple_graph = Graph.from_dict(
            {
                "nodes": [
                    {"id": "0", "type": "videotestsrc", "data": {}},
                    {"id": "1", "type": "fakesink", "data": {}},
                    {"id": "2", "type": "new_element", "data": {}},  # Added node
                ],
                "edges": [
                    {"id": "0", "source": "0", "target": "1"},
                ],
            }
        )

        with self.assertRaises(ValueError) as context:
            manager.validate_and_convert_simple_to_advanced(
                variant, modified_simple_graph
            )

        self.assertIn("Invalid pipeline_graph_simple", str(context.exception))

    def test_validate_and_convert_simple_to_advanced_empty_nodes_raises_error(self):
        """Test that empty nodes in simple graph raises error."""
        manager = PipelineManager()
        manager.pipelines = []

        new_pipeline = create_pipeline_definition(
            name="test-conversion",
            description="Test",
        )
        added = manager.add_pipeline(new_pipeline)
        variant = added.variants[0]

        # Create empty graph
        empty_graph = Graph(nodes=[], edges=[])

        with self.assertRaises(ValueError) as context:
            manager.validate_and_convert_simple_to_advanced(variant, empty_graph)

        self.assertIn("at least one node and one edge", str(context.exception))


class TestBuildPipelineCommandExecutionConfig(unittest.TestCase):
    """Test cases for ExecutionConfig and metadata_mode validation in build_pipeline_command."""

    def setUp(self):
        PipelineManager._instance = None
        self.manager = PipelineManager()
        self.manager.pipelines = []
        self.job_id = "test-job-456"

        # Create internal specs for all tests
        self.specs = [
            create_internal_performance_spec(
                pipeline_id="/pipelines/test-execution-config/variants/cpu",
                pipeline_name="test-execution-config",
                streams=1,
            )
        ]

    def test_file_output_with_max_runtime_raises_error(self):
        """Test that file output mode with max_runtime > 0 raises ValueError."""
        execution_config = create_internal_execution_config(
            output_mode=InternalOutputMode.FILE,
            max_runtime=60,
            metadata_mode=InternalMetadataMode.DISABLED,
        )

        with self.assertRaises(ValueError) as context:
            self.manager.build_pipeline_command(
                self.specs, execution_config, self.job_id
            )

        self.assertIn(
            "output_mode='file' cannot be combined with max_runtime > 0",
            str(context.exception),
        )

    def test_file_output_with_zero_max_runtime_succeeds(self):
        """Test that file output mode with max_runtime=0 works correctly."""
        execution_config = create_internal_execution_config(
            output_mode=InternalOutputMode.FILE,
            max_runtime=0,
            metadata_mode=InternalMetadataMode.DISABLED,
        )

        pipeline_cmd = self.manager.build_pipeline_command(
            self.specs, execution_config, self.job_id
        )
        self.assertIsInstance(pipeline_cmd.command, str)
        self.assertGreater(len(pipeline_cmd.command), 0)
        self.assertIn("filesink", pipeline_cmd.command)

    def test_disabled_output_with_max_runtime_succeeds(self):
        """Test that disabled output mode with max_runtime > 0 works correctly."""
        execution_config = create_internal_execution_config(
            output_mode=InternalOutputMode.DISABLED,
            max_runtime=60,
            metadata_mode=InternalMetadataMode.DISABLED,
        )

        pipeline_cmd = self.manager.build_pipeline_command(
            self.specs, execution_config, self.job_id
        )

        self.assertIsInstance(pipeline_cmd.command, str)
        self.assertGreater(len(pipeline_cmd.command), 0)
        self.assertIn("fakesink", pipeline_cmd.command)

        """Test that live stream output mode with max_runtime > 0 works correctly."""
        execution_config = create_internal_execution_config(
            output_mode=InternalOutputMode.LIVE_STREAM,
            max_runtime=60,
            metadata_mode=InternalMetadataMode.DISABLED,
        )

        pipeline_cmd = self.manager.build_pipeline_command(
            self.specs, execution_config, self.job_id
        )

        self.assertIsInstance(pipeline_cmd.command, str)
        self.assertGreater(len(pipeline_cmd.command), 0)
        self.assertIn("rtspclientsink", pipeline_cmd.command)
        pipeline_id = "/pipelines/test-execution-config/variants/cpu"
        self.assertIn(pipeline_id, pipeline_cmd.live_stream_urls)

    def test_live_stream_output_returns_stream_urls(self):
        """Test that live stream output mode returns correct stream URLs."""
        execution_config = create_internal_execution_config(
            output_mode=InternalOutputMode.LIVE_STREAM,
            max_runtime=0,
            metadata_mode=InternalMetadataMode.DISABLED,
        )

        pipeline_cmd = self.manager.build_pipeline_command(
            self.specs, execution_config, self.job_id
        )

        pipeline_id = "/pipelines/test-execution-config/variants/cpu"
        self.assertIn(pipeline_id, pipeline_cmd.live_stream_urls)
        stream_url = pipeline_cmd.live_stream_urls[pipeline_id]
        self.assertTrue(stream_url.startswith("rtsp://"))

        """Test that only one live stream URL is generated per pipeline."""
        specs = [
            create_internal_performance_spec(
                pipeline_id="/pipelines/test-execution-config/variants/cpu",
                pipeline_name="test-execution-config",
                streams=3,
            ),
            create_internal_performance_spec(
                pipeline_id="/pipelines/test-execution-config-2/variants/cpu",
                pipeline_name="test-execution-config-2",
                streams=2,
            ),
        ]
        execution_config = create_internal_execution_config(
            output_mode=InternalOutputMode.LIVE_STREAM,
            max_runtime=60,
            metadata_mode=InternalMetadataMode.DISABLED,
        )

        pipeline_cmd = self.manager.build_pipeline_command(
            specs, execution_config, self.job_id
        )

        # Should have exactly 2 live stream URLs (one per pipeline)
        self.assertEqual(len(pipeline_cmd.live_stream_urls), 2)
        # Only first stream of each pipeline should have rtspclientsink
        self.assertEqual(pipeline_cmd.command.count("rtspclientsink"), 2)

    def test_metadata_file_paths_empty_when_mode_disabled(self):
        execution_config = create_internal_execution_config(
            metadata_mode=InternalMetadataMode.DISABLED,
        )

        pipeline_cmd = self.manager.build_pipeline_command(
            self.specs, execution_config, self.job_id
        )

        self.assertEqual(pipeline_cmd.metadata_file_paths, {})

    def test_metadata_mode_disabled_with_gvametapublish_does_not_inject_paths(self):
        """When metadata is disabled, gvametapublish nodes must not have file-path set."""
        specs = [
            InternalPipelinePerformanceSpec(
                pipeline_id="/pipelines/test-meta/variants/cpu",
                pipeline_name="test-meta",
                pipeline_graph=create_gvametapublish_graph(),
                streams=1,
            )
        ]
        execution_config = create_internal_execution_config(
            metadata_mode=InternalMetadataMode.DISABLED,
        )

        pipeline_cmd = self.manager.build_pipeline_command(
            specs, execution_config, self.job_id
        )

        self.assertEqual(pipeline_cmd.metadata_file_paths, {})
        # file-path must NOT appear in the command (no injection happened)
        self.assertNotIn("file-path", pipeline_cmd.command)

    def test_metadata_mode_file_without_gvametapublish_raises_error(self):
        """metadata_mode=FILE on a pipeline that has no gvametapublish must raise ValueError."""
        execution_config = create_internal_execution_config(
            metadata_mode=InternalMetadataMode.FILE,
        )

        with self.assertRaises(ValueError) as ctx:
            self.manager.build_pipeline_command(
                self.specs, execution_config, self.job_id
            )

        self.assertIn(
            "Metadata generation is enabled, but the pipeline does not contain any gvametapublish element.",
            str(ctx.exception),
        )

    def test_metadata_mode_file_multiple_pipelines_one_missing_gvametapublish_raises(
        self,
    ):
        """Even if only one pipeline in a multi-pipeline spec lacks gvametapublish the
        error must be raised."""
        specs = [
            # has gvametapublish
            InternalPipelinePerformanceSpec(
                pipeline_id="/pipelines/with-publish/variants/cpu",
                pipeline_name="with-publish",
                pipeline_graph=create_gvametapublish_graph(),
                streams=1,
            ),
            # does NOT have gvametapublish
            create_internal_performance_spec(
                pipeline_id="/pipelines/no-publish/variants/cpu",
                pipeline_name="no-publish",
                streams=1,
            ),
        ]
        execution_config = create_internal_execution_config(
            metadata_mode=InternalMetadataMode.FILE,
        )

        with self.assertRaises(ValueError) as ctx:
            self.manager.build_pipeline_command(specs, execution_config, self.job_id)

        self.assertIn(
            "Metadata generation is enabled, but the pipeline does not contain any gvametapublish element.",
            str(ctx.exception),
        )

    def test_metadata_mode_file_returns_paths_for_pipeline(self):
        """metadata_file_paths must contain the pipeline_id mapped to a list of paths."""
        pipeline_id = "/pipelines/with-publish/variants/cpu"
        specs = [
            InternalPipelinePerformanceSpec(
                pipeline_id=pipeline_id,
                pipeline_name="with-publish",
                pipeline_graph=create_gvametapublish_graph(),
                streams=1,
            )
        ]
        execution_config = create_internal_execution_config(
            metadata_mode=InternalMetadataMode.FILE,
        )

        pipeline_cmd = self.manager.build_pipeline_command(
            specs, execution_config, self.job_id
        )

        self.assertIn(pipeline_id, pipeline_cmd.metadata_file_paths)
        paths = pipeline_cmd.metadata_file_paths[pipeline_id]
        self.assertIsInstance(paths, list)
        self.assertEqual(len(paths), 1)

    def test_metadata_mode_file_paths_end_with_jsonl(self):
        """Each injected metadata path must be a .jsonl file."""
        pipeline_id = "/pipelines/with-publish/variants/cpu"
        specs = [
            InternalPipelinePerformanceSpec(
                pipeline_id=pipeline_id,
                pipeline_name="with-publish",
                pipeline_graph=create_gvametapublish_graph(),
                streams=1,
            )
        ]
        execution_config = create_internal_execution_config(
            metadata_mode=InternalMetadataMode.FILE,
        )

        pipeline_cmd = self.manager.build_pipeline_command(
            specs, execution_config, self.job_id
        )

        for path in pipeline_cmd.metadata_file_paths[pipeline_id]:
            self.assertTrue(
                path.endswith(".jsonl"),
                f"Expected .jsonl extension, got: {path}",
            )

    def test_metadata_mode_file_paths_are_under_metadata_dir(self):
        """Injected metadata paths must be located beneath METADATA_DIR."""

        pipeline_id = "/pipelines/with-publish/variants/cpu"
        specs = [
            InternalPipelinePerformanceSpec(
                pipeline_id=pipeline_id,
                pipeline_name="with-publish",
                pipeline_graph=create_gvametapublish_graph(),
                streams=1,
            )
        ]
        execution_config = create_internal_execution_config(
            metadata_mode=InternalMetadataMode.FILE,
        )

        pipeline_cmd = self.manager.build_pipeline_command(
            specs, execution_config, self.job_id
        )

        for path in pipeline_cmd.metadata_file_paths[pipeline_id]:
            self.assertTrue(
                path.startswith(METADATA_DIR),
                f"Expected path under {METADATA_DIR}, got: {path}",
            )

    def test_metadata_mode_file_paths_appear_in_command(self):
        """The injected metadata file paths must be present in the GStreamer command."""
        pipeline_id = "/pipelines/with-publish/variants/cpu"
        specs = [
            InternalPipelinePerformanceSpec(
                pipeline_id=pipeline_id,
                pipeline_name="with-publish",
                pipeline_graph=create_gvametapublish_graph(),
                streams=1,
            )
        ]
        execution_config = create_internal_execution_config(
            metadata_mode=InternalMetadataMode.FILE,
        )

        pipeline_cmd = self.manager.build_pipeline_command(
            specs, execution_config, self.job_id
        )

        for path in pipeline_cmd.metadata_file_paths[pipeline_id]:
            self.assertIn(path, pipeline_cmd.command)

    def test_metadata_mode_file_multiple_gvametapublish_returns_one_path_each(self):
        """A pipeline with two gvametapublish elements must produce two metadata paths."""
        pipeline_id = "/pipelines/with-publish/variants/cpu"
        specs = [
            InternalPipelinePerformanceSpec(
                pipeline_id=pipeline_id,
                pipeline_name="with-publish",
                pipeline_graph=create_gvametapublish_graph(publish_nodes=2),
                streams=1,
            )
        ]
        execution_config = create_internal_execution_config(
            metadata_mode=InternalMetadataMode.FILE,
        )

        pipeline_cmd = self.manager.build_pipeline_command(
            specs, execution_config, self.job_id
        )

        self.assertIn(pipeline_id, pipeline_cmd.metadata_file_paths)
        self.assertEqual(len(pipeline_cmd.metadata_file_paths[pipeline_id]), 2)

    def test_metadata_mode_file_only_injects_paths_for_first_stream(self):
        """Metadata paths must be returned as a single list regardless of stream count
        (injection happens only for stream_index 0)."""
        pipeline_id = "/pipelines/with-publish/variants/cpu"
        specs = [
            InternalPipelinePerformanceSpec(
                pipeline_id=pipeline_id,
                pipeline_name="with-publish",
                pipeline_graph=create_gvametapublish_graph(),
                streams=3,
            )
        ]
        execution_config = create_internal_execution_config(
            metadata_mode=InternalMetadataMode.FILE,
        )

        pipeline_cmd = self.manager.build_pipeline_command(
            specs, execution_config, self.job_id
        )

        # Paths list length equals number of gvametapublish nodes, NOT stream count
        self.assertIn(pipeline_id, pipeline_cmd.metadata_file_paths)
        self.assertEqual(len(pipeline_cmd.metadata_file_paths[pipeline_id]), 1)

    def test_metadata_mode_file_multiple_pipelines_get_independent_paths(self):
        """Each pipeline in a multi-pipeline spec gets its own entry in metadata_file_paths."""
        pipeline_id_1 = "/pipelines/pipe-1/variants/cpu"
        pipeline_id_2 = "/pipelines/pipe-2/variants/cpu"
        specs = [
            InternalPipelinePerformanceSpec(
                pipeline_id=pipeline_id_1,
                pipeline_name="pipe-1",
                pipeline_graph=create_gvametapublish_graph(),
                streams=1,
            ),
            InternalPipelinePerformanceSpec(
                pipeline_id=pipeline_id_2,
                pipeline_name="pipe-2",
                pipeline_graph=create_gvametapublish_graph(),
                streams=1,
            ),
        ]
        execution_config = create_internal_execution_config(
            metadata_mode=InternalMetadataMode.FILE,
        )

        pipeline_cmd = self.manager.build_pipeline_command(
            specs, execution_config, self.job_id
        )

        self.assertIn(pipeline_id_1, pipeline_cmd.metadata_file_paths)
        self.assertIn(pipeline_id_2, pipeline_cmd.metadata_file_paths)
        # Paths for the two pipelines must be different
        self.assertNotEqual(
            pipeline_cmd.metadata_file_paths[pipeline_id_1],
            pipeline_cmd.metadata_file_paths[pipeline_id_2],
        )

    def test_metadata_mode_file_paths_are_unique_across_pipelines(self):
        """The injected metadata paths for different pipelines must not overlap."""
        pipeline_id_1 = "/pipelines/pipe-a/variants/cpu"
        pipeline_id_2 = "/pipelines/pipe-b/variants/cpu"
        specs = [
            InternalPipelinePerformanceSpec(
                pipeline_id=pipeline_id_1,
                pipeline_name="pipe-a",
                pipeline_graph=create_gvametapublish_graph(),
                streams=1,
            ),
            InternalPipelinePerformanceSpec(
                pipeline_id=pipeline_id_2,
                pipeline_name="pipe-b",
                pipeline_graph=create_gvametapublish_graph(),
                streams=1,
            ),
        ]
        execution_config = create_internal_execution_config(
            metadata_mode=InternalMetadataMode.FILE,
        )

        pipeline_cmd = self.manager.build_pipeline_command(
            specs, execution_config, self.job_id
        )

        all_paths = (
            pipeline_cmd.metadata_file_paths[pipeline_id_1]
            + pipeline_cmd.metadata_file_paths[pipeline_id_2]
        )
        self.assertEqual(
            len(all_paths), len(set(all_paths)), "Metadata paths must be unique"
        )


class TestBuildPipelineCommandLooping(unittest.TestCase):
    """Test cases for looping behavior in build_pipeline_command."""

    def setUp(self):
        PipelineManager._instance = None
        self.manager = PipelineManager()
        self.manager.pipelines = []
        self.job_id = "test-job-789"

        # Create internal specs for looping tests
        graph = Graph.from_dict(
            {
                "nodes": [
                    {"id": "0", "type": "videotestsrc", "data": {}},
                    {
                        "id": "1",
                        "type": "fakesink",
                        "data": {"name": "default_output_sink"},
                    },
                ],
                "edges": [{"id": "0", "source": "0", "target": "1"}],
            }
        )
        self.specs = [
            InternalPipelinePerformanceSpec(
                pipeline_id="/pipelines/test-looping/variants/cpu",
                pipeline_name="test-looping",
                pipeline_graph=graph,
                streams=1,
            )
        ]

    def test_looping_not_applied_when_max_runtime_zero(self):
        """Test that looping modifications are not applied when max_runtime=0."""
        execution_config = create_internal_execution_config(
            output_mode=InternalOutputMode.DISABLED,
            max_runtime=0,
            metadata_mode=InternalMetadataMode.DISABLED,
        )

        pipeline_cmd = self.manager.build_pipeline_command(
            self.specs, execution_config, self.job_id
        )

        self.assertIn("videotestsrc", pipeline_cmd.command)
        self.assertNotIn("multifilesrc", pipeline_cmd.command)

    def test_looping_applied_when_max_runtime_positive_and_disabled_mode(self):
        """Test that looping modifications are applied for disabled mode with max_runtime > 0."""
        execution_config = create_internal_execution_config(
            output_mode=InternalOutputMode.DISABLED,
            max_runtime=60,
            metadata_mode=InternalMetadataMode.DISABLED,
        )

        pipeline_cmd = self.manager.build_pipeline_command(
            self.specs, execution_config, self.job_id
        )

        self.assertIn("videotestsrc", pipeline_cmd.command)
        self.assertIn("fakesink", pipeline_cmd.command)

    def test_looping_applied_when_max_runtime_positive_and_live_stream_mode(self):
        """Test that looping modifications are applied for live stream mode with max_runtime > 0."""
        execution_config = create_internal_execution_config(
            output_mode=InternalOutputMode.LIVE_STREAM,
            max_runtime=60,
            metadata_mode=InternalMetadataMode.DISABLED,
        )

        pipeline_cmd = self.manager.build_pipeline_command(
            self.specs, execution_config, self.job_id
        )

        self.assertIn("rtspclientsink", pipeline_cmd.command)
        pipeline_id = "/pipelines/test-looping/variants/cpu"
        self.assertIn(pipeline_id, pipeline_cmd.live_stream_urls)

    def test_looping_not_applied_for_file_mode(self):
        """Test that looping modifications are never applied for file mode."""
        execution_config = create_internal_execution_config(
            output_mode=InternalOutputMode.FILE,
            max_runtime=0,
            metadata_mode=InternalMetadataMode.DISABLED,
        )

        pipeline_cmd = self.manager.build_pipeline_command(
            self.specs, execution_config, self.job_id
        )

        self.assertIn("videotestsrc", pipeline_cmd.command)
        self.assertNotIn("multifilesrc", pipeline_cmd.command)


# Mock pipeline configs for testing predefined pipelines
MOCK_PIPELINE_CONFIGS = [
    {
        "name": "object-detection",
        "definition": "Object detection pipeline for testing",
        "tags": ["detection", "test"],
        "thumbnail": "",
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
        mock_loader_cls.list.return_value = mock_pipeline_loader_list()
        mock_loader_cls.config.side_effect = mock_pipeline_loader_config
        mock_loader_cls.get_pipelines_directory.return_value = "/mock/pipelines"

        manager = PipelineManager()
        pipelines = manager.get_pipelines()

        predefined_count = 0
        for pipeline in pipelines:
            if pipeline.source == InternalPipelineSource.PREDEFINED:
                predefined_count += 1

                self.assertIsNotNone(pipeline.id)
                self.assertIsNotNone(pipeline.name)
                self.assertIsNotNone(pipeline.description)

                self.assertIsInstance(pipeline.created_at, datetime)
                self.assertIsInstance(pipeline.modified_at, datetime)
                self.assertEqual(pipeline.created_at.tzinfo, timezone.utc)

                self.assertGreater(len(pipeline.variants), 0)

                for variant in pipeline.variants:
                    self.assertIsNotNone(variant.id)
                    self.assertGreater(len(variant.id), 0)
                    self.assertIsNotNone(variant.name)
                    self.assertIn(variant.name, ["CPU", "GPU", "NPU"])
                    self.assertIn(variant.id, ["cpu", "gpu", "npu"])
                    self.assertTrue(variant.read_only)
                    self.assertIsNotNone(variant.pipeline_graph)
                    self.assertIsNotNone(variant.pipeline_graph_simple)

                    self.assertIsInstance(variant.created_at, datetime)
                    self.assertIsInstance(variant.modified_at, datetime)
                    self.assertEqual(variant.created_at.tzinfo, timezone.utc)

                    self.assertGreater(len(variant.pipeline_graph.nodes), 0)
                    self.assertGreater(len(variant.pipeline_graph_simple.nodes), 0)

        self.assertGreater(predefined_count, 0)
        self.assertEqual(predefined_count, len(MOCK_PIPELINE_CONFIGS))

    @patch("managers.pipeline_manager.PipelineLoader")
    def test_predefined_pipelines_have_multiple_variants(self, mock_loader_cls):
        """Verify predefined pipelines have multiple variants (CPU/GPU/NPU)."""
        mock_loader_cls.list.return_value = mock_pipeline_loader_list()
        mock_loader_cls.config.side_effect = mock_pipeline_loader_config
        mock_loader_cls.get_pipelines_directory.return_value = "/mock/pipelines"

        manager = PipelineManager()
        pipelines = manager.get_pipelines()

        multi_variant_count = 0
        predefined_count = 0
        for pipeline in pipelines:
            if pipeline.source == InternalPipelineSource.PREDEFINED:
                predefined_count += 1
                if len(pipeline.variants) > 1:
                    multi_variant_count += 1

        self.assertGreater(multi_variant_count, 0)
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
        mock_loader_cls.list.return_value = mock_pipeline_loader_list()
        mock_loader_cls.config.side_effect = mock_pipeline_loader_config
        mock_loader_cls.get_pipelines_directory.return_value = "/mock/pipelines"

        manager = PipelineManager()

        predefined = None
        for p in manager.get_pipelines():
            if p.source == InternalPipelineSource.PREDEFINED:
                predefined = p
                break

        assert predefined is not None

        with self.assertRaises(ValueError) as context:
            manager.delete_pipeline_by_id(predefined.id)

        self.assertIn("PREDEFINED", str(context.exception))


class TestNameTrimmingAndValidation(unittest.TestCase):
    """Test cases for name trimming and validation in pipeline and variant operations."""

    def setUp(self):
        PipelineManager._instance = None

    def test_add_pipeline_trims_variant_names(self):
        """Test that variant names are trimmed when adding a pipeline."""
        manager = PipelineManager()
        manager.pipelines = []

        new_pipeline = create_pipeline_definition(
            name="test-pipeline",
            description="Test",
            variants=[create_variant_create(name="  CPU  ")],
        )

        added_pipeline = manager.add_pipeline(new_pipeline)

        # Verify the variant name was trimmed
        self.assertEqual(added_pipeline.variants[0].name, "CPU")
        # Verify ID was generated from trimmed name
        self.assertEqual(added_pipeline.variants[0].id, "cpu")

    def test_add_pipeline_whitespace_only_variant_name_raises_error(self):
        """Test that whitespace-only variant name raises ValueError when adding pipeline.

        Note: Empty string is rejected by Pydantic validation at model level.
        Whitespace-only names pass Pydantic but are rejected by manager.
        """
        manager = PipelineManager()
        manager.pipelines = []

        # Use whitespace-only name (passes Pydantic min_length=1 but fails manager validation)
        new_pipeline = create_pipeline_definition(
            name="test-pipeline",
            description="Test",
            variants=[create_variant_create(name="   ")],
        )

        with self.assertRaises(ValueError) as context:
            manager.add_pipeline(new_pipeline)

        self.assertIn("Variant name cannot be empty", str(context.exception))

    def test_add_variant_trims_name(self):
        """Test that variant name is trimmed when adding a variant."""
        manager = PipelineManager()
        manager.pipelines = []

        new_pipeline = create_pipeline_definition(
            name="test-add-variant",
            description="Test",
            variants=[create_variant_create(name="CPU")],
        )
        added = manager.add_pipeline(new_pipeline)

        new_variant = manager.add_variant(
            pipeline_id=added.id,
            name="  GPU  ",
            pipeline_graph=create_simple_graph(),
            pipeline_graph_simple=create_simple_graph(),
        )

        # Verify name was trimmed
        self.assertEqual(new_variant.name, "GPU")
        # Verify ID was generated from trimmed name
        self.assertEqual(new_variant.id, "gpu")

    def test_add_variant_empty_name_raises_error(self):
        """Test that empty variant name raises ValueError."""
        manager = PipelineManager()
        manager.pipelines = []

        new_pipeline = create_pipeline_definition(
            name="test-add-variant",
            description="Test",
            variants=[create_variant_create(name="CPU")],
        )
        added = manager.add_pipeline(new_pipeline)

        with self.assertRaises(ValueError) as context:
            manager.add_variant(
                pipeline_id=added.id,
                name="",
                pipeline_graph=create_simple_graph(),
                pipeline_graph_simple=create_simple_graph(),
            )

        self.assertIn("Variant name cannot be empty", str(context.exception))

    def test_add_variant_whitespace_only_name_raises_error(self):
        """Test that whitespace-only variant name raises ValueError."""
        manager = PipelineManager()
        manager.pipelines = []

        new_pipeline = create_pipeline_definition(
            name="test-add-variant",
            description="Test",
            variants=[create_variant_create(name="CPU")],
        )
        added = manager.add_pipeline(new_pipeline)

        with self.assertRaises(ValueError) as context:
            manager.add_variant(
                pipeline_id=added.id,
                name="   ",
                pipeline_graph=create_simple_graph(),
                pipeline_graph_simple=create_simple_graph(),
            )

        self.assertIn("Variant name cannot be empty", str(context.exception))

    def test_update_variant_trims_name(self):
        """Test that variant name is trimmed when updating."""
        manager = PipelineManager()
        manager.pipelines = []

        new_pipeline = create_pipeline_definition(
            name="test-update-variant",
            description="Test",
            variants=[create_variant_create(name="CPU")],
        )
        added = manager.add_pipeline(new_pipeline)

        updated = manager.update_variant(
            pipeline_id=added.id,
            variant_id=added.variants[0].id,
            name="  GPU-optimized  ",
        )

        # Verify name was trimmed
        self.assertEqual(updated.name, "GPU-optimized")

    def test_update_variant_empty_name_raises_error(self):
        """Test that empty variant name raises ValueError when updating."""
        manager = PipelineManager()
        manager.pipelines = []

        new_pipeline = create_pipeline_definition(
            name="test-update-variant",
            description="Test",
            variants=[create_variant_create(name="CPU")],
        )
        added = manager.add_pipeline(new_pipeline)

        with self.assertRaises(ValueError) as context:
            manager.update_variant(
                pipeline_id=added.id,
                variant_id=added.variants[0].id,
                name="",
            )

        self.assertIn("Variant name cannot be empty", str(context.exception))

    def test_update_variant_whitespace_only_name_raises_error(self):
        """Test that whitespace-only variant name raises ValueError when updating."""
        manager = PipelineManager()
        manager.pipelines = []

        new_pipeline = create_pipeline_definition(
            name="test-update-variant",
            description="Test",
            variants=[create_variant_create(name="CPU")],
        )
        added = manager.add_pipeline(new_pipeline)

        with self.assertRaises(ValueError) as context:
            manager.update_variant(
                pipeline_id=added.id,
                variant_id=added.variants[0].id,
                name="   ",
            )

        self.assertIn("Variant name cannot be empty", str(context.exception))

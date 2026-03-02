import unittest
from datetime import datetime, timezone
from unittest.mock import patch

from api.api_schemas import (
    Edge,
    Node,
    PipelineDefinition,
    PipelineGraph,
    PipelineSource,
    Variant,
    VariantCreate,
)
from graph import Graph
from internal_types import (
    InternalExecutionConfig,
    InternalOutputMode,
    InternalPipelinePerformanceSpec,
)
from managers.pipeline_manager import PipelineManager
from utils import get_current_timestamp
from videos import OUTPUT_VIDEO_DIR


def create_simple_graph() -> PipelineGraph:
    """Helper to create a simple valid pipeline graph."""
    return PipelineGraph(
        nodes=[
            Node(id="0", type="fakesrc", data={}),
            Node(id="1", type="fakesink", data={"name": "default_output_sink"}),
        ],
        edges=[Edge(id="0", source="0", target="1")],
    )


def create_simple_graph_object() -> Graph:
    """Helper to create a simple valid Graph object."""
    return Graph.from_dict(create_simple_graph().model_dump())


def create_variant_create(name: str = "CPU") -> VariantCreate:
    """Helper to create a valid VariantCreate for testing PipelineDefinition."""
    graph = create_simple_graph()
    return VariantCreate(
        name=name,
        pipeline_graph=graph,
        pipeline_graph_simple=graph,
    )


def create_variant(name: str = "CPU", read_only: bool = False) -> Variant:
    """Helper to create a valid Variant for testing."""
    graph = create_simple_graph()
    timestamp = get_current_timestamp()
    return Variant(
        id="variant-test",
        name=name,
        read_only=read_only,
        pipeline_graph=graph,
        pipeline_graph_simple=graph,
        created_at=timestamp,
        modified_at=timestamp,
    )


def create_internal_execution_config(
    output_mode: InternalOutputMode = InternalOutputMode.DISABLED,
    max_runtime: float = 0,
) -> InternalExecutionConfig:
    """Helper to create InternalExecutionConfig for testing."""
    return InternalExecutionConfig(
        output_mode=output_mode,
        max_runtime=max_runtime,
    )


def create_internal_performance_spec(
    pipeline_id: str,
    pipeline_name: str,
    streams: int = 1,
    graph: Graph | None = None,
) -> InternalPipelinePerformanceSpec:
    """Helper to create InternalPipelinePerformanceSpec for testing."""
    if graph is None:
        graph = create_simple_graph_object()
    return InternalPipelinePerformanceSpec(
        pipeline_id=pipeline_id,
        pipeline_name=pipeline_name,
        pipeline_graph=graph,
        streams=streams,
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

        new_pipeline = PipelineDefinition(
            name="user-defined-pipelines",
            description="A test pipeline",
            source=PipelineSource.USER_CREATED,
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

        new_pipeline = PipelineDefinition(
            name="multi-variant-pipeline",
            description="Pipeline with CPU and GPU variants",
            source=PipelineSource.USER_CREATED,
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
        new_pipeline = PipelineDefinition(
            name="test-variant-lookup",
            description="Test pipeline for variant lookup",
            source=PipelineSource.USER_CREATED,
            tags=[],
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

        new_pipeline = PipelineDefinition(
            name="test-variant-lookup",
            description="Test pipeline",
            source=PipelineSource.USER_CREATED,
            tags=[],
            variants=[create_variant_create()],
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

        new_pipeline = PipelineDefinition(
            name="test-variant-copy",
            description="Test pipeline",
            source=PipelineSource.USER_CREATED,
            tags=[],
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
            if pipeline.source == PipelineSource.PREDEFINED:
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

        command, output_paths, live_stream_urls = manager.build_pipeline_command(
            pipeline_performance_specs, execution_config, self.job_id
        )

        # Verify command is not empty and contains pipeline elements
        self.assertIsInstance(command, str)
        self.assertIsInstance(output_paths, dict)
        self.assertIsInstance(live_stream_urls, dict)
        self.assertGreater(len(command), 0)
        self.assertIn("fakesrc", command)
        self.assertIn("fakesink", command)

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

        command, output_paths, live_stream_urls = manager.build_pipeline_command(
            pipeline_performance_specs, execution_config, self.job_id
        )

        self.assertIsInstance(command, str)
        self.assertGreater(len(command), 0)
        self.assertIn("fakesrc", command)

        # Verify output_paths key uses __graph- prefix for inline graphs
        for key in output_paths.keys():
            self.assertTrue(key.startswith("__graph-"))

    def test_build_pipeline_command_single_pipeline_multiple_streams(self):
        manager = PipelineManager()
        manager.pipelines = []

        # Create Graph object with tee element
        tee_graph_dict = {
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
        tee_graph = Graph.from_dict(tee_graph_dict)

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

        command, output_paths, live_stream_urls = manager.build_pipeline_command(
            pipeline_performance_specs, execution_config, self.job_id
        )

        # Verify command contains multiple instances
        self.assertIsInstance(command, str)
        self.assertGreater(len(command), 0)
        # Should have 3 instances of videotestsrc (one per stream)
        self.assertEqual(command.count("videotestsrc"), 3)

    def test_build_pipeline_command_multiple_pipelines(self):
        manager = PipelineManager()
        manager.pipelines = []

        # Create two different Graph objects
        graph1_dict = {
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
        graph2_dict = {
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

        # Build command with two pipelines
        pipeline_performance_specs = [
            InternalPipelinePerformanceSpec(
                pipeline_id="/pipelines/pipeline-1/variants/cpu",
                pipeline_name="pipeline-1",
                pipeline_graph=Graph.from_dict(graph1_dict),
                streams=2,
            ),
            InternalPipelinePerformanceSpec(
                pipeline_id="/pipelines/pipeline-2/variants/cpu",
                pipeline_name="pipeline-2",
                pipeline_graph=Graph.from_dict(graph2_dict),
                streams=3,
            ),
        ]
        execution_config = create_internal_execution_config()

        command, output_paths, live_stream_urls = manager.build_pipeline_command(
            pipeline_performance_specs, execution_config, self.job_id
        )

        # Verify both pipeline types are present
        self.assertIsInstance(command, str)
        self.assertGreater(len(command), 0)
        # Should have 2 instances of fakesrc and 3 instances of videotestsrc
        self.assertEqual(command.count("fakesrc"), 2)
        self.assertEqual(command.count("videotestsrc"), 3)

    def test_update_pipeline_description_and_name(self):
        manager = PipelineManager()
        manager.pipelines = []

        new_pipeline = PipelineDefinition(
            name="original-name",
            description="Original description",
            source=PipelineSource.USER_CREATED,
            tags=["original"],
            variants=[create_variant_create()],
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

        new_pipeline = PipelineDefinition(
            name="test-tags",
            description="Test",
            source=PipelineSource.USER_CREATED,
            tags=["original"],
            variants=[create_variant_create()],
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
            variants=[create_variant_create()],
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
            if p.source == PipelineSource.PREDEFINED:
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

        graph_dict = {
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

        pipeline_id = "/pipelines/test-video-output/variants/cpu"
        pipeline_performance_specs = [
            InternalPipelinePerformanceSpec(
                pipeline_id=pipeline_id,
                pipeline_name="test-video-output",
                pipeline_graph=Graph.from_dict(graph_dict),
                streams=1,
            )
        ]
        execution_config = create_internal_execution_config(
            output_mode=InternalOutputMode.FILE,
            max_runtime=0,
        )

        command, output_paths, live_stream_urls = manager.build_pipeline_command(
            pipeline_performance_specs, execution_config, self.job_id
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

        _, output_paths, _ = manager.build_pipeline_command(
            pipeline_performance_specs, execution_config, self.job_id
        )

        # Verify pipeline ID format for variant reference
        self.assertIn(pipeline_id, output_paths.keys())


class TestVariantCRUD(unittest.TestCase):
    """Test cases for variant CRUD operations."""

    def setUp(self):
        PipelineManager._instance = None

    def test_add_variant_to_pipeline(self):
        """Test adding a new variant to an existing pipeline."""
        manager = PipelineManager()
        manager.pipelines = []

        new_pipeline = PipelineDefinition(
            name="test-add-variant",
            description="Test",
            source=PipelineSource.USER_CREATED,
            tags=[],
            variants=[create_variant_create(name="CPU")],
        )
        added = manager.add_pipeline(new_pipeline)
        self.assertEqual(len(added.variants), 1)
        original_pipeline_modified_at = added.modified_at

        import time

        time.sleep(0.01)

        new_graph = PipelineGraph(
            nodes=[
                Node(id="0", type="videotestsrc", data={}),
                Node(id="1", type="fakesink", data={"name": "default_output_sink"}),
            ],
            edges=[Edge(id="0", source="0", target="1")],
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

        new_pipeline = PipelineDefinition(
            name="test-delete-variant",
            description="Test",
            source=PipelineSource.USER_CREATED,
            tags=[],
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

        new_pipeline = PipelineDefinition(
            name="test-last-variant",
            description="Test",
            source=PipelineSource.USER_CREATED,
            tags=[],
            variants=[create_variant_create()],
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
            variants=[create_variant_create()],
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

        new_pipeline = PipelineDefinition(
            name="test-update-graph",
            description="Test",
            source=PipelineSource.USER_CREATED,
            tags=[],
            variants=[create_variant_create()],
        )
        added = manager.add_pipeline(new_pipeline)

        new_graph = PipelineGraph(
            nodes=[
                Node(id="0", type="videotestsrc", data={}),
                Node(id="1", type="videoconvert", data={}),
                Node(id="2", type="fakesink", data={"name": "default_output_sink"}),
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

        self.assertEqual(len(updated.pipeline_graph.nodes), 3)
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
            variants=[create_variant_create()],
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

        # Create a pipeline with a variant
        new_pipeline = PipelineDefinition(
            name="test-conversion",
            description="Test",
            source=PipelineSource.USER_CREATED,
            tags=[],
            variants=[create_variant_create()],
        )
        manager.add_pipeline(new_pipeline)

        # Create an advanced graph with some hidden elements (use videotestsrc, not filesrc)
        advanced_graph_dict = {
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
        advanced_graph = Graph.from_dict(advanced_graph_dict)

        # Convert to simple
        simple_graph = manager.validate_and_convert_advanced_to_simple(advanced_graph)

        # Verify simple graph has fewer nodes (queue should be hidden)
        self.assertIsInstance(simple_graph, Graph)
        self.assertLessEqual(len(simple_graph.nodes), len(advanced_graph.nodes))

    def test_validate_and_convert_advanced_to_simple_empty_nodes_raises_error(self):
        """Test that empty nodes in advanced graph raises error."""
        manager = PipelineManager()
        manager.pipelines = []

        new_pipeline = PipelineDefinition(
            name="test-conversion",
            description="Test",
            source=PipelineSource.USER_CREATED,
            tags=[],
            variants=[create_variant_create()],
        )
        manager.add_pipeline(new_pipeline)

        # Create empty graph
        empty_graph = Graph(nodes=[], edges=[])

        with self.assertRaises(ValueError) as context:
            manager.validate_and_convert_advanced_to_simple(empty_graph)

        self.assertIn("at least one node and one edge", str(context.exception))

    def test_validate_and_convert_simple_to_advanced_success(self):
        """Test successful conversion from simple to advanced graph."""
        manager = PipelineManager()
        manager.pipelines = []

        # Create a pipeline with variant that has both graphs (use videotestsrc, not filesrc)
        graph = PipelineGraph(
            nodes=[
                Node(id="0", type="videotestsrc", data={"pattern": "0"}),
                Node(id="1", type="queue", data={}),
                Node(id="2", type="fakesink", data={}),
            ],
            edges=[
                Edge(id="0", source="0", target="1"),
                Edge(id="1", source="1", target="2"),
            ],
        )
        simple_graph = PipelineGraph(
            nodes=[
                Node(id="0", type="videotestsrc", data={"pattern": "0"}),
                Node(id="2", type="fakesink", data={}),
            ],
            edges=[
                Edge(id="0", source="0", target="2"),
            ],
        )

        new_pipeline = PipelineDefinition(
            name="test-conversion",
            description="Test",
            source=PipelineSource.USER_CREATED,
            tags=[],
            variants=[
                VariantCreate(
                    name="CPU",
                    pipeline_graph=graph,
                    pipeline_graph_simple=simple_graph,
                )
            ],
        )
        added = manager.add_pipeline(new_pipeline)
        variant = added.variants[0]

        # Modify simple graph (change property)
        modified_simple_graph_dict = {
            "nodes": [
                {"id": "0", "type": "videotestsrc", "data": {"pattern": "1"}},
                {"id": "2", "type": "fakesink", "data": {}},
            ],
            "edges": [
                {"id": "0", "source": "0", "target": "2"},
            ],
        }
        modified_simple_graph = Graph.from_dict(modified_simple_graph_dict)

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

        graph = PipelineGraph(
            nodes=[
                Node(id="0", type="videotestsrc", data={}),
                Node(id="1", type="fakesink", data={}),
            ],
            edges=[
                Edge(id="0", source="0", target="1"),
            ],
        )

        new_pipeline = PipelineDefinition(
            name="test-conversion",
            description="Test",
            source=PipelineSource.USER_CREATED,
            tags=[],
            variants=[
                VariantCreate(
                    name="CPU",
                    pipeline_graph=graph,
                    pipeline_graph_simple=graph,
                )
            ],
        )
        added = manager.add_pipeline(new_pipeline)
        variant = added.variants[0]

        # Try to add a node in simple graph (structural change)
        modified_simple_graph_dict = {
            "nodes": [
                {"id": "0", "type": "videotestsrc", "data": {}},
                {"id": "1", "type": "fakesink", "data": {}},
                {"id": "2", "type": "new_element", "data": {}},  # Added node
            ],
            "edges": [
                {"id": "0", "source": "0", "target": "1"},
            ],
        }
        modified_simple_graph = Graph.from_dict(modified_simple_graph_dict)

        with self.assertRaises(ValueError) as context:
            manager.validate_and_convert_simple_to_advanced(
                variant, modified_simple_graph
            )

        self.assertIn("Invalid pipeline_graph_simple", str(context.exception))

    def test_validate_and_convert_simple_to_advanced_empty_nodes_raises_error(self):
        """Test that empty nodes in simple graph raises error."""
        manager = PipelineManager()
        manager.pipelines = []

        new_pipeline = PipelineDefinition(
            name="test-conversion",
            description="Test",
            source=PipelineSource.USER_CREATED,
            tags=[],
            variants=[create_variant_create()],
        )
        added = manager.add_pipeline(new_pipeline)
        variant = added.variants[0]

        # Create empty graph
        empty_graph = Graph(nodes=[], edges=[])

        with self.assertRaises(ValueError) as context:
            manager.validate_and_convert_simple_to_advanced(variant, empty_graph)

        self.assertIn("at least one node and one edge", str(context.exception))


class TestBuildPipelineCommandExecutionConfig(unittest.TestCase):
    """Test cases for ExecutionConfig validation in build_pipeline_command."""

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
        )

        command, output_paths, live_stream_urls = self.manager.build_pipeline_command(
            self.specs, execution_config, self.job_id
        )

        self.assertIsInstance(command, str)
        self.assertGreater(len(command), 0)
        self.assertIn("filesink", command)

    def test_disabled_output_with_max_runtime_succeeds(self):
        """Test that disabled output mode with max_runtime > 0 works correctly."""
        execution_config = create_internal_execution_config(
            output_mode=InternalOutputMode.DISABLED,
            max_runtime=60,
        )

        command, output_paths, live_stream_urls = self.manager.build_pipeline_command(
            self.specs, execution_config, self.job_id
        )

        self.assertIsInstance(command, str)
        self.assertGreater(len(command), 0)
        self.assertIn("fakesink", command)

    def test_live_stream_output_with_max_runtime_succeeds(self):
        """Test that live stream output mode with max_runtime > 0 works correctly."""
        execution_config = create_internal_execution_config(
            output_mode=InternalOutputMode.LIVE_STREAM,
            max_runtime=60,
        )

        command, output_paths, live_stream_urls = self.manager.build_pipeline_command(
            self.specs, execution_config, self.job_id
        )

        self.assertIsInstance(command, str)
        self.assertGreater(len(command), 0)
        self.assertIn("rtspclientsink", command)
        pipeline_id = "/pipelines/test-execution-config/variants/cpu"
        self.assertIn(pipeline_id, live_stream_urls)

    def test_live_stream_output_returns_stream_urls(self):
        """Test that live stream output mode returns correct stream URLs."""
        execution_config = create_internal_execution_config(
            output_mode=InternalOutputMode.LIVE_STREAM,
            max_runtime=0,
        )

        command, output_paths, live_stream_urls = self.manager.build_pipeline_command(
            self.specs, execution_config, self.job_id
        )

        pipeline_id = "/pipelines/test-execution-config/variants/cpu"
        self.assertIn(pipeline_id, live_stream_urls)
        stream_url = live_stream_urls[pipeline_id]
        self.assertTrue(stream_url.startswith("rtsp://"))

    def test_live_stream_one_url_per_pipeline(self):
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
        )

        command, output_paths, live_stream_urls = self.manager.build_pipeline_command(
            specs, execution_config, self.job_id
        )

        # Should have exactly 2 live stream URLs (one per pipeline)
        self.assertEqual(len(live_stream_urls), 2)
        # Only first stream of each pipeline should have rtspclientsink
        self.assertEqual(command.count("rtspclientsink"), 2)


class TestBuildPipelineCommandLooping(unittest.TestCase):
    """Test cases for looping behavior in build_pipeline_command."""

    def setUp(self):
        PipelineManager._instance = None
        self.manager = PipelineManager()
        self.manager.pipelines = []
        self.job_id = "test-job-789"

        # Create internal specs for looping tests
        graph_dict = {
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
        self.specs = [
            InternalPipelinePerformanceSpec(
                pipeline_id="/pipelines/test-looping/variants/cpu",
                pipeline_name="test-looping",
                pipeline_graph=Graph.from_dict(graph_dict),
                streams=1,
            )
        ]

    def test_looping_not_applied_when_max_runtime_zero(self):
        """Test that looping modifications are not applied when max_runtime=0."""
        execution_config = create_internal_execution_config(
            output_mode=InternalOutputMode.DISABLED,
            max_runtime=0,
        )

        command, _, _ = self.manager.build_pipeline_command(
            self.specs, execution_config, self.job_id
        )

        self.assertIn("videotestsrc", command)
        self.assertNotIn("multifilesrc", command)

    def test_looping_applied_when_max_runtime_positive_and_disabled_mode(self):
        """Test that looping modifications are applied for disabled mode with max_runtime > 0."""
        execution_config = create_internal_execution_config(
            output_mode=InternalOutputMode.DISABLED,
            max_runtime=60,
        )

        command, _, _ = self.manager.build_pipeline_command(
            self.specs, execution_config, self.job_id
        )

        self.assertIn("videotestsrc", command)
        self.assertIn("fakesink", command)

    def test_looping_applied_when_max_runtime_positive_and_live_stream_mode(self):
        """Test that looping modifications are applied for live stream mode with max_runtime > 0."""
        execution_config = create_internal_execution_config(
            output_mode=InternalOutputMode.LIVE_STREAM,
            max_runtime=60,
        )

        command, _, live_stream_urls = self.manager.build_pipeline_command(
            self.specs, execution_config, self.job_id
        )

        self.assertIn("rtspclientsink", command)
        pipeline_id = "/pipelines/test-looping/variants/cpu"
        self.assertIn(pipeline_id, live_stream_urls)

    def test_looping_not_applied_for_file_mode(self):
        """Test that looping modifications are never applied for file mode."""
        execution_config = create_internal_execution_config(
            output_mode=InternalOutputMode.FILE,
            max_runtime=0,
        )

        command, _, _ = self.manager.build_pipeline_command(
            self.specs, execution_config, self.job_id
        )

        self.assertIn("videotestsrc", command)
        self.assertNotIn("multifilesrc", command)


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
            if pipeline.source == PipelineSource.PREDEFINED:
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
            if pipeline.source == PipelineSource.PREDEFINED:
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
            if p.source == PipelineSource.PREDEFINED:
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

        new_pipeline = PipelineDefinition(
            name="test-pipeline",
            description="Test",
            source=PipelineSource.USER_CREATED,
            tags=[],
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
        new_pipeline = PipelineDefinition(
            name="test-pipeline",
            description="Test",
            source=PipelineSource.USER_CREATED,
            tags=[],
            variants=[create_variant_create(name="   ")],
        )

        with self.assertRaises(ValueError) as context:
            manager.add_pipeline(new_pipeline)

        self.assertIn("Variant name cannot be empty", str(context.exception))

    def test_add_variant_trims_name(self):
        """Test that variant name is trimmed when adding a variant."""
        manager = PipelineManager()
        manager.pipelines = []

        new_pipeline = PipelineDefinition(
            name="test-add-variant",
            description="Test",
            source=PipelineSource.USER_CREATED,
            tags=[],
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

        new_pipeline = PipelineDefinition(
            name="test-add-variant",
            description="Test",
            source=PipelineSource.USER_CREATED,
            tags=[],
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

        new_pipeline = PipelineDefinition(
            name="test-add-variant",
            description="Test",
            source=PipelineSource.USER_CREATED,
            tags=[],
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

        new_pipeline = PipelineDefinition(
            name="test-update-variant",
            description="Test",
            source=PipelineSource.USER_CREATED,
            tags=[],
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

        new_pipeline = PipelineDefinition(
            name="test-update-variant",
            description="Test",
            source=PipelineSource.USER_CREATED,
            tags=[],
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

        new_pipeline = PipelineDefinition(
            name="test-update-variant",
            description="Test",
            source=PipelineSource.USER_CREATED,
            tags=[],
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

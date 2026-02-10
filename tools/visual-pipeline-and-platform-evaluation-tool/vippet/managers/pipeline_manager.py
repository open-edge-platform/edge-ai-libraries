from copy import deepcopy
import logging
import threading
from typing import Optional, List

from pipelines.loader import PipelineLoader
from video_encoder import VideoEncoder
from utils import generate_unique_id
from graph import Graph, OUTPUT_PLACEHOLDER
from api.api_schemas import (
    PipelineType,
    PipelineSource,
    Pipeline,
    PipelineDefinition,
    PipelinePerformanceSpec,
    ExecutionConfig,
    OutputMode,
    PipelineGraph,
    PipelineParameters,
)

logger = logging.getLogger("pipeline_manager")


class PipelineManager:
    """
    Thread-safe singleton that manages pipelines including both advanced and simple graph views.

    Implements singleton pattern using __new__ with double-checked locking.
    Create instances with PipelineManager() to get the shared singleton instance.

    Responsibilities:
    * Load predefined pipelines from configuration
    * Create, read, update, delete user-created pipelines
    * Maintain both advanced and simple views for all pipelines
    * Generate simple views automatically from advanced views
    * Apply simple view changes back to advanced views
    * Build executable GStreamer pipeline commands with proper video encoding
    """

    _instance: Optional["PipelineManager"] = None
    _lock = threading.Lock()

    def __new__(cls) -> "PipelineManager":
        if cls._instance is None:
            with cls._lock:
                # Double-checked locking
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        # Protect against multiple initialization
        if hasattr(self, "_initialized"):
            return
        self._initialized = True

        self.logger = logging.getLogger("PipelineManager")
        # Shared lock protecting access to pipelines
        self._pipelines_lock = threading.Lock()
        # List of pipelines managed by this instance
        self.pipelines = self.load_predefined_pipelines()
        # Video encoder instance used by pipelines
        self.video_encoder = VideoEncoder()

    def add_pipeline(self, new_pipeline: PipelineDefinition):
        """
        Create a new pipeline from a pipeline definition.

        The method:
        * Validates version numbering rules
        * Generates a unique pipeline ID
        * Parses GStreamer pipeline string (pipeline_description) into advanced graph
        * Generates simple view from advanced graph
        * Stores pipeline with both views

        Args:
            new_pipeline: PipelineDefinition with name, version, description (human-readable text),
                type, pipeline_description (GStreamer pipeline string), and optional parameters.

        Returns:
            Pipeline: Created pipeline with generated ID and both graph views.

        Raises:
            ValueError: If version numbering rules are violated or GStreamer pipeline
                string cannot be parsed.
        """
        with self._pipelines_lock:
            # Enforce strictly increasing, consecutive pipeline versions per name.
            self._ensure_next_version(new_pipeline.name, new_pipeline.version)

            # Generate ID with "pipeline" prefix
            pipeline_id = generate_unique_id("pipeline")

            # Parse pipeline description into advanced graph
            graph = Graph.from_pipeline_description(new_pipeline.pipeline_description)
            pipeline_graph = PipelineGraph.model_validate(graph.to_dict())

            # Generate simple view from advanced graph
            simple_graph = graph.to_simple_view()
            pipeline_graph_simple = PipelineGraph.model_validate(simple_graph.to_dict())

            pipeline = Pipeline(
                id=pipeline_id,
                name=new_pipeline.name,
                version=new_pipeline.version,
                description=new_pipeline.description,
                source=new_pipeline.source,
                type=new_pipeline.type,
                pipeline_graph=pipeline_graph,
                pipeline_graph_simple=pipeline_graph_simple,
                parameters=new_pipeline.parameters,
            )

            self.pipelines.append(pipeline)
        self.logger.debug(f"Pipeline added: {pipeline}")
        return pipeline

    def _ensure_next_version(self, name: str, proposed_version: int) -> None:
        """Ensure that the proposed version is exactly one greater than the
        latest existing version for the given pipeline name.

        Rules:
        * If no pipeline with this ``name`` exists yet, only version ``1`` is allowed.
        * If pipelines exist, the proposed version must be exactly
          ``latest_version + 1``.

        Raises:
            ValueError: If the proposed version is not valid. The error message
            includes the expected next version to help the caller correct
            the request.
        """

        # Collect all versions for the given name (may be empty).
        existing_versions = [
            pipeline.version for pipeline in self.pipelines if pipeline.name == name
        ]

        if not existing_versions:
            # First version for a new pipeline name must be 1.
            if proposed_version != 1:
                raise ValueError(
                    f"Invalid version '{proposed_version}' for pipeline '{name}'. "
                    "Expected version '1' for a new pipeline."
                )
            return

        latest_version = max(existing_versions)
        expected_version = latest_version + 1

        if proposed_version != expected_version:
            raise ValueError(
                f"Invalid version '{proposed_version}' for pipeline '{name}'. "
                f"Expected next version to be '{expected_version}'."
            )

    def get_pipelines(self) -> list[Pipeline]:
        with self._pipelines_lock:
            return [deepcopy(p) for p in self.pipelines]

    def get_pipeline_by_id(self, pipeline_id: str) -> Pipeline:
        """
        Retrieve a pipeline by its ID.

        Args:
            pipeline_id: The unique ID of the pipeline.

        Returns:
            Pipeline: The pipeline object.

        Raises:
            ValueError: If pipeline with given ID is not found.
        """
        with self._pipelines_lock:
            pipeline = self._find_pipeline_by_id(pipeline_id)
            if pipeline is not None:
                return deepcopy(pipeline)
        raise ValueError(f"Pipeline with id '{pipeline_id}' not found.")

    def _pipeline_exists(self, name: str, version: int) -> bool:
        return self._find_pipeline_by_name_and_version(name, version) is not None

    def _find_pipeline_by_name_and_version(
        self, name: str, version: int
    ) -> Pipeline | None:
        for pipeline in self.pipelines:
            if pipeline.name == name and pipeline.version == version:
                return pipeline
        return None

    def _find_pipeline_by_id(self, pipeline_id: str) -> Pipeline | None:
        """Find a pipeline by its ID."""
        for pipeline in self.pipelines:
            if pipeline.id == pipeline_id:
                return pipeline
        return None

    def update_pipeline(
        self,
        pipeline_id: str,
        name: Optional[str] = None,
        description: Optional[str] = None,
        pipeline_graph: Optional[PipelineGraph] = None,
        pipeline_graph_simple: Optional[PipelineGraph] = None,
        parameters: Optional[PipelineParameters] = None,
    ) -> Pipeline:
        """Update selected fields of an existing pipeline.

        Important: Only ONE of pipeline_graph or pipeline_graph_simple should be provided.
        If pipeline_graph is provided, it replaces the advanced view and a new simple view
        is auto-generated. If pipeline_graph_simple is provided, changes are merged into
        the advanced view using apply_simple_view_changes(), and a new simple view is
        regenerated from the updated advanced view.

        Args:
            pipeline_id: ID of the pipeline to update.
            name: Optional new pipeline name.
            description: Optional new human-readable text describing what the pipeline does.
            pipeline_graph: Optional new advanced graph representation.
            pipeline_graph_simple: Optional modified simple graph with property changes.
            parameters: Optional new pipeline parameters.

        Returns:
            The updated :class:`Pipeline` instance with both graph views.

        Raises:
            ValueError: If the pipeline with the given ID does not exist.
            ValueError: If both pipeline_graph and pipeline_graph_simple are provided.
            ValueError: If pipeline_graph_simple changes are invalid (structural changes).
            ValueError: If provided pipeline graph cannot be converted to a valid GStreamer pipeline string.
        """

        with self._pipelines_lock:
            pipeline = self._find_pipeline_by_id(pipeline_id)
            if pipeline is None:
                raise ValueError(f"Pipeline with id '{pipeline_id}' not found.")

            # Validate that only one graph type is provided
            if pipeline_graph is not None and pipeline_graph_simple is not None:
                raise ValueError(
                    "Cannot update both 'pipeline_graph' and 'pipeline_graph_simple' at the same time. "
                    "Please provide only one."
                )

            # Update fields if provided
            if name is not None:
                pipeline.name = name

            if description is not None:
                pipeline.description = description

            # Handle pipeline graph updates
            if pipeline_graph is not None:
                # User provided new advanced graph - validate and regenerate simple view
                pipeline_description = Graph.from_dict(
                    pipeline_graph.model_dump()
                ).to_pipeline_description()
                if not pipeline_description:
                    raise ValueError("Provided pipeline graph is invalid.")

                pipeline.pipeline_graph = pipeline_graph

                # Auto-generate simple view from new advanced graph
                graph = Graph.from_dict(pipeline_graph.model_dump())
                simple_graph = graph.to_simple_view()
                pipeline.pipeline_graph_simple = PipelineGraph.model_validate(
                    simple_graph.to_dict()
                )

                self.logger.debug(
                    f"Updated advanced graph for pipeline {pipeline_id} and regenerated simple view"
                )

            elif pipeline_graph_simple is not None:
                # User provided modified simple graph - merge changes into advanced view
                original_advanced_graph = Graph.from_dict(
                    pipeline.pipeline_graph.model_dump()
                )
                original_simple_graph = Graph.from_dict(
                    pipeline.pipeline_graph_simple.model_dump()
                )
                modified_simple_graph = Graph.from_dict(
                    pipeline_graph_simple.model_dump()
                )

                # Apply simple view changes to advanced view
                updated_advanced_graph = Graph.apply_simple_view_changes(
                    modified_simple=modified_simple_graph,
                    original_simple=original_simple_graph,
                    original_advanced=original_advanced_graph,
                )

                # Validate updated advanced graph can be converted to pipeline description
                pipeline_description = updated_advanced_graph.to_pipeline_description()
                if not pipeline_description:
                    raise ValueError(
                        "Updated pipeline graph is invalid after applying simple view changes."
                    )

                # Store updated advanced graph
                pipeline.pipeline_graph = PipelineGraph.model_validate(
                    updated_advanced_graph.to_dict()
                )

                # Regenerate simple view from updated advanced graph
                new_simple_graph = updated_advanced_graph.to_simple_view()
                pipeline.pipeline_graph_simple = PipelineGraph.model_validate(
                    new_simple_graph.to_dict()
                )

                self.logger.debug(
                    f"Applied simple view changes to pipeline {pipeline_id} and regenerated both views"
                )

            if parameters is not None:
                pipeline.parameters = parameters

            self.logger.debug("Pipeline updated: %s", pipeline)
            return pipeline

    def delete_pipeline_by_id(self, pipeline_id: str):
        """
        Delete a pipeline by its ID.

        Args:
            pipeline_id: The unique ID of the pipeline to delete.

        Raises:
            ValueError: If pipeline with given ID is not found.
        """
        with self._pipelines_lock:
            pipeline = self._find_pipeline_by_id(pipeline_id)
            if pipeline is not None:
                self.pipelines.remove(pipeline)
                self.logger.debug(f"Pipeline deleted: {pipeline}")
            else:
                raise ValueError(f"Pipeline with id '{pipeline_id}' not found.")

    def load_predefined_pipelines(self):
        """
        Load predefined pipelines from configuration files.

        For each pipeline:
        * Parse GStreamer pipeline string (pipeline_description) into advanced graph
        * Generate simple view from advanced graph
        * Create Pipeline object with both views

        Returns:
            list[Pipeline]: List of predefined pipelines with both graph views.
        """
        predefined_pipelines = []
        for config_path in PipelineLoader.list():
            config = PipelineLoader.config(config_path)

            pipeline_description = config.get("pipeline_description", "")

            # Parse into advanced graph
            graph = Graph.from_pipeline_description(pipeline_description)
            pipeline_graph = PipelineGraph.model_validate(graph.to_dict())

            # Generate simple view
            simple_graph = graph.to_simple_view()
            pipeline_graph_simple = PipelineGraph.model_validate(simple_graph.to_dict())

            predefined_pipelines.append(
                Pipeline(
                    id=generate_unique_id("pipeline"),
                    name=config.get("name", "unnamed-pipeline"),
                    version=int(config.get("version", 1)),
                    description=config.get("definition", ""),
                    source=PipelineSource.PREDEFINED,
                    type=PipelineType.GSTREAMER,
                    pipeline_graph=pipeline_graph,
                    pipeline_graph_simple=pipeline_graph_simple,
                    parameters=None,
                )
            )
        self.logger.debug("Loaded predefined pipelines: %s", predefined_pipelines)
        return predefined_pipelines

    def build_pipeline_command(
        self,
        pipeline_performance_specs: list[PipelinePerformanceSpec],
        execution_config: ExecutionConfig,
    ) -> tuple[str, dict[str, List[str]], dict[str, str]]:
        """
        Build a complete executable GStreamer pipeline command from run specifications.

        This method takes pipeline specifications with stream counts, retrieves the
        corresponding pipeline graphs, and constructs a complete GStreamer command line
        that can be executed to run all specified pipelines with all their streams.

        Args:
            pipeline_performance_specs: List of PipelinePerformanceSpec defining pipelines and streams.
            execution_config: Configuration for output generation and runtime limits.

        Returns:
            tuple: (Complete GStreamer command string,
                    dictionary mapping pipeline IDs to output file paths,
                    dictionary mapping pipeline IDs to live stream URLs)

            Note: live_stream_urls will be empty for density tests since they do not
            support live-streaming output mode. The caller is responsible for validating
            that output_mode=live_stream is not used with density tests.

        Raises:
            ValueError: If any pipeline in specs is not found.
            ValueError: If execution_config.max_runtime is negative.
            ValueError: If output_mode=file is combined with max_runtime>0.
        """
        # Validate max_runtime
        if execution_config.max_runtime < 0:
            raise ValueError(
                f"Invalid max_runtime value: {execution_config.max_runtime}. "
                "Negative values are not allowed."
            )

        # Validate output_mode + max_runtime combination
        if (
            execution_config.output_mode == OutputMode.FILE
            and execution_config.max_runtime > 0
        ):
            raise ValueError(
                "Invalid execution_config: output_mode='file' cannot be combined with max_runtime > 0. "
                "File output does not support looping. Use max_runtime=0 to run until EOS, "
                "or use output_mode='disabled' or 'live_stream' for time-limited execution."
            )

        pipeline_parts = []
        video_output_paths: dict[str, List[str]] = {}
        live_stream_urls: dict[str, str] = {}
        output_subpipeline: str | None = None

        # Determine if we need looping behavior based on max_runtime
        # Looping is only supported for disabled and live_stream modes
        needs_looping = (
            execution_config.max_runtime > 0
            and execution_config.output_mode != OutputMode.FILE
        )

        for pipeline_index, run_spec in enumerate(pipeline_performance_specs):
            # Retrieve the pipeline definition by ID
            pipeline = self.get_pipeline_by_id(run_spec.id)

            # Convert pipeline graph dict back to Graph object
            base_graph = Graph.from_dict(pipeline.pipeline_graph.model_dump())

            base_graph = base_graph.unify_model_instance_ids()

            # Apply looping modifications if needed
            if needs_looping:
                base_graph = base_graph.apply_looping_modifications()

            base_graph, intermediate_output_paths = (
                base_graph.prepare_intermediate_output_sinks()
            )

            video_output_paths[pipeline.id] = intermediate_output_paths

            output_mode = execution_config.output_mode

            # prepare main video output path if output is enabled (file or live stream)
            if output_mode != OutputMode.DISABLED:
                # Retrieve input video filenames and recommended encoder device
                input_video_filenames = base_graph.get_input_video_filenames()
                encoder_device = base_graph.get_recommended_encoder_device()

                # Create output subpipeline based on output mode (file or live stream)
                if output_mode == OutputMode.FILE:
                    output_subpipeline, output_path = (
                        self.video_encoder.create_video_output_subpipeline(
                            pipeline.id, encoder_device, input_video_filenames
                        )
                    )
                    video_output_paths[pipeline.id].append(output_path)
                elif output_mode == OutputMode.LIVE_STREAM:
                    output_subpipeline, stream_url = (
                        self.video_encoder.create_live_stream_output_subpipeline(
                            pipeline.id,
                            encoder_device,
                            input_video_filenames,
                        )
                    )
                    live_stream_urls[pipeline.id] = stream_url

            # Build pipeline parts for all streams of this pipeline specification
            for stream_index in range(run_spec.streams):
                graph_instance = deepcopy(base_graph)

                if output_mode != OutputMode.DISABLED and stream_index == 0:
                    # Create a placeholder node for the main output sink to be replaced later
                    graph_instance = graph_instance.prepare_main_output_placeholder()

                graph_instance = graph_instance.unify_all_element_names(
                    pipeline_index, stream_index
                )

                unique_pipeline_str = graph_instance.to_pipeline_description()

                if output_mode != OutputMode.DISABLED and stream_index == 0:
                    # Replace the main output placeholder with the actual output subpipeline (file or live stream)
                    if OUTPUT_PLACEHOLDER not in unique_pipeline_str:
                        raise ValueError(
                            f"Pipeline '{pipeline.name}' (id: {pipeline.id}) is missing required output sink. "
                            f"Please add 'fakesink name=default_output_sink' at the end of the pipeline definition."
                        )
                    if output_subpipeline is None:
                        raise ValueError(
                            "Output subpipeline was not created as expected."
                        )
                    unique_pipeline_str = unique_pipeline_str.replace(
                        OUTPUT_PLACEHOLDER, output_subpipeline
                    )

                pipeline_parts.append(unique_pipeline_str)

        return " ".join(pipeline_parts), video_output_paths, live_stream_urls

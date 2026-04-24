import logging
import threading
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, List

from graph import Graph, OUTPUT_PLACEHOLDER
from internal_types import (
    InternalExecutionConfig,
    InternalOutputMode,
    InternalMetadataMode,
    InternalPipeline,
    InternalPipelineDefinition,
    InternalPipelinePerformanceSpec,
    InternalPipelineSource,
    InternalStreamInfo,
    InternalVariant,
)
from pipelines.loader import PipelineLoader
from utils import (
    generate_unique_id,
    get_current_timestamp,
    load_thumbnail_as_base64,
    make_output_dir,
)
from video_encoder import VideoEncoder
from videos import OUTPUT_VIDEO_DIR
from managers.metadata_manager import METADATA_DIR

logger = logging.getLogger("pipeline_manager")


@dataclass
class PipelineCommand:
    """
    Result bundle returned by :meth:`PipelineManager.build_pipeline_command`.

    Groups all outputs in a single object so callers use attribute
    access and the public signature stays stable as fields are added.

    Attributes:
        command: Complete, ready-to-run GStreamer ``gst-launch``-style
            pipeline description string covering every pipeline and
            every stream of the test.
        video_output_paths: Mapping from pipeline id to that pipeline's
            output directory path. Empty when no pipeline produces
            video files (e.g. ``output_mode=disabled``).
        live_stream_urls: Mapping from pipeline id to its RTSP live
            stream URL. Only populated when
            ``output_mode=live_stream``. Empty for density tests,
            which do not support live streaming.
        metadata_file_paths: Mapping from pipeline id to the list of
            ``gvametapublish`` JSON-Lines file paths (one per
            ``gvametapublish`` element) injected into the pipeline
            when ``metadata_mode=file``. Empty otherwise.
        streams_per_pipeline: Mapping from pipeline id to the list of
            :class:`InternalStreamInfo` records describing every
            running stream of that pipeline, in creation order. Each
            entry carries the exact ``source_name``/``sink_name``
            applied to the main source/sink pair of the stream —
            these are the values external tracers (e.g. DLStreamer
            ``latency_tracer``) will report, so they act as the
            correlation key between tracer rows and streams.
    """

    command: str
    video_output_paths: dict[str, str] = field(default_factory=dict)
    live_stream_urls: dict[str, str] = field(default_factory=dict)
    metadata_file_paths: dict[str, list[str]] = field(default_factory=dict)
    streams_per_pipeline: dict[str, list[InternalStreamInfo]] = field(
        default_factory=dict
    )

    @property
    def all_stream_ids(self) -> list[str]:
        """
        Return every ``stream_id`` declared by this command, flat.

        The returned list preserves pipeline order and, within each
        pipeline, stream creation order. It is the exhaustive set of
        identifiers that external tracers are expected to report for
        this run; any row they emit with a ``stream_id`` outside this
        list refers to an element that is NOT one of the
        user-facing source/sink pairs (internal bin sinks, the
        intermediate ``splitmuxsink`` recorder, and similar) and must
        be ignored.
        """
        return [
            info.stream_id
            for infos in self.streams_per_pipeline.values()
            for info in infos
        ]


class PipelineManager:
    """
    Thread-safe singleton that manages pipelines including both advanced and simple graph views.

    Implements singleton pattern using __new__ with double-checked locking.
    Create instances with PipelineManager() to get the shared singleton instance.

    Responsibilities:
    * Load predefined pipelines from configuration
    * Create, read, update, delete user-created pipelines
    * Maintain variants with both advanced and simple views
    * Convert between advanced and simple graph views
    * Build executable GStreamer pipeline commands with proper video encoding
    * Track creation and modification timestamps for pipelines and variants
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

    def add_pipeline(
        self, new_pipeline: InternalPipelineDefinition
    ) -> InternalPipeline:
        """
        Create a new pipeline from a pipeline definition.

        The method:
        * Generates a unique pipeline ID
        * Sets created_at and modified_at timestamps
        * Trims and validates variant names (raises ValueError if empty after trimming)
        * Generates unique variant IDs from variant names
        * Sets read_only=False for all variants
        * Sets timestamps for all variants
        * Stores pipeline with variants containing both graph views

        Args:
            new_pipeline: InternalPipelineDefinition with name, description, tags, and variants.

        Returns:
            InternalPipeline: Created pipeline with generated ID and timestamps.

        Raises:
            ValueError: If pipeline definition is invalid.
            ValueError: If any variant name is empty after trimming.
        """
        with self._pipelines_lock:
            # Get existing pipeline IDs for collision check
            existing_ids = [p.id for p in self.pipelines]

            # Generate ID from pipeline name
            pipeline_id = generate_unique_id(new_pipeline.name, existing_ids)

            # Set timestamps
            current_time = get_current_timestamp()

            # Collect existing variant IDs for collision check
            existing_variant_ids: List[str] = []

            # Generate variant IDs and set timestamps for all variants
            variants_with_timestamps = []
            for variant_create in new_pipeline.variants:
                # Validate and trim variant name
                trimmed_name = self._validate_and_trim_variant_name(variant_create.name)

                # Generate variant ID from variant name (same logic as add_variant)
                variant_id = generate_unique_id(trimmed_name, existing_variant_ids)
                existing_variant_ids.append(variant_id)

                variant_with_ts = InternalVariant(
                    id=variant_id,
                    name=trimmed_name,
                    read_only=False,  # User-created variants are never read-only
                    pipeline_graph=variant_create.pipeline_graph,
                    pipeline_graph_simple=variant_create.pipeline_graph_simple,
                    created_at=current_time,
                    modified_at=current_time,
                )
                variants_with_timestamps.append(variant_with_ts)

            pipeline = InternalPipeline(
                id=pipeline_id,
                name=new_pipeline.name,
                description=new_pipeline.description,
                source=new_pipeline.source,
                tags=new_pipeline.tags,
                variants=variants_with_timestamps,
                thumbnail=None,  # User-created pipelines do not have thumbnails
                created_at=current_time,
                modified_at=current_time,
            )

            self.pipelines.append(pipeline)
        self.logger.debug(f"Pipeline added: {pipeline}")
        return pipeline

    def get_pipelines(self) -> list[InternalPipeline]:
        with self._pipelines_lock:
            return [deepcopy(p) for p in self.pipelines]

    def get_pipeline_by_id(self, pipeline_id: str) -> InternalPipeline:
        """
        Retrieve a pipeline by its ID.

        Args:
            pipeline_id: The unique ID of the pipeline.

        Returns:
            InternalPipeline: The pipeline object.

        Raises:
            ValueError: If pipeline with given ID is not found.
        """
        with self._pipelines_lock:
            pipeline = self._find_pipeline_by_id(pipeline_id)
            if pipeline is not None:
                return deepcopy(pipeline)
        raise ValueError(f"Pipeline with id '{pipeline_id}' not found.")

    def get_variant_by_ids(self, pipeline_id: str, variant_id: str) -> InternalVariant:
        """
        Retrieve a variant by pipeline ID and variant ID.

        Args:
            pipeline_id: The unique ID of the pipeline.
            variant_id: The unique ID of the variant.

        Returns:
            InternalVariant: The variant object.

        Raises:
            ValueError: If pipeline with given ID is not found.
            ValueError: If variant with given ID is not found in the pipeline.
        """
        with self._pipelines_lock:
            pipeline = self._find_pipeline_by_id(pipeline_id)
            if pipeline is None:
                raise ValueError(f"Pipeline with id '{pipeline_id}' not found.")

            variant = self._find_variant_by_id(pipeline, variant_id)
            if variant is None:
                raise ValueError(
                    f"Variant '{variant_id}' not found in pipeline '{pipeline_id}'."
                )

            return deepcopy(variant)

    def _find_pipeline_by_id(self, pipeline_id: str) -> InternalPipeline | None:
        """Find a pipeline by its ID."""
        for pipeline in self.pipelines:
            if pipeline.id == pipeline_id:
                return pipeline
        return None

    def _find_variant_by_id(
        self, pipeline: InternalPipeline, variant_id: str
    ) -> InternalVariant | None:
        """
        Find a variant by its ID within a pipeline.

        Args:
            pipeline: The pipeline to search in.
            variant_id: The unique ID of the variant.

        Returns:
            InternalVariant if found, None otherwise.
        """
        for variant in pipeline.variants:
            if variant.id == variant_id:
                return variant
        return None

    def update_pipeline(
        self,
        pipeline_id: str,
        name: Optional[str] = None,
        description: Optional[str] = None,
        tags: Optional[List[str]] = None,
    ) -> InternalPipeline:
        """Update selected fields of an existing pipeline.

        Args:
            pipeline_id: ID of the pipeline to update.
            name: Optional new pipeline name.
            description: Optional new human-readable text describing what the pipeline does.
            tags: Optional list of tags.

        Returns:
            The updated :class:`InternalPipeline` instance.

        Raises:
            ValueError: If the pipeline with the given ID does not exist.
        """

        with self._pipelines_lock:
            pipeline = self._find_pipeline_by_id(pipeline_id)
            if pipeline is None:
                raise ValueError(f"Pipeline with id '{pipeline_id}' not found.")

            # Update fields if provided
            if name is not None:
                pipeline.name = name

            if description is not None:
                pipeline.description = description

            if tags is not None:
                pipeline.tags = tags

            # Update modified_at timestamp
            pipeline.modified_at = get_current_timestamp()

            self.logger.debug("Pipeline updated: %s", pipeline)
            return pipeline

    def delete_pipeline_by_id(self, pipeline_id: str):
        """
        Delete a pipeline by its ID.

        Args:
            pipeline_id: The unique ID of the pipeline to delete.

        Raises:
            ValueError: If pipeline with given ID is not found.
            ValueError: If pipeline is PREDEFINED (cannot be deleted).
        """
        with self._pipelines_lock:
            pipeline = self._find_pipeline_by_id(pipeline_id)
            if pipeline is None:
                raise ValueError(f"Pipeline with id '{pipeline_id}' not found.")

            if pipeline.source == InternalPipelineSource.PREDEFINED:
                raise ValueError(f"Cannot delete PREDEFINED pipeline '{pipeline_id}'.")

            self.pipelines.remove(pipeline)
            self.logger.debug(f"Pipeline deleted: {pipeline}")

    def load_predefined_pipelines(self):
        """
        Load predefined pipelines from configuration files.

        For each pipeline:
        * Parse each variant's pipeline_description from variants field
        * Generate advanced and simple graphs for each variant
        * Set read_only=true for all variants of predefined pipelines
        * Set created_at and modified_at timestamps
        * Load thumbnail from file if specified and valid
        * Validate that name is non-empty
        * Validate that variant names and pipeline descriptions are non-empty

        Returns:
            list[InternalPipeline]: List of predefined pipelines with both graph views.

        Raises:
            ValueError: If name, variant name, or variant pipeline_description is empty.
        """
        predefined_pipelines = []

        # Get the pipelines directory for resolving relative thumbnail paths
        pipelines_base_path = PipelineLoader.get_pipelines_directory()

        for config_path in PipelineLoader.list():
            config = PipelineLoader.config(config_path)

            pipeline_name = config.get("name", "").strip()
            if not pipeline_name:
                raise ValueError(
                    f"Pipeline name cannot be empty in config: {config_path}"
                )

            pipeline_description = config.get("definition", "")
            # Description can be empty, no validation needed

            # Set timestamps for predefined pipelines
            current_time = get_current_timestamp()

            variants_config = config.get("variants", [])
            variants_list = []

            # Collect existing variant IDs for collision check
            existing_variant_ids: List[str] = []

            # Parse each variant
            for variant_config in variants_config:
                variant_name = variant_config.get("name", "").strip()
                if not variant_name:
                    raise ValueError(
                        f"Variant name cannot be empty in pipeline '{pipeline_name}'"
                    )

                variant_pipeline_desc = variant_config.get(
                    "pipeline_description", ""
                ).strip()
                if not variant_pipeline_desc:
                    raise ValueError(
                        f"Variant pipeline_description cannot be empty for variant '{variant_name}' in pipeline '{pipeline_name}'"
                    )

                # Parse variant pipeline description into advanced graph
                variant_graph = Graph.from_pipeline_description(variant_pipeline_desc)

                # Generate simple view for variant
                variant_simple_graph = variant_graph.to_simple_view()

                # Generate variant ID from variant name
                variant_id = generate_unique_id(variant_name, existing_variant_ids)
                existing_variant_ids.append(variant_id)

                variants_list.append(
                    InternalVariant(
                        id=variant_id,
                        name=variant_name,
                        read_only=True,  # All predefined variants are read-only
                        pipeline_graph=variant_graph,
                        pipeline_graph_simple=variant_simple_graph,
                        created_at=current_time,
                        modified_at=current_time,
                    )
                )

            # Read tags from config, default to empty list
            tags = config.get("tags", [])
            if not isinstance(tags, list):
                tags = []

            # Load thumbnail if specified, using pipelines directory as base path
            thumbnail_path = config.get("thumbnail", "")
            thumbnail_base64 = load_thumbnail_as_base64(
                thumbnail_path, pipeline_name, base_path=pipelines_base_path
            )

            # Get existing pipeline IDs for collision check
            existing_pipeline_ids = [p.id for p in predefined_pipelines]

            # Generate pipeline ID from pipeline name
            pipeline_id = generate_unique_id(pipeline_name, existing_pipeline_ids)

            predefined_pipelines.append(
                InternalPipeline(
                    id=pipeline_id,
                    name=pipeline_name,
                    description=pipeline_description,
                    source=InternalPipelineSource.PREDEFINED,
                    tags=tags,
                    variants=variants_list,
                    thumbnail=thumbnail_base64,
                    created_at=current_time,
                    modified_at=current_time,
                )
            )
        self.logger.debug("Loaded predefined pipelines: %s", predefined_pipelines)
        return predefined_pipelines

    def build_pipeline_command(
        self,
        pipeline_performance_specs: list[InternalPipelinePerformanceSpec],
        execution_config: InternalExecutionConfig,
        job_id: str,
    ) -> PipelineCommand:
        """
        Build a complete executable GStreamer pipeline command from internal specifications.

        This method takes internal pipeline specifications with resolved Graph objects and
        stream counts, and constructs a complete GStreamer command line that can be executed
        to run all specified pipelines with all their streams.

        Creates a job output directory structure:
            OUTPUT_VIDEO_DIR/<timestamp>_<job_id>/<pipeline_id>/

        Each pipeline's output files (intermediate and main) are placed in its own directory.

        Args:
            pipeline_performance_specs: List of InternalPipelinePerformanceSpec with
                resolved pipeline_id, pipeline_name, pipeline_graph (as Graph object), and streams.
            execution_config: InternalExecutionConfig for output generation and runtime limits.
            job_id: Unique job identifier used for directory naming and stream names.

        Returns:
            A :class:`PipelineCommand` bundle carrying the complete
            pipeline string plus all per-pipeline side outputs
            (video / live-stream / metadata / stream identifiers). See
            :class:`PipelineCommand` for field semantics.

            Note: live_stream_urls will be empty for density tests since they do not
            support live-streaming output mode. The caller is responsible for validating
            that output_mode=live_stream is not used with density tests.

        Raises:
            ValueError: If execution_config.max_runtime is negative.
            ValueError: If output_mode=file is combined with max_runtime>0.
        """
        # Initialize video encoder helper
        video_encoder = VideoEncoder()

        # Validate max_runtime
        if execution_config.max_runtime < 0:
            raise ValueError(
                f"Invalid max_runtime value: {execution_config.max_runtime}. "
                "Negative values are not allowed."
            )

        # Validate output_mode + max_runtime combination
        if (
            execution_config.output_mode == InternalOutputMode.FILE
            and execution_config.max_runtime > 0
        ):
            raise ValueError(
                "Invalid execution_config: output_mode='file' cannot be combined with max_runtime > 0. "
                "File output does not support looping. Use max_runtime=0 to run until EOS, "
                "or use output_mode='disabled' or 'live_stream' for time-limited execution."
            )

        # Create job output directories for videos and metadata using job_id and timestamp for uniqueness
        job_dir_name = f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{job_id}"
        video_job_dir = make_output_dir(OUTPUT_VIDEO_DIR, job_dir_name)
        metadata_job_dir = make_output_dir(METADATA_DIR, job_dir_name)

        pipeline_parts = []
        video_output_paths: dict[str, str] = {}
        live_stream_urls: dict[str, str] = {}
        metadata_file_paths: dict[str, list[str]] = {}
        output_subpipeline: str | None = None

        # Per-pipeline collection of streams. Each entry is a list of
        # `InternalStreamInfo` objects — one per stream of that pipeline,
        # in creation order. We keep source/sink names separate here
        # because external tracers (latency_tracer) report them as
        # separate tokens; the combined `stream_id` is exposed via the
        # computed `InternalStreamInfo.stream_id` property and used as a
        # key in the job's `latency_tracer_metrics` map.
        streams_per_pipeline: dict[str, list[InternalStreamInfo]] = {}

        # Determine if we need looping behavior based on max_runtime
        # Looping is only supported for disabled and live_stream modes
        needs_looping = (
            execution_config.max_runtime > 0
            and execution_config.output_mode != InternalOutputMode.FILE
        )

        for pipeline_index, spec in enumerate(pipeline_performance_specs):
            # Use resolved pipeline information from internal spec
            pipeline_id = spec.pipeline_id
            pipeline_name = spec.pipeline_name
            base_graph = spec.pipeline_graph.unify_model_instance_ids()

            # Validate camera sources (rtspsrc, v4l2src), if present, are followed by decodebin3
            base_graph.validate_camera_sources_followed_by_decodebin3()

            # Validate pipeline has gvametapublish when metadata publishing is enabled
            if (
                execution_config.metadata_mode != InternalMetadataMode.DISABLED
                and not base_graph.has_gvametapublish()
            ):
                raise ValueError(
                    f"Metadata generation is enabled, but the pipeline does not contain any gvametapublish element. "
                    f"Please add a gvametapublish element to the pipeline '{pipeline_name}' (id: '{pipeline_id}') definition to enable metadata output."
                )

            # Apply RTSP credentials and settings to rtspsrc nodes
            base_graph = base_graph.apply_rtsp_connection_settings()

            # Create output directories for this pipeline's video and metadata outputs
            video_pipeline_dir = make_output_dir(video_job_dir, pipeline_id)
            metadata_pipeline_dir = make_output_dir(metadata_job_dir, pipeline_id)

            # Store the pipeline directory path for later video file collection
            video_output_paths[pipeline_id] = video_pipeline_dir

            # Replace decodebin3 with parsebin + specific decoder based on input codec and target device
            if base_graph.has_decodebin3():
                codec = base_graph.determine_input_codec()
                target_device = base_graph.get_target_device()
                base_graph = base_graph.apply_decodebin3_replacement(
                    codec, target_device
                )

            # Apply looping modifications if needed
            if needs_looping:
                base_graph = base_graph.apply_looping_modifications()

            output_mode = execution_config.output_mode

            # Prepare main video output subpipeline if output is enabled (file or live stream)
            if output_mode != InternalOutputMode.DISABLED:
                # Retrieve recommended encoder device
                encoder_device = base_graph.get_recommended_encoder_device()

                # Create output subpipeline based on output mode (file or live stream)
                if output_mode == InternalOutputMode.FILE:
                    output_subpipeline = video_encoder.create_video_output_subpipeline(
                        video_pipeline_dir, encoder_device
                    )
                elif output_mode == InternalOutputMode.LIVE_STREAM:
                    output_subpipeline, stream_url = (
                        video_encoder.create_live_stream_output_subpipeline(
                            pipeline_id, encoder_device, job_id
                        )
                    )
                    live_stream_urls[pipeline_id] = stream_url

            # Build pipeline parts for all streams of this pipeline specification
            for stream_index in range(spec.streams):
                graph_instance = deepcopy(base_graph)

                # Prepare intermediate output sinks per stream
                graph_instance = graph_instance.prepare_intermediate_output_sinks(
                    video_pipeline_dir, stream_index
                )

                if output_mode != InternalOutputMode.DISABLED and stream_index == 0:
                    # Create a placeholder node for the main output sink to be replaced later
                    graph_instance = graph_instance.prepare_main_output_placeholder()

                # Inject metadata file paths into gvametapublish elements for metadata streaming
                if (
                    execution_config.metadata_mode == InternalMetadataMode.FILE
                    and stream_index == 0
                ):
                    paths = graph_instance.inject_metadata_file_paths(
                        metadata_pipeline_dir
                    )
                    if paths:
                        metadata_file_paths[pipeline_id] = paths

                # Remove gvawatermark nodes when all sinks are fakesink (no real video output)
                graph_instance = graph_instance.strip_watermark_if_all_sinks_are_fake()

                # Assign explicit, unique element names to the main-branch
                # source and sink BEFORE the generic "unify_all_element_names"
                # rename. This lets us build a distinct `stream_id` per
                # running stream that external tracers (latency_tracer) can
                # use to correlate their rows. Tee-branch sinks are
                # intentionally left untouched by this method.
                (
                    graph_instance,
                    stream_source_name,
                    stream_sink_name,
                    _,
                ) = graph_instance.apply_stream_identifiers(
                    pipeline_index, stream_index
                )

                graph_instance = graph_instance.unify_all_element_names(
                    pipeline_index, stream_index
                )

                # `unify_all_element_names` appends `_{pipeline_index}_{stream_index}`
                # to every `name`, so the effective source/sink names used in
                # the final pipeline string are the suffixed versions. We
                # recompute them here so downstream logic (output subpipeline
                # injection below, and the InternalStreamInfo record for this
                # stream) uses the exact final names.
                final_source_name = (
                    f"{stream_source_name}_{pipeline_index}_{stream_index}"
                )
                final_sink_name = f"{stream_sink_name}_{pipeline_index}_{stream_index}"

                # Record this stream with its final, run-unique source/sink
                # names. These names are exactly what the GStreamer
                # subprocess sees, and therefore exactly what external
                # tracers (latency_tracer) will report back to us.
                streams_per_pipeline.setdefault(pipeline_id, []).append(
                    InternalStreamInfo(
                        source_name=final_source_name,
                        sink_name=final_sink_name,
                    )
                )

                unique_pipeline_str = graph_instance.to_pipeline_description()

                if output_mode != InternalOutputMode.DISABLED and stream_index == 0:
                    # Replace the main output placeholder with the actual output subpipeline (file or live stream)
                    if OUTPUT_PLACEHOLDER not in unique_pipeline_str:
                        raise ValueError(
                            f"Pipeline '{pipeline_name}' (id: {pipeline_id}) is missing required output sink. "
                            f"Please add 'fakesink name=default_output_sink' at the end of the pipeline definition."
                        )
                    if output_subpipeline is None:
                        raise ValueError(
                            "Output subpipeline was not created as expected."
                        )
                    # Inject the explicit sink name into the output subpipeline
                    # so the terminal sink element (filesink / rtspclientsink)
                    # carries a deterministic, stream-unique GStreamer name.
                    # This preserves the stream_id correlation even when the
                    # main sink is replaced by the encoder + writer subpipeline.
                    output_subpipeline_with_name = (
                        f"{output_subpipeline} name={final_sink_name}"
                    )
                    unique_pipeline_str = unique_pipeline_str.replace(
                        OUTPUT_PLACEHOLDER, output_subpipeline_with_name
                    )

                pipeline_parts.append(unique_pipeline_str)

        # TODO: Must be removed once the live metrics stream is in place
        # Diagnostic summary so the stream-to-tracer correlation can be
        # verified from the logs. Kept at INFO because it is printed once
        # per run (not per sample).
        if streams_per_pipeline:
            lines = ["Stream identifiers per pipeline:"]
            for pid, infos in streams_per_pipeline.items():
                lines.append(f"  pipeline '{pid}' ({len(infos)} stream(s)):")
                for info in infos:
                    lines.append(f"    - {info.stream_id}")
            logger.info("\n".join(lines))

        return PipelineCommand(
            command=" ".join(pipeline_parts),
            video_output_paths=video_output_paths,
            live_stream_urls=live_stream_urls,
            metadata_file_paths=metadata_file_paths,
            streams_per_pipeline=streams_per_pipeline,
        )

    def add_variant(
        self,
        pipeline_id: str,
        name: str,
        pipeline_graph: Graph,
        pipeline_graph_simple: Graph,
    ) -> InternalVariant:
        """
        Add a new variant to an existing pipeline.

        The method:
        * Trims and validates variant name (raises ValueError if empty after trimming)
        * Generates a unique variant ID from trimmed name
        * Creates variant with read_only=false
        * Sets created_at and modified_at timestamps for variant
        * Updates pipeline's modified_at timestamp
        * Adds variant to the pipeline's variants list

        Args:
            pipeline_id: ID of the pipeline to add variant to.
            name: Variant name (trimmed, must be non-empty after trimming).
            pipeline_graph: Advanced graph representation as Graph object.
            pipeline_graph_simple: Simplified graph representation as Graph object.

        Returns:
            InternalVariant: Created variant with generated ID and timestamps.

        Raises:
            ValueError: If pipeline with given ID is not found.
            ValueError: If variant name is empty after trimming.
        """
        with self._pipelines_lock:
            pipeline = self._find_pipeline_by_id(pipeline_id)
            if pipeline is None:
                raise ValueError(f"Pipeline with id '{pipeline_id}' not found.")

            # Validate and trim variant name
            trimmed_name = self._validate_and_trim_variant_name(name)

            # Get existing variant IDs for collision check
            existing_variant_ids = [v.id for v in pipeline.variants]

            # Generate new variant ID from trimmed variant name
            variant_id = generate_unique_id(trimmed_name, existing_variant_ids)

            # Set timestamps
            current_time = get_current_timestamp()

            # Create new variant with read_only=false for user-created variants
            new_variant = InternalVariant(
                id=variant_id,
                name=trimmed_name,
                read_only=False,
                pipeline_graph=pipeline_graph,
                pipeline_graph_simple=pipeline_graph_simple,
                created_at=current_time,
                modified_at=current_time,
            )

            # Add variant to pipeline
            pipeline.variants.append(new_variant)

            # Update pipeline's modified_at timestamp
            pipeline.modified_at = current_time

            self.logger.debug(f"Variant {variant_id} added to pipeline {pipeline_id}")
            return new_variant

    def delete_variant(self, pipeline_id: str, variant_id: str) -> None:
        """
        Delete a variant from a pipeline.

        The method:
        * Validates that pipeline exists
        * Validates that variant exists
        * Checks that variant is not read-only
        * Checks that it's not the last variant
        * Removes variant from pipeline
        * Updates pipeline's modified_at timestamp

        Args:
            pipeline_id: ID of the pipeline containing the variant.
            variant_id: ID of the variant to delete.

        Raises:
            ValueError: If pipeline is not found.
            ValueError: If variant is not found.
            ValueError: If variant is read-only (cannot delete).
            ValueError: If variant is the last one in pipeline (cannot delete).
        """
        with self._pipelines_lock:
            pipeline = self._find_pipeline_by_id(pipeline_id)
            if pipeline is None:
                raise ValueError(f"Pipeline with id '{pipeline_id}' not found.")

            # Find the variant using helper method
            variant_to_delete = self._find_variant_by_id(pipeline, variant_id)

            if variant_to_delete is None:
                raise ValueError(
                    f"Variant '{variant_id}' not found in pipeline '{pipeline_id}'."
                )

            # Check if variant is read-only
            if variant_to_delete.read_only:
                raise ValueError(f"Cannot delete read-only variant '{variant_id}'.")

            # Check if this is the last variant
            if len(pipeline.variants) == 1:
                raise ValueError(
                    f"Cannot delete variant '{variant_id}' as it is the last variant in pipeline '{pipeline_id}'."
                )

            # Delete the variant
            pipeline.variants.remove(variant_to_delete)

            # Update pipeline's modified_at timestamp
            pipeline.modified_at = get_current_timestamp()

            self.logger.debug(
                f"Variant {variant_id} deleted from pipeline {pipeline_id}"
            )

    def update_variant(
        self,
        pipeline_id: str,
        variant_id: str,
        name: Optional[str] = None,
        pipeline_graph: Optional[Graph] = None,
        pipeline_graph_simple: Optional[Graph] = None,
    ) -> InternalVariant:
        """
        Update an existing variant.

        The method:
        * Validates that pipeline exists
        * Validates that variant exists and is not read-only
        * If name is provided, trims and validates it (raises ValueError if empty after trimming)
        * Ensures only one of pipeline_graph or pipeline_graph_simple is provided
        * For pipeline_graph: validates and regenerates simple view using validate_and_convert_advanced_to_simple()
        * For pipeline_graph_simple: validates and merges changes using validate_and_convert_simple_to_advanced()
        * Updates provided fields
        * Updates variant's modified_at timestamp
        * Updates pipeline's modified_at timestamp
        * Returns updated variant

        Args:
            pipeline_id: ID of the pipeline containing the variant.
            variant_id: ID of the variant to update.
            name: Optional new variant name (trimmed, must be non-empty after trimming if provided).
            pipeline_graph: Optional new advanced graph as Graph object. When provided, simple view
                is auto-generated from it. Mutually exclusive with pipeline_graph_simple.
            pipeline_graph_simple: Optional modified simple graph as Graph object with property changes only.
                When provided, changes are merged into advanced view using validate_and_convert_simple_to_advanced(),
                and both views are regenerated.
                Structural changes (add/remove nodes or edges) are not allowed.
                Mutually exclusive with pipeline_graph.

        Returns:
            InternalVariant: Updated variant object.

        Raises:
            ValueError: If pipeline is not found.
            ValueError: If variant is not found.
            ValueError: If variant is read-only (cannot update).
            ValueError: If name is empty after trimming (when provided).
            ValueError: If both pipeline_graph and pipeline_graph_simple are provided.
            ValueError: If pipeline_graph cannot be converted to valid GStreamer string.
            ValueError: If pipeline_graph_simple contains structural changes.
        """
        with self._pipelines_lock:
            pipeline = self._find_pipeline_by_id(pipeline_id)
            if pipeline is None:
                raise ValueError(f"Pipeline with id '{pipeline_id}' not found.")

            # Find the variant using helper method
            variant_to_update = self._find_variant_by_id(pipeline, variant_id)

            if variant_to_update is None:
                raise ValueError(
                    f"Variant '{variant_id}' not found in pipeline '{pipeline_id}'."
                )

            # Check if variant is read-only
            if variant_to_update.read_only:
                raise ValueError(f"Cannot update read-only variant '{variant_id}'.")

            # Validate mutual exclusivity of graph updates
            if pipeline_graph is not None and pipeline_graph_simple is not None:
                raise ValueError(
                    "Cannot update both 'pipeline_graph' and 'pipeline_graph_simple' at the same time. Please provide only one."
                )

            # Update name if provided (validate and trim)
            if name is not None:
                trimmed_name = self._validate_and_trim_variant_name(name)
                variant_to_update.name = trimmed_name

            # Update pipeline_graph (advanced view)
            if pipeline_graph is not None:
                # Validate and generate simple view
                simple_graph = self.validate_and_convert_advanced_to_simple(
                    pipeline_graph
                )

                # Update advanced view
                variant_to_update.pipeline_graph = pipeline_graph

                # Update simple view
                variant_to_update.pipeline_graph_simple = simple_graph

                self.logger.debug(
                    f"Updated variant {variant_id} with new pipeline_graph and auto-generated simple view"
                )

            # Update pipeline_graph_simple (simple view with property changes)
            elif pipeline_graph_simple is not None:
                # Validate and generate advanced view
                updated_advanced_graph = self.validate_and_convert_simple_to_advanced(
                    variant_to_update, pipeline_graph_simple
                )

                # Update both views
                variant_to_update.pipeline_graph = updated_advanced_graph

                # Regenerate simple view from updated advanced view
                new_simple_graph = updated_advanced_graph.to_simple_view()
                variant_to_update.pipeline_graph_simple = new_simple_graph

                self.logger.debug(
                    f"Updated variant {variant_id} with changes from pipeline_graph_simple and regenerated both views"
                )

            # Update timestamps
            current_time = get_current_timestamp()
            variant_to_update.modified_at = current_time
            pipeline.modified_at = current_time

            self.logger.debug(f"Variant {variant_id} updated in pipeline {pipeline_id}")
            return variant_to_update

    def validate_and_convert_advanced_to_simple(self, pipeline_graph: Graph) -> Graph:
        """
        Validate advanced graph and convert it to simple graph.

        This method validates that the advanced graph can be converted to a valid
        GStreamer pipeline string, then generates the simplified view.

        Does not modify the variant - only performs validation and conversion.

        Args:
            pipeline_graph: Advanced graph (Graph object) to validate and convert.

        Returns:
            Graph: Simplified graph generated from the advanced graph.

        Raises:
            ValueError: If graph has no nodes or edges.
            ValueError: If graph cannot be converted to valid GStreamer pipeline string.
        """
        # Validate that graph has nodes and edges
        if not pipeline_graph.nodes or not pipeline_graph.edges:
            raise ValueError(
                "Field 'pipeline_graph' must contain at least one node and one edge."
            )

        try:
            # Validate by converting to pipeline description
            _ = pipeline_graph.to_pipeline_description()
        except Exception as e:
            raise ValueError(
                f"Invalid pipeline_graph: cannot convert to valid GStreamer pipeline string. Error: {str(e)}"
            )

        # Generate simple view from advanced view
        simple_graph = pipeline_graph.to_simple_view()

        return simple_graph

    def validate_and_convert_simple_to_advanced(
        self, variant: InternalVariant, pipeline_graph_simple: Graph
    ) -> Graph:
        """
        Validate simple graph changes and merge them into advanced graph.

        This method validates that the simple graph contains only property changes
        (no structural changes like adding/removing nodes or edges), then applies
        those changes to the variant's current advanced graph.

        Does not modify the variant - only performs validation and conversion.

        Args:
            variant: The variant containing the current advanced and simple graphs.
            pipeline_graph_simple: Modified simple graph (Graph object) with property changes.

        Returns:
            Graph: Updated advanced graph with changes from simple graph applied.

        Raises:
            ValueError: If graph has no nodes or edges.
            ValueError: If simple graph contains structural changes (nodes/edges added/removed).
            ValueError: If updated advanced graph cannot be converted to valid GStreamer pipeline.
        """
        # Validate that graph has nodes and edges
        if not pipeline_graph_simple.nodes or not pipeline_graph_simple.edges:
            raise ValueError(
                "Field 'pipeline_graph_simple' must contain at least one node and one edge."
            )

        # Load current advanced graph
        current_advanced_graph = variant.pipeline_graph

        # Load current simple graph (original, before user modifications)
        current_simple_graph = variant.pipeline_graph_simple

        # Apply simple view changes to advanced graph
        # This validates that only property changes are made, no structural changes
        try:
            updated_advanced_graph = Graph.apply_simple_view_changes(
                pipeline_graph_simple,
                current_simple_graph,
                current_advanced_graph,
            )
        except ValueError as e:
            # Re-raise validation errors from apply_simple_view_changes
            raise ValueError(f"Invalid pipeline_graph_simple: {str(e)}")

        # Validate updated advanced graph can be converted to pipeline description
        try:
            _ = updated_advanced_graph.to_pipeline_description()
        except Exception as e:
            raise ValueError(
                f"Updated pipeline graph is invalid after applying simple view changes. Error: {str(e)}"
            )

        return updated_advanced_graph

    def _validate_and_trim_variant_name(self, name: str) -> str:
        """
        Validate and trim variant name.

        Trims whitespace from the name and validates it is not empty.

        Args:
            name: Variant name to validate and trim.

        Returns:
            Trimmed variant name.

        Raises:
            ValueError: If name is empty after trimming.
        """
        trimmed_name = name.strip()
        if not trimmed_name:
            raise ValueError("Variant name cannot be empty.")
        return trimmed_name

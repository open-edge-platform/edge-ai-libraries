from copy import deepcopy
import logging
import sys
import threading
from typing import Optional, List

from pipelines.loader import PipelineLoader
from video_encoder import get_video_encoder
from utils import make_tee_names_unique, generate_unique_id
from graph import Graph
from api.api_schemas import (
    PipelineType,
    PipelineSource,
    Pipeline,
    PipelineDefinition,
    PipelinePerformanceSpec,
    VideoOutputConfig,
    PipelineGraph,
    PipelineParameters,
)

logger = logging.getLogger("pipeline_manager")

# Singleton instance for PipelineManager
_pipeline_manager_instance: Optional["PipelineManager"] = None


def get_pipeline_manager() -> "PipelineManager":
    """
    Returns the singleton instance of PipelineManager.
    If it cannot be created, logs an error and exits the application.
    """
    global _pipeline_manager_instance
    if _pipeline_manager_instance is None:
        try:
            _pipeline_manager_instance = PipelineManager()
        except Exception as e:
            logger.error(f"Failed to initialize PipelineManager: {e}")
            sys.exit(1)
    return _pipeline_manager_instance


class PipelineManager:
    def __init__(self):
        self.logger = logging.getLogger("PipelineManager")
        # Shared lock protecting access to pipelines
        self.lock = threading.Lock()
        # List of pipelines managed by this instance
        self.pipelines = self.load_predefined_pipelines()
        # Video encoder instance used by pipelines
        self.video_encoder = get_video_encoder()

    def add_pipeline(self, new_pipeline: PipelineDefinition):
        with self.lock:
            # Enforce strictly increasing, consecutive pipeline versions per name.
            self._ensure_next_version(new_pipeline.name, new_pipeline.version)

            # Generate ID with "pipeline" prefix
            pipeline_id = generate_unique_id("pipeline")

            pipeline_graph = Graph.from_pipeline_description(
                new_pipeline.pipeline_description
            ).to_dict()

            pipeline = Pipeline(
                id=pipeline_id,
                name=new_pipeline.name,
                version=new_pipeline.version,
                description=new_pipeline.description,
                source=new_pipeline.source,
                type=new_pipeline.type,
                pipeline_graph=PipelineGraph.model_validate(pipeline_graph),
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
        with self.lock:
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
        with self.lock:
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
        parameters: Optional[PipelineParameters] = None,
    ) -> Pipeline:
        """Update selected fields of an existing pipeline.

        Args:
            pipeline_id: ID of the pipeline to update.
            name: Optional new pipeline name.
            description: Optional new human-readable description.
            pipeline_graph: Optional new pipeline graph representation.
            parameters: Optional new pipeline parameters.

        Returns:
            The updated :class:`Pipeline` instance.

        Raises:
            ValueError: If the pipeline with the given ID does not exist.
        """

        with self.lock:
            pipeline = self._find_pipeline_by_id(pipeline_id)
            if pipeline is None:
                raise ValueError(f"Pipeline with id '{pipeline_id}' not found.")

            # Update fields if provided
            if name is not None:
                pipeline.name = name

            if description is not None:
                pipeline.description = description

            # If a new pipeline graph is provided, validate and replace the existing one
            if pipeline_graph is not None:
                # Validate the pipeline graph by converting it to a pipeline description
                pipeline_description = Graph.from_dict(
                    pipeline_graph.model_dump()
                ).to_pipeline_description()
                if not pipeline_description:
                    raise ValueError("Provided pipeline graph is invalid.")

                pipeline.pipeline_graph = pipeline_graph

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
        with self.lock:
            pipeline = self._find_pipeline_by_id(pipeline_id)
            if pipeline is not None:
                self.pipelines.remove(pipeline)
                self.logger.debug(f"Pipeline deleted: {pipeline}")
            else:
                raise ValueError(f"Pipeline with id '{pipeline_id}' not found.")

    def load_predefined_pipelines(self):
        predefined_pipelines = []
        for pipeline_name in PipelineLoader.list():
            config = PipelineLoader.config(pipeline_name)

            pipeline_description = config.get("pipeline_description", "")
            pipeline_graph = Graph.from_pipeline_description(
                pipeline_description
            ).to_dict()

            predefined_pipelines.append(
                Pipeline(
                    id=generate_unique_id("pipeline"),
                    name=config.get("name", "unnamed-pipeline"),
                    version=int(config.get("version", 1)),
                    description=config.get("definition", ""),
                    source=PipelineSource.PREDEFINED,
                    type=PipelineType.GSTREAMER,
                    pipeline_graph=PipelineGraph.model_validate(pipeline_graph),
                    parameters=None,
                )
            )
        self.logger.debug("Loaded predefined pipelines: %s", predefined_pipelines)
        return predefined_pipelines

    def build_pipeline_command(
        self,
        pipeline_performance_specs: list[PipelinePerformanceSpec],
        video_config: VideoOutputConfig,
    ) -> tuple[str, dict[str, List[str]]]:
        """
        Build a complete GStreamer pipeline command from run specifications.

        Args:
            pipeline_performance_specs: List of PipelinePerformanceSpec defining pipelines and streams.

        Returns:
            str: Complete GStreamer pipeline command string.

        Raises:
            ValueError: If any pipeline in specs is not found.
        """
        pipeline_parts = []
        video_output_paths: dict[str, List[str]] = {}

        for pipeline_index, run_spec in enumerate(pipeline_performance_specs):
            # Retrieve the pipeline definition by ID
            pipeline = self.get_pipeline_by_id(run_spec.id)

            # Convert pipeline graph dict back to Graph object
            graph = Graph.from_dict(pipeline.pipeline_graph.model_dump())

            # Retrieve input video filenames from the graph
            input_video_filenames = graph.get_input_video_filenames()

            # Prepare intermediate output sinks and get updated graph and output paths
            graph, output_paths = graph.prepare_output_sinks()

            # Store output paths for this pipeline
            video_output_paths[pipeline.id] = output_paths

            # Extract the pipeline description string
            base_pipeline_str = graph.to_pipeline_description()

            # Create one pipeline instance per stream with unique tee names
            for stream_index in range(run_spec.streams):
                unique_pipeline_str = make_tee_names_unique(
                    base_pipeline_str, pipeline_index, stream_index
                )

                # Handle final video output if enabled
                if video_config.enabled and stream_index == 0:
                    unique_pipeline_str, generated_paths = (
                        self.video_encoder.replace_fakesink_with_video_output(
                            pipeline.id,
                            unique_pipeline_str,
                            video_config.encoder_device,
                            input_video_filenames,
                        )
                    )
                    video_output_paths[pipeline.id].extend(generated_paths)

                pipeline_parts.append(unique_pipeline_str)

        return " ".join(pipeline_parts), video_output_paths

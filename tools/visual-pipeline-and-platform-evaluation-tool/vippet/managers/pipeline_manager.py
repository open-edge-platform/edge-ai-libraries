import logging

from gstpipeline import PipelineLoader
from api.api_schemas import PipelineType, Pipeline, PipelineDefinition, LaunchConfig
from explore import GstInspector
from convert import string_to_config

gst_inspector = GstInspector()


class PipelineManager:
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.pipelines = self.load_predefined_pipelines()

    def add_pipeline(self, new_pipeline: PipelineDefinition):
        if self.pipeline_exists(new_pipeline.name, new_pipeline.version):
            raise ValueError(
                f"Pipeline with name '{new_pipeline.name}' and version '{new_pipeline.version}' already exists."
            )

        cfg = string_to_config(new_pipeline.launch_string)

        pipeline = Pipeline(
            name=new_pipeline.name,
            version=new_pipeline.version,
            description=new_pipeline.description,
            type=new_pipeline.type,
            launch_config=LaunchConfig.model_validate(cfg),
            parameters=new_pipeline.parameters,
        )

        self.pipelines.append(pipeline)
        self.logger.debug(f"Pipeline added: {pipeline}")

    def get_pipelines(self) -> list[Pipeline]:
        return self.pipelines

    def get_pipeline_by_name_and_version(self, name: str, version: str) -> Pipeline:
        pipeline = self._find_pipeline(name, version)
        if pipeline is not None:
            return pipeline
        raise ValueError(
            f"Pipeline with name '{name}' and version '{version}' not found."
        )

    def pipeline_exists(self, name: str, version: str) -> bool:
        return self._find_pipeline(name, version) is not None

    def _find_pipeline(self, name: str, version: str) -> Pipeline | None:
        for pipeline in self.pipelines:
            if pipeline.name == name and pipeline.version == version:
                return pipeline
        return None

    def load_predefined_pipelines(self):
        predefined_pipelines = []
        for pipeline_name in PipelineLoader.list():
            pipeline_gst, config = PipelineLoader.load(pipeline_name)
            launch_string = pipeline_gst.get_default_gst_launch(
                gst_inspector.get_elements()
            )
            cfg = string_to_config(launch_string)

            predefined_pipelines.append(
                Pipeline(
                    name="predefined_pipelines",
                    version=config.get("metadata", {}).get(
                        "classname", "Unnamed Pipeline"
                    ),
                    description=config.get("name", "Unnamed Pipeline"),
                    type=PipelineType.GSTREAMER,
                    launch_config=LaunchConfig.model_validate(cfg),
                    parameters=None,
                )
            )
        self.logger.debug("Loaded predefined pipelines: %s", predefined_pipelines)
        return predefined_pipelines

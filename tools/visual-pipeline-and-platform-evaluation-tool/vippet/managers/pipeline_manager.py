import logging

from gstpipeline import PipelineLoader
from api.api_schemas import PipelineType, Pipeline, PipelineDefinition


class PipelineManager:
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.pipelines = self.load_predefined_pipelines()

    def add_pipeline(self, new_pipeline: PipelineDefinition):
        if self.pipeline_exists(new_pipeline.name, new_pipeline.version):
            raise ValueError(
                f"Pipeline with name '{new_pipeline.name}' and version '{new_pipeline.version}' already exists."
            )

        pipeline_description = {
            "converted_pipeline_description": new_pipeline.pipeline_description
        }  # TODO: Convert pipeline_description to pipeline_graph in JSON format

        pipeline = Pipeline(
            name=new_pipeline.name,
            version=new_pipeline.version,
            description=new_pipeline.description,
            type=new_pipeline.type,
            pipeline_graph=pipeline_description,
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
            config = PipelineLoader.config(pipeline_name)

            pipeline_description = config.get("pipeline_description", "")
            pipeline_graph = {
                "converted_pipeline_description": pipeline_description
            }  # TODO: Convert pipeline_description to pipeline_graph in JSON format

            predefined_pipelines.append(
                Pipeline(
                    name="predefined_pipelines",
                    version=config.get("name", "UnnamedPipeline"),
                    description=config.get("display_name", "Unnamed Pipeline"),
                    type=PipelineType.GSTREAMER,
                    pipeline_graph=pipeline_graph,
                    parameters=None,
                )
            )
        self.logger.debug("Loaded predefined pipelines: %s", predefined_pipelines)
        return predefined_pipelines

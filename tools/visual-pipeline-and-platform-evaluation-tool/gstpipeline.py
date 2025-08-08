import importlib
import os
from pathlib import Path
from typing import Dict, List, Tuple

import yaml


class GstPipeline:
    def __init__(self):
        pass

    def pipeline(self) -> str:
        if not hasattr(self, "_pipeline"):
            raise ValueError("Pipeline is not defined")

        return self._pipeline

    def evaluate(
        self,
        constants: dict,
        parameters: dict,
        regular_channels: int,
        inference_channels: int,
        elements: list,
    ) -> str:
        raise NotImplementedError(
            "The evaluate method must be implemented by subclasses"
        )

    def diagram(self) -> Path:
        if not hasattr(self, "_diagram"):
            raise ValueError("Diagram is not defined")

        return self._diagram

    def bounding_boxes(self) -> List:
        if not hasattr(self, "_bounding_boxes"):
            raise ValueError("Bounding Boxes is not defined")

        return self._bounding_boxes


class PipelineLoader:
    @staticmethod
    def _validate_pipeline_name(pipeline_name: str, pipeline_path: str = "pipelines") -> None:
        """Validate pipeline_name and raise ValueError with details if invalid."""
        if (
            not pipeline_name
            or "/" in pipeline_name
            or "\\" in pipeline_name
            or ".." in pipeline_name
            or Path(pipeline_name).is_absolute()
        ):
            raise ValueError(f"Invalid pipeline name: '{pipeline_name}'")
        valid_pipelines = PipelineLoader.list(pipeline_path)
        if pipeline_name not in valid_pipelines:
            raise ValueError(f"Pipeline '{pipeline_name}' not found in '{pipeline_path}'")

    @staticmethod
    def list(pipeline_path: str = "pipelines") -> List[str]:
        """Return available pipeline folder names (not display names)."""
        pipelines_dir = Path(pipeline_path)
        return [
            name.name
            for name in pipelines_dir.iterdir()
            if name.is_dir() and not name.name.startswith("_")
        ]

    @staticmethod
    def config(pipeline_name: str, pipeline_path: str = "pipelines") -> dict:
        """Return full config dict for a pipeline."""
        PipelineLoader._validate_pipeline_name(pipeline_name, pipeline_path)
        config_path = Path(pipeline_path) / pipeline_name / "config.yaml"
        # Validate that config_path is within the intended pipelines directory using realpath
        pipelines_dir_real = os.path.realpath(pipeline_path)
        config_path_real = os.path.realpath(str(config_path))
        if not config_path_real.startswith(pipelines_dir_real + os.sep):
            raise ValueError(f"Invalid pipeline name or path traversal detected for '{pipeline_name}'")
        if not os.path.isfile(config_path_real):
            raise FileNotFoundError(f"Config file for pipeline '{pipeline_name}' could not be resolved at {config_path}")
        # At this point, config_path_real is guaranteed to exist and be within pipelines_dir
        with open(config_path_real, "r", encoding="utf-8") as f:
            return yaml.safe_load(f.read())

    @staticmethod
    def load(pipeline_name: str, pipeline_path: str = "pipelines") ->  Tuple[GstPipeline, Dict]:
        """Load pipeline class and config, or just metadata.name"""
        PipelineLoader._validate_pipeline_name(pipeline_name, pipeline_path)
        config = PipelineLoader.config(pipeline_name, pipeline_path)
        classname = config.get("metadata", {}).get("classname")
        if not classname:
            raise ValueError(
                f"Pipeline '{pipeline_name}' does not have a classname defined in config.yaml"
            )

        # NOTE: This code always imports from the pipelines directory.
        module = importlib.import_module(f"pipelines.{pipeline_name}.pipeline")
        pipeline_cls = getattr(module, classname)
        return pipeline_cls(), config

import os
from pathlib import Path
from typing import List
import yaml


class PipelineLoader:
    @staticmethod
    def _validate_pipeline_name(
        pipeline_name: str, pipeline_path: str = "pipelines"
    ) -> None:
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
            raise ValueError(
                f"Pipeline '{pipeline_name}' not found in '{pipeline_path}'"
            )

    @staticmethod
    def list(pipeline_path: str = "pipelines") -> List[str]:
        """Return available predefined pipeline folder names (not display names)."""
        pipelines_dir = Path(pipeline_path)
        pipelines = [
            name.name
            for name in pipelines_dir.iterdir()
            if name.is_dir() and not name.name.startswith("_")
        ]
        return sorted(pipelines)

    @staticmethod
    def config(pipeline_name: str, pipeline_path: str = "pipelines") -> dict:
        """Return full config dict for a predefined pipeline."""
        PipelineLoader._validate_pipeline_name(pipeline_name, pipeline_path)
        config_path = Path(pipeline_path) / pipeline_name / "config.yaml"
        # Validate that config_path is within the intended pipelines directory using realpath
        pipelines_dir_real = os.path.realpath(pipeline_path)
        config_path_real = os.path.realpath(str(config_path))
        if not config_path_real.startswith(pipelines_dir_real + os.sep):
            raise ValueError(
                f"Invalid pipeline name or path traversal detected for '{pipeline_name}'"
            )
        if not os.path.isfile(config_path_real):
            raise FileNotFoundError(
                f"Config file for pipeline '{pipeline_name}' could not be resolved at {config_path}"
            )
        # At this point, config_path_real is guaranteed to exist and be within pipelines_dir
        with open(config_path_real, "r", encoding="utf-8") as f:
            return yaml.safe_load(f.read())

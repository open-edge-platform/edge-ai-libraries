import os
from pathlib import Path
from typing import List
import yaml


class PipelineLoader:
    @staticmethod
    def list(pipeline_path: str = "pipelines") -> List[Path]:
        """Return available predefined pipeline config paths."""
        pipelines_dir = Path(pipeline_path)
        pipeline_config_paths = [
            path
            for path in pipelines_dir.iterdir()
            if path.is_file() and path.name.endswith(".yaml")
        ]
        return sorted(pipeline_config_paths)

    @staticmethod
    def config(pipeline_config_path: Path) -> dict:
        """Return full config dict for a predefined pipeline."""
        config_path_real = os.path.realpath(str(pipeline_config_path))

        if not os.path.isfile(config_path_real):
            raise FileNotFoundError(
                f"Config file could not be resolved at {pipeline_config_path}"
            )
        # At this point, config_path_real is guaranteed to exist and be within pipelines_dir
        with open(config_path_real, "r", encoding="utf-8") as f:
            return yaml.safe_load(f.read())

import logging
import threading
from copy import deepcopy
from pathlib import Path
from typing import Optional

from api.api_schemas import (
    Pipeline,
    PipelineGraph,
    PipelineSource,
    Variant,
)
from graph import Graph
from pipelines.loader import PipelineLoader
from utils import generate_unique_id, get_current_timestamp

logger = logging.getLogger("pipeline_template_manager")

TEMPLATES_DIR_NAME = "templates"


class PipelineTemplateManager:
    """
    Thread-safe singleton managing read-only pipeline templates.

    Implements singleton pattern using __new__ with double-checked locking.
    Create instances with PipelineTemplateManager() to get the shared singleton instance.

    Responsibilities:

    * Load pipeline templates from YAML configuration files at startup
    * Expose read-only list of templates via get_templates()
    * Expose single template lookup via get_template_by_id()
    """

    _instance: Optional["PipelineTemplateManager"] = None
    _lock = threading.Lock()

    def __new__(cls) -> "PipelineTemplateManager":
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

        self.logger = logging.getLogger("PipelineTemplateManager")
        # Shared lock protecting access to templates list
        self._templates_lock = threading.Lock()
        # list of templates – loaded once at startup, never mutated afterwards
        self.templates: list[Pipeline] = self._load_templates()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_templates(self) -> list[Pipeline]:
        """
        Return all available pipeline templates.

        Returns:
            List of deep-copied Pipeline objects with source=TEMPLATE.
        """
        with self._templates_lock:
            return [deepcopy(t) for t in self.templates]

    def get_template_by_id(self, template_id: str) -> Pipeline:
        """
        Retrieve a single template by its ID.

        Args:
            template_id: Unique template identifier.

        Returns:
            Deep-copied Pipeline object with source=TEMPLATE.

        Raises:
            ValueError: If template with given ID is not found.
        """
        with self._templates_lock:
            for template in self.templates:
                if template.id == template_id:
                    return deepcopy(template)
        raise ValueError(f"Template with id '{template_id}' not found.")

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _load_templates(self) -> list[Pipeline]:
        """
        Load pipeline templates from YAML files in the templates subdirectory.

        Templates are loaded similarly to predefined pipelines but:
            * source is set to TEMPLATE
            * all variants are read_only=True
            * fields that require user input are stored as empty strings

        Returns:
            List of Pipeline template objects.

        Raises:
            ValueError: If a template YAML is missing required fields.
        """
        templates: list[Pipeline] = []
        templates_dir = (
            Path(PipelineLoader.get_pipelines_directory()) / TEMPLATES_DIR_NAME
        )

        if not templates_dir.exists():
            self.logger.warning(
                f"Templates directory not found: {templates_dir}. No templates will be loaded."
            )
            return templates

        for config_path in sorted(templates_dir.glob("*.yaml")):
            try:
                config = PipelineLoader.config(config_path)
                template = self._build_template_from_config(
                    config, str(config_path), existing_templates=templates
                )
                templates.append(template)
                self.logger.debug(
                    f"Loaded pipeline template '{template.name}' from {config_path}"
                )
            except Exception as exc:
                self.logger.error(f"Failed to load template from {config_path}: {exc}")
                raise

        self.logger.debug(f"Loaded {len(templates)} pipeline template(s).")
        return templates

    def _build_template_from_config(
        self,
        config: dict,
        config_path: str,
        existing_templates: list[Pipeline],
    ) -> Pipeline:
        """
        Build a Pipeline template object from a parsed YAML config.

        Args:
            config: Parsed YAML configuration dictionary.
            config_path: Path to the config file (used in error messages).
            existing_templates: Already-built templates used for ID collision checks.

        Returns:
            Pipeline object with source=TEMPLATE and read_only variants.

        Raises:
            ValueError: If required fields are missing or empty.
        """
        name = config.get("name", "").strip()
        if not name:
            raise ValueError(f"Template name cannot be empty in config: {config_path}")

        description = config.get("definition", "")
        tags = config.get("tags", [])
        if not isinstance(tags, list):
            tags = []

        current_time = get_current_timestamp()
        existing_variant_ids: list[str] = []
        variants: list[Variant] = []

        for variant_config in config.get("variants", []):
            variant_name = variant_config.get("name", "").strip()
            if not variant_name:
                raise ValueError(f"Variant name cannot be empty in template '{name}'")

            pipeline_desc = variant_config.get("pipeline_description", "").strip()
            if not pipeline_desc:
                raise ValueError(
                    f"Variant pipeline_description cannot be empty for variant "
                    f"'{variant_name}' in template '{name}'"
                )

            graph = Graph.from_pipeline_description(pipeline_desc)
            pipeline_graph = PipelineGraph.model_validate(graph.to_dict())

            simple_graph = graph.to_simple_view()
            pipeline_graph_simple = PipelineGraph.model_validate(simple_graph.to_dict())

            variant_id = generate_unique_id(variant_name, existing_variant_ids)
            existing_variant_ids.append(variant_id)

            variants.append(
                Variant(
                    id=variant_id,
                    name=variant_name,
                    read_only=True,
                    pipeline_graph=pipeline_graph,
                    pipeline_graph_simple=pipeline_graph_simple,
                    created_at=current_time,
                    modified_at=current_time,
                )
            )

        existing_ids = [t.id for t in existing_templates]
        template_id = generate_unique_id(name, existing_ids)

        return Pipeline(
            id=template_id,
            name=name,
            description=description,
            source=PipelineSource.TEMPLATE,
            tags=tags,
            variants=variants,
            thumbnail=None,
            created_at=current_time,
            modified_at=current_time,
        )

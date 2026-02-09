# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import asyncio
import os
import re
import shutil
import tarfile
import zipfile
from typing import Any, Dict, List, Optional, Tuple

from geti_sdk import Geti
from geti_sdk.http_session.exception import GetiRequestException
from geti_sdk.rest_clients import ModelClient, ProjectClient

from src.core.interfaces import DownloadTask, ModelDownloadPlugin
from src.utils.logging import logger

# Constants
DEFAULT_API_VERSION = "v1"
DEFAULT_MODEL_FORMAT = "OpenVINO"
DEFAULT_PRECISION = "FP16"
DEFAULT_EXPORT_TYPE = "optimized"


class GetiPlugin(ModelDownloadPlugin):
    """
    Plugin for downloading OpenVINO models from Intel Geti Server.
    
    Manages model discovery and downloads from a Geti server instance,
    supporting both base and optimized model variants.
    """

    _instance: Optional["GetiPlugin"] = None
    _verify_server_ssl_cert: Optional[bool] = None

    def __new__(cls) -> "GetiPlugin":
        """Singleton pattern: return the same instance."""
        if cls._instance is None:
            cls._instance = super(GetiPlugin, cls).__new__(cls)
        return cls._instance

    async def __aenter__(self):
        """Async context manager entry"""
        self._initialize_geti_sdk()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit with cleanup"""
        # Clean up SDK session if needed
        if self.geti and hasattr(self.geti, 'session'):
            try:
                self.geti.session.close()
            except Exception as e:
                logger.warning(f"Error closing Geti session: {e}")
        return False

    def __init__(self) -> None:
        """Initialize the Geti plugin instance."""
        if hasattr(self, '_initialized'):
            return

        self._initialized = True

        self._server_url: Optional[str] = os.environ.get("GETI_HOST")
        self._server_api_token: Optional[str] = os.environ.get("GETI_TOKEN")
        
        if not self._server_url or not self._server_api_token:
            logger.warning(
                "Geti env vars not set: GETI_HOST, GETI_TOKEN. "
                "Geti-related requests will fail."
            )

        if self.__class__._verify_server_ssl_cert is None:
            self.__class__._verify_server_ssl_cert = self._parse_bool(
                os.getenv("GETI_SERVER_SSL_VERIFY", "False"), ignore_empty=True
            )

        self.geti: Optional[Geti] = None
        self._project_client: Optional[ProjectClient] = None
        self._model_clients: Dict[str, ModelClient] = {}
        self._req_timeout: int = 30

    @staticmethod
    def _parse_bool(value: str, ignore_empty: bool = False) -> bool:
        """Parse string value to boolean.
        
        Args:
            value: String value to parse.
            ignore_empty: Return True if value is empty.
        """
        if ignore_empty and not value:
            return True
        return value.lower() in ("true", "1", "yes", "on")

    async def _get_project(self, project_id: Optional[str] = None) -> Optional[Any]:
        """Get project object - factory method to eliminate duplication."""
        projects = await self.get_projects(project_id=project_id)
        return projects[0]["project"] if projects else None

    def _initialize_geti_sdk(self) -> None:
        """Initialize Geti SDK instance if not already done using SDK pattern"""
        if self.geti is None:
            self.geti = Geti(
                host=self._server_url,
                token=self._server_api_token,
                verify_certificate=self.__class__._verify_server_ssl_cert
            )
            self.geti.workspace_id = os.environ.get("GETI_WORKSPACE_ID")

    def _get_project_client(self) -> ProjectClient:
        """Get or create ProjectClient using factory pattern."""
        if self._project_client is None:
            if self.geti is None:
                raise RuntimeError("Geti SDK not initialized. Call _initialize_geti_sdk() first.")
            self._project_client = ProjectClient(
                session=self.geti.session,
                workspace_id=self.geti.workspace_id
            )
        return self._project_client

    async def _get_or_create_model_client(self, project_id: str, project: Any) -> ModelClient:
        """Get or create and cache ModelClient using factory pattern."""
        if project_id not in self._model_clients:
            self._model_clients[project_id] = ModelClient(
                workspace_id=self.geti.workspace_id,
                project=project,
                session=self.geti.session
            )
        return self._model_clients[project_id]

    @property
    def plugin_name(self) -> str:
        return "geti"

    @property
    def plugin_type(self) -> str:
        return "downloader"

    def can_handle(self, model_name: str, hub: str, **kwargs: Any) -> bool:
        """Check if plugin can handle the given model.
        
        Returns True if hub is 'geti' and required credentials are set.
        """
        if hub.lower() != "geti":
            return False

        required_vars = [self._server_url, self._server_api_token]

        if any(var is None for var in required_vars):
            logger.warning(
                "One or more required Geti environment variables are not set. "
                "Required: GETI_HOST, GETI_TOKEN"
            )
            return False

        return True

    async def _validate_env_vars(self) -> None:
        """Validate that all required environment variables are set"""
        if any([self._server_url is None, self._server_api_token is None]):
            raise ValueError(
                "Required env vars not set: GETI_HOST, GETI_TOKEN"
            )

    async def _ensure_initialized(self) -> None:
        """Ensure SDK is initialized and environment variables are validated."""
        await self._validate_env_vars()
        self._initialize_geti_sdk()

    def _filter_optimized_models(self, models: List[Any], model_format: Optional[str], precision: Optional[str], 
                                extra_filters: Optional[Dict[str, Any]] = None) -> Tuple[List[Any], List[str]]:
        """Filter optimized models by format, precision, and custom criteria.
        
        Args:
            models: List of optimized models to filter.
            model_format: Target format (e.g., 'OpenVINO').
            precision: Target precision.
            extra_filters: Dictionary of extra filter criteria to apply.
            
        Returns:
            Tuple of (filtered_list, ignored_fields_list) where ignored_fields_list contains
            fields that were requested in extra_filters but not found on ANY model object.
        """
        target_format = model_format or DEFAULT_MODEL_FORMAT
        extra_filters = extra_filters or {}
        ignored_fields = []
        
        filtered = [
            om for om in models
            if (not model_format or (hasattr(om, 'model_format') and om.model_format == target_format))
            and (not precision or (hasattr(om, 'precision') and om.precision and 
                 any(p.lower() == precision.lower() for p in (om.precision if isinstance(om.precision, list) else [om.precision]))))
        ]
        
        # Apply extra filter criteria if provided
        for filter_key, filter_value in extra_filters.items():
            # Check if ANY model has this attribute
            has_field_in_any = any(hasattr(om, filter_key) for om in filtered)
            
            if not has_field_in_any:
                # Field doesn't exist on any model - track as ignored
                ignored_fields.append(filter_key)
                logger.warning(f"Filter field '{filter_key}' is not present in model data. This filter will be ignored.")
                continue
            
            # Field exists on at least some models - apply the filter
            filtered = [
                om for om in filtered
                if hasattr(om, filter_key) and self._match_filter_value(getattr(om, filter_key), filter_value)
            ]
        
        return filtered, ignored_fields
    
    def _match_filter_value(self, attr_value: Any, filter_value: Any) -> bool:
        """Check if an attribute value matches the filter value.
        
        Supports string matching (case-insensitive), list membership, and equality.
        """
        if isinstance(filter_value, str):
            if isinstance(attr_value, str):
                return attr_value.lower() == filter_value.lower()
            elif isinstance(attr_value, list):
                return any(
                    (item.lower() if isinstance(item, str) else item) == filter_value.lower() 
                    for item in attr_value
                )
        elif isinstance(attr_value, list):
            return filter_value in attr_value
        return attr_value == filter_value
    
    def _build_extra_filters_path(self, extra_filters: Optional[Dict[str, Any]] = None) -> str:
        """Build a path segment from extra filter criteria for folder differentiation.
        
        For string values: uses just the value (e.g., 'version2')
        For non-string values: uses the key name (e.g., 'count')
        
        Args:
            extra_filters: Dictionary of extra filter criteria.
            
        Returns:
            Path segment string (e.g., 'version2/count') in lowercase
            or empty string if no extra filters.
        """
        if not extra_filters:
            return ""
        
        path_parts = []
        for key, value in sorted(extra_filters.items()):
            if isinstance(value, str):
                # For string values, just use the value (sanitized and lowercase)
                safe_value = re.sub(r'[\s/\\]+', '_', value).lower()
                path_parts.append(safe_value)
            else:
                # For non-string values, use the key as identifier (lowercase)
                path_parts.append(key.lower())
        
        return "/".join(path_parts) if path_parts else ""

    def _build_criteria_message(self, model_name: Optional[str] = None, export_type: Optional[str] = None,
                               precision: Optional[str] = None, model_format: Optional[str] = None,
                               extra_filters: Optional[Dict[str, Any]] = None) -> str:
        """Build human-readable criteria message.
        
        Args:
            model_name: Model name (optional).
            export_type: Export type (optional).
            precision: Model precision (optional).
            model_format: Model format (optional).
            extra_filters: Dictionary of extra filters (optional).
            
        Returns:
            Formatted criteria string.
        """
        parts = []
        if model_name:
            parts.append(f"name='{model_name}'")
        if export_type:
            parts.append(f"export_type='{export_type}'")
        if precision:
            parts.append(f"precision='{precision}'")
        if model_format:
            parts.append(f"format='{model_format or DEFAULT_MODEL_FORMAT}'")
        
        # Add extra filter criteria
        if extra_filters:
            for key, value in extra_filters.items():
                parts.append(f"{key}='{value}'")
        
        return ", ".join(parts) if parts else "no criteria"

    async def get_projects(self, project_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get all projects or a specific project.
        
        Args:
            project_id: Specific project ID (optional).
            
        Returns:
            List of project dictionaries.
        """
        await self._ensure_initialized()

        try:
            project_client = self._get_project_client()
            project_list = await asyncio.to_thread(project_client.list_projects)

            # Convert to dicts and filter
            projects = [
                {
                    "id": p.id,
                    "name": p.name,
                    "creation_time": p.creation_time.isoformat() if hasattr(p.creation_time, 'isoformat') else str(p.creation_time),
                    "project": p
                }
                for p in project_list
                if project_id is None or p.id == project_id
            ]
            
            return projects

        except GetiRequestException as e:
            logger.error(f"Geti API error retrieving projects: {e}")
            raise
        except Exception as e:
            logger.error(f"Error retrieving projects: {type(e).__name__}: {e}")
            raise

    async def get_model_id_by_name(self, project_id: str, model_group_id: str, model_name: str) -> Optional[str]:
        """Find model ID by name.
        
        Args:
            project_id: Project ID.
            model_group_id: Model group ID.
            model_name: Model name to search for.
            
        Returns:
            Model ID if found, None otherwise.
        """
        try:
            model_group = await self.get_model_group(project_id, model_group_id)
            if not model_group:
                logger.warning(f"Model group {model_group_id} not found")
                return None

            models = model_group.get("models", [])
            # Optimized search: direct match first
            for model in models:
                if model.get("name", "").lower() == model_name.lower():
                    return model.get("id")
            return None

        except Exception as e:
            logger.error(f"Error fetching model by name: {type(e).__name__}: {e}")
            return None

    async def search_model(
        self,
        model_name: str,
        export_type: Optional[str] = None,
        precision: Optional[str] = None,
        revision: Optional[int] = None,
        model_format: Optional[str] = None,
        extra_filters: Optional[Dict[str, Any]] = None,
    ) -> Tuple[Optional[str], Optional[str], Optional[str], Optional[str], Optional[List[str]]]:
        """Search for model across all projects.
        
        Args:
            model_name: Model name to find.
            export_type: Export type ('base' or 'optimized').
            precision: Model precision.
            revision: Model revision (unused).
            model_format: Model format.
            extra_filters: Dictionary of extra filter criteria to apply.
            
        Returns:
            Tuple of (project_id, model_group_id, model_id, error_message, ignored_filter_fields).
        """
        extra_filters = extra_filters or {}
        try:
            await self._ensure_initialized()
            
            # Get all projects
            projects = await self.get_projects()
            if not projects:
                return None, None, None, None, None
            
            # Search across each project and its model groups
            for project_info in projects:
                project_id = project_info["id"]
                project = project_info["project"]
                
                try:
                    # Get or create ModelClient
                    model_client = await self._get_or_create_model_client(project_id, project)
                    
                    # Get all models (single thread call)
                    all_models = await asyncio.to_thread(model_client.get_latest_model_for_all_model_groups)
                    
                    # Search for matching model - early return on first match
                    for model in all_models:
                        if model.name.lower() != model_name.lower():
                            continue
                            
                        model_group_id = model.model_group_id
                        
                        # Check optimized models only if not base export
                        if export_type != 'base' and hasattr(model, 'optimized_models') and model.optimized_models:
                            openvino_models, ignored_fields = self._filter_optimized_models(model.optimized_models, model_format, precision, extra_filters)
                            
                            if openvino_models:
                                return project_id, model_group_id, model.id, None, ignored_fields
                            else:
                                break  # Stop searching this project
                        
                        # Handle base model export
                        elif export_type == 'base':
                            return project_id, model_group_id, model.id, None, None
                        else:
                            break  # Stop searching this project
                    
                except Exception as e:
                    logger.debug(f"Error searching project {project_id}: {type(e).__name__}: {e}")
                    continue
            
            # Build descriptive error message based on search criteria
            criteria = self._build_criteria_message(model_name, export_type, precision, model_format, extra_filters)
            error_msg = f"Model not found matching criteria: {criteria}"
            return None, None, None, error_msg, None
            
        except GetiRequestException as e:
            error_msg = f"Geti connection error: {e}"
            logger.error(error_msg)
            return None, None, None, error_msg, None
        except Exception as e:
            error_msg = f"Geti initialization/discovery error: {type(e).__name__}: {e}"
            logger.error(error_msg)
            return None, None, None, error_msg, None

    async def get_model_group(self, project_id: str, model_group_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve a model group with all its models.
        
        Args:
            project_id: Project ID.
            model_group_id: Model group ID.
            
        Returns:
            Model group dictionary or None if not found.
        """
        await self._ensure_initialized()

        try:
            project = await self._get_project(project_id)
            if not project:
                return None

            model_client = await self._get_or_create_model_client(project_id, project)

            # Fetch model groups and models in a single thread call
            def _fetch_groups_and_models():
                model_groups = model_client.get_all_model_groups()
                all_models = model_client.get_latest_model_for_all_model_groups()
                return model_groups, all_models
            
            model_groups, all_models = await asyncio.to_thread(_fetch_groups_and_models)
            target_mg = next((mg for mg in model_groups if mg.id == model_group_id), None)
            
            if not target_mg:
                return None

            return {
                "id": target_mg.id,
                "name": target_mg.name,
                "models": [
                    {"id": m.id, "name": m.name, "model": m}
                    for m in all_models
                    if m.model_group_id == model_group_id
                ],
                "model_group": target_mg
            }

        except GetiRequestException as e:
            logger.error(f"Geti API error: {e}")
            return None
        except Exception as e:
            logger.error(f"Error retrieving model group: {type(e).__name__}: {e}")
            return None

    async def download_model_from_geti(
        self, model_id: str, output_dir: str, model_name: str = "", **kwargs: Any
    ) -> Tuple[Optional[str], Optional[str], Optional[List[str]]]:
        """Download model files from Geti server.
        
        Args:
            model_id: Base model ID.
            output_dir: Output directory path.
            model_name: Model name for logging.
            **kwargs: export_type, project_id, model_group_id, optimized_model_id, precision, model_format, extra_filters.
            
        Returns:
            Tuple of (model_path, error_message, ignored_fields).
        """
        await self._ensure_initialized()

        try:
            project = await self._get_project(kwargs.get("project_id"))
            if not project:
                error_msg = f"Project not found: {kwargs.get('project_id')}"
                logger.error(error_msg)
                return None, error_msg, None

            model_client = await self._get_or_create_model_client(kwargs.get("project_id"), project)
            model = await asyncio.to_thread(model_client._get_model_detail, kwargs.get("model_group_id"), model_id)
            
            if not model:
                error_msg = f"Model not found: {model_id}"
                logger.error(error_msg)
                return None, error_msg, None

            ignored_fields = None
            
            # Select model variant based on export_type
            if kwargs.get("export_type") == "optimized":
                if not hasattr(model, 'optimized_models') or not model.optimized_models:
                    error_msg = f"No optimized models available for model {model_id}"
                    logger.error(error_msg)
                    return None, error_msg, None
                
                model_to_download, ignored_fields = await self.select_optimized_model(
                    model, kwargs.get("optimized_model_id"), kwargs.get("precision"), 
                    model_id, kwargs.get('model_format'), kwargs.get('extra_filters')
                )
                if not model_to_download:
                    extra_filters = kwargs.get('extra_filters', {})
                    criteria = self._build_criteria_message(
                        model_format=kwargs.get('model_format'),
                        precision=kwargs.get('precision'),
                        extra_filters=extra_filters
                    )
                    error_msg = f"No optimized model found matching criteria: {criteria}"
                    logger.error(error_msg)
                    return None, error_msg, ignored_fields
            else:
                model_to_download = model

            # Prepare output directory with extra filter criteria in path for differentiation
            extra_filters = kwargs.get('extra_filters', {})
            extra_path = self._build_extra_filters_path(extra_filters)
            
            # Build path: output_dir/geti/model_name/[extra_filters/]precision (all lowercase)
            model_name_lower = model_name.lower()
            precision_lower = kwargs.get('precision', '').lower()
            
            if extra_path:
                model_dir = os.path.join(output_dir, "geti", model_name_lower, extra_path, precision_lower)
            else:
                model_dir = os.path.join(output_dir, "geti", model_name_lower, precision_lower)
            
            os.makedirs(model_dir, exist_ok=True)
            await asyncio.to_thread(model_client._download_model, model_to_download, model_dir)
            await self.extract_model_files(model_dir)
            return model_dir, None, ignored_fields

        except GetiRequestException as e:
            error_msg = f"Geti API error: {e}"
            logger.error(error_msg)
            return None, error_msg, None
        except Exception as e:
            error_msg = f"Download failed: {type(e).__name__}: {e}"
            logger.error(error_msg)
            return None, error_msg, None

    async def select_optimized_model(self, model: Any, optimized_model_id: Optional[str], 
                               precision: Optional[str], base_model_id: str,
                               model_format: Optional[str] = None,
                               extra_filters: Optional[Dict[str, Any]] = None) -> Tuple[Optional[Any], Optional[List[str]]]:
        """Select optimized model variant using factory pattern.
        
        Returns:
            Tuple of (selected_model, ignored_fields)
            
        Strategy:
        1. If optimized_model_id provided, find exact match (no fallback)
        2. If precision and/or model_format provided, find model with matching criteria (no fallback)
        3. Otherwise, use first available
        4. If none available, return None
        """
        extra_filters = extra_filters or {}
        
        if optimized_model_id:
            return next((om for om in model.optimized_models if om.id == optimized_model_id), None), None

        if precision or model_format or extra_filters:
            filtered, ignored_fields = self._filter_optimized_models(model.optimized_models, model_format, precision, extra_filters)
            if not filtered:
                return None, ignored_fields
            return filtered[0], ignored_fields

        return model.optimized_models[0] if model.optimized_models else None, None

    async def _resolve_model_ids(self, model_name: str, model_id: Optional[str], project_id: Optional[str], 
                           model_group_id: Optional[str], export_type: str, precision: str,
                           model_format: str, extra_filters: Optional[Dict[str, Any]] = None) -> Tuple[Optional[str], Optional[str], Optional[str], Optional[str], Optional[List[str]]]:
        """Resolve all required model IDs - factory method to consolidate lookup logic.
        
        Returns:
            Tuple of (model_id, project_id, model_group_id, error, ignored_fields)
        """
        extra_filters = extra_filters or {}
        
        # If only model_id provided, search for missing project/group IDs
        if model_id and (not project_id or not model_group_id):
            p_id, mg_id, _, error, ignored = await self.search_model(model_name, export_type, precision, None, model_format, extra_filters)
            return model_id if (p_id and mg_id) else None, p_id, mg_id, error, ignored

        # If model_id not provided, search for all IDs
        if not model_id:
            if not project_id or not model_group_id:
                p_id, mg_id, m_id, error, ignored = await self.search_model(model_name, export_type, precision, None, model_format, extra_filters)
                return m_id, p_id, mg_id, error, ignored
            else:
                # Use provided IDs to lookup model
                m_id = await self.get_model_id_by_name(project_id, model_group_id, model_name)
                return m_id, project_id, model_group_id, None if m_id else f"Model not found: {model_name}", None

        return model_id, project_id, model_group_id, None, None

    async def extract_model_files(self, model_dir: str) -> None:
        """Extract nested model files from SDK structure.
        
        Moves files from 'models' subdirectory to parent directory.
        """
        models_subdir = os.path.join(model_dir, "models")
        if not os.path.exists(models_subdir):
            return

        try:
            for item in os.listdir(models_subdir):
                src = os.path.join(models_subdir, item)
                dst = os.path.join(model_dir, item)
                if os.path.isdir(src):
                    shutil.copytree(src, dst, dirs_exist_ok=True)
                    continue

                shutil.copy2(src, dst)

                lower_dst = dst.lower()
                if lower_dst.endswith(".zip") and zipfile.is_zipfile(dst):
                    with zipfile.ZipFile(dst, "r") as zip_ref:
                        zip_ref.extractall(model_dir)
                    os.remove(dst)
                elif lower_dst.endswith((".tar.gz", ".tgz")) and tarfile.is_tarfile(dst):
                    with tarfile.open(dst, "r:gz") as tar_ref:
                        tar_ref.extractall(model_dir)
                    os.remove(dst)
            shutil.rmtree(models_subdir)
        except Exception as e:
            logger.warning(f"File extraction issue: {e}")

    async def download(self, model_name: str, output_dir: str, **kwargs: Any) -> Dict[str, Any]:
        """Download models from Geti server.
        
        Orchestrates project/model lookup and download. Supports extra filter criteria passed via config.
        
        Args:
            model_name: Model name to download.
            output_dir: Output directory for model files.
            **kwargs: Config dict with optional parameters and extra filter criteria.
            
        Returns:
            Dictionary with success status and download metadata.
        """
        try:
            config = kwargs.get("config", {}) or {}
            
            export_type = (config.get("export_type") or DEFAULT_EXPORT_TYPE).lower()
            precision = (config.get("precision") or DEFAULT_PRECISION).lower()
            model_format = config.get("model_format") or DEFAULT_MODEL_FORMAT
            
            # Define config keys used by geti_plugin
            supported_config_keys = {
                'export_type', 'precision', 'model_format', 'model_group_id', 
                'optimized_model_id'
            }
            
            # Extract extra filters for model filtering (all non-supported fields)
            extra_filters = {
                key: value for key, value in config.items() 
                if key not in supported_config_keys and value is not None
            }

            # Resolve all model IDs using factory method
            model_id, project_id, model_group_id, resolve_error, resolve_ignored = await self._resolve_model_ids(
                model_name, config.get("model_id"), config.get("project_id"),
                config.get("model_group_id"), export_type, precision, model_format, extra_filters
            )
            
            if not model_id:
                return {"success": False, "error": resolve_error or f"Model not found: {model_name}"}

            # Download model
            model_path, download_error, download_ignored = await self.download_model_from_geti(
                model_id, output_dir, model_name,
                export_type=export_type,
                project_id=project_id,
                model_group_id=model_group_id,
                optimized_model_id=config.get("optimized_model_id"),
                precision=precision,
                model_format=model_format,
                extra_filters=extra_filters
            )
            
            if not model_path:
                return {"success": False, "error": download_error or "Download failed"}

            # Collect ignored fields from entire pipeline only if unsupported fields were provided
            all_ignored_fields = []
            
            # Add any extra filter fields that don't exist on the models (from resolve stage)
            if extra_filters and resolve_ignored:
                all_ignored_fields.extend(resolve_ignored)
            
            # Add any extra filter fields that don't exist on the models (from download stage)
            if extra_filters and download_ignored:
                all_ignored_fields.extend(download_ignored)
            
            # Remove duplicates
            all_ignored_fields = list(set(all_ignored_fields))

            # Prepare response path and return success
            host_path = os.path.join(output_dir, "geti")
            if host_path.startswith("/opt/models/"):
                host_path = host_path.replace("/opt/models/", f"{os.getenv('MODEL_PATH', 'models')}/")

            response = {
                "model_name": model_name,
                "source": "geti",
                "download_path": host_path,
                "success": True,
            }
            
            # Only add fields to response if they were explicitly provided in the request
            if "model_id" in config:
                response["model_id"] = model_id
            if "model_group_id" in config:
                response["model_group_id"] = model_group_id
            if "export_type" in config:
                response["export_type"] = export_type
            if "model_format" in config:
                response["model_format"] = model_format
            
            # Add warning about ignored fields only if user provided filters/config fields that were ignored
            if all_ignored_fields:
                response["warnings"] = {
                    "ignored_fields": all_ignored_fields,
                    "message": f"The following fields were ignored during model download because they are not present in the Geti model metadata: {', '.join(sorted(all_ignored_fields))}"
                }
                logger.warning(response["warnings"]["message"])
            
            return response

        except Exception as e:
            logger.error(f"Download error: {type(e).__name__}: {e}")
            return {"success": False, "error": str(e)}

    def get_download_tasks(self, model_name: str, **kwargs: Any) -> List[DownloadTask]:
        """Get download tasks (not supported)."""
        raise NotImplementedError("Geti plugin does not support task-based downloading")

    def download_task(self, task: DownloadTask, output_dir: str, **kwargs: Any) -> str:
        """Download a task (not supported)."""
        raise NotImplementedError("Geti plugin does not support task-based downloading")

    async def post_process(
        self, model_name: str, output_dir: str, downloaded_paths: List[str], **kwargs: Any
    ) -> Dict[str, Any]:
        """Post-process downloaded models."""
        return {
            "model_name": model_name,
            "source": "geti",
            "download_path": output_dir,
            "success": True,
        }


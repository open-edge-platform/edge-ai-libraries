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

from src.core.interfaces import DownloadTask, ModelDownloadPlugin, PluginConfigKey
from src.utils.logging import logger

# Constants
DEFAULT_API_VERSION = "v1"
DEFAULT_MODEL_FORMAT = "OpenVINO"
DEFAULT_PRECISION = "FP16"
DEFAULT_EXPORT_TYPE = "optimized"
GETI_LISTING_FILTER_FIELDS = [
    "project_id",
    "project_name",
    "model_group_id",
    "model_group_name",
    "model_name",
    "export_type",
    "precision",
    "model_format",
]


class _GetiSession:
    """Per-request Geti credentials and lazily created SDK clients.

    Built fresh for each request from the resolved configuration (per-request
    overrides with environment variables as the fallback). Because the
    credentials and SDK clients live on this short-lived object rather than on
    the shared plugin singleton, values never persist globally and cannot leak
    between concurrent requests or users.
    """

    def __init__(self, server_url: Optional[str], api_token: Optional[str],
                 workspace_id: Optional[str], verify_ssl: bool) -> None:
        self.server_url = server_url
        self.api_token = api_token
        self.workspace_id = workspace_id
        self.verify_ssl = verify_ssl
        self.geti: Optional[Geti] = None
        self.project_client: Optional[ProjectClient] = None
        self.model_clients: Dict[str, ModelClient] = {}


class GetiPlugin(ModelDownloadPlugin):
    """
    Plugin for downloading OpenVINO models from Intel Geti Server.

    Manages model discovery and downloads from a Geti server instance,
    supporting both base and optimized model variants. Connection credentials
    are resolved per request, so a single shared plugin instance can serve
    callers with different Geti connections without leaking state or requiring
    a restart.
    """

    _instance: Optional["GetiPlugin"] = None

    def __new__(cls) -> "GetiPlugin":
        """Singleton pattern: return the same instance."""
        if cls._instance is None:
            cls._instance = super(GetiPlugin, cls).__new__(cls)
        return cls._instance

    def __init__(self) -> None:
        """Initialize the Geti plugin instance.

        Credentials are intentionally NOT read here. They are resolved per
        request (see ``resolve_config`` / ``_build_session``) so the shared
        instance never holds another caller's credentials.
        """
        if hasattr(self, '_initialized'):
            return

        self._initialized = True
        self._req_timeout: int = 30

    def config_keys(self) -> List[PluginConfigKey]:
        return [
            PluginConfigKey(
                name="GETI_HOST",
                description="Geti server URL.",
                sensitive=True,
                required=True,
                group="geti",
            ),
            PluginConfigKey(
                name="GETI_TOKEN",
                description="Geti personal access token.",
                sensitive=True,
                required=True,
                group="geti",
            ),
            PluginConfigKey(
                name="GETI_WORKSPACE_ID",
                description="Geti workspace ID.",
                required=True,
                group="geti",
            ),
        ]

    def _build_session(self, resolved_config: Dict[str, Any]) -> _GetiSession:
        """Create a per-request session from resolved configuration.

        GETI_SERVER_SSL_VERIFY is read only from the environment (never
        overridable per request) so a caller cannot weaken TLS verification.
        """
        return _GetiSession(
            server_url=resolved_config.get("GETI_HOST"),
            api_token=resolved_config.get("GETI_TOKEN"),
            workspace_id=resolved_config.get("GETI_WORKSPACE_ID"),
            verify_ssl=self._parse_bool(
                os.getenv("GETI_SERVER_SSL_VERIFY", "False"), ignore_empty=True
            ),
        )

    def _session_from_kwargs(self, kwargs: Dict[str, Any]) -> _GetiSession:
        """Build a per-request session from resolved_config (or raw overrides) in kwargs."""
        resolved = kwargs.get("resolved_config")
        if resolved is None:
            resolved = self.resolve_config(kwargs.get("override_credentials"))
        return self._build_session(resolved)

    @staticmethod
    def _parse_bool(value: Any, ignore_empty: bool = False) -> bool:
        """Parse string value to boolean.
        
        Args:
            value: String value to parse.
            ignore_empty: Return True if value is empty.
        """
        if isinstance(value, bool):
            return value
        value = value or ""
        if ignore_empty and not value:
            return True
        return str(value).lower() in ("true", "1", "yes", "on")

    async def _get_project(self, session: _GetiSession, project_id: Optional[str] = None) -> Optional[Any]:
        """Get project object - factory method to eliminate duplication."""
        projects = await self.get_projects(session, project_id=project_id)
        return projects[0]["project"] if projects else None

    def _initialize_geti_sdk(self, session: _GetiSession) -> None:
        """Initialize Geti SDK instance if not already done using SDK pattern"""
        if session.geti is None:
            session.geti = Geti(
                host=session.server_url,
                token=session.api_token,
                verify_certificate=session.verify_ssl
            )
            session.geti.workspace_id = session.workspace_id

    def _get_project_client(self, session: _GetiSession) -> ProjectClient:
        """Get or create ProjectClient using factory pattern."""
        if session.project_client is None:
            if session.geti is None:
                raise RuntimeError("Geti SDK not initialized. Call _initialize_geti_sdk() first.")
            session.project_client = ProjectClient(
                session=session.geti.session,
                workspace_id=session.geti.workspace_id
            )
        return session.project_client

    async def _get_or_create_model_client(self, session: _GetiSession, project_id: str, project: Any) -> ModelClient:
        """Get or create and cache ModelClient using factory pattern."""
        if project_id not in session.model_clients:
            session.model_clients[project_id] = ModelClient(
                workspace_id=session.geti.workspace_id,
                project=project,
                session=session.geti.session
            )
        return session.model_clients[project_id]

    @property
    def plugin_name(self) -> str:
        return "geti"

    @property
    def plugin_type(self) -> str:
        return "downloader"

    @property
    def supports_listing(self) -> bool:
        return True

    @property
    def listing_filter_fields(self) -> List[str]:
        return GETI_LISTING_FILTER_FIELDS

    def list_models(self, filters: Optional[Dict[str, Any]] = None, limit: int = 50,
                    offset: int = 0, **kwargs: Any) -> Dict[str, Any]:
        """List models available on the configured Geti server."""
        session = self._session_from_kwargs(kwargs)
        return asyncio.run(self._list_models_async(session, filters=filters, limit=limit, offset=offset))

    async def _list_models_async(self, session: _GetiSession, filters: Optional[Dict[str, Any]] = None,
                                 limit: int = 50, offset: int = 0) -> Dict[str, Any]:
        filters = filters or {}
        self._validate_listing_filters(filters)
        await self._ensure_initialized(session)

        if not session.geti.workspace_id:
            raise ValueError(
                "Missing Geti workspace id. Set GETI_WORKSPACE_ID or provide it in the "
                "request 'override_credentials'."
            )

        project_id = str(filters.get("project_id")) if filters.get("project_id") is not None else None
        project_name = str(filters.get("project_name")).lower() if filters.get("project_name") is not None else None
        model_group_id = str(filters.get("model_group_id")) if filters.get("model_group_id") is not None else None
        model_group_name = str(filters.get("model_group_name")).lower() if filters.get("model_group_name") is not None else None
        model_name = str(filters.get("model_name")).lower() if filters.get("model_name") is not None else None
        export_type = str(filters.get("export_type") or DEFAULT_EXPORT_TYPE).lower()
        precision = str(filters.get("precision")).lower() if filters.get("precision") is not None else None
        model_format = filters.get("model_format")

        projects = await self.get_projects(session, project_id=project_id)
        if project_name and not project_id:
            projects = [p for p in projects if project_name in str(p.get("name", "")).lower()]

        items = []
        for project_info in projects:
            project = project_info["project"]
            model_client = await self._get_or_create_model_client(session, project_info["id"], project)
            model_groups, latest_models = await asyncio.to_thread(self._get_model_groups_and_latest_models, model_client)
            groups_by_id = {mg.id: mg for mg in model_groups}

            for model in latest_models:
                group = groups_by_id.get(model.model_group_id)
                if model_group_id and model.model_group_id != model_group_id:
                    continue
                if model_group_name and not model_group_id and (group is None or model_group_name not in str(group.name).lower()):
                    continue
                if model_name and model_name not in str(model.name).lower():
                    continue

                optimized_models = list(getattr(model, "optimized_models", []) or [])
                if export_type == "optimized":
                    matched_optimized_models, _ = self._filter_optimized_models(
                        optimized_models, model_format, precision
                    )
                    # if none matched, skip the model
                    if not matched_optimized_models:
                        continue
                else:
                    matched_optimized_models = optimized_models

                creation_time = getattr(model, "creation_time", None)
                last_modified = getattr(model, "last_updated", None) or getattr(model, "update_time", None) or creation_time
                metadata = {
                    "workspace_id": getattr(session.geti, "workspace_id", None),
                    "project_id": project_info.get("id"),
                    "project_name": project_info.get("name"),
                    "model_group_id": getattr(model, "model_group_id", None),
                    "model_group_name": getattr(group, "name", None),
                    "model_id": getattr(model, "id", None),
                    "optimized_model_ids": [getattr(om, "id", None) for om in matched_optimized_models],
                }

                items.append({
                    "name": getattr(model, "name", None) or getattr(model, "id", ""),
                    "owner": project_info.get("name"), # Project name is owner
                    "precisions": self._collect_model_precisions(matched_optimized_models),
                    "model_type": self._get_task_type_for_group(project, group),
                    "last_modified": last_modified.isoformat() if hasattr(last_modified, "isoformat") else last_modified,
                    "metadata": metadata,
                })

        total = len(items)
        page = items[offset: offset + limit]
        return {"items": page, "total": total}

    @staticmethod
    def _get_model_groups_and_latest_models(model_client: ModelClient) -> Tuple[List[Any], List[Any]]:
        return model_client.get_all_model_groups(), model_client.get_latest_model_for_all_model_groups()

    @staticmethod
    def _collect_model_precisions(models: List[Any]) -> List[str]:
        precisions = set()
        for model in models:
            model_precision = getattr(model, "precision", None)
            model_precisions = model_precision if isinstance(model_precision, list) else [model_precision]
            precisions.update(str(precision) for precision in model_precisions if precision is not None)
        return sorted(precisions)

    @staticmethod
    def _get_task_type_for_group(project: Any, model_group: Any) -> Optional[str]:
        if model_group is None:
            return None

        group_task_id = getattr(model_group, "task_id", None)
        for task in project.get_trainable_tasks():
            if getattr(task, "id", None) == group_task_id:
                return str(getattr(task, "task_type", None))
        return None

    def can_handle(self, model_name: str, hub: str, **kwargs: Any) -> bool:
        """Check if plugin can handle the given model.

        Returns True whenever the hub is 'geti'. Credentials are resolved and
        validated per request (see ``download`` / ``list_models``), so plugin
        selection does not depend on process-wide environment variables.
        """
        return hub.lower() == "geti"

    async def _validate_credentials(self, session: _GetiSession) -> None:
        """Validate that the required credentials are present for this request."""
        if session.server_url is None or session.api_token is None:
            raise ValueError(
                "Required Geti configuration not provided. Set GETI_HOST and "
                "GETI_TOKEN via environment variables or the request "
                "'override_credentials' field."
            )

    async def _ensure_initialized(self, session: _GetiSession) -> None:
        """Ensure SDK is initialized and credentials are validated."""
        await self._validate_credentials(session)
        self._initialize_geti_sdk(session)

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

    async def get_projects(self, session: _GetiSession, project_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get all projects or a specific project.
        
        Args:
            session: Per-request Geti session.
            project_id: Specific project ID (optional).
            
        Returns:
            List of project dictionaries.
        """
        await self._ensure_initialized(session)

        try:
            project_client = self._get_project_client(session)
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

    async def get_model_id_by_name(self, session: _GetiSession, project_id: str, model_group_id: str, model_name: str) -> Optional[str]:
        """Find model ID by name.
        
        Args:
            session: Per-request Geti session.
            project_id: Project ID.
            model_group_id: Model group ID.
            model_name: Model name to search for.
            
        Returns:
            Model ID if found, None otherwise.
        """
        try:
            model_group = await self.get_model_group(session, project_id, model_group_id)
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
        session: _GetiSession,
        model_name: str,
        export_type: Optional[str] = None,
        precision: Optional[str] = None,
        revision: Optional[int] = None,
        model_format: Optional[str] = None,
        extra_filters: Optional[Dict[str, Any]] = None,
    ) -> Tuple[Optional[str], Optional[str], Optional[str], Optional[str], Optional[List[str]]]:
        """Search for model across all projects.
        
        Args:
            session: Per-request Geti session.
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
            await self._ensure_initialized(session)
            
            # Get all projects
            projects = await self.get_projects(session)
            if not projects:
                return None, None, None, None, None
            
            # Search across each project and its model groups
            for project_info in projects:
                project_id = project_info["id"]
                project = project_info["project"]
                
                try:
                    # Get or create ModelClient
                    model_client = await self._get_or_create_model_client(session, project_id, project)
                    
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

    async def get_model_group(self, session: _GetiSession, project_id: str, model_group_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve a model group with all its models.
        
        Args:
            session: Per-request Geti session.
            project_id: Project ID.
            model_group_id: Model group ID.
            
        Returns:
            Model group dictionary or None if not found.
        """
        await self._ensure_initialized(session)

        try:
            project = await self._get_project(session, project_id)
            if not project:
                return None

            model_client = await self._get_or_create_model_client(session, project_id, project)

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
        self, session: _GetiSession, model_id: str, output_dir: str, model_name: str = "", **kwargs: Any
    ) -> Tuple[Optional[str], Optional[str], Optional[List[str]]]:
        """Download model files from Geti server.
        
        Args:
            session: Per-request Geti session.
            model_id: Base model ID.
            output_dir: Output directory path.
            model_name: Model name for logging.
            **kwargs: export_type, project_id, model_group_id, optimized_model_id, precision, model_format, extra_filters.
            
        Returns:
            Tuple of (model_path, error_message, ignored_fields).
        """
        await self._ensure_initialized(session)

        try:
            project = await self._get_project(session, kwargs.get("project_id"))
            if not project:
                error_msg = f"Project not found: {kwargs.get('project_id')}"
                logger.error(error_msg)
                return None, error_msg, None

            model_client = await self._get_or_create_model_client(session, kwargs.get("project_id"), project)
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

    async def _resolve_model_ids(self, session: _GetiSession, model_name: str, model_id: Optional[str], project_id: Optional[str], 
                           model_group_id: Optional[str], export_type: str, precision: str,
                           model_format: str, extra_filters: Optional[Dict[str, Any]] = None) -> Tuple[Optional[str], Optional[str], Optional[str], Optional[str], Optional[List[str]]]:
        """Resolve all required model IDs - factory method to consolidate lookup logic.
        
        Returns:
            Tuple of (model_id, project_id, model_group_id, error, ignored_fields)
        """
        extra_filters = extra_filters or {}
        
        # If only model_id provided, search for missing project/group IDs
        if model_id and (not project_id or not model_group_id):
            p_id, mg_id, _, error, ignored = await self.search_model(session, model_name, export_type, precision, None, model_format, extra_filters)
            return model_id if (p_id and mg_id) else None, p_id, mg_id, error, ignored

        # If model_id not provided, search for all IDs
        if not model_id:
            if not project_id or not model_group_id:
                p_id, mg_id, m_id, error, ignored = await self.search_model(session, model_name, export_type, precision, None, model_format, extra_filters)
                return m_id, p_id, mg_id, error, ignored
            else:
                # Use provided IDs to lookup model
                m_id = await self.get_model_id_by_name(session, project_id, model_group_id, model_name)
                return m_id, project_id, model_group_id, None if m_id else f"Model not found: {model_name}", None

        return model_id, project_id, model_group_id, None, None

    def _safe_extract_archive(self, archive_path: str, extract_dir: str) -> None:
        """Safely extract a zip or tar.gz archive, blocking path traversal attacks.

        Validates every archive entry to ensure it resolves within extract_dir
        before extraction. Unsafe entries are skipped with a warning.

        Args:
            archive_path: Path to the zip or tar.gz/.tgz archive file.
            extract_dir: Directory to extract files into.
        """
        abs_extract_dir = os.path.realpath(extract_dir)

        def _is_safe(name: str) -> bool:
            return os.path.realpath(os.path.join(abs_extract_dir, name)).startswith(abs_extract_dir + os.sep)

        lower_path = archive_path.lower()
        if lower_path.endswith(".zip") and zipfile.is_zipfile(archive_path):
            with zipfile.ZipFile(archive_path, "r") as zip_ref:
                for member in zip_ref.namelist():
                    if _is_safe(member):
                        zip_ref.extract(member, extract_dir)
                    else:
                        logger.warning(f"Skipping unsafe zip entry: {member}")
        elif lower_path.endswith((".tar.gz", ".tgz")) and tarfile.is_tarfile(archive_path):
            with tarfile.open(archive_path, "r:gz") as tar_ref:
                safe_members = [m for m in tar_ref.getmembers() if _is_safe(m.name)]
                tar_ref.extractall(extract_dir, members=safe_members)

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
                if lower_dst.endswith(".zip") or lower_dst.endswith((".tar.gz", ".tgz")):
                    self._safe_extract_archive(dst, model_dir)
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

            # Build a per-request session (override credentials win, env is the
            # fallback). Scoped to this call only, so nothing leaks globally.
            session = self._session_from_kwargs(kwargs)

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
                session, model_name, config.get("model_id"), config.get("project_id"),
                config.get("model_group_id"), export_type, precision, model_format, extra_filters
            )
            
            if not model_id:
                return {"success": False, "error": resolve_error or f"Model not found: {model_name}"}

            # Download model
            model_path, download_error, download_ignored = await self.download_model_from_geti(
                session, model_id, output_dir, model_name,
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

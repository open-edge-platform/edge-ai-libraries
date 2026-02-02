# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import os
import shutil
import json
import asyncio
from typing import Dict, Any, List, Optional, Tuple

from geti_sdk import Geti
from geti_sdk.http_session.exception import GetiRequestException
from geti_sdk.rest_clients import ProjectClient, ModelClient
from pydantic import TypeAdapter

from src.core.interfaces import ModelDownloadPlugin, DownloadTask
from src.utils.logging import logger


class GetiPlugin(ModelDownloadPlugin):
    """
    Plugin for downloading OpenVINO models from Intel Geti Server.
    
    Architecture:
    - Singleton pattern for SDK instance
    - Cached clients: ProjectClient, ModelClient (per project)
    - Lazy initialization for SDK and clients
    - Type-safe exception handling with retry logic
    """
    
    # Class-level instance holder for singleton pattern
    _instance = None
    _verify_server_ssl_cert = None  # Will be set in __init__
    
    def __new__(cls):
        """Singleton pattern: return the same instance"""
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

    def __init__(self):
        """Initialize the Geti plugin instance"""
        # Only initialize once (singleton pattern)
        if hasattr(self, '_initialized'):
            return
        
        self._initialized = True
        
        # Read environment variables fresh at initialization time
        self._server_url = os.environ.get("GETI_HOST")
        self._server_api_token = os.environ.get("GETI_TOKEN")
        self._server_api_ver = os.environ.get("GETI_SERVER_API_VERSION", "v1")
        
        
        # Check required environment variables during instance creation
        if any([self._server_url is None, self._server_api_token is None]):
            logger.warning(
                "Geti env vars not set: GETI_HOST, GETI_TOKEN. "
                "Geti-related requests will fail."
            )
        
        # Parse SSL verification setting
        if self.__class__._verify_server_ssl_cert is None:
            self.__class__._verify_server_ssl_cert = self._parse_bool(
                os.getenv("GETI_SERVER_SSL_VERIFY", "False"), ignore_empty=True
            )
        
        # Client instances (lazy initialized)
        self.geti = None
        self._project_client = None
        self._model_clients = {}  # Cache ModelClient per project
        self._req_timeout = 30
        
        logger.debug("GetiPlugin initialized")

    @staticmethod
    def _parse_bool(value: str, ignore_empty: bool = False) -> bool:
        """Parse a string value to boolean"""
        if ignore_empty and not value:
            return True
        return value.lower() in ("true", "1", "yes", "on")

    def _initialize_geti_sdk(self) -> None:
        """Initialize Geti SDK instance if not already done using SDK pattern"""
        if self.geti is None:
            logger.debug(f"Initializing Geti SDK (host={self._server_url})")
            self.geti = Geti(
                host=self._server_url,
                token=self._server_api_token,
                verify_certificate=self.__class__._verify_server_ssl_cert
            )
            self.geti.workspace_id = os.environ.get("GETI_WORKSPACE_ID")
            logger.info(f"SDK initialized. workspace_id={self.geti.workspace_id}")

    def _get_project_client(self) -> ProjectClient:
        """Get or create ProjectClient (cached)"""
        if self._project_client is None:
            self._project_client = ProjectClient(
                session=self.geti.session,
                workspace_id=self.geti.workspace_id
            )
        return self._project_client

    def _get_model_client(self, project_id: str) -> ModelClient:
        """Get or create ModelClient for a project (cached per project)"""
        if project_id not in self._model_clients:
            # This is set later with the project object
            pass
        return self._model_clients.get(project_id)

    def _set_model_client(self, project_id: str, model_client: ModelClient) -> None:
        """Cache ModelClient for a project"""
        self._model_clients[project_id] = model_client

    @property
    def plugin_name(self) -> str:
        return "geti"

    @property
    def plugin_type(self) -> str:
        return "downloader"

    def can_handle(self, model_name: str, hub: str, **kwargs) -> bool:
        """
        Check if this plugin can handle the given model.
        Returns True if hub is 'geti' and GETI_HOST and GETI_TOKEN are set.
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

    async def get_projects(self, project_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Get all projects or a specific project.

        Args:
            project_id (str, optional): The ID of a specific project. Defaults to None.

        Returns:
            List[Dict[str, Any]]: List of projects with 'id', 'name', 'creation_time', 'project'
        """
        await self._validate_env_vars()
        self._initialize_geti_sdk()

        try:
            logger.info("Fetching projects from Geti server")
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
            
            logger.info(f"Retrieved {len(projects)} project(s)")
            return projects

        except GetiRequestException as e:
            logger.error(f"Geti API error retrieving projects: {e.message}")
            raise
        except Exception as e:
            logger.error(f"Error retrieving projects: {type(e).__name__}: {e}")
            raise

    async def get_model_id_by_name(self, project_id: str, model_group_id: str, model_name: str) -> Optional[str]:
        """
        Fetch model_id by name using cached model groups.

        Args:
            project_id (str): The project ID
            model_group_id (str): The model group ID
            model_name (str): The model name to search for

        Returns:
            Optional[str]: The model_id if found, None otherwise
        """
        try:
            model_group = await self.get_model_group(project_id, model_group_id)
            if not model_group:
                logger.warning(f"Model group {model_group_id} not found 261")
                return None

            models = model_group.get("models", [])
            logger.info(f"Searching for model '{model_name}' in {models} models")
            # Optimized search: direct match first
            for model in models:
                if model.get("name", "").lower() == model_name.lower():
                    logger.info(f"Found model '{model_name}' -> {model['id']}")
                    return model.get("id")

            logger.warning(f"Model '{model_name}' not found in group")
            return None

        except Exception as e:
            logger.error(f"Error fetching model by name: {type(e).__name__}: {e}")
            return None

    async def search_model(self, model_name: str) -> Tuple[Optional[str], Optional[str], Optional[str]]:
        """
        Search model by lookup across all projects and model groups.
        Used for minimal request payloads where project_id and model_group_id are not provided.

        Args:
            model_name (str): The model name to search for

        Returns:
            Tuple[Optional[str], Optional[str], Optional[str]]: (project_id, model_group_id, model_id) or (None, None, None)
        """
        try:
            await self._validate_env_vars()
            self._initialize_geti_sdk()
            
            logger.info(f"Searching model location for: {model_name}")
            
            # Get all projects
            projects = await self.get_projects()
            if not projects:
                logger.warning("No projects found in Geti server")
                return None, None, None
            
            # Search across each project and its model groups
            for project_info in projects:
                project_id = project_info["id"]
                project = project_info["project"]
                
                try:
                    # Get or create ModelClient
                    model_client = self._get_model_client(project_id)
                    if model_client is None:
                        model_client = ModelClient(
                            workspace_id=self.geti.workspace_id,
                            project=project,
                            session=self.geti.session
                        )
                        self._set_model_client(project_id, model_client)
                    
                    # Get all model groups and models
                    model_groups = await asyncio.to_thread(model_client.get_all_model_groups)
                    all_models = await asyncio.to_thread(model_client.get_latest_model_for_all_model_groups)
                    
                    # Search for matching model
                    for model in all_models:
                        if model.name.lower() == model_name.lower():
                            model_group_id = model.model_group_id
                            logger.info(f"Found model '{model_name}' in project={project_id}, model_group={model_group_id}, model_id={model.id}")
                            return project_id, model_group_id, model.id
                    
                except Exception as e:
                    logger.debug(f"Error searching project {project_id}: {type(e).__name__}: {e}")
                    continue
            
            logger.warning(f"Model '{model_name}' not found in any project or model group")
            return None, None, None
            
        except Exception as e:
            logger.error(f"Error during model discovery: {type(e).__name__}: {e}")
            return None, None, None

    async def get_model_group(self, project_id: str, model_group_id: str) -> Optional[Dict[str, Any]]:
        """
        Retrieve model group with all its models.

        Args:
            project_id (str): The project ID
            model_group_id (str): The model group ID

        Returns:
            Optional[Dict[str, Any]]: Model group data with 'id', 'name', 'models', 'model_group'
        """
        await self._validate_env_vars()
        self._initialize_geti_sdk()

        try:
            logger.info(f"Fetching model group {model_group_id}")
            
            # Get project
            projects = await self.get_projects(project_id=project_id)
            if not projects:
                logger.error(f"Project {project_id} not found")
                return None

            project = projects[0]["project"]
            
            # Create or get ModelClient (cached per project)
            model_client = self._get_model_client(project_id)
            if model_client is None:
                model_client = ModelClient(
                    workspace_id=self.geti.workspace_id,
                    project=project,
                    session=self.geti.session
                )
                self._set_model_client(project_id, model_client)

            # Fetch model groups and models
            model_groups = await asyncio.to_thread(model_client.get_all_model_groups)
            target_mg = next((mg for mg in model_groups if mg.id == model_group_id), None)
            
            if not target_mg:
                logger.warning(f"Model group {model_group_id} not found")
                return None

            # Get all models and filter by group
            all_models = await asyncio.to_thread(model_client.get_latest_model_for_all_model_groups)
            models_in_group = [
                {"id": m.id, "name": m.name, "model": m}
                for m in all_models
                if m.model_group_id == model_group_id
            ]

            result = {
                "id": target_mg.id,
                "name": target_mg.name,
                "models": models_in_group,
                "model_group": target_mg
            }

            logger.info(f"Model group loaded: {len(models_in_group)} models")
            return result

        except GetiRequestException as e:
            logger.error(f"Geti API error: {e.message}")
            return None
        except Exception as e:
            logger.error(f"Error retrieving model group: {type(e).__name__}: {e}")
            return None

    async def _download_model_from_geti(
        self, model_id: str, output_dir: str, model_name: str = "", **kwargs
    ) -> Optional[str]:
        """
        Download model files from Geti server using cached clients.

        Args:
            model_id (str): Base model ID (for optimized exports, this is the base)
            output_dir (str): Output directory path
            model_name (str, optional): Model name for logging
            **kwargs: export_type, optimized_model_id, project_id, model_group_id

        Returns:
            Optional[str]: Path to downloaded model or None if failed
        """
        await self._validate_env_vars()
        self._initialize_geti_sdk()

        export_type = kwargs.get("export_type")
        model_group_id = kwargs.get("model_group_id")
        project_id = kwargs.get("project_id")
        optimized_model_id = kwargs.get("optimized_model_id")
        precision = kwargs.get("precision")

        try:
            # Get project (cached)
            projects = await self.get_projects(project_id=project_id)
            if not projects:
                logger.error(f"Project not found: {project_id}")
                return None

            project = projects[0]["project"]

            # Get or create ModelClient (cached)
            model_client = self._get_model_client(project_id)
            if model_client is None:
                model_client = ModelClient(
                    workspace_id=self.geti.workspace_id,
                    project=project,
                    session=self.geti.session
                )
                self._set_model_client(project_id, model_client)

            logger.info(f"Getting model: {model_id}")
            model = await asyncio.to_thread(model_client._get_model_detail, model_group_id, model_id)
            if not model:
                logger.error(f"Model not found: {model_id}")
                return None

            # Prepare output directory
            hub_dir = os.path.join(output_dir, "geti")
            model_dir = os.path.join(hub_dir, f"{precision}/{model_name}")
            os.makedirs(model_dir, exist_ok=True)

            # Select model variant to download
            if export_type == "optimized":
                model_to_download = self._select_optimized_model(
                    model, optimized_model_id, precision, model_id
                )
                if not model_to_download:
                    logger.error(f"No optimized models for {model_id}")
                    return None
                logger.info(f"Downloading optimized: {model_to_download.name}")
                await asyncio.to_thread(model_client._download_model, model_to_download, model_dir)
            else:
                logger.info(f"Downloading base model: {model_id}")
                await asyncio.to_thread(model_client._download_model, model, model_dir)

            # Reorganize SDK output structure
            self._extract_model_files(model_dir)

            logger.info(f"Model downloaded: {model_dir}")
            return model_dir

        except GetiRequestException as e:
            logger.error(f"Geti API error: {e.message}")
            raise
        except Exception as e:
            logger.error(f"Download failed: {type(e).__name__}: {e}")
            raise

    def _select_optimized_model(self, model: Any, optimized_model_id: Optional[str], 
                               precision: Optional[str], base_model_id: str) -> Optional[Any]:
        """
        Select optimized model variant.
        
        Strategy:
        1. If optimized_model_id provided, find exact match
        2. If precision provided, find model with matching precision
        3. Otherwise, use first available
        4. If none available, return None
        """
        if optimized_model_id:
            # Direct lookup by ID (O(n) but small n)
            model_found = next(
                (om for om in model.optimized_models if om.id == optimized_model_id),
                None
            )
            if model_found:
                logger.info(f"Selected optimized by ID: {model_found.name}")
                return model_found
            logger.warning(f"Optimized model {optimized_model_id} not found, trying precision")

        if precision:
            # Lookup by precision field
            model_found = next(
                (om for om in model.optimized_models if hasattr(om, 'precision') and om.precision == precision),
                None
            )
            if model_found:
                logger.info(f"Selected optimized model with precision '{precision}': {model_found.name}")
                return model_found
            logger.warning(f"No optimized model found with precision '{precision}', selecting first available")

        # select first available
        if model.optimized_models:
            selected = model.optimized_models[0]
            logger.info(f"Selected optimized: {selected.name}")
            return selected

        return None

    def _extract_model_files(self, model_dir: str) -> None:
        """
        Extract SDK's nested model structure up one level.
        SDK places models in 'models' subdirectory, we extract to parent.
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
                else:
                    shutil.copy2(src, dst)
            shutil.rmtree(models_subdir)
            logger.info(f"Extracted model files from: {models_subdir}")
        except Exception as e:
            logger.warning(f"File extraction issue: {e}")

    async def download(self, model_name: str, output_dir: str, **kwargs) -> Dict[str, Any]:
        """
        Download OpenVINO models from Geti server.

        Entry point: orchestrates project/model lookup and download.

        Args:
            model_name (str): Model name to download
            output_dir (str): Output directory for model files
            **kwargs: Must contain 'config' dict with parameters (except model_name, hub, type):
                      - project_id (opt): Project ID
                      - model_group_id (opt): Model group ID
                      - model_id (opt): Model ID
                      - export_type (opt): 'base' or 'optimized'
                      - optimized_model_id (opt): Optimized model ID
                      - precision (opt): Model precision (default: FP16)

        Returns:
            Dict[str, Any]: {success, download_path, error?, model_id, export_type, ...}
        """
        try:
            # Extract config dict from kwargs (all parameters except model_name, hub, type)
            config = kwargs.get("config", {})

            project_id = config.get("project_id")
            model_group_id = config.get("model_group_id")
            export_type = (config.get("export_type") or "base").lower()
            precision = (config.get("precision") or "FP16").lower()
            model_id = config.get("model_id")
            optimized_model_id = config.get("optimized_model_id")

            logger.info(f"Geti download: {model_name} ({export_type}) -> {output_dir}")

            # Get model_id (from config or lookup by name)
            if not model_id:
                logger.info(f"Looking up model: {model_name}")
                
                # If project_id and model_group_id not provided, search them
                if not project_id or not model_group_id:
                    logger.info("Searching model location ")
                    search_project_id, search_model_group_id, search_model_id = await self.search_model(model_name)
                    
                    if search_model_id:
                        project_id = search_project_id
                        model_group_id = search_model_group_id
                        model_id = search_model_id
                        logger.info(f"Search successful: project={project_id}, group={model_group_id}")
                    else:
                        return {"success": False, "error": f"Model not found: {model_name}"}
                else:
                    # Use the provided IDs to look up model
                    model_id = await self.get_model_id_by_name(project_id, model_group_id, model_name)
                    if not model_id:
                        return {"success": False, "error": f"Model not found: {model_name}"}
            else:
                logger.info(f"Using provided model_id: {model_id}")
                # If only model_id provided but not project/group, search those
                if not project_id or not model_group_id:
                    logger.info("Searching project and model group for provided model_id")
                    search_project_id, search_model_group_id, _ = await self.search_model(model_name)
                    if search_project_id and search_model_group_id:
                        project_id = search_project_id
                        model_group_id = search_model_group_id
                        logger.info(f"Search successful: project={project_id}, group={model_group_id}")

            # Download model
            model_path = await self._download_model_from_geti(
                model_id, output_dir, model_name,
                export_type=export_type,
                project_id=project_id,
                model_group_id=model_group_id,
                optimized_model_id=optimized_model_id,
                precision=precision
                
            )

            if not model_path:
                return {"success": False, "error": "Download failed"}

            # Prepare response path
            host_path = os.path.join(output_dir, "geti")
            if host_path.startswith("/opt/models/"):
                host_path = host_path.replace(
                    "/opt/models/",
                    f"{os.getenv('MODEL_PATH', 'models')}/"
                )

            logger.info(f"Download complete: {host_path}")

            return {
                "model_name": model_name,
                "source": "geti",
                "download_path": host_path,
                "success": True,
                "model_id": model_id,
                "model_group_id": model_group_id,
                "export_type": export_type,
                "model_format": "OpenVINO" if export_type == "optimized" else "Base"
            }

        except Exception as e:
            logger.error(f"Download error: {type(e).__name__}: {e}")
            return {"success": False, "error": str(e)}

    def get_download_tasks(self, model_name: str, **kwargs) -> List[DownloadTask]:
        """Geti plugin does not support task-based downloading"""
        raise NotImplementedError("Geti plugin does not support task-based downloading")

    def download_task(self, task: DownloadTask, output_dir: str, **kwargs) -> str:
        """Geti plugin does not support task-based downloading"""
        raise NotImplementedError("Geti plugin does not support task-based downloading")

    async def post_process(
        self, model_name: str, output_dir: str, downloaded_paths: List[str], **kwargs
    ) -> Dict[str, Any]:
        """Post-process downloaded Geti models"""
        return {
            "model_name": model_name,
            "source": "geti",
            "download_path": output_dir,
            "success": True,
        }


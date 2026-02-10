# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from abc import ABC, abstractmethod
from typing import Optional, Dict, Any, List

class DownloadTask:
    """
    Represents a sub-task in a model download process.
    Used for parallel downloading of model files.
    """
    def __init__(self, file_id: str, url: str, destination: str):
        self.file_id = file_id
        self.url = url
        self.destination = destination

class ModelDownloadPlugin(ABC):
    @property
    def plugin_name(self) -> str:
        """Return the name of the plugin"""
        return self.__class__.__name__.lower()
        
    @property
    def plugin_type(self) -> str:
        """Return the type of the plugin (downloader/converter)"""
        return "downloader"
    
    def can_handle(self, model_name: str,hub: str, **kwargs) -> bool:
        """
        Check if this plugin can handle the given model name.
        Plugins should override this to implement their specific logic.
        """
        return False
        
    def get_download_tasks(self, model_name: str, **kwargs) -> List[DownloadTask]:
        """
        Get list of download tasks for a model.
        Used for parallel downloading.
        """
        raise NotImplementedError("This plugin does not support task-based downloading")
    
    def download_task(self, task: DownloadTask, output_dir: str, **kwargs) -> str:
        """
        Download a single task file.
        Used for parallel downloading.
        """
        raise NotImplementedError("This plugin does not support task-based downloading")
    
    async def post_process(self, model_name: str, output_dir: str, downloaded_paths: List[str], **kwargs) -> Dict[str, Any]:
        """
        Post-process downloaded files.
        Called after all files have been downloaded.
        """
        # Default implementation just returns basic info
        return {
            "model_name": model_name,
            "download_path": output_dir,
            "success": True
        }
    
    @abstractmethod
    async def download(self, model_name: str, output_dir: str, **kwargs) -> Dict[str, Any]:
        pass
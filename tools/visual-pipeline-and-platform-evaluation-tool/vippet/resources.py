import os
import sys
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger("resources")

# Default directories for resources
DEFAULT_LABELS_DIR = "/home/dlstreamer/dlstreamer/samples/labels"
DEFAULT_SCRIPTS_DIR = "/scripts"
DEFAULT_PUBLIC_MODEL_PROC_DIR = (
    "/home/dlstreamer/dlstreamer/samples/gstreamer/model_proc/public"
)

# Read resource paths from environment variables if set
LABELS_PATH = os.path.normpath(os.environ.get("LABELS_PATH", DEFAULT_LABELS_DIR))
SCRIPTS_PATH = os.path.normpath(os.environ.get("SCRIPTS_PATH", DEFAULT_SCRIPTS_DIR))
PUBLIC_MODEL_PROC_PATH = os.path.normpath(
    os.environ.get("PUBLIC_MODEL_PROC_PATH", DEFAULT_PUBLIC_MODEL_PROC_DIR)
)


# Singleton instance for LabelsManager
_labels_manager_instance: Optional["DirectoryResourceManager"] = None


def get_labels_manager() -> "DirectoryResourceManager":
    """
    Returns the singleton instance of LabelsManager.
    If it cannot be created, logs an error and exits the application.
    """
    global _labels_manager_instance
    if _labels_manager_instance is None:
        try:
            _labels_manager_instance = DirectoryResourceManager(LABELS_PATH)
        except Exception as e:
            logger.error(f"Failed to initialize LabelsManager: {e}")
            sys.exit(1)
    return _labels_manager_instance


# Singleton instance for ScriptsManager
_scripts_manager_instance: Optional["DirectoryResourceManager"] = None


def get_scripts_manager() -> "DirectoryResourceManager":
    """
    Returns the singleton instance of ScriptsManager.
    If it cannot be created, logs an error and exits the application.
    """
    global _scripts_manager_instance
    if _scripts_manager_instance is None:
        try:
            _scripts_manager_instance = DirectoryResourceManager(SCRIPTS_PATH)
        except Exception as e:
            logger.error(f"Failed to initialize ScriptsManager: {e}")
            sys.exit(1)
    return _scripts_manager_instance


# Singleton instance for PublicModelProcManager
_public_model_proc_manager_instance: Optional["DirectoryResourceManager"] = None


def get_public_model_proc_manager() -> "DirectoryResourceManager":
    """
    Returns the singleton instance of PublicModelProcManager.
    If it cannot be created, logs an error and exits the application.
    """
    global _public_model_proc_manager_instance
    if _public_model_proc_manager_instance is None:
        try:
            _public_model_proc_manager_instance = DirectoryResourceManager(
                PUBLIC_MODEL_PROC_PATH
            )
        except Exception as e:
            logger.error(f"Failed to initialize PublicModelProcManager: {e}")
            sys.exit(1)
    return _public_model_proc_manager_instance


class DirectoryResourceManager:
    """Manages resources in a specific directory."""

    def __init__(self, directory: Path | str):
        self.directory = Path(directory)

    def get_filename(self, path: str) -> str:
        """Extract filename from path."""
        filename = Path(path).name
        return filename

    def get_path(self, filename: str) -> str | None:
        """Get full path if file exists in directory."""
        if self.file_exists(filename):
            return str(self.directory / filename)
        return None

    def file_exists(self, filename: str) -> bool:
        """Check if file exists in managed directory."""
        return (self.directory / filename).is_file()

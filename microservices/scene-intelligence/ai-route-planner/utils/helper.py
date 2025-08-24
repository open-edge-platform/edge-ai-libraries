from pathlib import Path

from config import GPX_DIR
from utils.logging_config import get_logger

logger = get_logger(__name__)


def get_all_available_route_files() -> list[Path]:
    """
    Get a list of all available GPX route files in the GPX_DIR.

    Returns:
        list[Path]: List of GPX file paths
    """
    if not GPX_DIR.is_dir():
        logger.error("Error reading GPX Routes Directory")
        return []

    return [
        Path(f).name
        for f in GPX_DIR.iterdir()
        if f.is_file() and str(f).endswith(".gpx")
    ]

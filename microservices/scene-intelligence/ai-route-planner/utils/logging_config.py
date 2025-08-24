import logging
import os
from datetime import datetime


def setup_logging(log_level=logging.DEBUG):
    """Setup application logging configuration"""

    # Create logs directory if it doesn't exist
    log_dir = os.path.dirname(os.path.abspath(__file__))
    log_file = os.path.join(log_dir, "..", "route_app.log")

    # Configure logging
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[logging.FileHandler(log_file), logging.StreamHandler()],
    )

    logger = logging.getLogger(__name__)
    logger.info(f"Logging initialized at {datetime.now()}")

    return logger


def get_logger(name):
    """Get a logger instance for the given name"""
    return logging.getLogger(name)

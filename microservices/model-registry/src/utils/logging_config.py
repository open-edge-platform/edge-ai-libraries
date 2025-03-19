"""Logging Configuration"""
import logging
import os

def configure_alembic_logger():
    """_summary_
    """
    a_logger = logging.getLogger('alembic.runtime.migration')
    a_logger.setLevel(logging.ERROR)


def configure_mr_logger():
    """Configure the logger and return it

    Returns:
        Logger: the logger
    """
    mr_logger = logging.getLogger(name="mr")

    if len(mr_logger.handlers) == 0:
        min_log_level = os.getenv("MIN_LOG_LEVEL", "INFO").upper()
        log_level_int = getattr(logging, min_log_level)
        mr_logger.setLevel(log_level_int)
        stream_handler = logging.StreamHandler()
        formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
        stream_handler.setFormatter(formatter)
        mr_logger.addHandler(stream_handler)
        mr_logger.propagate = False

    return mr_logger

logger = configure_mr_logger()

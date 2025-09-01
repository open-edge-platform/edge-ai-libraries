from .config import config
from typing import Optional
import logging
import sys


def initialize_logger(name: Optional[str] = None) -> logging.Logger:
    """
    Initializes and returns a logger with a specific configuration.
    If a logger with the given name does not already have handlers, this function sets up a stream handler
    that outputs to stdout, with a formatter that includes timestamp, logger name, filename, line number,
    log level, and message. The log level is set to DEBUG if config.DEBUG is True, otherwise INFO.
    Args:
        name (Optional[str]): The name of the logger. If None, uses the module's __name__.
    Returns:
        logging.Logger: The configured logger instance.
    """

    logger_name = name if name else __name__
    logger = logging.getLogger(logger_name)

    if not logger.handlers:
        log_level = logging.DEBUG if config.DEBUG else logging.INFO
        logger.setLevel(log_level)

        handler = logging.StreamHandler(sys.stdout)
        handler.setLevel(log_level)

        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(filename)s:%(lineno)d - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )

        handler.setFormatter(formatter)

        logger.addHandler(handler)

    return logger


# Optional: create a default logger instance for convenience
logger = initialize_logger(config.APP_DISPLAY_NAME)

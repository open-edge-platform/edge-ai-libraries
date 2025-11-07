# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import structlog
import sys

class Colors:
    RESET = "\033[0m"
    RED = "\033[31m"
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    BLUE = "\033[34m"
    MAGENTA = "\033[35m"
    CYAN = "\033[36m"
    WHITE = "\033[37m"
    BOLD = "\033[1m"

# Only use colors when output is to a terminal
USE_COLORS = sys.stdout.isatty()

def get_colored_message(message, color):
    """Apply color to message if output is to a terminal"""
    if USE_COLORS:
        return f"{color}{message}{Colors.RESET}"
    return message

def log_info(message):
    """Log info messages in green"""
    if not USE_COLORS or not structlog.is_configured():
        logger.info(message)
    else:
        logger.info(get_colored_message(message, Colors.GREEN))

def log_error(message):
    """Log error messages in red"""
    if not USE_COLORS or not structlog.is_configured():
        logger.error(message)
    else:
        logger.error(get_colored_message(message, Colors.RED))

def log_warning(message):
    """Log warning messages in yellow"""
    if not USE_COLORS or not structlog.is_configured():
        logger.warning(message)
    else:
        logger.warning(get_colored_message(message, Colors.YELLOW))

# Configure structlog
processors = [
    structlog.processors.TimeStamper(fmt="iso"),
    lambda _, __, event_dict: dict(event_dict, service_name="model_download"),
]

if USE_COLORS and sys.stdout.isatty():
    # Use ConsoleRenderer with colors for terminal output
    processors.append(structlog.dev.ConsoleRenderer(colors=True))
else:
    # Use JSONRenderer for non-terminal output or when colors are disabled
    processors.append(structlog.processors.JSONRenderer())

structlog.configure(
    processors=processors,
    cache_logger_on_first_use=True,  # Improve performance
)

# Create logger
logger = structlog.get_logger()

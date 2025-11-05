# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import logging
import sys
from typing import Optional

from video_analyzer.core.settings import settings


def setup_logger(name: Optional[str] = None) -> logging.Logger:
    """
    Configure and return a logger with the specified name.
    
    Args:
        name: Name for the logger, defaults to the module name
        
    Returns:
        Configured logger instance
    """
    logger_name = name if name else __name__
    logger = logging.getLogger(logger_name)
    
    if not logger.handlers:
        # Set log level based on debug setting
        log_level = logging.DEBUG if settings.DEBUG else logging.INFO
        logger.setLevel(log_level)
        
        handler = logging.StreamHandler(sys.stdout)
        handler.setLevel(log_level)
        
        # Create formatter with filename and line number
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(filename)s:%(lineno)d - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        handler.setFormatter(formatter)
        
        logger.addHandler(handler)
    
    return logger


logger = setup_logger("video_analyzer")
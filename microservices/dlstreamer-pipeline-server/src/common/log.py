#
# Apache v2 license
# Copyright (C) 2024 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
#

"""Logging utilities
"""
import os
import sys
from distutils.util import strtobool
import logging

LOG_LEVELS = {
    'DEBUG': logging.DEBUG,
    'INFO': logging.INFO,
    'ERROR': logging.ERROR,
    'WARN': logging.WARN
}

# Globals
LOG_LEVEL = None

def configure_logging(log_level):
    """Set the global variables for the logging utilities.
    :param str log_level: Global application log level
    """
    global LOG_LEVEL

    log_level = log_level.upper()

    LOG_LEVEL = log_level


def get_logger(name):
    """Get a new logger with the specified name.

    :param str name: Logger name
    :return: New Python logger
    """
    logger = logging.getLogger(__name__)
    if 'LOG_LEVEL' in os.environ and os.environ['LOG_LEVEL'].upper() in LOG_LEVELS:
        logger.setLevel(LOG_LEVELS[os.environ['LOG_LEVEL'].upper()])
    else:
        logger.setLevel(logging.INFO)
    logger.propagate = True
    formatter = logging.Formatter(
        "%(asctime)s - %(levelname)s - %(module)s\t - %(funcName)s [%(lineno)3d] - %(message)s")
    streamHandler = logging.StreamHandler(sys.stdout)
    streamHandler.setFormatter(formatter)

    if len(logger.handlers):
        for handler in logger.handlers:
            logger.removeHandler(handler)

    logger.addHandler(streamHandler)

    return logger

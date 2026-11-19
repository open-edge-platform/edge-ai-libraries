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


# Dedicated audit trail for pipeline lifecycle actions (start/stop/request),
# separate from general application logs so it can be shipped/retained
# independently. Writes to stdout (captured by container logging) and to
# AUDIT_LOG_PATH for in-container persistence. Defaults to the app-owned
# pipeline_root scratch dir (not the shared, world-writable /tmp - see
# CWE-377) matching the convention already used elsewhere in this service.
AUDIT_LOG_PATH = os.environ.get('AUDIT_LOG_PATH', '/var/cache/pipeline_root/dlsps_audit.log')


def get_audit_logger():
    """Get the shared structured audit logger.

    :return: Python logger configured for audit entries
    """
    logger = logging.getLogger('audit')
    logger.setLevel(logging.INFO)
    logger.propagate = False

    if not logger.handlers:
        formatter = logging.Formatter("%(message)s")

        stream_handler = logging.StreamHandler(sys.stdout)
        stream_handler.setFormatter(formatter)
        logger.addHandler(stream_handler)

        try:
            file_handler = logging.FileHandler(AUDIT_LOG_PATH)
            file_handler.setFormatter(formatter)
            logger.addHandler(file_handler)
        except OSError:
            pass  # best-effort - audit entries still reach stdout

    return logger


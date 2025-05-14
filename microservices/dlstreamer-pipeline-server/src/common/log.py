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

if os.getenv("RUN_MODE") == "EII":
    import util.log as eii_logging
else:
    import logging

    LOG_LEVELS = {
        'DEBUG': logging.DEBUG,
        'INFO': logging.INFO,
        'ERROR': logging.ERROR,
        'WARN': logging.WARN
    }

# Globals
DEV_MODE = None
LOG_LEVEL = None

def configure_logging(log_level, dev_mode):
    """Set the global variables for the logging utilities.

    :param str log_level: Global application log level
    :param bool dev_mode: Flag for whether the service is running in dev mode
    """
    global DEV_MODE
    global LOG_LEVEL

    log_level = log_level.upper()
    # assert log_level in eii_logging.LOG_LEVEL, \
    #         f'Invalid log level: {log_level}'

    DEV_MODE = dev_mode
    LOG_LEVEL = log_level


def get_logger(name):
    """Get a new logger with the specified name.

    :param str name: Logger name
    :return: New Python logger
    """
    if os.getenv('RUN_MODE') == "EII":

        global DEV_MODE
        global LOG_LEVEL
        if 'DEV_MODE' in os.environ:
            dev_mode = strtobool(os.environ['DEV_MODE'])
        else:
            # By default, this will run NOT in dev mode
            dev_mode = False

        if 'LOG_LEVEL' in os.environ:
            log_level = os.environ['LOG_LEVEL'].upper()
        else:
            # Default log level is INFO
            log_level = 'INFO'

        # Configure DLStreamer Pipeline Server logging globals
        configure_logging(log_level, dev_mode)
        return eii_logging.configure_logging(LOG_LEVEL, name, DEV_MODE)
    else:
        logger = logging.getLogger(__name__)
        if 'LOG_LEVEL' in os.environ and os.environ['LOG_LEVEL'].upper() in LOG_LEVELS:
            logger.setLevel(LOG_LEVELS[os.environ['LOG_LEVEL'].upper()])
        else:
            logger.setLevel(logging.INFO)
        logger.propagate = 0
        formatter = logging.Formatter(
            "%(asctime)s - %(levelname)s - %(module)s\t - %(funcName)s [%(lineno)3d] - %(message)s")
        streamHandler = logging.StreamHandler(sys.stdout)
        streamHandler.setFormatter(formatter)

        if len(logger.handlers):
            for handler in logger.handlers:
                logger.removeHandler(handler)

        logger.addHandler(streamHandler)

        return logger

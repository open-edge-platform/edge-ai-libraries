# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import importlib.util
import traceback

from audio_analyzer.utils.logger import logger


def is_intel_gpu_available() -> bool:
    """
    Check if Intel GPU is available for acceleration with OpenVINO.
    
    Returns:
        True if Intel GPU is available, False otherwise
    """
    logger.debug("Checking Intel GPU availability with OpenVINO")
    
    # Check for OpenVINO
    try:
        if importlib.util.find_spec("openvino") and importlib.util.find_spec("openvino_genai"):
            
            import openvino as ov
            
            core = ov.Core()
            available_devices = core.available_devices
            
            # Check if GPU is available
            if "GPU" in available_devices:
                logger.info("Intel GPU detected and available with OpenVINO")
                return True
            else:
                logger.warning("OpenVINO installed but GPU is not available")
        else:
            logger.warning("Required OpenVINO packages not found")
    except Exception as e:
        logger.error(f"Error checking Intel GPU availability: {e}")
        logger.debug(f"Error details: {traceback.format_exc()}")
    
    # If we reach here, no Intel GPU was found or OpenVINO is not avaialable
    return False
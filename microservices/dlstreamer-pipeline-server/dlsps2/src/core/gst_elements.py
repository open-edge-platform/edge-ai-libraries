# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
GStreamer element discovery and inspection utilities.
"""

import logging
import subprocess
import sys
from typing import Optional

logger = logging.getLogger(__name__)


def get_available_elements() -> list[dict]:
    """
    Get list of available GStreamer elements.
    
    Returns:
        List of element info dicts with keys: name, description, type, plugin
    """
    try:
        logger.info("Querying GStreamer elements...")
        
        # Use gst-inspect-1.0 to list all elements
        result = subprocess.run(
            ["gst-inspect-1.0"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=10,
        )
        
        logger.debug("gst-inspect-1.0 exit code: %d", result.returncode)
        
        if result.returncode != 0:
            logger.warning("gst-inspect-1.0 failed: %s", result.stderr[:200] if result.stderr else "(no error message)")
            return []
        
        elements = []
        
        # Show first few lines for debugging
        lines_list = result.stdout.splitlines()
        logger.debug("gst-inspect-1.0 output: %d lines total", len(lines_list))
        if lines_list:
            logger.debug("First 5 lines: %s", lines_list[:5])
        
        # Format: "group:  element: description"
        for line in lines_list:
            line = line.strip()
            
            # Skip empty lines
            if not line:
                continue
            
            # Parse format: "group:  element: description"
            parts = line.split(":", 2)  # Split on first two colons
            if len(parts) >= 3:
                plugin = parts[0].strip()  # group name
                name = parts[1].strip()    # element name
                description = parts[2].strip()  # description
                
                elements.append({
                    "name": name,
                    "plugin": plugin,
                    "description": description,
                })
                logger.debug("Found element: %s (plugin: %s)", name, plugin)
            else:
                logger.debug("Could not parse line: %r", line)
        
        logger.info("Found %d GStreamer elements", len(elements))
        
        return sorted(elements, key=lambda x: x["name"])
    
    except FileNotFoundError:
        logger.warning("gst-inspect-1.0 not found; GStreamer element discovery unavailable")
        return []
    except subprocess.TimeoutExpired:
        logger.warning("gst-inspect-1.0 timed out")
        return []
    except Exception as e:  # noqa: BLE001
        logger.error("Failed to get GStreamer elements: %s", e, exc_info=True)
        return []


def get_element_info(element_name: str) -> Optional[dict]:
    """
    Get detailed information about a specific GStreamer element.
    
    Args:
        element_name: Name of the element to inspect
    
    Returns:
        Element info dict or None if not found
    """
    try:
        logger.info("Querying info for element: %s", element_name)
        
        # First, get all elements and find basic info
        result = subprocess.run(
            ["gst-inspect-1.0"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=10,
        )
        
        if result.returncode != 0:
            logger.warning("gst-inspect-1.0 failed: %s", result.stderr[:200] if result.stderr else "(no error message)")
            return None
        
        basic_info = None
        
        # Format: "plugin:  element: description"
        for line in result.stdout.splitlines():
            line = line.strip()
            
            if not line:
                continue
            
            # Parse format: "group:  element: description"
            parts = line.split(":", 2)
            if len(parts) >= 3:
                plugin = parts[0].strip()
                name = parts[1].strip()
                description = parts[2].strip()
                
                if name == element_name:
                    basic_info = {
                        "name": name,
                        "plugin": plugin,
                        "description": description,
                    }
                    logger.info("Found element: %s (plugin: %s)", name, plugin)
                    break
        
        if not basic_info:
            logger.warning("Element '%s' not found in GStreamer", element_name)
            return None
        
        # Now get full details from gst-inspect-1.0 element_name
        detail_result = subprocess.run(
            ["gst-inspect-1.0", element_name],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=5,
        )
        
        details = ""
        if detail_result.returncode == 0:
            details = detail_result.stdout
            logger.debug("Got full details for element: %s", element_name)
        else:
            logger.debug("Could not get full details for %s (exit code: %d)", element_name, detail_result.returncode)
            details = f"Element: {basic_info['name']}\nPlugin: {basic_info['plugin']}\nDescription: {basic_info['description']}"
        
        return {
            "name": basic_info["name"],
            "plugin": basic_info["plugin"],
            "description": basic_info["description"],
            "details": details,
        }
    
    except Exception as e:  # noqa: BLE001
        logger.error("Failed to get element info for %s: %s", element_name, e, exc_info=True)
        return None

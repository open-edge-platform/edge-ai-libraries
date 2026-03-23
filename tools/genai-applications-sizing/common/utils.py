# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
Utility functions for GenAI application performance profiling.

This module provides core utility functions and re-exports from submodules
for backward compatibility. Use specific submodule imports for new code:

- common.constants: Constants and magic numbers
- common.config: Configuration reading functions
- common.metrics: Metrics calculation and reporting
- common.video: Video file processing
- common.perf_tools: Performance tool management

Note: Gevent monkey-patching should be done at the entry point (profile-runner.py)
BEFORE any other imports to avoid ssl-related RecursionError.
"""

from gevent import monkey
if not monkey.is_module_patched('ssl'):
    monkey.patch_all()

import ast
import json
import os
import subprocess
from datetime import datetime

import requests

# Re-export everything from submodules for backward compatibility
from common.constants import (
    VIDEO_SUMMARY_TIMEOUT_SECONDS,
    POLLING_INTERVAL_SECONDS,
    PERF_TOOL_STOP_DELAY_SECONDS,
    DOCKER_REMOVAL_TIMEOUT_SECONDS,
    FRAME_EXTRACTION_RATIO,
    NORMALIZED_FPS_BASELINE,
    DIRECTORY_PERMISSION,
    UMASK_VALUE,
    DEFAULT_BUCKET_NAME,
    DEFAULT_MAX_TOKENS,
    DEFAULT_CAPTION_DURATION,
)

from common.config import (
    read_yaml_config,
    get_global_config,
    get_stream_log_config,
    get_document_config,
    get_profile_details,
    get_enabled_apis,
    get_stream_api_profile_details,
    get_document_api_profile_details,
    get_video_summary_config,
    get_video_search_config,
    get_enabled_video_apis,
    get_video_summary_profile_details,
    get_video_search_profile_details,
    get_live_caption_config,
    get_enabled_live_caption_apis,
    get_live_caption_profile_details,
    get_global_details,
)

from common.metrics import (
    calculate_metrics,
    write_metrics,
    write_chatqna_metrics_to_csv,
    write_rest_metrics,
    write_rest_metrics_summary_to_csv,
    rest_api_metrics,
    write_vss_metrics,
    write_video_summary_metrics,
    write_video_search_metrics,
    write_video_search_metrics_summary_to_csv,
    write_video_summary_metrics_summary_to_csv,
    get_video_summary_telemetry_kpis,
    get_video_search_telemetry_kpis,
    save_video_summary_search_telemetry_kpis,
    convert_summary_metrics_to_wsf_format,
    convert_search_metrics_to_wsf_format,
    get_live_caption_metrics,
    save_live_video_caption_telemetry_kpis,
    save_metrics_to_wsf_format,
)

from common.video import (
    get_video_details,
    upload_video_file,
    embedding_video_file,
    wait_for_video_summary_complete,
    get_video_summary,
    embedding_creation_per_sec,
    summarization_fps,
    convert_timestamp_to_float,
    get_live_caption_metadata,
    stop_all_run_request,
)

from common.perf_tools import (
    start_perf_tool,
    stop_perf_tool,
    plot_graphs,
    copy_perf_tools_logs,
)


# =============================================================================
# Core Utility Functions
# =============================================================================

def setup_report_permissions(report_dir):
    """
    Set up permissions on the report directory and configure umask for inheritance.
    
    All subdirectories and files created after this call will inherit permissions:
    - Directories: 0o770 (rwxrwx---)
    - Files: 0o660 (rw-rw----)
    
    Args:
        report_dir: Path to the root report directory.
    """
    os.umask(UMASK_VALUE)
    
    try:
        os.chmod(report_dir, DIRECTORY_PERMISSION)
    except OSError as e:
        print(f"Warning: Failed to set permissions on {report_dir}: {e}")


def safe_parse_string_to_dict(data_string):
    """
    Safely parse a string that contains either JSON or Python literal format.
    
    Tries JSON parsing first, then falls back to ast.literal_eval for Python literals.
    
    Args:
        data_string: String to parse.
        
    Returns:
        dict/list: Parsed data structure.
        
    Raises:
        ValueError: If parsing fails.
    """
    if not data_string or not isinstance(data_string, str):
        raise ValueError("Input must be a non-empty string")
    
    # First, try JSON parsing (safer)
    try:
        return json.loads(data_string)
    except (json.JSONDecodeError, ValueError):
        pass
    
    # Fall back to ast.literal_eval for Python literals
    try:
        return ast.literal_eval(data_string)
    except (ValueError, SyntaxError):
        raise ValueError(f"Cannot parse string: {data_string}. Must be valid JSON or Python literal.")


def get_ip_address():
    """
    Retrieve the IP address of the current machine.
    
    Returns:
        str: First IP address found, or empty string on error.
    """
    try:
        result = subprocess.run(["hostname", "-I"], capture_output=True, text=True, check=True)
        ip_addresses = result.stdout.strip().split()
        return ip_addresses[0] if ip_addresses else ""
    except Exception as e:
        print(f"Failed to retrieve IP address: {e}")
        return ""


def delete_existing_docs(url):
    """
    Delete all existing documents from the specified bucket.
    
    Args:
        url: The API endpoint URL for document deletion.
    """
    print("Deleting existing documents...")
    params = {"bucket_name": DEFAULT_BUCKET_NAME, "delete_all": True}
    
    try:
        response = requests.delete(url, params=params, timeout=30)
        
        if response.status_code == 204:
            print("All existing documents deleted.")
        elif response.status_code == 404:
            print("No existing documents to delete.")
        else:
            print(f"Failed to delete existing documents: {response.status_code}")
    except Exception as e:
        print(f"Error during document deletion: {e}")


def upload_document_before_conversation(url, filename, filepath):
    """
    Upload a document file to the specified endpoint for conversation context.
    
    Args:
        url: The upload API endpoint URL.
        filename: Name of the file to upload.
        filepath: Path to the file to upload.
        
    Returns:
        dict: File details containing name and size in MB.
    """
    print("Uploading file for the context...")
    file_details = {"name": filename, "size_mb": 0.0}
    
    try:
        file_size_bytes = os.path.getsize(filepath)
        file_size_mb = round(file_size_bytes / (1024 * 1024), 2)
        file_details["size_mb"] = file_size_mb

        delete_existing_docs(url)
        upload_files = [("files", (filename, open(filepath, 'rb'), 'application/octet-stream'))]
        upload_response = requests.request("POST", url=url, files=upload_files)
        
        if upload_response.status_code == 200:
            print(f"{filename} uploaded for the conversation context. Size: {file_size_mb} MB")
        else:
            print(f"{filename} upload failed with status code: {upload_response.status_code}")
            
    except FileNotFoundError:
        print(f"Error: File not found at {filepath}")
    except requests.exceptions.Timeout:
        print(f"Error: Upload request timed out for {filename}")
    except requests.exceptions.RequestException as e:
        print(f"Error: Upload request failed for {filename}: {e}")
    except Exception as e:
        print(f"Unexpected error during file upload: {e}")
    
    return file_details


def setup_document_upload(file_details):
    """
    Prepare a list of files for multipart/form-data upload.
    
    Args:
        file_details: List of dictionaries with 'path' and 'name' keys.
        
    Returns:
        list: List of tuples ready for requests.post(files=...).
    """
    upload_files = []
    for file_detail in file_details:
        file_path = file_detail["path"]
        file_name = file_detail["name"]
        with open(file_path, 'rb') as file_obj:
            file_content = file_obj.read()
        upload_files.append(("files", (file_name, file_content, 'application/octet-stream')))
    return upload_files


def get_response(response, report_dir, answer=None):
    """
    Handle streaming responses from chat APIs and save to file.
    
    This function processes streaming responses, removes protocol prefixes,
    and saves the result to a timestamped file.
    
    Args:
        response: HTTP response object (used if answer not provided).
        report_dir: Directory to save the response file.
        answer: Pre-processed answer string (optional).
    """
    responses_dir = os.path.join(report_dir, "responses")
    os.makedirs(responses_dir, exist_ok=True)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = os.path.join(responses_dir, f"chat_response_{timestamp}.txt")
    
    if answer is None:
        answer_parts = []
        for chunk in response.iter_lines():
            decoded_chunk = chunk.decode("utf-8")[6:]  # Strip data: prefix
            answer_parts.append(decoded_chunk)
        answer = "".join(answer_parts)
    
    try:
        with open(filename, "w") as file:
            file.write(answer)
        print(f"Response saved to: {filename}")
    except IOError as e:
        print(f"Error writing response to {filename}: {e}")


# All exported symbols
__all__ = [
    # Constants
    'VIDEO_SUMMARY_TIMEOUT_SECONDS',
    'POLLING_INTERVAL_SECONDS',
    'PERF_TOOL_STOP_DELAY_SECONDS',
    'DOCKER_REMOVAL_TIMEOUT_SECONDS',
    'FRAME_EXTRACTION_RATIO',
    'NORMALIZED_FPS_BASELINE',
    'DIRECTORY_PERMISSION',
    'UMASK_VALUE',
    'DEFAULT_BUCKET_NAME',
    'DEFAULT_MAX_TOKENS',
    'DEFAULT_CAPTION_DURATION',
    # Config
    'read_yaml_config',
    'get_global_config',
    'get_stream_log_config',
    'get_document_config',
    'get_profile_details',
    'get_enabled_apis',
    'get_stream_api_profile_details',
    'get_document_api_profile_details',
    'get_video_summary_config',
    'get_video_search_config',
    'get_enabled_video_apis',
    'get_video_summary_profile_details',
    'get_video_search_profile_details',
    'get_live_caption_config',
    'get_enabled_live_caption_apis',
    'get_live_caption_profile_details',
    'get_global_details',
    # Core functions (defined in this module)
    'setup_report_permissions',
    'safe_parse_string_to_dict',
    'get_ip_address',
    'delete_existing_docs',
    'upload_document_before_conversation',
    'setup_document_upload',
    'get_response',
    # Metrics
    'calculate_metrics',
    'write_metrics',
    'write_chatqna_metrics_to_csv',
    'write_rest_metrics',
    'write_rest_metrics_summary_to_csv',
    'rest_api_metrics',
    'write_vss_metrics',
    'write_video_summary_metrics',
    'write_video_search_metrics',
    'write_video_search_metrics_summary_to_csv',
    'write_video_summary_metrics_summary_to_csv',
    'get_video_summary_telemetry_kpis',
    'get_video_search_telemetry_kpis',
    'save_video_summary_search_telemetry_kpis',
    'convert_summary_metrics_to_wsf_format',
    'convert_search_metrics_to_wsf_format',
    'get_live_caption_metrics',
    'save_live_video_caption_telemetry_kpis',
    'save_metrics_to_wsf_format',
    # Video
    'get_video_details',
    'upload_video_file',
    'embedding_video_file',
    'wait_for_video_summary_complete',
    'get_video_summary',
    'embedding_creation_per_sec',
    'summarization_fps',
    'convert_timestamp_to_float',
    'get_live_caption_metadata',
    'stop_all_run_request',
    # Perf Tools
    'start_perf_tool',
    'stop_perf_tool',
    'plot_graphs',
    'copy_perf_tools_logs',
]

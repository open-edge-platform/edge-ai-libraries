# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
Utility functions for GenAI application performance profiling.

"""

import ast
import json
import os
from datetime import datetime
import requests


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
    DIRECTORY_PERMISSION = 0o770
    UMASK_VALUE = 0o007

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



def delete_existing_docs(url):
    """
    Delete all existing documents from the specified bucket.
    
    Args:
        url: The API endpoint URL for document deletion.
    """
    print("Deleting existing documents...")
    params = {"bucket_name": "appuser.gai.ragfiles", "delete_all": True}
    
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
    if not os.path.isfile(filepath):
        print(f"Error: File not found at {filepath}")
        return None
    
    try:
        file_size_bytes = os.path.getsize(filepath)
        file_size_mb = round(file_size_bytes / (1024 * 1024), 2)
        file_details["size_mb"] = file_size_mb

        delete_existing_docs(url)
        with open(filepath, 'rb') as file_obj:
            upload_files = [('files', (filename, file_obj, 'application/octet-stream'))]
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



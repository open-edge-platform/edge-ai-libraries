# Copyright (C) 2024 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import time
import sys
from gevent import monkey
monkey.patch_all()
import subprocess
import json
import ast
from datetime import datetime, timezone
import numpy as np
import csv
import os
import yaml
import requests
import shutil
from moviepy import VideoFileClip


def safe_parse_string_to_dict(data_string):
    """
    Safely parse a string that contains either JSON or Python literal format.
    Tries JSON parsing first, then falls back to ast.literal_eval for Python literals.
    
    Args:
        data_string (str): String to parse
        
    Returns:
        dict/list: Parsed data structure
        
    Raises:
        ValueError: If parsing fails
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


def read_yaml_config(config_path='config.yaml'):
    """
    Reads configuration from a YAML file.
    """
    if not os.path.exists(config_path):
        raise FileNotFoundError(f"Configuration file not found: {config_path}")
    with open(config_path, 'r') as file:
        return yaml.safe_load(file)


def get_global_config(config=None, config_path='config.yaml'):
    """
    Retrieves global configuration.
    """
    if config is None:
        config = read_yaml_config(config_path)
    return config.get('global', {})


def get_stream_log_config(config=None, config_path='config.yaml'):
    """
    Retrieves stream log API configuration.
    """
    if config is None:
        config = read_yaml_config(config_path)
    return config.get('apis', {}).get('stream_log', {})


def get_document_config(config=None, config_path='config.yaml'):
    """
    Retrieves document API configuration.
    """
    if config is None:
        config = read_yaml_config(config_path)
    return config.get('apis', {}).get('document', {})


def get_profile_details(profile_path='input_profiles.yaml', profile_name='stream_log_small_text'):
    """
    Retrieves profile details from a YAML file.
    """
    if not os.path.exists(profile_path):
        raise FileNotFoundError(f"Profile file not found: {profile_path}")
    with open(profile_path, 'r') as file:
        profiles = yaml.safe_load(file)
        return profiles.get('profiles', {}).get(profile_name, {})


def get_ip_address():
    """
    Retrieves the IP address of the current machine.
    """
    try:
        result = subprocess.run(["hostname", "-I"], capture_output=True, text=True, check=True)
        ip_addresses = result.stdout.strip().split()
        return ip_addresses[0] if ip_addresses else ""
    except Exception as e:
        print(f"Failed to retrieve IP address: {e}")
        return ""


def write_metrics(metrics, report_dir):
    """
    Writes metrics to a JSON file.
    """
    latencies, input_tokens, output_tokens, ttfts, itls, tpss = [], [], [], [], [], []
    #timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = os.path.join(report_dir, f"chat_api_individual_metrics.json")
    try:
        with open(filename, "a") as file:
            for metric in metrics:
                json.dump(metric, file, indent=4)
                latencies.append(metric["LATENCY (ms)"])
                ttfts.append(metric["TTFT (ms)"])
                itls.append(metric["ITL (ms)"])
                tpss.append(metric["TPS"])
                input_tokens.append(metric["INPUT_TOKENS"])
                output_tokens.append(metric["OUTPUT_TOKENS"])                
        return latencies, input_tokens, output_tokens, ttfts, itls, tpss
    except Exception as e:
        print(f"Failed to write metrics to file: {e}")
        return [], [], [], [], [], []


def calculate_metrics(latencies):
    """
    Calculates statistical metrics for a given dataset.

    Args:
        latencies (list): List of numerical values.

    Returns:
        tuple: Average, min, max, p99, p90, and p75 values.
    """
    try:
        return (
            round(np.mean(latencies), 2),
            round(np.min(latencies), 2),
            round(np.max(latencies), 2),
            round(np.percentile(latencies, 99), 2),
            round(np.percentile(latencies, 90), 2),
            round(np.percentile(latencies, 75), 2),
        )
    except Exception as e:
        print(f"Failed to calculate metrics: {e}")
        return None, None, None, None, None, None

def write_chatqna_metrics_to_csv(report_dir, latencies, input_tokens, output_tokens, ttfts, itls, tpss, file_details):
    """
    Writes metrics summary to CSV files (both detailed and WSF format).

    Args:
        report_dir (str): Directory to save the CSV files.
        latencies (list): List of latencies.
        input_tokens (list): List of input tokens.
        output_tokens (list): List of output tokens.
        ttfts (list): List of time-to-first-token values.
        itls (list): List of inter-token latencies.
        tpss (list): List of tokens per second.
        file_details (dict): Details of the file including name and size.
    """
    summary_file = os.path.join(report_dir, "chat_api_summary_metrics.csv")
    wsf_file = os.path.join(report_dir, "chatqna_metrics_wsf.csv")
    
    try:
        throughput = len(latencies) / (sum(latencies) / 1000) if sum(latencies) > 0 else 0
        
        # Calculate detailed metrics for summary file
        detailed_metrics = {
            "Request Latency (ms)": calculate_metrics(latencies),
            "Time to First Token (ms)": calculate_metrics(ttfts),
            "Inter Token Latency (ms)": calculate_metrics(itls),           
            "Tokens Per Second": calculate_metrics(tpss),
            "Input Tokens": calculate_metrics(input_tokens),
            "Output Tokens": calculate_metrics(output_tokens)            
        }
        
        # Write detailed summary metrics CSV
        with open(summary_file, mode='w', newline='') as file:
            writer = csv.writer(file)
            writer.writerow(['Metric', 'Avg', 'Min', 'Max', 'p99', 'p90', 'p75'])
            for metric_name, values in detailed_metrics.items():
                writer.writerow([metric_name, *values])
            writer.writerow(['Throughput', round(throughput, 2), 'NA', 'NA', 'NA', 'NA', 'NA'])
            writer.writerow(['File Name', file_details.get("name", "N/A"), '', '', '', '', ''])
            writer.writerow(['File Size (MB)', file_details.get("size_mb", "N/A"), '', '', '', '', ''])
        
        # Calculate WSF metrics (averages only)
        wsf_metrics = {
            "Request Latency (ms)": round(np.mean(latencies), 2),
            "Time to First Token (ms)": round(np.mean(ttfts), 2),
            "Inter Token Latency (ms)": round(np.mean(itls), 2),           
            "Tokens Per Second": round(np.mean(tpss), 2),
            "Input Tokens": round(np.mean(input_tokens), 2) if input_tokens else 0,
            "Output Tokens": round(np.mean(output_tokens), 2) if output_tokens else 0
        }
        
        # Write WSF metrics CSV
        with open(wsf_file, mode='w', newline='') as file:
            writer = csv.writer(file)
            for metric_name, avg_value in wsf_metrics.items():
                writer.writerow([metric_name, avg_value])
            #writer.writerow(['Throughput', round(throughput, 2)])
            writer.writerow(['File Name', file_details.get("name", "N/A")])
            writer.writerow(['File Size (MB)', file_details.get("size_mb", "N/A")])
            
    except Exception as e:
        print(f"Failed to write metrics to CSV: {e}")


def write_rest_metrics(report_dir, metrics):
    """
    Writes API metrics to a JSON file.
    """
    #timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    json_file = os.path.join(report_dir, f"document_api_individual_metrics.json")
    try:
        with open(json_file, "a") as file:
            for metric in metrics:
                json.dump({"LATENCY (ms)":metric}, file, indent=4)
    except Exception as e:
        print(f"Writing rest metrics to file, failed with exception {e}")


def write_rest_metrics_summary_to_csv(report_dir, latency, throughput):
    """
    Writes a summary of REST API metrics to a CSV file.

    """
    output_file = os.path.join(report_dir, "document_api_summary_metrics.csv")
    
    try:
        # Calculate statistical metrics
        metrics = calculate_metrics(latency)
        if metrics[0] is None:  # Check if calculation failed
            print("Failed to calculate metrics. Check latency data.")
            return
        
        avg, min_val, max_val, p99, p90, p75 = metrics
        
        # Write to CSV file
        with open(output_file, mode='w', newline='') as file:
            writer = csv.writer(file)
            
            # Header rows
            writer.writerow(['', '', '', 'Rest API Metrics', '', '', ''])
            writer.writerow(['Statistic', 'Avg', 'Min', 'Max', 'p99', 'p90', 'p75'])
            
            # Metrics rows
            writer.writerow(['Latency (ms)', avg, min_val, max_val, p99, p90, p75])
            writer.writerow(['Throughput', round(throughput, 4), 'NA', 'NA', 'NA', 'NA', 'NA'])
        
        print(f"REST API metrics summary written to: {output_file}")
        
    except TypeError as e:
        print(f"Invalid data type for latency or throughput: {e}")
    except IOError as e:
        print(f"Failed to write metrics to file {output_file}: {e}")
    except Exception as e:
        print(f"Unexpected error writing REST metrics summary: {e}")

def get_enabled_apis(input_file):
    """
    Determines which APIs are enabled based on the configuration file.
    """
    config = read_yaml_config(input_file)
    stream_log_api_enabled = config.get('apis', {}).get('stream_log', {}).get("enabled", False)
    document_api_enabled = config.get('apis', {}).get('document', {}).get("enabled", False)
    return stream_log_api_enabled, document_api_enabled

def get_stream_api_profile_details(profile_path, input_file):
    """
    Retrieves stream API profile details from configuration and profile files.
    """
    # Load configuration and extract stream log API details
    config = read_yaml_config(input_file)
    stream_log_api_details = get_stream_log_config(config=config)
    
    # Extract endpoints safely
    endpoints = stream_log_api_details.get("endpoints", {})
    doc_endpoint = endpoints.get("document")
    chat_endpoint = endpoints.get("chat")
    
    # Extract service configuration
    service_name = stream_log_api_details.get("service_name", {})
    profile = stream_log_api_details.get("input_profile", {})
    
    # Load profile-specific details
    stream_log_profile_details = get_profile_details(profile_path=profile_path, profile_name=profile)
    prompt = stream_log_profile_details.get("prompt")
    max_tokens = stream_log_profile_details.get("max_tokens", "1024")
    
    # Extract file information
    file_details = stream_log_profile_details.get('files', [])
    if not file_details:
        raise ValueError("No files defined in the profile")
    
    filename = file_details[0]["name"]
    filepath = file_details[0]["path"]
    
    return profile, chat_endpoint, doc_endpoint, prompt, filename, filepath, service_name, max_tokens


def delete_existing_docs(url):
    """
    Deletes all existing documents from the specified bucket.
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
    Uploads a document file to the specified endpoint for conversation context.
    
    Returns:
        dict: file_details containing name and size in MB
    """
    print("Uploading file for the context...")
    upload_response, upload_files = {}, []
    # Track file metadata as a dict; will be JSON-encoded for callers
    file_details = {"name": filename, "size_mb": 0.0}
    
    try:
        # Get file size before upload
        file_size_bytes = os.path.getsize(filepath)
        file_size_mb = round(file_size_bytes / (1024 * 1024), 2)
        file_details["size_mb"] = file_size_mb

        delete_existing_docs(url)
        upload_files.append(("files", (filename, open(filepath, 'rb'), 'application/octet-stream')))
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

def get_global_details(input_file):
    """
    Retrieves global configuration details from the input configuration file.
    """
    config = read_yaml_config(input_file)
    global_details = get_global_config(config=config)
    
    # Extract configuration values with defaults
    report_dir = global_details.get('report_dir', 'reports')
    perf_tool_repo = global_details.get('perf_tool_repo', '')
    profile_path = global_details.get('input_profiles_path', 'input_profiles.yaml')
    
    # Ensure report directory exists
    os.makedirs(report_dir, exist_ok=True)
    
    return report_dir, perf_tool_repo, profile_path


def setup_document_upload(file_details):
    """
    Prepares a list of files for multipart/form-data upload.
    """
    upload_files = []
    for file_detail in file_details:
        file_path = file_detail["path"]
        file_name = file_detail["name"]
        with open(file_path, 'rb') as file_obj:
            file_content = file_obj.read()
        upload_files.append(("files", (file_name, file_content, 'application/octet-stream')))
    return upload_files


def get_document_api_profile_details(profile_path, input_file):
    """
    Retrieves document API profile details from configuration and profile files.
    
    """
    # Load configuration and extract document API details
    config = read_yaml_config(input_file)
    document_api_details = get_document_config(config=config)
    
    # Extract profile name and load profile-specific details
    document_profile = document_api_details.get("input_profile", "")
    document_profile_details = get_profile_details(
        profile_path=profile_path, 
        profile_name=document_profile
    )
    
    # Extract endpoint URL safely with nested get
    document_endpoint = document_api_details.get("endpoints", {}).get("document")
    
    # Extract file details with proper default
    file_details = document_profile_details.get('files', [])
    
    return document_profile, document_endpoint, file_details

def get_response(response, report_dir, answer=None):
    """    
    This function handles streaming responses from chat APIs,
    processes the content by removing protocol prefixes, and saves the result
    to a timestamped file in the responses subdirectory.
    
    """
    # Create responses subdirectory
    responses_dir = os.path.join(report_dir, "responses")
    os.makedirs(responses_dir, exist_ok=True)
    
    # Generate timestamped filename
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = os.path.join(responses_dir, f"chat_response_{timestamp}.txt")
    
    # Process response if not provided
    if answer is None:
        answer_parts = []
        for chunk in response.iter_lines():
            decoded_chunk = chunk.decode("utf-8")[6:]  # Strip data: prefix
            answer_parts.append(decoded_chunk)
        answer = "".join(answer_parts)
    
    # Write to file
    try:
        with open(filename, "w") as file:  
            file.write(answer)
        print(f"Response saved to: {filename}")
    except IOError as e:
        print(f"Error writing response to {filename}: {e}")

def copy_perf_tools_logs(logs_dir, report_dir):
    """
    Copies performance tools logs to the report directory.
    """
    if not os.path.exists(logs_dir):
        print(f"Logs directory {logs_dir} does not exist.")
        return
    try:
        report_logs_dir = os.path.join(report_dir, f"perf_tools_logs")    
        os.makedirs(report_logs_dir, exist_ok=True)    
        for file in os.listdir(logs_dir):
            src_file = os.path.join(logs_dir, file)
            dest_file = os.path.join(report_logs_dir, file)
            if os.path.isfile(src_file):
                with open(src_file, 'rb') as fsrc, open(dest_file, 'wb') as fdest:
                    fdest.write(fsrc.read())
        return report_logs_dir
    except Exception as e:
        print(f"Failed to copy logs: {e}")

# Video summary functions
def get_video_summary_config(config=None, config_path='config.yaml'):
    """
    Retrieves video summary API configuration from the YAML config file.
    """
    if config is None:
        config = read_yaml_config(config_path)
    return config.get('apis', {}).get('video_summary', {})

def get_video_search_config(config=None, config_path='config.yaml'):
    """
    Retrieves video search API configuration from the YAML config file.
    """
    if config is None:
        config = read_yaml_config(config_path)
    return config.get('apis', {}).get('video_search', {})


def get_enabled_video_apis(input_file):
    """
    Determines which video-related APIs are enabled based on the configuration file.
    """
    # Read config once and reuse for both API checks
    config = read_yaml_config(input_file)
    
    # Extract enabled status for both APIs
    video_summary_enabled = get_video_summary_config(config=config).get("enabled", False)
    video_search_enabled = get_video_search_config(config=config).get("enabled", False)
    
    return video_summary_enabled, video_search_enabled

def get_video_summary_profile_details(profile_path, input_file, warmup=False):
    """
    Retrieves video summary API profile details from configuration and profile files.
    """
    # Load configuration and extract video summary API details
    config = read_yaml_config(input_file)
    video_summary_details = get_video_summary_config(config=config)
    
    # Extract endpoints safely
    endpoints = video_summary_details.get("endpoints", {})
    upload_endpoint = endpoints.get("upload")
    summary_endpoint = endpoints.get("summary")
    states_endpoint = endpoints.get("states")
    telemetry_endpoint = endpoints.get("telemetry")
    
    # Extract profile name and load profile-specific details
    if warmup:
        video_profile = "video_summary_warmup_profile"
        profile_details = get_profile_details(profile_path=profile_path, profile_name=video_profile)
    else:
        video_profile = video_summary_details.get("input_profile", '')
        profile_details = get_profile_details(profile_path=profile_path, profile_name=video_profile)
    
    # Extract file information
    file_details = profile_details.get('files', [])
    if not file_details:
        raise ValueError("No files defined in the video summary profile")
    
    filename = file_details[0]["name"]
    filepath = file_details[0]["path"]
    
    # Extract payload configuration
    payload = profile_details.get('payload', {})
    
    return video_profile, upload_endpoint, summary_endpoint, states_endpoint, telemetry_endpoint, filename, filepath, payload



def get_video_search_profile_details(profile_path, input_file, warmup=False):
    """
    Retrieves video search API profile details from configuration and profile files.
    """
    # Load configuration and extract video search API details
    config = read_yaml_config(input_file)
    video_search_details = get_video_search_config(config=config)
    
    # Extract endpoints safely
    endpoints = video_search_details.get("endpoints", {})
    upload_endpoint = endpoints.get("upload")
    search_endpoint = endpoints.get("search")
    embed_endpoint = endpoints.get("embedding")
    telemetry_endpoint = endpoints.get("telemetry")

    # Extract profile name and load profile-specific details
    if warmup:
        video_profile = "video_search_warmup_profile"
        profile_details = get_profile_details(profile_path=profile_path, profile_name=video_profile)
    else:    
        video_profile = video_search_details.get("input_profile", '')
        profile_details = get_profile_details(profile_path=profile_path, profile_name=video_profile)
    
    # Extract file details and queries
    file_details = profile_details.get('files')
    queries = profile_details.get('queries')
    
    return video_profile, upload_endpoint, search_endpoint, embed_endpoint, telemetry_endpoint, file_details, queries


def upload_video_file(url, filename, filepath):
    """
    Uploads a video file to the specified endpoint and retrieves the video ID.
    """
    try:
        if filepath is None or filename is None:
            print("Error: Filepath or filename is None.")
            return None
        
        print(f"Video file to be uploaded: {filename} at {filepath}")

        with open(filepath, 'rb') as video_file:
            files = [('video', (filename, video_file, 'application/octet-stream'))]
            response = requests.post(url, headers={}, files=files)
            response.raise_for_status()
            video_id = response.json().get("videoId")
            if video_id:
                print(f"Video upload complete. Video ID: {video_id}")
                return video_id
            else:
                print("Video upload succeeded but no video ID returned.")
                return None
                
    except Exception as e:
        print(f"Error: Unexpected error during video upload: {e}")
        return None

def embedding_video_file(url, video_id):
    """
    Initiates embedding generation for an uploaded video.
    """

    try:
        print("waiting for video embedding creation to complete...")
        headers = {'Content-Type': 'application/json'}
        endpoint = f"{url}/{video_id}"
        start_time = time.time()
        response = requests.post(endpoint, headers=headers, data={})
        end_time = time.time()
        elapsed_time = round (end_time - start_time, 2)
        print(f"Embedding creation took {elapsed_time} seconds.")
        response.raise_for_status()
        return response.status_code
        
    except requests.exceptions.Timeout:
        print(f"Error: Embedding request timed out for video ID {video_id}")
        return None
    except requests.exceptions.HTTPError as e:
        print(f"Error: HTTP error during embedding creation: {e.response.status_code} - {e.response.text}")
        return None
    except requests.exceptions.RequestException as e:
        print(f"Error: Network error during embedding creation: {e}")
        return None
    except Exception as e:
        print(f"Error: Unexpected error during video embedding creation: {e}")
        return None
    
def wait_for_video_summary_complete(url):
    """
    Polls the video summary API endpoint until processing is complete.
    """
    video_summary_complete = False
    response = ""
    must_end = time.time() + 3600  # 1 hour timeout
    print("Waiting for video summary to complete...")
    
    while time.time() < must_end:
        try:        
            response = requests.get(url, timeout=10)
            status_code = response.status_code
            
            # Handle non-200 responses
            if status_code != 200:
                print(f"Error: Received status code {status_code}. Response: {response.text}")
                break            
            json_response = response.json()
            
            # Check if video summary is complete
            if json_response.get("videoSummaryStatus") == "complete":
                video_summary_complete = True
                break            
            time.sleep(10)

        except KeyboardInterrupt:
            print("Keyboard interrupt received. Exiting...")
            sys.exit(130)
        except requests.exceptions.RequestException as e:
            print(f"Connection error, retrying: {e}...")
            time.sleep(1)
            continue
        except Exception as e:
            print(f"Unexpected error, retrying: {e}...")
            break
    if not video_summary_complete:
        print("Video summarization failed.")
    return video_summary_complete, response

def get_video_summary(report_dir, response, summary_id):
    """    
    Processes a video summary API response and saves formatted summaries to a file.
    """
    # Create responses subdirectory
    filename = os.path.join(report_dir, f"video_response_{summary_id}.txt")
    
    try:
        response_data = response.json()
        overall_summary = response_data.get("summary", "")
        frame_summaries = response_data.get("frameSummaries", [])
        
        # Write all content in a single file operation
        with open(filename, "w") as file:
            # Write overall summary
            if overall_summary:
                file.write(overall_summary + "\n\n")
            
            # Write frame summaries
            for frame_summary in frame_summaries:
                start_frame = frame_summary.get('startFrame', 'N/A')
                end_frame = frame_summary.get('endFrame', 'N/A')
                summary_text = frame_summary.get('summary', '')
                
                file.write(f"\nFrames: {start_frame} -- {end_frame}\n")
                file.write(f"{summary_text}\n")
        
        print(f"Video summary saved to {filename}")
        
    except ValueError as e:
        print(f"Error: Invalid JSON response format: {e}")
    except KeyError as e:
        print(f"Error: Missing expected key in response: {e}")
    except IOError as e:
        print(f"Error: Failed to write summary to {filename}: {e}")
    except Exception as e:
        print(f"Error: Unexpected error saving video summary: {e}")

def write_vss_metrics(report_dir, metrics):
    json_file = os.path.join(report_dir, f"video_summary_metrics.json")
    try:
        with open(json_file, "a") as file:
                json.dump(metrics, file, indent=4)
    except Exception as e:
        print(f"Writing rest metrics to file, failed with exception {e}")

def write_video_summary_metrics(report_dir, metrics):
    """
    Writes individual video summary API metrics to a JSON file.
        None
    """
    json_file = os.path.join(report_dir, "summary_api_individual_metrics.json")
    try:
        with open(json_file, "a") as file:
            json.dump(metrics, file, indent=4)
            file.write('\n')  # Add newline for better readability between entries
    except IOError as e:
        print(f"Failed to write video summary metrics to {json_file}: {e}")
    except TypeError as e:
        print(f"Invalid metrics data type (must be JSON serializable): {e}")
    except Exception as e:
        print(f"Unexpected error writing video summary metrics: {e}")

def write_video_search_metrics(report_dir, metrics):
    """
    Writes individual video search API metrics to a JSON file.
    """
    json_file = os.path.join(report_dir, "search_api_individual_metrics.json")
    try:
        with open(json_file, "a") as file:
            json.dump(metrics, file, indent=4)
            file.write('\n')  # Add newline for better readability between entries
    except IOError as e:
        print(f"Failed to write video search metrics to {json_file}: {e}")
    except TypeError as e:
        print(f"Invalid metrics data type (must be JSON serializable): {e}")
    except Exception as e:
        print(f"Unexpected error writing video search metrics: {e}")

def write_video_search_metrics_summary_to_csv(report_dir, search_latencies, throughput, video_file_paths=None):
    """
    Writes a comprehensive summary of video search API metrics to a CSV file.
    
    """
    output_file = os.path.join(report_dir, "search_api_metrics_summary.csv")
    
    try:
        # Calculate metrics once
        latency_metrics = calculate_metrics(search_latencies)
        
        if latency_metrics[0] is None:
            print("Failed to calculate metrics. Check search latency data.")
            return
        
        avg_latency, min_latency, max_latency = latency_metrics[:3]
        
        with open(output_file, mode='w', newline='') as file:
            writer = csv.writer(file)
            
            # Video file details section
            if video_file_paths:
                writer.writerow(['', 'Video file details', '', ''])
                
                # Define video detail fields to avoid repetition
                detail_fields = [
                    ('File Size (MB)', 'File Size (MB)'),
                    ('Length (s)', 'Duration (s)'),
                    ('FPS', 'FPS'),
                    ('File Name', 'Video File Name'),
                    ('Resolution', 'Resolution'),
                    ('Codec', 'Video Codec'),
                    ('Audio Codec', 'Audio Codec')
                ]
                
                for i, video_path in enumerate(video_file_paths, 1):
                    try:
                        video_details = get_video_details(video_path)
                        
                        for label, key in detail_fields:
                            prefix = 'Audio' if 'Audio' in label else 'Video'
                            writer.writerow([f'{prefix}_{i} {label}', video_details.get(key, 'N/A'), '', ''])
                            
                    except Exception as e:
                        print(f"Error getting video details for {video_path}: {e}")
                        writer.writerow([f'Video_{i} Error', str(e), '', ''])
                
                writer.writerow(['', '', '', ''])  # Empty row for spacing
            
            # Performance metrics section
            writer.writerow(['', 'Video Search API Metrics', '', ''])
            writer.writerow(['Statistic', 'Avg', 'Min', 'Max'])        
            writer.writerow(['Query Search Duration (in seconds)', avg_latency, min_latency, max_latency])
            writer.writerow(['Search Throughput', round(throughput, 4), 'NA', 'NA'])
        
        print(f"Video search metrics written to: {output_file}")
        
    except TypeError as e:
        print(f"Invalid data type for metrics: {e}")
    except IOError as e:
        print(f"Failed to write metrics to file {output_file}: {e}")
    except Exception as e:
        print(f"Unexpected error writing video search metrics: {e}")

        


def rest_api_metrics(api_name, report_dir, latencies):
    """
    Collects and writes REST API metrics to files.
    """   
    
    out_put_file = os.path.join(report_dir, f"{api_name}_api_summary_metrics.csv")
    json_file = os.path.join(report_dir, f"{api_name}_api_metrics.json")
    average_latency, min_latency, max_latency, p99_latency, p90_latency, p75_latency = calculate_metrics(latencies) 
    throughput = len(latencies) / (sum(latencies) / 1000) if sum(latencies) > 0 else 0
    try:
        with open(json_file, "a") as file:
            for latency in latencies:
                json.dump({"LATENCY (ms)":latency}, file, indent=4)     
                
        with open(out_put_file, mode='w', newline='') as file:
            writer = csv.writer(file)
            writer.writerow(['', '', '', 'Rest API Metrics', '', '', ''])
            writer.writerow(['Statistic', 'Avg', 'Min', 'Max', 'p99', 'p90', 'p75'])
            writer.writerow(['Latency (ms)', average_latency, min_latency, max_latency, p99_latency, p90_latency, p75_latency])
            writer.writerow(['Throughput', round(throughput,2), "NA", "NA", "NA", "NA", "NA"])

    except Exception as e:
        print(f"Writing rest metrics to file, failed with exception {e}")
        print(f"{api_name.capitalize()} API metrics collection completed. Reports saved in: {report_dir}")


def start_perf_tool(repo_url, report_dir):
    """
    Initializes and starts the performance monitoring tool in a Docker container.
    Args:
        repo_url (str): Git repository URL for the performance-tools repo.
                       Should be a valid Git HTTPS or SSH URL that includes the
                       'discrete-gpu-fix' branch.
        report_dir (str): Absolute or relative path to the report directory where
                         performance logs will be stored. The function creates a
                         'perf_tool_logs' subdirectory within this path.
    
    Returns:
        str: Absolute path to the log directory where performance metrics are stored.
             This directory is created as 'perf_tool_logs' inside report_dir.
    """
    repo_name = "performance-tools"
    compose_file = os.path.join(repo_name, 'docker', 'docker-compose-reg.yaml')
    
    # Create log directory
    log_dir = os.path.join(report_dir, "perf_tool_logs")
    abs_log_dir = os.path.abspath(log_dir)
    os.makedirs(abs_log_dir, exist_ok=True)

    try:
        # Clean up existing repository
        if os.path.exists(repo_name):
            if os.path.isdir(repo_name):
                shutil.rmtree(repo_name)
            else:
                os.remove(repo_name)
        
        # Clone the specific branch
        print(f"Cloning performance-tools repository from {repo_url}...")
        subprocess.run(
            ['git', 'clone', repo_url, repo_name],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        
        # Prepare environment with log directory
        env = os.environ.copy()
        env['log_dir'] = abs_log_dir
        
        # Start docker compose with wait flag
        print("Starting performance monitoring containers, it takes some time to initialize...")
        subprocess.run(
            ['docker', 'compose', '-f', compose_file, 'up', '-d', '--wait'],
            env=env,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        
        print(f"Performance tool started. Logs directory: {abs_log_dir}")
        
    except subprocess.CalledProcessError as e:
        print(f"Error during performance tool setup: {e}")
        if e.stderr:
            print(f"Error details: {e.stderr.decode('utf-8', errors='ignore')}")
    except OSError as e:
        print(f"File system error during performance tool setup: {e}")
    except Exception as e:
        print(f"Unexpected error during performance tool setup: {e}")
    
    return abs_log_dir


def stop_perf_tool():
    """
    Stops and removes the performance monitoring Docker container.
    
    This function gracefully shuts down the metrics-collector Docker container
    that was started by the start_perf_tool function. It waits briefly to ensure
    any pending metrics are flushed before forcefully removing the container.
    
    Args:
        None
    
    Returns:
        None
    """
    try:
        # Brief delay to ensure metrics are flushed
        time.sleep(2)
        
        # Force remove the metrics collector container
        subprocess.run(
            ["docker", "rm", "-f", "metrics-collector"],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=5
        )
        
        print("Performance tool stopped.")
        
    except subprocess.TimeoutExpired:
        print("Warning: Docker container removal timed out after 30 seconds.")
    except subprocess.CalledProcessError as e:
        error_msg = e.stderr.decode('utf-8', errors='ignore') if e.stderr else str(e)
        print(f"Error stopping performance tool: {error_msg}")
    except FileNotFoundError:
        print("Error: Docker command not found. Ensure Docker is installed and in PATH.")
    except Exception as e:
        print(f"Unexpected error stopping performance tool: {e}")


def plot_graphs(log_dir):
    """
    Generates performance visualization graphs from collected metrics logs.
    
    Args:
        log_dir (str): Absolute or relative path to the directory containing raw
                      performance metrics logs. This directory should contain the
                      output from the metrics-collector container started by
                      start_perf_tool(). The same directory will be used to store
                      parsed JSON metrics and generated graph images.
    
    Returns:
        None
    """
    scripts_base = "performance-tools/benchmark-scripts"
    
    # Define script paths once
    qmasa_parser = os.path.abspath(os.path.join(scripts_base, "parse_qmassa_metrics_to_json.py"))
    graph_plotter = os.path.abspath(os.path.join(scripts_base, "usage_graph_plot.py"))
    
    try:
        # Parse QMASA metrics to JSON format
        # print(f"Parsing QMASA metrics from {log_dir}...")
        subprocess.run(
            ['python3', qmasa_parser, '--dir', log_dir],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=5
        )
        
        # Generate visualization graphs
        print(f"Generating usage graphs from {log_dir}...")
        subprocess.run(
            ['python3', graph_plotter, '--dir', log_dir],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=5
        )
        
        print(f"Performance graphs successfully generated in: {log_dir}")
        
    except subprocess.CalledProcessError as e:
        error_msg = e.stderr.decode('utf-8', errors='ignore') if e.stderr else str(e)
        print(f"Plot graph failed with subprocess error: {error_msg}")
    except FileNotFoundError as e:
        print(f"Error: Required script not found. Ensure performance-tools repo is cloned: {e}")
    except Exception as e:
        print(f"Unexpected error during graph generation: {e}")


def get_video_details(video_file_path):
    """
    Extracts comprehensive metadata from a video file.
    """
    # Extract file metadata
    # file_name = os.path.basename(video_file_path)
    file_size_mb = os.path.getsize(video_file_path) / (1024 * 1024)

    # Load video and extract properties using context-like approach
    clip = None
    try:
        clip = VideoFileClip(video_file_path)
        duration = clip.duration
        fps = clip.fps
        # width, height = clip.size
        # resolution = f"{width}x{height}"
        
        # Safely extract codec information from reader infos
        # reader_infos = getattr(clip.reader, 'infos', {})
        # video_codec = reader_infos.get('video_codec', 'Unknown')
        # audio_codec = reader_infos.get('audio_codec', 'Unknown')
        
    finally:
        # Ensure clip is always closed to free resources
        if clip is not None:
            clip.close()

    return {
        "File_Size (MB)": round(file_size_mb, 2),
        "File_Duration (s)": round(duration, 2),
        "File_videoFPS": round(fps, 2)        
    }


def embedding_creation_per_sec(video_details, embedding_time):
    """
    Calculates the embedding creation rate in frames per second.   
    """
    try:
        duration = video_details.get("Duration (s)", 0)
        fps = video_details.get("FPS", 0)
        
        # Validate inputs
        if duration <= 0 or fps <= 0 or embedding_time <= 0:
            return 0.0        
        
        total_frames = duration * fps
        extracted_frames = total_frames / 15
        # embedding_rate = total_frames / embedding_time
        embedding_rate = extracted_frames / embedding_time
        
        return round(embedding_rate, 2)
        
    except (TypeError, ZeroDivisionError) as e:
        print(f"Error calculating embedding creation rate: {e}")
        return 0.0
    except Exception as e:
        print(f"Unexpected error calculating embedding creation rate: {e}")
        return 0.0

def summarization_fps(video_details, summarization_time):
    """
    Calculates the video summarization rate in frames per second.
    """
    try:
        duration = video_details.get("Duration (s)", 0)
        fps = video_details.get("FPS", 0)
        
        # Validate inputs
        if duration <= 0 or fps <= 0 or summarization_time <= 0:
            return 0.0
        
        total_frames = duration * fps
        frames_per_second = total_frames / summarization_time
        
        return round(frames_per_second, 2)
        
    except (TypeError, ZeroDivisionError) as e:
        print(f"Error calculating summarization frames per second: {e}")
        return 0.0
    except Exception as e:
        print(f"Unexpected error calculating summarization fps: {e}")
        return 0.0
    


def convert_timestamp_to_float(timestamp):
    """
    Converts an ISO 8601 formatted timestamp string to a Unix epoch float.
    """
    try:
        # Validate input type
        if not isinstance(timestamp, str):
            raise TypeError(f"Timestamp must be a string, not {type(timestamp).__name__}")
        
        if not timestamp:
            raise ValueError("Timestamp string cannot be empty")
        
        dt = datetime.strptime(timestamp, "%Y-%m-%dT%H:%M:%S.%fZ")
        dt_utc = dt.replace(tzinfo=timezone.utc)
        timestamp_float = dt_utc.timestamp()
        
        return timestamp_float
        
    except TypeError as e:
        print(f"Error: Invalid timestamp type - {e}")
        raise
    except ValueError as e:
        print(f"Error: Invalid timestamp format - {e}. Expected format: 'YYYY-MM-DDTHH:MM:SS.ffffffZ'")
        raise
    except Exception as e:
        print(f"Error: Unexpected error converting timestamp to float: {e}")
        raise

def get_video_summary_telemetry_kpis(start_time, end_time, telemetry_json_response, video_properties):
    """
    Extracts and calculates video summarization telemetry KPIs from telemetry response data.
    """
    try:
        ttfts, latencies, tpss, timestamps, prompt_tokens, output_tokens, total_tokens, tpots, telemetry_details  = {}, {}, [], [], [], [], [], [], []
        items = telemetry_json_response.get("items", [])

        for item in items:
            timestamp = convert_timestamp_to_float(item.get("timestamp"))       
            if start_time <= timestamp:            
                timestamps.append(timestamp)
                telemetry_details.append(item)
                kpis = item.get("telemetry", {})
                ttfts[timestamp] = kpis.get("ttft_ms", 0)  
                latencies[timestamp] = kpis.get("generate_time_ms", 0)  
                tpss.append(kpis.get("throughput_tps", 0))
                prompt_tokens.append(kpis.get("prompt_tokens", 0))
                output_tokens.append(kpis.get("completion_tokens", 0))  
                total_tokens.append(kpis.get("total_tokens", 0))
                tpots.append(kpis.get("tpot_ms", 0))
        
        # Calculating metrics based on telemetry data
        min_timestamp = min(timestamps)
        ttft = ttfts.get(min_timestamp, 0)  
        late = latencies.get(min_timestamp, 0) / 1000 #Convert to seconds
        delta = (min_timestamp - late) - start_time
        tps = sum(tpss) / len(tpss) if len(tpss) > 0 else 0
        input_tokens = sum(prompt_tokens) / len(prompt_tokens) if len(prompt_tokens) > 0 else 0
        output_tokens = sum(output_tokens) / len(output_tokens) if len(output_tokens) > 0 else 0
        total_tokens = sum(total_tokens) / len(total_tokens) if len(total_tokens) > 0 else 0
        tpot = sum(tpots) / len(tpots) if len(tpots) > 0 else 0
        e2e_summary_latency = end_time - start_time
        rtf = e2e_summary_latency / (video_properties.get('File_Duration (s)', 1))
        complexity = (video_properties.get('File_videoFPS', 0) * video_properties.get('File_Duration (s)', 0)) / e2e_summary_latency   # ((fps * video duration)/latency)

        # writing all metrics to video properties
        video_properties['Average_Prompt_Tokens'] = input_tokens
        video_properties['Average_Completion_Tokens'] = output_tokens
        video_properties['Average_Total_Tokens'] = total_tokens
        video_properties['Average_Time_Per_Output_Token (s)'] = tpot / 1000
        video_properties['Time To First Token (s)'] = ttft / 1000
        video_properties['Throughput (tokens/sec)'] = tps
        video_properties['Video Summary Pre ProcessingTime (s)'] = delta
        video_properties['Video Summary E2E Latency (s)'] = e2e_summary_latency
        video_properties['Video Summarization RTF (latency/duration)'] = rtf
        video_properties['Video Summary Processing Efficiency ((fps*duration)/latency)'] = complexity

        return video_properties, telemetry_details

    except Exception as e:
        print(f"Unexpected error in get_video_summary_telemetry_kpis: {e}")


def convert_summary_metrics_to_wsf_format(report_dir, json_file_path, samples=None):    
    """
    Read values from a JSON file and write to CSV in key,value format.
    """
    output_file = os.path.join(report_dir, "video_summary_metrics_wsf.csv")
    # Read the JSON file
    with open(json_file_path, 'r') as f:
        data = json.load(f)
    
    # Handle both list and dict formats
    if isinstance(data, list):
        data = data[0]  # Take first element if it's a list
    
    # Write to CSV
    with open(output_file, 'w', newline='') as f:
        writer = csv.writer(f)
        
        # Write sampling parameters first if provided
        if samples:
            for key, value in samples.items():
                writer.writerow([f"Sampling-{key}", value])
        
        # Write the JSON data
        for key, value in data.items():
            if key in ['File_Duration (s)', 'File_videoFPS', 'Time To First Token (s)','Throughput (tokens/sec)', 'Video Summary Pre ProcessingTime (s)', 'Video Summary E2E Latency (s)', 'Video Summarization RTF (latency/duration)', 'Video Summary Processing Efficiency ((fps*duration)/latency)']:
                writer.writerow([key, value])

    print(f"WSF formatted output written to: {output_file}")


def write_video_summary_metrics_summary_to_csv(report_dir, latencies, ttft, tps, video_file_path=None, sampling_params=None):
    """
    Writes a comprehensive summary of video summary API metrics to a CSV file.
    
    """
    output_file = os.path.join(report_dir, "summary_api_metrics_summary.csv")
    
    try:
        # Calculate metrics once
        latency_metrics = calculate_metrics(latencies)
        ttft_metrics = calculate_metrics(ttft)
        tps_metrics = calculate_metrics(tps)
        
        if latency_metrics[0] is None or ttft_metrics[0] is None:
            print("Failed to calculate metrics. Check input data.")
            return
        
        avg_latency, min_latency, max_latency = latency_metrics[:3]
        avg_ttft, min_ttft, max_ttft = ttft_metrics[:3]
        avg_tps, min_tps, max_tps = tps_metrics[:3]
        
        with open(output_file, mode='w', newline='') as file:
            writer = csv.writer(file)
            
            # Video file details section
            if video_file_path:
                writer.writerow(['', 'Video file details', '', ''])
                try:
                    video_details = get_video_details(video_file_path)
                    
                    # Define video detail fields to avoid repetition
                    detail_fields = [
                        ('Video File Size (MB)', 'File Size (MB)'),
                        ('Video Length (s)', 'Duration (s)'),
                        ('Video FPS', 'FPS'),
                        ('Video File Name', 'Video File Name'),
                        ('Video Resolution', 'Resolution'),
                        ('Video Codec', 'Video Codec'),
                        ('Audio Codec', 'Audio Codec')
                    ]
                    
                    for label, key in detail_fields:
                        writer.writerow([label, video_details.get(key, 'N/A'), '', ''])
                        
                except Exception as e:
                    print(f"Error getting video details for {video_file_path}: {e}")
                    writer.writerow(['Error retrieving video details', str(e), '', ''])
                
                writer.writerow(['', '', '', ''])  # Empty row for spacing
            
            # Sampling configuration section
            if sampling_params:
                writer.writerow(['', 'Sampling Configuration', '', ''])
                
                # Define sampling parameter fields
                sampling_fields = [
                    ('Chunk Duration', 'chunkDuration'),
                    ('Sample Frame Per Chunk', 'samplingFrame'),
                    ('Frames Overlap', 'frameOverlap'),
                    ('MultiFrame', 'multiFrame')
                ]
                
                for label, key in sampling_fields:
                    writer.writerow([label, sampling_params.get(key, 'N/A'), '', ''])
                
                writer.writerow(['', '', '', ''])  # Empty row for spacing
            
            # Performance metrics section
            writer.writerow(['', 'Video Summary API Metrics', '', ''])
            writer.writerow(['Statistic', 'Avg', 'Min', 'Max'])
            writer.writerow(['Time to First Chunk Summary (in seconds)', avg_ttft, min_ttft, max_ttft])
            writer.writerow(['Video Summarization Duration (in seconds)', avg_latency, min_latency, max_latency])
            writer.writerow(['Token Per Sec', avg_tps, min_tps, max_tps])
        
        print(f"Video summary metrics written to: {output_file}")
        
    except TypeError as e:
        print(f"Invalid data type for metrics: {e}")
    except IOError as e:
        print(f"Failed to write metrics to file {output_file}: {e}")
    except Exception as e:
        print(f"Unexpected error writing video summary metrics: {e}")


def get_video_search_telemetry_kpis(start_time, end_time, telemetry_json_response, search_metrics):
    """
    Extracts video search telemetry KPIs from the telemetry response within a time window.
    """
    metrics = {}
    input_videos = []
    telemetry_details = []
    
    metrics["Video_Search_E2E_Latency"] = round(end_time - start_time, 2)
    items = telemetry_json_response.get("items", [])
    
    for item in items:
        try:
            # Extract and validate timestamp
            timestamp_str = item.get("timestamps", {}).get("requested_at", "")
            if not timestamp_str:
                continue
            
            timestamp = convert_timestamp_to_float(timestamp_str)
            
            # Filter by time window
            if not (start_time <= timestamp):
                continue
            
            # Extract video file details
            telemetry_details.append(item)
            video_file_details = item.get("video", {})
            video_details = {
                "id": video_file_details.get("video_id"),
                "file_name": video_file_details.get("filename", "N/A"),
                "duration_seconds": round(video_file_details.get("video_duration_seconds", 0), 2),
                "fps": round(video_file_details.get("fps", 0), 2),
                "total_frames": video_file_details.get("total_frames", 0),
                "frames_extracted": item.get("counts", {}).get("frames_extracted", 0)
            }
            
            # Extract embedding details from stages
            stages = item.get("stages", [])
            for stage in stages:
                stage_name = stage.get("name")
                stage_seconds = stage.get("seconds", 0)
                video_details[stage_name] = stage_seconds
                
                if stage_name == "embedding":
                    video_details["embedding_percent_of_total"] = stage.get("percent_of_total", 0)
            
            video_details["wall_time_seconds"] = item.get("timestamps", {}).get("wall_time_seconds", 0)
            video_details["embedding_per_sec"] = item.get("throughput", {}).get("embeddings_per_second", 0)     
            relative_rtf = (video_details.get("wall_time_seconds", 0) / video_details.get("duration_seconds", 1)) * (30 / video_details.get("fps", 1))   
            video_details["Normalized_Embedding_RTF"] = round(relative_rtf, 4) 
            input_videos.append(video_details)            
            
        except (ValueError, TypeError, KeyError) as e:
            # Skip items with invalid data
            print(f"Warning: Skipping telemetry item due to error: {e}")
            continue
    
    metrics["Input_Videos"] = input_videos
    metrics["Search_Metrics"] = search_metrics
    return metrics, telemetry_details


def save_video_summary_search_telemetry_kpis(report_dir, metrics, telemetry_details=None):
    """
    Saves video search telemetry KPIs to a JSON file.
    """
    output_file = os.path.join(report_dir, "video_summary_search_metrics.json")
    telemetry_file = os.path.join(report_dir, "video_summary_search_telemetry_details.json")
    
    try:

        with open(output_file, "w") as file:
            json.dump(metrics, file, indent=4)
        print(f"Video summary and search embedding metrics written to: {output_file}")    

        with open(telemetry_file, "w") as t_file:
            json.dump(telemetry_details, t_file, indent=4)  
        print(f"Video summary and search embedding telemetry details written to: {telemetry_file}")  

    except IOError as e:
        print(f"Failed to write video search embedding metrics to {output_file}: {e}")
    except TypeError as e:
        print(f"Invalid data type for embedding metrics: {e}")
    except Exception as e:
        print(f"Unexpected error writing video search embedding metrics: {e}")    
    return output_file


def convert_search_metrics_to_wsf_format(report_dir, json_file_path):
    """
    Read video metrics from JSON file and write to CSV file.
    """

    output_file = os.path.join(report_dir, "video_search_embedding_metrics_wsf.csv")

    # Read JSON file
    with open(json_file_path, 'r') as f:
        data = json.load(f)
       
    videos = data.get('Input_Videos', [])
    
    # Collect embedding_per_sec values for min/avg/max calculation
    embedding_per_sec_values = []
    
    rows = []
    
    for idx, video in enumerate(videos, start=1):
        video_prefix = f"Video_{idx}"
            
        
       # rows.append([f"{video_prefix} file size(Mb)", 0.0])
        rows.append([f"{video_prefix}_00_duration (s)", video.get('duration_seconds', 0.0)])
        rows.append([f"{video_prefix}_01_FPS", video.get('fps', 0.0)])
        rows.append([f"{video_prefix}_02_total_frames", video.get('total_frames', 0)])
        rows.append([f"{video_prefix}_03_frames_extracted", video.get('frames_extracted', 0)])
        rows.append([f"{video_prefix}_04_Embedding_Throughput (frames/sec)", video.get('embedding_per_sec', 0.0)])
        # rows.append([f"{video_prefix}_05_Relative_RTF ((embedding latency/duration)*(30/FPS))", round(relative_rtf, 4)])
        # rows.append([f"{video_prefix}_05_Normalized_Embedding_RTF", round(relative_rtf, 4)])
        if 'embedding_per_sec' in video:
            embedding_per_sec_values.append(video['embedding_per_sec'])
    
    embedding_avg, embedding_min, embedding_max = calculate_metrics(embedding_per_sec_values)[:3]
    rows.append(["Embedding_Throughput_min (frames/sec)", embedding_min])
    rows.append(["Embedding_Throughput_avg (frames/sec)", embedding_avg])
    rows.append(["Embedding_Throughput_max (frames/sec)", embedding_max])
    
    
    # Write to CSV file
    with open(output_file, 'w', newline='') as f:
        writer = csv.writer(f)
        writer.writerows(rows)
    
    print(f"WSF formatted output written to: {output_file}")

    return output_file










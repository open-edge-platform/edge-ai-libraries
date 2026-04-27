# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
Video file processing and analysis utilities.

This module provides functions for uploading, processing, and analyzing
video files including metadata extraction, embedding creation, and summary handling.
"""

import os
import time
from datetime import datetime, timezone

import requests
from moviepy import VideoFileClip


def get_video_details(video_file_path):
    """
    Extract comprehensive metadata from a video file.
    
    Args:
        video_file_path: Path to the video file.
        
    Returns:
        dict: Video metadata including file size, duration, and FPS.
    """
    file_size_mb = os.path.getsize(video_file_path) / (1024 * 1024)

    clip = None
    try:
        clip = VideoFileClip(video_file_path)
        duration = clip.duration
        fps = clip.fps
    finally:
        if clip is not None:
            clip.close()

    return {
        "File_Size (MB)": round(file_size_mb, 2),
        "File_Duration (s)": round(duration, 2),
        "File_videoFPS": round(fps, 2)
    }


def upload_video_file(url, filename, filepath):
    """
    Upload a video file to the specified endpoint and retrieve the video ID.
    
    Args:
        url: The upload API endpoint URL.
        filename: Name of the video file.
        filepath: Path to the video file.
        
    Returns:
        str: Video ID if upload succeeded, None otherwise.
    """
    try:
        if filepath is None or filename is None:
            print("Error: Filepath or filename is None.")
            return None
        if not os.path.isfile(filepath):
            print(f"Error: File not found at {filepath}")
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
    Initiate embedding generation for an uploaded video.
    
    Args:
        url: The embedding API endpoint URL.
        video_id: ID of the uploaded video.
        
    Returns:
        int: HTTP status code if successful, None on error.
    """
    try:
        print("Waiting for video embedding creation to complete...")
        headers = {'Content-Type': 'application/json'}
        endpoint = f"{url}/{video_id}"
        start_time = time.time()
        response = requests.post(endpoint, headers=headers, data={})
        end_time = time.time()
        elapsed_time = round(end_time - start_time, 2)
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
    Poll the video summary API endpoint until processing is complete.
    
    Args:
        url: The API endpoint URL to poll for status.
        
    Returns:
        tuple: (completion_status, response) where completion_status is True if
               video summary completed successfully, False otherwise.
    """
    video_summary_complete = False
    response = ""
    must_end = time.time() + 3600 # Set a maximum wait time of 1 hour for video summary completion
    print("Waiting for video summary to complete...")
    
    while time.time() < must_end:
        try:
            response = requests.get(url, timeout=10)
            status_code = response.status_code
            
            if status_code != 200:
                print(f"Error: Received status code {status_code}. Response: {response.text}")
                break
            
            json_response = response.json()
            
            if json_response.get("videoSummaryStatus") == "complete":
                video_summary_complete = True
                break
            
            time.sleep(10)

        except KeyboardInterrupt:
            print("Keyboard interrupt received. Exiting...")
            raise SystemExit(130)
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
    Process a video summary API response and save formatted summaries to a file.
    
    Args:
        report_dir: Directory to save the summary file.
        response: API response object containing the summary.
        summary_id: ID of the summary for filename.
    """
    filename = os.path.join(report_dir, f"video_response_{summary_id}.txt")
    
    try:
        response_data = response.json()
        overall_summary = response_data.get("summary", "")
        frame_summaries = response_data.get("frameSummaries", [])
        
        with open(filename, "w") as file:
            if overall_summary:
                file.write(overall_summary + "\n\n")
            
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


def embedding_creation_per_sec(video_details, embedding_time):
    """
    Calculate the embedding creation rate in frames per second.
    
    Args:
        video_details: Dictionary containing video metadata (Duration, FPS).
        embedding_time: Time taken for embedding creation in seconds.
        
    Returns:
        float: Embedding creation rate in frames per second, or 0.0 on error.
    """
    try:
        duration = video_details.get("Duration (s)", 0)
        fps = video_details.get("FPS", 0)
        
        if duration <= 0 or fps <= 0 or embedding_time <= 0:
            return 0.0
        
        total_frames = duration * fps
        extracted_frames = total_frames / 15
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
    Calculate the video summarization rate in frames per second.
    
    Args:
        video_details: Dictionary containing video metadata (Duration, FPS).
        summarization_time: Time taken for summarization in seconds.
        
    Returns:
        float: Summarization rate in frames per second, or 0.0 on error.
    """
    try:
        duration = video_details.get("Duration (s)", 0)
        fps = video_details.get("FPS", 0)
        
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
    Convert an ISO 8601 formatted timestamp string to a Unix epoch float.
    
    Args:
        timestamp: ISO 8601 timestamp string (e.g., '2024-01-01T12:00:00.000000Z').
        
    Returns:
        float: Unix epoch timestamp.
        
    Raises:
        TypeError: If timestamp is not a string.
        ValueError: If timestamp format is invalid.
    """
    try:
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

def wait_for_search_to_complete(search_url, query_id):
    querySearchStatus = None 
    search_time = 0 
    each_response = {}
    while querySearchStatus != "idle":
        get_response = requests.get(search_url)

        if get_response.status_code != 200:
            print(f"Error: Failed to fetch search status. HTTP status code: {get_response.status_code}")
            break
        
        for each in get_response.json():
            if each.get("queryId") == query_id:
                querySearchStatus = each.get("queryStatus")
                each_search_time = convert_timestamp_to_float(each.get("updatedAt", 0)) - convert_timestamp_to_float(each.get("createdAt", 0))
                each_response = each
            time.sleep(1)
    search_time = round(each_search_time, 4)
    return search_time, each_response

def get_live_caption_metadata(url, duration_seconds=120):
    """
    Collect metadata from live caption stream for the specified duration.
    
    Args:
        url: The streaming API endpoint URL.
        duration_seconds: Duration to collect data in seconds (default: 120).
        
    Returns:
        list: List of collected data entries.
    """
    collected_data = []
    start_time = time.time()
    end_time = start_time + duration_seconds
    
    print(f"Collecting video caption data for {duration_seconds} seconds...")
    
    with requests.get(url, stream=True) as response:
        try:
            for line in response.iter_lines(decode_unicode=True):
                if time.time() >= end_time:
                    print(f"\nCollection complete. Collected {len(collected_data)} data entries.")
                    break
                if line and "data" in line:
                    collected_data.append(line)
        except KeyboardInterrupt:
            print("\nStopped streaming")
    
    return collected_data


def stop_all_run_request(run_url, run_ids):
    """
    Stop all live caption runs by sending DELETE requests.
    
    Args:
        run_url: Base URL for the runs API.
        run_ids: List of run IDs to stop.
    """
    for run_id in run_ids:
        response = requests.request("DELETE", f"{run_url}/{run_id}")
        print("Stopped live caption:", response.json())

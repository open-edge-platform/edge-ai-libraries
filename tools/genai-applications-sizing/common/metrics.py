# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
Metrics calculation and reporting utilities.

This module provides functions for calculating performance metrics,
writing metrics to CSV and JSON files, and generating reports.
"""

import csv
import json
import os
import numpy as np



def calculate_metrics(latencies):
    """
    Calculate statistical metrics for a given dataset.

    Args:
        latencies: List of numerical values.

    Returns:
        tuple: (average, min, max, p99, p90, p75) values, or all None on error.
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


def write_metrics(metrics, report_dir):
    """
    Write metrics to a JSON file.
    
    Args:
        metrics: List of metric dictionaries.
        report_dir: Directory to save the JSON file.
        
    Returns:
        tuple: (latencies, input_tokens, output_tokens, ttfts, itls, tpss) lists.
    """
    latencies, input_tokens, output_tokens, ttfts, itls, tpss = [], [], [], [], [], []
    filename = os.path.join(report_dir, "chat_api_individual_metrics.json")
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


def write_chatqna_metrics_to_csv(report_dir, latencies, input_tokens, output_tokens, ttfts, itls, tpss, file_details=None):
    """
    Write metrics summary to CSV files (both detailed and WSF format).

    Args:
        report_dir: Directory to save the CSV files.
        latencies: List of latencies.
        input_tokens: List of input tokens.
        output_tokens: List of output tokens.
        ttfts: List of time-to-first-token values.
        itls: List of inter-token latencies.
        tpss: List of tokens per second.
        file_details: Details of the file including name and size (optional).
    """
    if file_details is None:
        file_details = {}
        
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
            writer.writerow(['File Name', file_details.get("name", "N/A")])
            writer.writerow(['File Size (MB)', file_details.get("size_mb", "N/A")])
            
    except Exception as e:
        print(f"Failed to write metrics to CSV: {e}")


def write_rest_metrics(report_dir, metrics):
    """
    Write API metrics to a JSON file.
    
    Args:
        report_dir: Directory to save the JSON file.
        metrics: List of latency values.
    """
    json_file = os.path.join(report_dir, "document_api_individual_metrics.json")
    try:
        with open(json_file, "a") as file:
            for metric in metrics:
                json.dump({"LATENCY (ms)": metric}, file, indent=4)
    except Exception as e:
        print(f"Writing rest metrics to file, failed with exception {e}")


def write_rest_metrics_summary_to_csv(report_dir, latency, throughput):
    """
    Write a summary of REST API metrics to a CSV file.
    
    Args:
        report_dir: Directory to save the CSV file.
        latency: List of latency values.
        throughput: Throughput value.
    """
    output_file = os.path.join(report_dir, "document_api_summary_metrics.csv")
    
    try:
        metrics = calculate_metrics(latency)
        if metrics[0] is None:
            print("Failed to calculate metrics. Check latency data.")
            return
        
        avg, min_val, max_val, p99, p90, p75 = metrics
        
        with open(output_file, mode='w', newline='') as file:
            writer = csv.writer(file)
            writer.writerow(['', '', '', 'Rest API Metrics', '', '', ''])
            writer.writerow(['Statistic', 'Avg', 'Min', 'Max', 'p99', 'p90', 'p75'])
            writer.writerow(['Latency (ms)', avg, min_val, max_val, p99, p90, p75])
            writer.writerow(['Throughput', round(throughput, 4), 'NA', 'NA', 'NA', 'NA', 'NA'])
        
        print(f"REST API metrics summary written to: {output_file}")
        
    except TypeError as e:
        print(f"Invalid data type for latency or throughput: {e}")
    except IOError as e:
        print(f"Failed to write metrics to file {output_file}: {e}")
    except Exception as e:
        print(f"Unexpected error writing REST metrics summary: {e}")


def rest_api_metrics(api_name, report_dir, latencies):
    """
    Collect and write REST API metrics to files.
    
    Args:
        api_name: Name of the API for file naming.
        report_dir: Directory to save the files.
        latencies: List of latency values.
    """
    output_file = os.path.join(report_dir, f"{api_name}_api_summary_metrics.csv")
    json_file = os.path.join(report_dir, f"{api_name}_api_metrics.json")
    
    average_latency, min_latency, max_latency, p99_latency, p90_latency, p75_latency = calculate_metrics(latencies)
    throughput = len(latencies) / (sum(latencies) / 1000) if sum(latencies) > 0 else 0
    
    try:
        with open(json_file, "a") as file:
            for latency in latencies:
                json.dump({"LATENCY (ms)": latency}, file, indent=4)
                
        with open(output_file, mode='w', newline='') as file:
            writer = csv.writer(file)
            writer.writerow(['', '', '', 'Rest API Metrics', '', '', ''])
            writer.writerow(['Statistic', 'Avg', 'Min', 'Max', 'p99', 'p90', 'p75'])
            writer.writerow(['Latency (ms)', average_latency, min_latency, max_latency, p99_latency, p90_latency, p75_latency])
            writer.writerow(['Throughput', round(throughput, 2), "NA", "NA", "NA", "NA", "NA"])

    except Exception as e:
        print(f"Writing rest metrics to file, failed with exception {e}")
        print(f"{api_name.capitalize()} API metrics collection completed. Reports saved in: {report_dir}")


# ==============================================================================
# Video Summary Metrics
# ==============================================================================

def write_vss_metrics(report_dir, metrics):
    """Write video summary/search metrics to a JSON file."""
    json_file = os.path.join(report_dir, "video_summary_metrics.json")
    try:
        with open(json_file, "a") as file:
            json.dump(metrics, file, indent=4)
    except Exception as e:
        print(f"Writing rest metrics to file, failed with exception {e}")


def write_video_summary_metrics(report_dir, metrics):
    """
    Write individual video summary API metrics to a JSON file.
    
    Args:
        report_dir: Directory path where the metrics file will be saved.
        metrics: Dictionary containing metrics data to be written.
    """
    json_file = os.path.join(report_dir, "summary_api_individual_metrics.json")
    try:
        with open(json_file, "a") as file:
            json.dump(metrics, file, indent=4)
            file.write('\n')
    except IOError as e:
        print(f"Failed to write video summary metrics to {json_file}: {e}")
    except TypeError as e:
        print(f"Invalid metrics data type (must be JSON serializable): {e}")
    except Exception as e:
        print(f"Unexpected error writing video summary metrics: {e}")


def write_video_search_metrics(report_dir, metrics):
    """Write individual video search API metrics to a JSON file."""
    json_file = os.path.join(report_dir, "search_api_individual_metrics.json")
    try:
        with open(json_file, "a") as file:
            json.dump(metrics, file, indent=4)
            file.write('\n')
    except IOError as e:
        print(f"Failed to write video search metrics to {json_file}: {e}")
    except TypeError as e:
        print(f"Invalid metrics data type (must be JSON serializable): {e}")
    except Exception as e:
        print(f"Unexpected error writing video search metrics: {e}")


def write_video_search_metrics_summary_to_csv(report_dir, search_latencies, throughput, video_file_paths=None):
    """
    Write a comprehensive summary of video search API metrics to a CSV file.
    
    Args:
        report_dir: Directory to save the CSV file.
        search_latencies: List of search latency values.
        throughput: Throughput value.
        video_file_paths: Optional list of video file paths for metadata.
    """
    from common.video import get_video_details
    
    output_file = os.path.join(report_dir, "search_api_metrics_summary.csv")
    
    try:
        latency_metrics = calculate_metrics(search_latencies)
        
        if latency_metrics[0] is None:
            print("Failed to calculate metrics. Check search latency data.")
            return
        
        avg_latency, min_latency, max_latency = latency_metrics[:3]
        
        with open(output_file, mode='w', newline='') as file:
            writer = csv.writer(file)
            
            if video_file_paths:
                writer.writerow(['', 'Video file details', '', ''])
                
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
                
                writer.writerow(['', '', '', ''])
            
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


def write_video_summary_metrics_summary_to_csv(report_dir, latencies, ttft, tps, video_file_path=None, sampling_params=None):
    """
    Write a comprehensive summary of video summary API metrics to a CSV file.
    """
    from common.video import get_video_details
    
    output_file = os.path.join(report_dir, "summary_api_metrics_summary.csv")
    
    try:
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
            
            if video_file_path:
                writer.writerow(['', 'Video file details', '', ''])
                try:
                    video_details = get_video_details(video_file_path)
                    
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
                
                writer.writerow(['', '', '', ''])
            
            if sampling_params:
                writer.writerow(['', 'Sampling Configuration', '', ''])
                sampling_fields = [
                    ('Chunk Duration', 'chunkDuration'),
                    ('Sample Frame Per Chunk', 'samplingFrame'),
                    ('Frames Overlap', 'frameOverlap'),
                    ('MultiFrame', 'multiFrame')
                ]
                
                for label, key in sampling_fields:
                    writer.writerow([label, sampling_params.get(key, 'N/A'), '', ''])
                
                writer.writerow(['', '', '', ''])
            
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


def get_video_summary_telemetry_kpis(start_time, end_time, telemetry_json_response, video_properties):
    """
    Extract and calculate video summarization telemetry KPIs from telemetry response data.
    
    Args:
        start_time: Start timestamp of the summarization.
        end_time: End timestamp of the summarization.
        telemetry_json_response: JSON response from telemetry API.
        video_properties: Dictionary to store video metrics.
        
    Returns:
        tuple: (video_properties, telemetry_details)
    """
    from common.video import convert_timestamp_to_float
    
    try:
        ttfts, latencies, tpss = {}, {}, []
        timestamps, prompt_tokens, output_tokens, total_tokens, tpots = [], [], [], [], []
        telemetry_details = []
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
        
        # Calculate metrics from telemetry data
        min_timestamp = min(timestamps)
        ttft = ttfts.get(min_timestamp, 0)
        late = latencies.get(min_timestamp, 0) / 1000  # Convert to seconds
        delta = (min_timestamp - late) - start_time
        tps = sum(tpss) / len(tpss) if len(tpss) > 0 else 0
        avg_input_tokens = sum(prompt_tokens) / len(prompt_tokens) if len(prompt_tokens) > 0 else 0
        avg_output_tokens = sum(output_tokens) / len(output_tokens) if len(output_tokens) > 0 else 0
        avg_total_tokens = sum(total_tokens) / len(total_tokens) if len(total_tokens) > 0 else 0
        tpot = sum(tpots) / len(tpots) if len(tpots) > 0 else 0
        e2e_summary_latency = end_time - start_time
        rtf = e2e_summary_latency / (video_properties.get('File_Duration (s)', 1))
        complexity = (video_properties.get('File_videoFPS', 0) * video_properties.get('File_Duration (s)', 0)) / e2e_summary_latency

        # Write metrics to video properties
        video_properties['Average_Prompt_Tokens'] = avg_input_tokens
        video_properties['Average_Completion_Tokens'] = avg_output_tokens
        video_properties['Average_Total_Tokens'] = avg_total_tokens
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
        return video_properties, []

## As per old implementaion
def get_video_search_telemetry_kpis(start_time, end_time, telemetry_json_response, search_metrics):
    """
    Extract video search telemetry KPIs from the telemetry response within a time window.
    
    Args:
        start_time: Start timestamp of the search.
        end_time: End timestamp of the search.
        telemetry_json_response: JSON response from telemetry API.
        search_metrics: Search metrics to include in output.
        
    Returns:
        tuple: (metrics, telemetry_details)
    """
    from common.video import convert_timestamp_to_float
    
    metrics = {}
    input_videos = []
    telemetry_details = []
    
    metrics["Video_Search_E2E_Latency"] = round(end_time - start_time, 2)
    items = telemetry_json_response.get("items", [])
    
    for item in items:
        try:
            timestamp_str = item.get("timestamps", {}).get("requested_at", "")
            if not timestamp_str:
                continue
            
            timestamp = convert_timestamp_to_float(timestamp_str)
            
            if not (start_time <= timestamp):
                continue
            
            telemetry_details.append(item)
            video_file_details = item.get("video", {})
            video_details = {
                "id": video_file_details.get("video_id"),
                "file_name": video_file_details.get("filename", "N/A"),
                "duration_seconds": round(video_file_details.get("video_duration_seconds", 1), 2),
                "fps": round(video_file_details.get("fps", 0), 2),
                "total_frames": video_file_details.get("total_frames", 0),
                "frames_extracted": item.get("counts", {}).get("frames_extracted", 0)
            }
            
            stages = item.get("stages", [])
            for stage in stages:
                stage_name = stage.get("name")
                stage_seconds = stage.get("seconds", 0)
                video_details[stage_name] = stage_seconds
                
                if stage_name == "embedding":
                    video_details["embedding_percent_of_total"] = stage.get("percent_of_total", 0)
            
            video_details["wall_time_seconds"] = item.get("timestamps", {}).get("wall_time_seconds", 0)
            video_details["embedding_per_sec"] = item.get("throughput", {}).get("embeddings_per_second", 0)
            relative_rtf = (
                (video_details.get("wall_time_seconds", 0) / video_details.get("duration_seconds", 1))
                * (30 / video_details.get("fps", 1))
            )
            video_details["Normalized_Embedding_RTF"] = round(relative_rtf, 4)
            input_videos.append(video_details)
            
        except (ValueError, TypeError, KeyError) as e:
            print(f"Warning: Skipping telemetry item due to error: {e}")
            continue
    
    metrics["Input_Videos"] = input_videos
    metrics["Search_Metrics"] = search_metrics
    return metrics, telemetry_details

## As per new implementaion
# def get_video_search_telemetry_kpis(start_time, end_time, telemetry_json_response, search_metrics):
#     """
#     Extract video search telemetry KPIs from the telemetry response within a time window.
    
#     Args:
#         start_time: Start timestamp of the search.
#         end_time: End timestamp of the search.
#         telemetry_json_response: JSON response from telemetry API.
#         search_metrics: Search metrics to include in output.
        
#     Returns:
#         tuple: (metrics, telemetry_details)
#     """
#     from common.video import convert_timestamp_to_float
    
#     metrics = {}
#     input_videos = []
#     telemetry_details = []
    
#     metrics["Video_Search_E2E_Latency"] = round(end_time - start_time, 2)
#     items = telemetry_json_response.get("items", [])
    
#     for item in items:
#         try:
#             timestamp_str = item.get("timestamps", {}).get("requested_at", "")
#             if not timestamp_str:
#                 continue
            
#             timestamp = convert_timestamp_to_float(timestamp_str)            
#             if not (start_time <= timestamp):
#                 continue
            
#             telemetry_details.append(item)
#             video_file_details = item.get("video", {})
#             video_details = {
#                 "id": video_file_details.get("video_id"),
#                 "file_name": video_file_details.get("filename", "N/A"),
#                 "duration_seconds": round(video_file_details.get("video_duration_seconds", 1), 2),
#                 "fps": round(video_file_details.get("fps", 0), 2),
#                 "total_frames": video_file_details.get("total_frames", 0),
#                 "frames_extracted": item.get("counts", {}).get("frames_extracted", 0),
#                 "embeddings_stored": item.get("counts", {}).get("embeddings_stored", 0)
#             }
            
#             video_details.update(item.get("stage_duration", {}))            
#             video_details["wall_time_seconds"] = item.get("timestamps", {}).get("wall_time_seconds", 0)
#             video_details["embedding_per_sec"] = item.get("stage_throughput", {}).get("embeddings_throughput", 0)
#             relative_rtf = (
#                 (video_details.get("wall_time_seconds", 0) / video_details.get("video_duration_seconds", 1))
#                 * (30 / video_details.get("fps", 1))
#             )
#             video_details["Normalized_Embedding_RTF"] = round(relative_rtf, 4)
#             input_videos.append(video_details)
            
#         except (ValueError, TypeError, KeyError) as e:
#             print(f"Warning: Skipping telemetry item due to error: {e}")
#             continue
    
#     metrics["Input_Videos"] = input_videos
#     metrics["Search_Metrics"] = search_metrics
#     return metrics, telemetry_details

def save_video_summary_search_telemetry_kpis(report_dir, metrics, telemetry_details=None, query_metrics=None):
    """
    Save video search telemetry KPIs to a JSON file.
    
    Args:
        report_dir: Directory to save the files.
        metrics: Metrics dictionary to save.
        telemetry_details: Optional telemetry details to save.
        query_metrics: Optional query metrics to save.
    Returns:
        str: Path to the output file.
    """
    output_file = os.path.join(report_dir, "video_summary_search_metrics.json")
    telemetry_file = os.path.join(report_dir, "video_summary_search_telemetry_details.json")

    telemetry_embedd_search_details = []
    telemetry_embedd_search_details.append({"Embedding_telemetry": telemetry_details})
    telemetry_embedd_search_details.append({"Search_telemetry": query_metrics})
    
    try:
        with open(output_file, "w") as file:
            json.dump(metrics, file, indent=4)
        print(f"Video summary and search embedding metrics written to: {output_file}")

        with open(telemetry_file, "w") as t_file:
            json.dump(telemetry_embedd_search_details, t_file, indent=4)
        print(f"Video embedding telemetry details written to: {telemetry_file}")


    except IOError as e:
        print(f"Failed to write video search embedding metrics to {output_file}: {e}")
    except TypeError as e:
        print(f"Invalid data type for embedding metrics: {e}")
    except Exception as e:
        print(f"Unexpected error writing video search embedding metrics: {e}")
    
    return output_file


def convert_summary_metrics_to_wsf_format(report_dir, json_file_path, samples=None):
    """
    Read values from a JSON file and write to CSV in key,value format.
    
    Args:
        report_dir: Directory to save the CSV file.
        json_file_path: Path to the input JSON file.
        samples: Optional sampling parameters to include.
    """
    output_file = os.path.join(report_dir, "video_summary_metrics_wsf.csv")
    
    with open(json_file_path, 'r') as f:
        data = json.load(f)
    
    if isinstance(data, list):
        data = data[0]
    
    with open(output_file, 'w', newline='') as f:
        writer = csv.writer(f)
        
        if samples:
            for key, value in samples.items():
                writer.writerow([f"Sampling-{key}", value])
        
        wsf_keys = [
            'File_Duration (s)', 'File_videoFPS', 'Time To First Token (s)',
            'Throughput (tokens/sec)', 'Video Summary Pre ProcessingTime (s)',
            'Video Summary E2E Latency (s)', 'Video Summarization RTF (latency/duration)',
            'Video Summary Processing Efficiency ((fps*duration)/latency)'
        ]
        
        for key, value in data.items():
            if key in wsf_keys:
                writer.writerow([key, value])

    print(f"WSF formatted output written to: {output_file}")


def convert_search_metrics_to_wsf_format(report_dir, json_file_path):
    """
    Read video metrics from JSON file and write to CSV file.
    
    Args:
        report_dir: Directory to save the CSV file.
        json_file_path: Path to the input JSON file.
        
    Returns:
        str: Path to the output file.
    """
    output_file = os.path.join(report_dir, "video_search_embedding_metrics_wsf.csv")

    with open(json_file_path, 'r') as f:
        data = json.load(f)
       
    videos = data.get('Input_Videos', [])
    embedding_per_sec_values = []
    rows = []
    
    for idx, video in enumerate(videos, start=1):
        video_prefix = f"Video_{idx}"
        
        rows.append([f"{video_prefix}_00_duration (s)", video.get('duration_seconds', 0.0)])
        rows.append([f"{video_prefix}_01_FPS", video.get('fps', 0.0)])
        rows.append([f"{video_prefix}_02_total_frames", video.get('total_frames', 0)])
        rows.append([f"{video_prefix}_03_frames_extracted", video.get('frames_extracted', 0)])
        rows.append([f"{video_prefix}_04_Embedding_Throughput (frames/sec)", video.get('embedding_per_sec', 0.0)])
        
        if 'embedding_per_sec' in video:
            embedding_per_sec_values.append(video['embedding_per_sec'])
    
    embedding_avg, embedding_min, embedding_max = calculate_metrics(embedding_per_sec_values)[:3]
    rows.append(["Embedding_Throughput_min (frames/sec)", embedding_min])
    rows.append(["Embedding_Throughput_avg (frames/sec)", embedding_avg])
    rows.append(["Embedding_Throughput_max (frames/sec)", embedding_max])
    
    with open(output_file, 'w', newline='') as f:
        writer = csv.writer(f)
        writer.writerows(rows)
    
    print(f"WSF formatted output written to: {output_file}")
    return output_file


# ==============================================================================
# Live Caption Metrics
# ==============================================================================

def get_live_caption_metrics(metadata_list):
    """
    Process collected metadata entries and return aggregated KPIs grouped by runId.
    
    Args:
        metadata_list: List of metadata strings from the live caption API.
        
    Returns:
        dict: Dictionary with runIds as keys and lists of KPI dictionaries as values.
    """
    kpis_by_run_id = {}
    
    for metadata in metadata_list:
        json_string = metadata[6:]
        try:
            parsed_data = json.loads(json_string)
            run_id = parsed_data.get("runId", "unknown")
            metrics = parsed_data.get("data", {}).get("metrics", {})
            
            kpis = {
                "InputTokens": metrics.get("num_input_tokens"),
                "TotalGeneratedTokens": metrics.get("num_generated_tokens"),
                "TTFT (ms)": metrics.get("ttft_mean"),
                "TPOT (ms)": metrics.get("tpot_mean"),
                "Latency (ms)": metrics.get("generate_duration_mean"),
                "Throughput (tok/s)": metrics.get("throughput_mean")
            }
            
            if run_id not in kpis_by_run_id:
                kpis_by_run_id[run_id] = []
            kpis_by_run_id[run_id].append(kpis)
            
        except json.JSONDecodeError as e:
            print(f"Skipping invalid JSON data: {e}")
            continue
    
    return kpis_by_run_id


def save_live_video_caption_telemetry_kpis(report_dir, kpis_by_run_id, run_configs=None):
    """
    Save live video caption telemetry KPIs grouped by runId.
    
    Args:
        report_dir: Directory to save the metrics files.
        kpis_by_run_id: Dictionary with runIds as keys and lists of KPI dictionaries as values.
        run_configs: Optional dictionary mapping runIds to their config.
        
    Returns:
        str: Path to the summary file.
    """
    os.makedirs(report_dir, exist_ok=True)
    run_configs = run_configs or {}
    
    filename = os.path.join(report_dir, "live_caption_indv_metrics.json")
    with open(filename, "w") as file:
        json.dump(kpis_by_run_id, file, indent=4)
    
    summary_file = os.path.join(report_dir, "live_caption_summary_metrics.json")
    summary = {}
    
    for run_id, kpis_list in kpis_by_run_id.items():
        if not kpis_list:
            continue
        
        config = run_configs.get(run_id, {})
        
        run_summary = {
            "rtspUrl": config.get("rtspUrl"),
            "modelName": config.get("modelName"),
            "pipelineName": config.get("pipelineName"),
            "sample_count": len(kpis_list),
            "Total InputTokens": max(kpi["InputTokens"] for kpi in kpis_list if kpi["InputTokens"] is not None) if kpis_list else None,
            "Total GeneratedTokens": max(kpi["TotalGeneratedTokens"] for kpi in kpis_list if kpi["TotalGeneratedTokens"] is not None) if kpis_list else None,
            "Average TTFT (ms)": sum(kpi["TTFT (ms)"] for kpi in kpis_list if kpi["TTFT (ms)"] is not None) / len(kpis_list),
            "Average TPOT (ms)": sum(kpi["TPOT (ms)"] for kpi in kpis_list if kpi["TPOT (ms)"] is not None) / len(kpis_list),
            "Average Latency (ms)": sum(kpi["Latency (ms)"] for kpi in kpis_list if kpi["Latency (ms)"] is not None) / len(kpis_list),
            "Average Throughput (tok/s)": sum(kpi["Throughput (tok/s)"] for kpi in kpis_list if kpi["Throughput (tok/s)"] is not None) / len(kpis_list)
        }
        summary[run_id] = run_summary
    
    with open(summary_file, "w") as file:
        json.dump(summary, file, indent=4)
    
    return summary_file


def save_metrics_to_wsf_format(report_dir, summary_file, live_caption_duration_seconds):
    """
    Save live caption metrics to WSF CSV format.
    
    Args:
        report_dir: Directory to save the CSV file.
        summary_file: Path to the summary JSON file.
        live_caption_duration_seconds: Duration of caption collection.
    """
    output_file = os.path.join(report_dir, "live_caption_metrics_wsf.csv")
    
    with open(summary_file, "r") as file:
        summary = json.load(file)
    
    with open(output_file, 'w', newline='') as f:
        writer = csv.writer(f)
        
        for run_id, metrics in summary.items():
            writer.writerow(["Avg TTFT (ms)", metrics.get("Average TTFT (ms)", 0)])
            writer.writerow(["Avg TPOT (ms)", metrics.get("Average TPOT (ms)", 0)])
            writer.writerow(["Avg Latency (ms)", metrics.get("Average Latency (ms)", 0)])
            writer.writerow(["Avg Throughput (tok/s)", metrics.get("Average Throughput (tok/s)", 0)])
            writer.writerow(["Caption Duration (s)", live_caption_duration_seconds])
            writer.writerow(["Total Requests (count)", metrics.get("sample_count", 0)])
            writer.writerow([])
    
    print(f"WSF formatted live caption metrics written to: {output_file}")

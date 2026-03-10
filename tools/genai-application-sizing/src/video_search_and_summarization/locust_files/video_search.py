# Copyright (C) 2024 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import json
from locust import task, events, HttpUser
import os
import time
from common.utils import convert_search_metrics_to_wsf_format, get_video_search_telemetry_kpis, save_video_summary_search_telemetry_kpis, upload_video_file, embedding_video_file, safe_parse_string_to_dict
import itertools

@events.init_command_line_parser.add_listener
def add_custom_arguments(parser):
    """
    Adds custom command-line arguments for the Locust test.

    Args:
        parser (argparse.ArgumentParser): The argument parser to add arguments to.
    """
    # parser.add_argument("--request_count", type=int, default=1, help="Number of requests per user.")
    parser.add_argument("--search_endpoint", type=str, default="", help="Video search API endpoint.")
    parser.add_argument("--embedding_endpoint", type=str, default="", help="Video embedding API endpoint.")
    parser.add_argument("--upload_endpoint", type=str, default="", help="Video upload API endpoint.")
    parser.add_argument("--telemetry_endpoint", type=str, default="6016/telemetry", help="Video telemetry API endpoint.")
    parser.add_argument("--file_details", type=str, default="", help="Details of the video file to be uploaded.")
    parser.add_argument("--queries", type=str, default="", help="Queries for video search.")
    parser.add_argument("--report_dir", type=str, default="reports", help="Directory to save reports.")


class VideoSearchHwSize(HttpUser):
    """
    Locust user class for testing the video search API hardware sizing.
    """
    # Class variables for shared data across all instances
    metrics = []
    search_metrics = []
    search_latencies = []
    queries = []

    def on_start(self):
        # Instance variables for per-user data
        parsed_opts = self.environment.parsed_options
        
        self.search_endpoint = parsed_opts.search_endpoint
        self.upload_endpoint = parsed_opts.upload_endpoint
        self.embedding_endpoint = parsed_opts.embedding_endpoint
        self.telemetry_endpoint = parsed_opts.telemetry_endpoint
        
        # Pre-compute URLs once
        self.upload_url = f"{self.host}:{self.upload_endpoint}"    
        self.embedding_url = f"{self.host}:{self.embedding_endpoint}"
        
        # Parse file details and queries once
        self.file_details = safe_parse_string_to_dict(parsed_opts.file_details)
        VideoSearchHwSize.queries = safe_parse_string_to_dict(parsed_opts.queries)
        
        # Setup report directory once
        report_dir = parsed_opts.report_dir
        VideoSearchHwSize.report_dir = os.path.join(report_dir, "video_search")
        os.makedirs(VideoSearchHwSize.report_dir, exist_ok=True)
        
        VideoSearchHwSize.process_start_time = time.time()

        # Process files with optimized timing
        for file_detail in self.file_details:
            filename = file_detail.get("name", None)
            filepath = file_detail.get("path", None)            
            video_id = upload_video_file(self.upload_url, filename, filepath)            
            if video_id is not None:
                embedding_status = embedding_video_file(self.embedding_url, video_id)      
        
        VideoSearchHwSize.process_end_time = time.time()

        # Create the query cycle after queries are populated
        self.query_cycle = itertools.cycle(VideoSearchHwSize.queries)

    @task
    def search_video(self):
        """
            Search video using queries
        """
        qry = next(self.query_cycle)
        headers = {'Content-Type': 'application/json'}
        
        try:          

            search_start_time = time.time()
            response = self.client.post(
                f":{self.search_endpoint}", 
                headers=headers, 
                json=qry
            )
            search_time = round(time.time() - search_start_time, 4)
            
            if response.status_code == 201:
                print("Video search completed.")
            else:
                print(f"Search failed with status {response.status_code}: {response.text}")
            
            # Append metrics efficiently
            VideoSearchHwSize.search_latencies.append(search_time)
            VideoSearchHwSize.search_metrics.append({
                **qry,
                "query_search_seconds": search_time
            })

            VideoSearchHwSize.telemetry_response = self.client.get(f":{self.telemetry_endpoint}", headers=headers)
            
        except Exception as e:
            print(f"Video search failed: {e}")


@events.quitting.add_listener
def collect_metrics(environment, **kwargs):
    """
        Collect and write metrics
    """
    print("Collecting metrics...")
    
    metrics, telemetry_details = get_video_search_telemetry_kpis(VideoSearchHwSize.process_start_time, VideoSearchHwSize.process_end_time, VideoSearchHwSize.telemetry_response.json(), VideoSearchHwSize.search_metrics)
    json_file = save_video_summary_search_telemetry_kpis(VideoSearchHwSize.report_dir, metrics, telemetry_details)
    convert_search_metrics_to_wsf_format(VideoSearchHwSize.report_dir, json_file)

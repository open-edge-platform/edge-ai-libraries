# Copyright (C) 2024 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import json
from locust import task, events, HttpUser
import os
import time
from common.utils import convert_summary_metrics_to_wsf_format, get_video_summary, get_video_summary_telemetry_kpis, save_video_summary_search_telemetry_kpis, upload_video_file, wait_for_video_summary_complete, get_video_details, safe_parse_string_to_dict



@events.init_command_line_parser.add_listener
def add_custom_arguments(parser):
    """
    Adds custom command-line arguments for the Locust test.

    Args:
        parser (argparse.ArgumentParser): The argument parser to add arguments to.
    """
# parser.add_argument("--request_count", type=int, default=1, help="Number of requests per user.")
    parser.add_argument("--summary_endpoint", type=str, default="config.yaml", help="video summary API endpoint.")
    parser.add_argument("--state_endpoint", type=str, default="config.yaml", help="video summary states API endpoint.")
    parser.add_argument("--upload_endpoint", type=str, default="config.yaml", help="video summary upload API endpoint.")
    parser.add_argument("--telemetry_endpoint", type=str, default="config.yaml", help="video summary upload API endpoint.")
    parser.add_argument("--filename", type=str, default="config.yaml", help="video summary filename API endpoint.")
    parser.add_argument("--filepath", type=str, default="config.yaml", help="video summary filepath API endpoint.")
    parser.add_argument("--payload", type=str, default="config.yaml", help="video summary payload API endpoint.")
    parser.add_argument("--report_dir", type=str, default="reports", help="Directory to save reports.")



class VideoSummaryHwSize(HttpUser):
    """
    Locust user class for testing the video summary API hardware sizing.
    """

    # Class variables for shared data across all instances
    report_dir = ''
    states_url = ''

    video_file_path = ''
    sampling_params = None
    # Cache video properties to avoid repeated file reads
    metrics = []

    def on_start(self):
        # Extract parsed options once for efficiency
        parsed_opts = self.environment.parsed_options
        # self.telemetry_endpoint = "9766/v1/telemetry"
        
        self.state_endpoint = parsed_opts.state_endpoint
        self.upload_endpoint = parsed_opts.upload_endpoint
        self.summary_endpoint = parsed_opts.summary_endpoint
        self.telemetry_endpoint = parsed_opts.telemetry_endpoint
        self.filename = parsed_opts.filename
        self.payload = parsed_opts.payload
        
        # Initialize class variables only once (first user)
        if not VideoSummaryHwSize.report_dir:
            VideoSummaryHwSize.filepath = parsed_opts.filepath
            report_dir = parsed_opts.report_dir
            VideoSummaryHwSize.report_dir = os.path.join(report_dir, "video_summary")
            os.makedirs(VideoSummaryHwSize.report_dir, exist_ok=True)
            VideoSummaryHwSize.states_url = f"{self.host}:{self.state_endpoint}"
            VideoSummaryHwSize.upload_url = f"{self.host}:{self.upload_endpoint}"
                 
    @task
    def summarize_video(self):
        """
            Upload Video and Summarize video
        """
        headers = {'Content-Type': 'application/json'}
        
        # Use cached video properties
        video_properties = get_video_details(VideoSummaryHwSize.filepath)   
        
        video_id = upload_video_file(VideoSummaryHwSize.upload_url, self.filename, VideoSummaryHwSize.filepath)
        
        if video_id is None:
            print(f"Video upload failed.")
            return
        
        try:
            # Parse payload once per user if not cached
            if not hasattr(self, '_parsed_payload'):
                self._parsed_payload = safe_parse_string_to_dict(self.payload)
                VideoSummaryHwSize.sampling_params = self._parsed_payload['sampling']
            
            payload = self._parsed_payload.copy()
            payload["videoId"] = video_id

            # Start summary and track timing
            summary_start = time.time()
            response = self.client.post(f":{self.summary_endpoint}", headers=headers, json=payload)
            summary_id = response.json().get("summaryPipelineId")
            print(f"Video summary started with ID: {summary_id}")
            
            # Wait for completion
            url = f"{VideoSummaryHwSize.states_url}/{summary_id}"
            video_summary_complete, response = wait_for_video_summary_complete(url)
            if video_summary_complete:                
                summary_end = time.time()
                get_video_summary(VideoSummaryHwSize.report_dir, response, summary_id)           

            # Telemetry details
            telemetry_response = self.client.get(f":{self.telemetry_endpoint}", headers=headers)
            if telemetry_response.status_code == 200:
                telemetry_kpis, VideoSummaryHwSize.telemetry_details =  get_video_summary_telemetry_kpis(summary_start, summary_end, telemetry_response.json(), video_properties)
                VideoSummaryHwSize.metrics.append(telemetry_kpis)
            else:
                print(f"Failed to retrieve telemetry data. Status code: {telemetry_response.status_code}")

        except Exception as e:
            print(f"Video summarization failed: {e}")


@events.quitting.add_listener
def collect_metrics(environment, **kwargs):
    """
        Collect logs 
    """
    print("Collecting metrics...")

    output_file = save_video_summary_search_telemetry_kpis(VideoSummaryHwSize.report_dir, VideoSummaryHwSize.metrics, VideoSummaryHwSize.telemetry_details) 
    convert_summary_metrics_to_wsf_format(VideoSummaryHwSize.report_dir, output_file, VideoSummaryHwSize.sampling_params) 
    
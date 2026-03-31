# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
Locust load test for Live Video Caption API.

This module defines a Locust user class that simulates live video captioning
requests, collecting streaming metadata and performance metrics.
"""

import json
import os

from locust import task, events, HttpUser

from common.utils import safe_parse_string_to_dict
from common.video import (
    get_live_caption_metadata,
    stop_all_run_request,
)
from common.metrics import (
    get_live_caption_metrics,
    save_live_video_caption_telemetry_kpis,
    save_metrics_to_wsf_format,
)


@events.init_command_line_parser.add_listener
def add_custom_arguments(parser):
    """
    Adds custom command-line arguments for the Locust test.

    Args:
        parser (argparse.ArgumentParser): The argument parser to add arguments to.
    """
    parser.add_argument("--request_count", type=int, default=1, help="Number of requests per user.")
    parser.add_argument("--runs_endpoint", type=str, default="config.yaml", help="live caption runs API endpoint.")
    parser.add_argument("--metadata_endpoint", type=str, default="config.yaml", help="live caption metadata API endpoint.")
    parser.add_argument("--payload", type=str, default="config.yaml", help="live video caption payload API endpoint.")
    parser.add_argument("--caption_duration", type=int, default=120, help="Duration to collect live caption metadata in seconds.")
    parser.add_argument("--report_dir", type=str, default="reports", help="Directory to save reports.")
    parser.add_argument("--warmup_time", type=int, default=0, help="Duration in seconds for warmup requests.")



class LiveCaptionHwSize(HttpUser):
    """
    Locust user class for testing the live caption API hardware sizing.
    """

    # Cache video properties to avoid repeated file reads
    metrics = []
    run_ids = []
    run_configs = {}  # Maps run_id -> {rtspUrl, modelName, pipelineName}
    report_dir = ''

    def on_start(self):
        # Extract parsed options once for efficiency
        parsed_opts = self.environment.parsed_options
        self.warmup_time = parsed_opts.warmup_time
        self.runs_endpoint = parsed_opts.runs_endpoint
        self.metadata_endpoint = parsed_opts.metadata_endpoint
        LiveCaptionHwSize.caption_duration = parsed_opts.caption_duration 
        self.payload = safe_parse_string_to_dict(parsed_opts.payload)      
        LiveCaptionHwSize.metadata_url = f"{self.host}:{self.metadata_endpoint}"
        LiveCaptionHwSize.run_url = f"{self.host}:{self.runs_endpoint}"
        self.report_dir = parsed_opts.report_dir
        
        print("Note: Live video caption HW sizing runs for a set duration; request_count is ignored.")
        
        if not LiveCaptionHwSize.report_dir:
            report_dir = parsed_opts.report_dir
            LiveCaptionHwSize.report_dir = os.path.join(report_dir, "live_video_caption")
            os.makedirs(LiveCaptionHwSize.report_dir, exist_ok=True)
        
        payload = self.payload[0].get("run")
        if self.warmup_time > 0:
            print("For Live Video Caption App warmup is not required as the test runs for a set duration and collects metrics for the entire duration...")

                 
    @task
    def live_video_caption(self):
        """
            Live caption test task that sends a request to start the live caption pipeline and collects metadata for the specified duration.
            Supports multiple payloads - if payload is a list, iterates through each run configuration.
        """
        headers = {'Content-Type': 'application/json'}
        try:
            
            for each_payload in self.payload:                
                run_payload = each_payload.get("run")
                response = self.client.post(f":{self.runs_endpoint}", headers=headers, data=run_payload)
                if response.status_code == 200:
                    run_id = response.json().get("runId")
                    LiveCaptionHwSize.run_ids.append(run_id)

                    payload_dict = json.loads(run_payload) if isinstance(run_payload, str) else run_payload
                    LiveCaptionHwSize.run_configs[run_id] = {
                        "rtspUrl": payload_dict.get("rtspUrl"),
                        "modelName": payload_dict.get("modelName"),
                        "pipelineName": payload_dict.get("pipelineName")
                    }
                    print(f"Started live caption pipeline with runId: {run_id}")
                    print(f"Make sure Model: {payload_dict.get('modelName')} is downloaded. If not, download the model and update the payload with correct model name before running the test")
                else:
                    print(f"Failed to start pipeline: status={response.status_code}")
            
        except Exception as e:
            print(f"Live caption failed: {e}")


@events.quitting.add_listener
def collect_metrics(environment, **kwargs):
    """
        Collect logs 
    """
    print("Collecting metrics...")
    
    if LiveCaptionHwSize.run_ids:
        LiveCaptionHwSize.metrics = get_live_caption_metadata(url=LiveCaptionHwSize.metadata_url, duration_seconds=LiveCaptionHwSize.caption_duration)
        stop_all_run_request(LiveCaptionHwSize.run_url, LiveCaptionHwSize.run_ids)
        all_metrics = get_live_caption_metrics(LiveCaptionHwSize.metrics)
        output_file = save_live_video_caption_telemetry_kpis(LiveCaptionHwSize.report_dir, all_metrics, LiveCaptionHwSize.run_configs)
        save_metrics_to_wsf_format(LiveCaptionHwSize.report_dir, output_file, LiveCaptionHwSize.caption_duration)

    
    
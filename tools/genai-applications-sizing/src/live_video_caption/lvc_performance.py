# Copyright (C) 2024 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
Live Video Caption Performance Profiling.

This module provides functionality to profile live video captioning APIs
by executing Locust-based load tests with optional warmup periods.
"""

import os
from datetime import datetime
from src.live_video_caption.utilities.utils import run_live_caption_hw_sizing
from common.utils import get_enabled_live_caption_apis, get_global_details, start_perf_tool, stop_perf_tool, plot_graphs


def lvc_performance(users, request_count, ip, input_file, collect_resource_metrics, warmup_time):
    """
    Execute hardware sizing for Live Video Caption API.

    This function orchestrates the live video caption profiling workflow:
    1. Calculates total requests based on users and request count
    2. Retrieves enabled APIs and global configuration
    3. Creates timestamped report directory
    4. Starts resource metrics collection (if requested)
    5. Runs Live Caption API profiling (if enabled)
    6. Generates performance graphs from collected metrics

    Args:
        users: Number of concurrent users for the test.
        request_count: Number of requests per user.
        ip: Host IP address where the application is deployed.
        input_file: Path to the input YAML configuration file.
        collect_resource_metrics: Whether to collect CPU/GPU/memory metrics.
        warmup_time: Duration in seconds for warmup requests.
    """
    # Calculate total request count (Locust limitation)
    total_requests = users * request_count

    # Retrieve enabled APIs and global configuration
    live_caption_enabled = get_enabled_live_caption_apis(input_file)
    report_dir, perf_tool_repo, profile_path = get_global_details(input_file)

    # Create report directory
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_dir = os.path.join(report_dir, f"live_caption_{timestamp}")
    os.makedirs(report_dir, exist_ok=True)

    try:            
        
        # Start performance metrics collection after warmup
        if collect_resource_metrics:
            # Start retail perfomace tool
            log_dir = start_perf_tool(repo_url=perf_tool_repo, report_dir=report_dir)

        # Run Live Caption API hardware sizing if enabled
        if live_caption_enabled:
            run_live_caption_hw_sizing(users, total_requests, ip, profile_path, input_file, report_dir, warmup_time)

    finally:
        try:
            if collect_resource_metrics and log_dir:                    
                stop_perf_tool()
                plot_graphs(log_dir)
            print(f"Hardware sizing completed for all enabled profiles. Check the '{report_dir}' directory for results.")
        except Exception as e:
            print(f"Error occurred while parsing and plotting perf_tool logs: {e}")

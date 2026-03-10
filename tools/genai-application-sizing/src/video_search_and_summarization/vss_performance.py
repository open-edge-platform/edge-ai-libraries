# Copyright (C) 2024 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import os
from datetime import datetime
from src.video_search_and_summarization.utilities.utils import run_video_summary_hw_sizing, run_video_search_hw_sizing, run_video_summary_warmup, run_video_search_warmup
from common.utils import get_enabled_video_apis, get_global_details, start_perf_tool, stop_perf_tool, plot_graphs


def vss_performance(users, request_count, ip, input_file, collect_resource_metrics, warmup_time=0):
    """
    Executes hardware sizing for ChatQnA Modular by running Locust tests for enabled APIs.

    Args:
        users (int): Number of users for the test.
        request_count (int): Number of requests per user.
        spawn_rate (int): Rate at which users are spawned.
        ip (str): Host IP address where the application is deployed.
        input_file (str): Path to the input YAML configuration file.
        collect_resource_metrics (bool): Whether to collect resource metrics.
        warmup_time (int): Duration in seconds for warmup requests (default: 0).   
    """
    # Calculate total request count (Locust limitation)
    total_requests = users * request_count

    # Retrieve enabled APIs and global configuration
    video_summary_enabled, video_search_enabled = get_enabled_video_apis(input_file)
    report_dir, perf_tool_repo, profile_path = get_global_details(input_file)

    # Create report directory
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_dir = os.path.join(report_dir, f"video_summary_search_{timestamp}")
    os.makedirs(report_dir, exist_ok=True)

    try:
        # Run warmup requests if warmup_time is specified
        if warmup_time > 0:
            
            # Run warmup for video summary if enabled
            if video_summary_enabled:
                run_video_summary_warmup(warmup_time, ip, profile_path, input_file)
            
            # Run warmup for video search if enabled
            if video_search_enabled:
                run_video_search_warmup(warmup_time, ip, profile_path, input_file)
            
        
        # Start performance metrics collection after warmup
        if collect_resource_metrics:
            # Start retail perfomace tool
            log_dir = start_perf_tool(repo_url=perf_tool_repo, report_dir=report_dir)

        # Run Stream Log API hardware sizing if enabled
        if video_summary_enabled:
            run_video_summary_hw_sizing(users, total_requests, ip, profile_path, input_file, report_dir)

        # Run Document API hardware sizing if enabled
        if video_search_enabled:
            run_video_search_hw_sizing(users, total_requests, ip, profile_path, input_file, report_dir)

        #print(f"Hardware sizing completed for all enabled profiles. Check the '{report_dir}' directory for results.")

    finally:
        try:
            if collect_resource_metrics and log_dir:                    
                stop_perf_tool()
                plot_graphs(log_dir)
            print(f"Hardware sizing completed for all enabled profiles. Check the '{report_dir}' directory for results.")
        except Exception as e:
            print(f"Error occurred while parsing and plotting perf_tool logs: {e}")

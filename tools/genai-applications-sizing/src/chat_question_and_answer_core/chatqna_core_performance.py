# Copyright (C) 2024 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
ChatQnA Core Application Performance Profiling.

This module provides functionality to profile the ChatQnA core application
by executing Locust-based load tests against enabled APIs (Stream Log and Document APIs).
"""

import os
from datetime import datetime
from common.utils import (
    get_enabled_apis,
    get_global_details,
    plot_graphs,
    start_perf_tool,
    stop_perf_tool
)
from src.chat_question_and_answer_core.utilities.utils import run_stream_log_hw_sizing, run_document_hw_sizing


def chatqna_core_performance(users, request_count, spawn_rate, ip, input_file, collect_resource_metrics):
    """
    Execute hardware sizing for ChatQnA Core by running Locust tests for enabled APIs.

    This function orchestrates the performance profiling workflow:
    1. Calculates total requests based on users and request count
    2. Retrieves enabled APIs and global configuration
    3. Creates timestamped report directory
    4. Optionally starts resource metrics collection
    5. Runs Stream Log API profiling (if enabled)
    6. Runs Document API profiling (if enabled)
    7. Generates performance graphs from collected metrics

    Args:
        users: Number of concurrent users for the test.
        request_count: Number of requests per user.
        spawn_rate: Rate at which users are spawned per second.
        ip: Host IP address where the application is deployed.
        input_file: Path to the input YAML configuration file.
        collect_resource_metrics: Whether to collect CPU/GPU/memory metrics.
    """
    # Calculate total request count (Locust limitation execution stops after specified number of iterations)
    total_requests = users * request_count

    # Retrieve enabled APIs and global configuration
    stream_log_api_enabled, document_api_enabled = get_enabled_apis(input_file)
    report_dir, perf_tool_repo, profile_path = get_global_details(input_file)


    # Create report directory
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_dir = os.path.join(report_dir, f"chatqna_core_{timestamp}")
    os.makedirs(report_dir, exist_ok=True)    
    
    try:
        # Start performance metrics collection if requested
        if collect_resource_metrics:
            # Start retail perfomace tool
            log_dir = start_perf_tool(repo_url=perf_tool_repo, report_dir=report_dir)

        # Run Chat API hardware sizing if enabled
        if stream_log_api_enabled:
            run_stream_log_hw_sizing(users, total_requests, spawn_rate, ip, profile_path, input_file, report_dir)

        # Run Document API hardware sizing if enabled
        if document_api_enabled:
            run_document_hw_sizing(users, total_requests, spawn_rate, ip, profile_path, input_file, report_dir)

    finally:
        try:
            if collect_resource_metrics and log_dir:                    
                stop_perf_tool()
                plot_graphs(log_dir)
            print(f"Hardware sizing completed for all enabled profiles. Check the '{report_dir}' directory for results.")
        except Exception as e:
            print(f"Error occurred while parsing and plotting perf_tool logs: {e}")
    

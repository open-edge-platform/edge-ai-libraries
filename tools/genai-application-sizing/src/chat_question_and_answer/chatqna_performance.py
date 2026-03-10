# Copyright (C) 2024 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import os
from datetime import datetime
from common.utils import (
    get_enabled_apis,
    get_global_details,
    plot_graphs,
    start_perf_tool,
    stop_perf_tool
)
from src.chat_question_and_answer.utilities.utils import run_document_hw_sizing, run_chat_hw_sizing


def chatqna_modular_performance(users, request_count, spawn_rate, ip, input_file, collect_resource_metrics):
    """
    Executes hardware sizing for ChatQnA Modular by running Locust tests for enabled APIs.

    Args:
        users (int): Number of users for the test.
        request_count (int): Number of requests per user.
        spawn_rate (int): Rate at which users are spawned.
        ip (str): Host IP address where the application is deployed.
        input_file (str): Path to the input YAML configuration file.
        collect_resource_metrics (bool): Whether to collect resource metrics.        
    """

    # Validate inputs
    if not os.path.exists(input_file):
        raise FileNotFoundError(f"Input file not found: {input_file}")
    if users <= 0 or request_count <= 0:
        raise ValueError("Users and request count must be positive integers")
        
    # Calculate total request count (Locust limitation)
    total_requests = users * request_count

    # Retrieve enabled APIs and global configuration
    stream_log_api_enabled, document_api_enabled = get_enabled_apis(input_file)
    report_dir, perf_tool_repo, profile_path = get_global_details(input_file)

    # Create report directory with timestamp
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_dir = os.path.join(report_dir, f"chatqna_modular_{timestamp}")
    os.makedirs(report_dir, exist_ok=True)
      
    try:
        # Start performance metrics collection if requested
        if collect_resource_metrics:
            # Start retail perfomace tool
            log_dir = start_perf_tool(repo_url=perf_tool_repo, report_dir=report_dir)

        # Run Chat API hardware sizing if enabled
        if stream_log_api_enabled:
            run_chat_hw_sizing(users, total_requests, spawn_rate, ip, profile_path, input_file, report_dir)

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
        




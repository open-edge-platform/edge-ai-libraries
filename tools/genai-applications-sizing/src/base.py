# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
Base performance profiling framework.

This module provides a base class for building application-specific
performance profiling implementations, reducing code duplication across
different application profilers.
"""

import os
from abc import ABC, abstractmethod
from datetime import datetime

from common.config import read_yaml_config, get_global_details
from common.perf_tools import start_perf_tool, stop_perf_tool, plot_graphs


class BasePerformanceProfiler(ABC):
    """
    Abstract base class for performance profiling applications.
    
    This class provides a common framework for:
    - Setting up report directories
    - Managing performance metrics collection
    - Handling warmup phases
    - Orchestrating the profiling workflow
    
    Subclasses must implement:
    - app_name: Property returning the application name for directory naming
    - get_enabled_apis: Method to determine which APIs are enabled
    - run_warmup: Method to execute warmup requests (if applicable)
    - run_profiling: Method to execute the actual profiling tests
    """
    
    def __init__(self, users, request_count, ip, input_file, 
                 collect_resource_metrics, warmup_time=0, spawn_rate=1):
        """
        Initialize the performance profiler.
        
        Args:
            users: Number of concurrent users for the test.
            request_count: Number of requests per user.
            ip: Host IP address where the application is deployed.
            input_file: Path to the input YAML configuration file.
            collect_resource_metrics: Whether to collect CPU/GPU/memory metrics.
            warmup_time: Duration in seconds for warmup requests (default: 0).
            spawn_rate: Rate at which users are spawned per second (default: 1).
        """
        self.users = users
        self.request_count = request_count
        self.total_requests = users * request_count
        self.ip = ip
        self.input_file = input_file
        self.collect_resource_metrics = collect_resource_metrics
        self.warmup_time = warmup_time
        self.spawn_rate = spawn_rate
        
        # Load configuration once and reuse throughout the profiler lifecycle
        self.config = read_yaml_config(input_file)
        
        # Get global configuration
        self.report_dir, self.perf_tool_repo, self.profile_path = get_global_details(self.config)
        
        # Will be set during execution
        self.log_dir = None
    
    @property
    @abstractmethod
    def app_name(self):
        """Return the application name used for report directory naming."""
        pass
    
    @abstractmethod
    def get_enabled_apis(self):
        """
        Determine which APIs are enabled based on configuration.
        
        Returns:
            Configuration-dependent return value (typically tuple of booleans).
        """
        pass
    
    def run_warmup(self, profile_path, input_file):
        """
        Execute warmup requests to prime the system.
        
        Override this method to implement application-specific warmup logic.
        Default implementation does nothing.
        
        Args:
            profile_path: Path to the profile YAML file.
            input_file: Path to the input configuration file.
        """
        pass
    
    @abstractmethod
    def run_profiling(self, report_dir):
        """
        Execute the actual profiling tests.
        
        Args:
            report_dir: Directory to save the test reports.
        """
        pass
    
    def setup_report_directory(self):
        """
        Create timestamped report directory.
        
        Returns:
            str: Path to the created report directory.
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        report_dir = os.path.join(self.report_dir, f"{self.app_name}_{timestamp}")
        os.makedirs(report_dir, exist_ok=True)
        return report_dir
    
    def start_metrics_collection(self, report_dir):
        """
        Start performance metrics collection if enabled.
        
        Args:
            report_dir: Directory for performance logs.
            
        Returns:
            tuple: Paths to log directory and compose file if started, (None, None) otherwise.
        """
        if self.collect_resource_metrics:
            log_dir, compose_file = start_perf_tool(repo_url=self.perf_tool_repo, report_dir=report_dir)
            return log_dir, compose_file
        return None, None   
    
    def stop_metrics_collection(self, compose_file):
        """Stop performance metrics collection and generate graphs."""
        if self.collect_resource_metrics and self.log_dir:
            try:
                stop_perf_tool(compose_file, self.log_dir)
                plot_graphs(self.log_dir)
            except Exception as e:
                print(f"Error occurred while parsing and plotting perf_tool logs: {e}")
    
    def execute(self):
        """
        Execute the complete profiling workflow.
        
        This method orchestrates the full profiling process:
        1. Creates timestamped report directory
        2. Runs warmup requests (if warmup_time > 0)
        3. Starts metrics collection (if enabled)
        4. Runs the profiling tests
        5. Stops metrics collection and generates graphs
        
        Returns:
            str: Path to the report directory containing results.
        """
        # Setup report directory
        report_dir = self.setup_report_directory()
        
        try:
            # Run warmup if specified
            if self.warmup_time > 0:
                self.run_warmup(self.profile_path, self.input_file)
            
            # Start metrics collection
            self.log_dir, compose_file = self.start_metrics_collection(report_dir)
            
            # Run the actual profiling
            self.run_profiling(report_dir)
            
        finally:
            # Cleanup and report
            try:
                self.stop_metrics_collection(compose_file)
                print(f"Hardware sizing completed for all enabled profiles. "
                      f"Check the '{report_dir}' directory for results.")
            except Exception as e:
                print(f"Error during cleanup: {e}")
        
        return report_dir

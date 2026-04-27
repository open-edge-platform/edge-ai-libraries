# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
Video Search and Summarization Performance Profiling.

This module provides functionality to profile video search and summarization APIs
by executing Locust-based load tests with optional warmup periods.
"""

from src.video_search_and_summarization.utilities.config import get_enabled_vss_apis
from src.base import BasePerformanceProfiler
from src.video_search_and_summarization.utilities.utils import (
    run_video_summary_hw_sizing,
    run_video_search_hw_sizing,
    run_video_summary_warmup,
    run_video_search_warmup
)


class VSSProfiler(BasePerformanceProfiler):
    """
    Performance profiler for Video Search and Summarization application.
    
    This profiler executes hardware sizing tests against the Video Summary
    and Video Search APIs with optional warmup support.
    """
    
    @property
    def app_name(self):
        return "video_summary_search"
    
    def get_enabled_apis(self):
        return get_enabled_vss_apis(self.config)
    
    def run_warmup(self, profile_path, input_file):
        """Execute warmup requests for enabled video APIs."""
        video_summary_enabled, video_search_enabled = self.get_enabled_apis()
        
        if video_summary_enabled:
            run_video_summary_warmup(self.warmup_time, self.ip, profile_path, self.config)
        
        if video_search_enabled:
            run_video_search_warmup(self.warmup_time, self.ip, profile_path, self.config)
    
    def run_profiling(self, report_dir):
        video_summary_enabled, video_search_enabled = self.get_enabled_apis()
        
        if video_summary_enabled:
            run_video_summary_hw_sizing(
                self.users, self.total_requests, self.ip,
                self.profile_path, report_dir, self.config
            )
        
        if video_search_enabled:
            run_video_search_hw_sizing(
                self.users, self.total_requests, self.ip,
                self.profile_path, report_dir, self.config
            )


def vss_performance(users, request_count, ip, input_file, collect_resource_metrics, warmup_time=0):
    """
    Execute hardware sizing for Video Summary and Search APIs.

    This function is the entry point that uses the VSSProfiler class
    to orchestrate the complete profiling workflow.

    Args:
        users: Number of concurrent users for the test.
        request_count: Number of requests per user.
        ip: Host IP address where the application is deployed.
        input_file: Path to the input YAML configuration file.
        collect_resource_metrics: Whether to collect CPU/GPU/memory metrics.
        warmup_time: Duration in seconds for warmup requests (default: 0).
    """
    profiler = VSSProfiler(
        users=users,
        request_count=request_count,
        ip=ip,
        input_file=input_file,
        collect_resource_metrics=collect_resource_metrics,
        warmup_time=warmup_time
    )
    profiler.execute()

# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
Live Video Caption Performance Profiling.

This module provides functionality to profile live video captioning APIs
by executing Locust-based load tests with optional warmup periods.
"""

from common.config import get_enabled_live_caption_apis
from src.base import BasePerformanceProfiler
from src.live_video_caption.utilities.utils import run_live_caption_hw_sizing


class LVCProfiler(BasePerformanceProfiler):
    """
    Performance profiler for Live Video Caption application.
    
    This profiler executes hardware sizing tests against the Live Caption API.
    Note: Warmup is handled internally by run_live_caption_hw_sizing.
    """
    
    @property
    def app_name(self):
        return "live_caption"
    
    def get_enabled_apis(self):
        return get_enabled_live_caption_apis(self.config)
    
    def run_profiling(self, report_dir):
        live_caption_enabled = self.get_enabled_apis()
        
        if live_caption_enabled:
            # Note: warmup_time is passed to the hw_sizing function
            # as it handles warmup internally
            run_live_caption_hw_sizing(
                self.users, self.total_requests, self.ip,
                self.profile_path, report_dir,
                self.warmup_time, self.config
            )


def lvc_performance(users, request_count, ip, input_file, collect_resource_metrics, warmup_time):
    """
    Execute hardware sizing for Live Video Caption API.

    This function is the entry point that uses the LVCProfiler class
    to orchestrate the complete profiling workflow.

    Args:
        users: Number of concurrent users for the test.
        request_count: Number of requests per user.
        ip: Host IP address where the application is deployed.
        input_file: Path to the input YAML configuration file.
        collect_resource_metrics: Whether to collect CPU/GPU/memory metrics.
        warmup_time: Duration in seconds for warmup requests.
    """
    profiler = LVCProfiler(
        users=users,
        request_count=request_count,
        ip=ip,
        input_file=input_file,
        collect_resource_metrics=collect_resource_metrics,
        warmup_time=warmup_time
    )
    profiler.execute()

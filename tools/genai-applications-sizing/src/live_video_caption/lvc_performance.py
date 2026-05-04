# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
"""
Live Video Caption Performance Profiling.

Entry point for profiling the Live Video Caption application via Locust.
Warmup is handled internally by the Locust test file.
"""

from src.base import BasePerformanceProfiler
from src.live_video_caption.utilities.config import is_live_caption_enabled
from src.live_video_caption.utilities.utils import run_live_caption_hw_sizing


class LVCProfiler(BasePerformanceProfiler):
    """
    Performance profiler for the Live Video Caption application.

    Delegates hardware-sizing execution to `run_live_caption_hw_sizing`,
    which launches a headless single-user Locust test.
    """

    @property
    def app_name(self) -> str:
        return "live_caption"

    def get_enabled_apis(self) -> bool:
        """Return True if the live_caption API is enabled in config."""
        return is_live_caption_enabled(self.config)

    def run_profiling(self, report_dir: str) -> None:
        """Execute the hardware-sizing test if the API is enabled."""
        if self.get_enabled_apis():
            run_live_caption_hw_sizing(
                self.users,
                self.total_requests,
                self.ip,
                self.profile_path,
                report_dir,
                self.warmup_time,
                self.config,
            )


def lvc_performance(
    users: int,
    request_count: int,
    ip: str,
    input_file: str,
    collect_resource_metrics: bool,
    warmup_time: int,
) -> None:
    """
    Entry point for Live Video Caption hardware sizing.

    Constructs an LVCProfiler and runs the full profiling workflow.

    Args:
        users: Number of concurrent users (use 1 for single-user sizing).
        request_count: Number of task iterations per user.
        ip: Host IP address where the application is deployed.
        input_file: Path to the input YAML configuration file.
        collect_resource_metrics: Whether to collect CPU/GPU/memory metrics.
        warmup_time: Duration in seconds for the warmup phase.
    """
    profiler = LVCProfiler(
        users=users,
        request_count=request_count,
        ip=ip,
        input_file=input_file,
        collect_resource_metrics=collect_resource_metrics,
        warmup_time=warmup_time,
    )
    profiler.execute()

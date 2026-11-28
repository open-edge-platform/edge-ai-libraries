# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
ChatQnA Core Application Performance Profiling.

This module provides functionality to profile the ChatQnA core application
by executing Locust-based load tests against enabled APIs (Stream Log and Document APIs).
"""

from src.chat_question_and_answer_core.utilities.config import get_enabled_chatqna_apis
from src.base import BasePerformanceProfiler
from src.chat_question_and_answer_core.utilities.utils import run_stream_log_hw_sizing, run_document_hw_sizing


class ChatQnACoreProfiler(BasePerformanceProfiler):
    """
    Performance profiler for ChatQnA Core application.
    
    This profiler executes hardware sizing tests against the Stream Log
    and Document APIs of the ChatQnA Core application.
    """
    
    @property
    def app_name(self):
        return "chatqna_core"
    
    def get_enabled_apis(self):
        return get_enabled_chatqna_apis(self.config)
    
    def run_profiling(self, report_dir):
        stream_log_api_enabled, document_api_enabled = self.get_enabled_apis()
        
        if stream_log_api_enabled:
            run_stream_log_hw_sizing(
                self.users, self.total_requests, self.spawn_rate,
                self.ip, self.profile_path, report_dir, self.config
            )
        
        if document_api_enabled:
            run_document_hw_sizing(
                self.users, self.total_requests, self.spawn_rate,
                self.ip, self.profile_path, report_dir, self.config
            )


def chatqna_core_performance(users, request_count, spawn_rate, ip, input_file, collect_resource_metrics):
    """
    Execute hardware sizing for ChatQnA Core by running Locust tests for enabled APIs.

    This function is the entry point that uses the ChatQnACoreProfiler class
    to orchestrate the complete profiling workflow.

    Args:
        users: Number of concurrent users for the test.
        request_count: Number of requests per user.
        spawn_rate: Rate at which users are spawned per second.
        ip: Host IP address where the application is deployed.
        input_file: Path to the input YAML configuration file.
        collect_resource_metrics: Whether to collect CPU/GPU/memory metrics.
    """
    profiler = ChatQnACoreProfiler(
        users=users,
        request_count=request_count,
        ip=ip,
        input_file=input_file,
        collect_resource_metrics=collect_resource_metrics,
        spawn_rate=spawn_rate
    )
    profiler.execute()

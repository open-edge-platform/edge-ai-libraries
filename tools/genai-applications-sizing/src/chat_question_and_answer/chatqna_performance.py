# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
ChatQnA Modular Application Performance Profiling.

This module provides functionality to profile the ChatQnA modular application
by executing Locust-based load tests against enabled APIs (Chat and Document APIs).
"""

from src.chat_question_and_answer.utilities.config import get_enabled_chatqna_apis
from src.base import BasePerformanceProfiler
from src.chat_question_and_answer.utilities.utils import run_document_hw_sizing, run_chat_hw_sizing, run_chat_warmup


class ChatQnAModularProfiler(BasePerformanceProfiler):
    """
    Performance profiler for ChatQnA Modular application.
    
    This profiler executes hardware sizing tests against the Chat and Document
    APIs of the ChatQnA Modular application.
    """
    
    @property
    def app_name(self):
        return "chatqna_modular"
    
    def get_enabled_apis(self):
        return get_enabled_chatqna_apis(self.config)

    def run_warmup(self, profile_path, input_file):
        """Execute warmup requests for enabled APIs."""
        stream_log_api_enabled, _ = self.get_enabled_apis()
        
        if stream_log_api_enabled:
            run_chat_warmup(self.warmup_time, self.ip, profile_path, self.config)

    
    def run_profiling(self, report_dir):
        stream_log_api_enabled, document_api_enabled = self.get_enabled_apis()
        
        if stream_log_api_enabled:
            run_chat_hw_sizing(
                self.users, self.total_requests, self.spawn_rate,
                self.ip, self.profile_path, report_dir, self.config
            )
        
        if document_api_enabled:
            run_document_hw_sizing(
                self.users, self.total_requests, self.spawn_rate,
                self.ip, self.profile_path, report_dir, self.config
            )


def chatqna_modular_performance(users, request_count, spawn_rate, ip, input_file, collect_resource_metrics, warmup_time=0):
    """
    Execute hardware sizing for ChatQnA Modular by running Locust tests for enabled APIs.

    This function is the entry point that uses the ChatQnAModularProfiler class
    to orchestrate the complete profiling workflow.

    Args:
        users: Number of concurrent users for the test.
        request_count: Number of requests per user.
        spawn_rate: Rate at which users are spawned per second.
        ip: Host IP address where the application is deployed.
        input_file: Path to the input YAML configuration file.
        collect_resource_metrics: Whether to collect CPU/GPU/memory metrics.
        warmup_time: Duration of the warmup phase in seconds.
    """
    
    profiler = ChatQnAModularProfiler(
        users=users,
        request_count=request_count,
        ip=ip,
        input_file=input_file,
        collect_resource_metrics=collect_resource_metrics,
        spawn_rate=spawn_rate,
        warmup_time=warmup_time
    )
    profiler.execute()
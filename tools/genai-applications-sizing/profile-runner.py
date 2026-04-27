# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

# Gevent monkey-patching must be done BEFORE any other imports
# to avoid RecursionError with ssl module
from gevent import monkey
monkey.patch_all()

import argparse
import os
import re
import sys
from src.chat_question_and_answer import chatqna_performance
from src.chat_question_and_answer_core import chatqna_core_performance
from src.video_search_and_summarization import vss_performance
from src.live_video_caption import lvc_performance


def validate_integer(value, name, min_value=0):
    """Validate that a value is an integer >= min_value."""
    if value < min_value:
        constraint = "positive" if min_value == 1 else "non-negative" if min_value == 0 else f">= {min_value}"
        raise ValueError(f"{name} must be a {constraint} integer (got {value})")
    return value


def validate_file_exists(filepath):
    """Validate that the input file exists."""
    if not os.path.isfile(filepath):
        raise FileNotFoundError(f"Input configuration file not found: {filepath}")
    return filepath


def validate_ip_address(ip):
    """Validate IP address format (IPv4)."""
    if not ip:
        raise ValueError("host_ip is required and cannot be empty")
    
    # Basic IPv4 pattern validation
    ipv4_pattern = r'^(\d{1,3}\.){3}\d{1,3}$'
    if not re.match(ipv4_pattern, ip):
        raise ValueError(f"Invalid IP address format: {ip}. Expected IPv4 format (e.g., 192.168.1.1)")
    
    # Validate each octet is within valid range
    octets = ip.split('.')
    for octet in octets:
        if not 0 <= int(octet) <= 255:
            raise ValueError(f"Invalid IP address: {ip}. Each octet must be between 0 and 255")
    
    return ip


def validate_args(args):
    """Validate all command line arguments."""
    errors = []
    
    try:
        validate_integer(args.users, "users", min_value=1)
    except ValueError as e:
        errors.append(str(e))
    
    try:
        validate_integer(args.request_count, "request_count", min_value=1)
    except ValueError as e:
        errors.append(str(e))
    
    try:
        validate_integer(args.spawn_rate, "spawn_rate", min_value=1)
    except ValueError as e:
        errors.append(str(e))
    
    try:
        validate_integer(args.warmup_time, "warmup_time", min_value=0)
    except ValueError as e:
        errors.append(str(e))
    
    
    try:
        validate_ip_address(args.host_ip)
    except ValueError as e:
        errors.append(str(e))
    
    if errors:
        print("Input validation failed:")
        for error in errors:
            print(f"  - {error}")
        sys.exit(1)


def main():
    """
    Main function to parse arguments and run the appropriate application performance profiling.
    
    This function serves as the entry point for the GenAI application sizing tool.
    It parses command-line arguments, validates inputs, and dispatches to the
    appropriate performance profiling module based on the selected application.
    
    Supported applications:
        - chatqna: ChatQnA modular application profiling
        - chatqna_core: ChatQnA core application profiling
        - video_summary_search: Video summary and search profiling
        - live_caption: Live video captioning profiling
    
    Raises:
        SystemExit: If input validation fails or required arguments are missing.
    """

    # Create the parser
    parser = argparse.ArgumentParser(
        description="Hardware sizing tool for Gen-AI applications (ChatQnA and Video Summary/Search)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
    Examples:
    python profile-runner.py --app=chatqna --input=profiles/chatqna-config.yaml --users=1 --request_count=10 --host_ip=<IP_ADDRESS_OF_APP_DEPLOYED> --collect_resource_metrics=yes
    python profile-runner.py --app=video_summary_search --input=profiles/video-search-config.yaml --host_ip=<IP_ADDRESS_OF_APP_DEPLOYED> --collect_resource_metrics=yes
            """
    )
    
    # Add arguments
    parser.add_argument("--users", default=1, type=int, 
                        help="Under implementation, this is set to 1 as the tool focuses on single user performance profiling")
    parser.add_argument("--request_count", default=1, type=int, 
                        help="Total number of requests to execute (default: 1) and not applicable for live_caption")
    parser.add_argument("--spawn_rate", default=1, type=int, 
                        help="Rate at which users are spawned per second (default: 1)")
    parser.add_argument("--input", default="config.yaml", type=str, 
                        help="Path to configuration YAML file (default: config.yaml)")
    parser.add_argument("--app", type=str, required=True,
                        choices=["chatqna", "chatqna_core", "video_summary_search", "live_caption"], 
                        help="Application to profile: chatqna (modular), chatqna_core, video_summary_search, or live_caption")
    parser.add_argument("--host_ip", type=str, required=True,
                        help="IP address of the machine where the application is deployed")
    parser.add_argument("--collect_resource_metrics", default="no", type=str, 
                        choices=["yes", "no"],
                        help="Enable collection of resource metrics (CPU, GPU, memory, etc.) - yes or no (default: no)")
    parser.add_argument("--warmup_time", default=0, type=int, 
                        help="Duration in seconds for warmup requests before performance testing (default: 0)")
    

    
    # Read arguments
    args = parser.parse_args()
    
    # Validate arguments
    validate_args(args)
    
    collect_resource_metrics = True if args.collect_resource_metrics.lower() == "yes" else False

    # Run the appropriate application profiling
    if args.app == "chatqna":        
        chatqna_performance.chatqna_modular_performance(users=1, request_count=args.request_count, spawn_rate=args.spawn_rate, ip=args.host_ip, input_file=args.input, collect_resource_metrics=collect_resource_metrics, warmup_time=args.warmup_time)
    elif args.app == "chatqna_core":
        chatqna_core_performance.chatqna_core_performance(users=1, request_count=args.request_count, spawn_rate=args.spawn_rate, ip=args.host_ip, input_file=args.input, collect_resource_metrics=collect_resource_metrics)
    elif args.app == "video_summary_search":
        vss_performance.vss_performance(users=1, request_count=args.request_count, ip=args.host_ip, input_file=args.input, collect_resource_metrics=collect_resource_metrics, warmup_time=args.warmup_time)
    elif args.app == "live_caption":
        lvc_performance.lvc_performance(users=1, request_count=1, ip=args.host_ip, input_file=args.input, collect_resource_metrics=collect_resource_metrics, warmup_time=args.warmup_time)
    # Note: No else branch needed - argparse choices validation ensures valid app names


if __name__ == "__main__":
    main()

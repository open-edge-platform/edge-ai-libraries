# Copyright (C) 2024 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import argparse
from src.chat_question_and_answer import chatqna_performance
from src.chat_question_and_answer_core import chatqna_core_performance
from src.video_search_and_summarization import vss_performance


def main():

    """
    Main function to parse arguments and run the appropriate application performance profiling.
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
                        help="Total number of requests to execute (default: 1)")
    parser.add_argument("--spawn_rate", default=1, type=int, 
                        help="Rate at which users are spawned per second (default: 1)")
    parser.add_argument("--input", default="config.yaml", type=str, 
                        help="Path to configuration YAML file (default: config.yaml)")
    parser.add_argument("--app", default="chatqna", type=str, 
                        choices=["chatqna", "chatqna_core", "video_summary_search"], 
                        help="Application to profile: chatqna (modular), chatqna_core, or video_summary_search (default: chatqna)")
    parser.add_argument("--host_ip", default="", type=str, 
                        help="IP address of the machine where the application is deployed")
    parser.add_argument("--collect_resource_metrics", default="no", type=str, 
                        choices=["yes", "no"],
                        help="Enable collection of resource metrics (CPU, GPU, memory, etc.) - yes or no (default: no)")
    parser.add_argument("--warmup_time", default=0, type=int, 
                        help="Duration in seconds for warmup requests before performance testing (default: 0)")
    

    
    # Read arguments
    args = parser.parse_args()    
    collect_resource_metrics = True if args.collect_resource_metrics.lower() == "yes" else False

    # Run the appropriate application profiling
    if args.app == "chatqna":        
        chatqna_performance.chatqna_modular_performance(users=1, request_count=args.request_count, spawn_rate=args.spawn_rate, ip=args.host_ip, input_file=args.input, collect_resource_metrics=collect_resource_metrics)
    elif args.app == "chatqna_core":
        chatqna_core_performance.chatqna_core_performance(users=1, request_count=args.request_count, spawn_rate=args.spawn_rate, ip=args.host_ip, input_file=args.input, collect_resource_metrics=collect_resource_metrics)
    elif args.app == "video_summary_search":
        vss_performance.vss_performance(users=1, request_count=args.request_count, ip=args.host_ip, input_file=args.input, collect_resource_metrics=collect_resource_metrics, warmup_time=args.warmup_time)
    else:
        print("Invalid application name. Please choose from chatqna, chatqna_core, video_summary.")

    
if __name__ == "__main__":
    main()

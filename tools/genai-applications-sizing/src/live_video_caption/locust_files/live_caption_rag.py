# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
Locust load test for Live Video Caption RAG API.

This module defines a Locust user class that simulates live video captioning
requests, collecting streaming metadata and performance metrics.
"""

import json
import os
import time
import gevent

from locust import task, events, HttpUser
import requests

from common.utils import safe_parse_string_to_dict
from common.video import (
    get_live_caption_metadata,
    stop_all_run_request,
)
from common.metrics import (
    get_live_caption_metrics,
    save_live_video_caption_telemetry_kpis,
    save_lvc_rag_metrics_to_wsf_format,
    write_metrics
)
from common.utils import get_response
from src.chat_question_and_answer_core.utilities.utils import get_token_length


@events.init_command_line_parser.add_listener
def add_custom_arguments(parser):
    """
    Adds custom command-line arguments for the Locust test.

    Args:
        parser (argparse.ArgumentParser): The argument parser to add arguments to.
    """
    parser.add_argument("--request_count", type=int, default=1, help="Number of requests per user.")
    parser.add_argument("--runs_endpoint", type=str, default="config.yaml", help="live caption runs API endpoint.")
    parser.add_argument("--metadata_endpoint", type=str, default="config.yaml", help="live caption metadata API endpoint.")
    parser.add_argument("--chat_endpoint", type=str, default="config.yaml", help="live caption chat API endpoint.")
    parser.add_argument("--payload", type=str, default="config.yaml", help="live video caption payload API endpoint.")
    parser.add_argument("--chat_payload", type=str, default="config.yaml", help="live video caption chat payload API endpoint.")
    parser.add_argument("--caption_duration", type=int, default=120, help="Duration to collect live caption metadata in seconds.")
    parser.add_argument("--report_dir", type=str, default="reports", help="Directory to save reports.")
    parser.add_argument("--warmup_time", type=int, default=0, help="Duration in seconds for warmup requests.")



class LiveCaptionRagHwSize(HttpUser):
    """
    Locust user class for testing the live caption API hardware sizing.
    """

    # Cache video properties to avoid repeated file reads
    metrics = []
    run_ids = []
    run_configs = {}  # Maps run_id -> {rtspUrl, modelName, pipelineName}
    report_dir = ''

    def on_start(self):
        # Extract parsed options once for efficiency
        parsed_opts = self.environment.parsed_options
        self.warmup_time = parsed_opts.warmup_time
        self.runs_endpoint = parsed_opts.runs_endpoint
        self.metadata_endpoint = parsed_opts.metadata_endpoint
        self.chat_endpoint = parsed_opts.chat_endpoint
        LiveCaptionRagHwSize.caption_duration = parsed_opts.caption_duration 
        self.payload = safe_parse_string_to_dict(parsed_opts.payload)      
        self.chat_payloads = safe_parse_string_to_dict(parsed_opts.chat_payload)
        LiveCaptionRagHwSize.metadata_url = f"{self.host}:{self.metadata_endpoint}"
        LiveCaptionRagHwSize.run_url = f"{self.host}:{self.runs_endpoint}"
        LiveCaptionRagHwSize.chat_url = f"{self.host}:{self.chat_endpoint}"
        self.report_dir = parsed_opts.report_dir
        LiveCaptionRagHwSize.all_metrics = []
        
        if not LiveCaptionRagHwSize.report_dir:
            report_dir = parsed_opts.report_dir
            LiveCaptionRagHwSize.report_dir = os.path.join(report_dir, "live_video_caption_rag")
            os.makedirs(LiveCaptionRagHwSize.report_dir, exist_ok=True)
        
        if self.warmup_time > 0:
            print("For LVC RAG application, only conversation api will be sent.")

        headers = {'Content-Type': 'application/json'}
        run_payload = self.payload[0].get("run") 
        response = requests.post(LiveCaptionRagHwSize.run_url, headers=headers, data=run_payload)
        if response.status_code == 200:
            run_id = response.json().get("runId")
            LiveCaptionRagHwSize.run_ids.append(run_id)

            payload_dict = json.loads(run_payload)
            LiveCaptionRagHwSize.run_configs[run_id] = {
                "rtspUrl": payload_dict.get("rtspUrl"),
                "modelName": payload_dict.get("modelName"),
                "pipelineName": payload_dict.get("pipelineName"),
                "frameRate": payload_dict.get("frameRate"),
                "chunkSize": payload_dict.get("chunkSize")
            }
            print(f"Started live caption pipeline with runId: {run_id}")
        else:
         print(f"Failed to start pipeline: status={response.status_code}")

    
    def collect_live_caption_metrics(self):
        """
        Starts the live caption pipeline by sending a request to the runs endpoint.
        """        
        if LiveCaptionRagHwSize.run_ids:
            LiveCaptionRagHwSize.metrics = get_live_caption_metadata(url=LiveCaptionRagHwSize.metadata_url, duration_seconds=LiveCaptionRagHwSize.caption_duration)
                       

    def send_chat_requests(self):
        """
            Send chat requests while live captioning and collect metrics.
        """
        time.sleep(10) # Wait for the 10 seconds for the live caption pipeline to start and stabilize before sending chat requests.
        headers = {'Content-Type': 'application/json'}
        # Initialize metrics
        ttft, itl, metrics, chunks = 0.0, [], {}, []
        start_time = time.perf_counter()
        most_recent_timestamp = start_time
        try:
            print("Sending chat requests to the live caption pipeline...")
            for chat_payload in self.chat_payloads:
                response = self.client.post(f":{self.chat_endpoint}", headers=headers, data=chat_payload.get("chat"), stream=True)
                if response.status_code == 200:
                    for chunk in response.iter_lines():
                        if b'data:' in chunk and chunk != b"":
                            if ttft == 0.0:
                                ttft = time.perf_counter() - start_time
                                itl.append(ttft)
                            else:
                                itl.append(time.perf_counter() - most_recent_timestamp)
                            most_recent_timestamp = time.perf_counter()
                            chunks.append(chunk)
                else:
                    metrics["ERROR_CODE"] = response.status_code

                # Process response chunks
                answer = ""
                for chunk in chunks:
                    without_data = chunk.decode("utf-8")[6:]
                    if without_data.startswith("["):
                        break
                    answer += without_data
                    
                # Save response and calculate metrics
                get_response(response={}, report_dir=LiveCaptionRagHwSize.report_dir, answer=answer)

                input_prompt = safe_parse_string_to_dict(chat_payload.get("chat"))
                input_tokens = get_token_length(input_prompt.get("input", ""))
                metrics["INPUT_TOKENS"] = input_tokens

                num_output_tokens = get_token_length(answer)
                metrics["LATENCY (ms)"] = sum(itl) * 1000
                metrics["TTFT (ms)"] = ttft * 1000
                metrics["ITL (ms)"] = ((sum(itl) - ttft) / (num_output_tokens - 1)) * 1000 if num_output_tokens > 1 else 0
                metrics["TPS"] = num_output_tokens / sum(itl) if sum(itl) > 0 else 0                
                metrics["OUTPUT_TOKENS"] = num_output_tokens
                LiveCaptionRagHwSize.all_metrics.append(metrics)

        except Exception as e:
            print(f"Live caption failed: {e}")
    
    @task
    def live_caption_rag_test(self):
        """
            Main task to start live caption pipeline and send chat requests.
        """
        start_live_catpion = gevent.spawn(self.collect_live_caption_metrics)
        chat_requests = gevent.spawn(self.send_chat_requests)
        gevent.joinall([start_live_catpion, chat_requests])


@events.quitting.add_listener
def collect_metrics(environment, **kwargs):
    """
        Collect logs 
    """
    print("Collecting metrics...")   
    stop_all_run_request(LiveCaptionRagHwSize.run_url, LiveCaptionRagHwSize.run_ids)      
    lvc_metrics = get_live_caption_metrics(LiveCaptionRagHwSize.metrics)    
    output_file = save_live_video_caption_telemetry_kpis(LiveCaptionRagHwSize.report_dir, lvc_metrics, LiveCaptionRagHwSize.run_configs)
    latencies, input_tokens, output_tokens, ttfts, itls, tpss = write_metrics(LiveCaptionRagHwSize.all_metrics, LiveCaptionRagHwSize.report_dir)
    save_lvc_rag_metrics_to_wsf_format(LiveCaptionRagHwSize.report_dir, output_file, LiveCaptionRagHwSize.caption_duration, latencies, input_tokens, output_tokens, ttfts, itls, tpss)

    
    
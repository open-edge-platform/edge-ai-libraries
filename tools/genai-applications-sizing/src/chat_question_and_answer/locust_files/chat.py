# Copyright (C) 2024 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from locust import task, constant, events, HttpUser
import os
import time
import json
from common.utils import get_response, write_metrics, write_chatqna_metrics_to_csv
from src.chat_question_and_answer_core.utilities.utils import get_token_length



@events.init_command_line_parser.add_listener
def add_custom_arguments(parser):
    """
    Adds custom command-line arguments for the Locust test.

    Args:
        parser (argparse.ArgumentParser): The argument parser to add arguments to.
    """
    parser.add_argument("--request_count", type=int, default=1, help="Number of requests per user.")
    parser.add_argument("--chat_endpoint", type=str, default="chat", help="Chat API endpoint.")
    parser.add_argument("--report_dir", type=str, default="reports", help="Directory to save reports.")
    parser.add_argument("--prompt", type=str, default="test", help="Prompt for the chat API.")
    parser.add_argument("--max_tokens", type=str, default="1024", help="Maximum output tokens.")
    parser.add_argument("--file_details", type=str, default="{}", help="File details in JSON format.")

class ChatHwSize(HttpUser):
    """
    Locust user class for testing the Chat API hardware sizing.
    """
    wait_time = constant(0.1)
    latencies = []

    def on_start(self):
        """
        Initializes the test by setting up configurations and creating the report directory.
        """
        self.chat_endpoint = self.environment.parsed_options.chat_endpoint
        self.prompt = self.environment.parsed_options.prompt
        report_dir = self.environment.parsed_options.report_dir
        self.max_tokens = int(self.environment.parsed_options.max_tokens)
        ChatHwSize.file_details = json.loads(self.environment.parsed_options.file_details)

        # Create report directory
        ChatHwSize.report_dir = os.path.join(report_dir, "chat")
        os.makedirs(ChatHwSize.report_dir, exist_ok=True)
        ChatHwSize.all_metrics = []

        print("Locust started sending traffic to the Chat API...")
        

    @task
    def chat_hw_sizing(self):
        """
        Sends a POST request to the Chat API and processes the response.

        If the request is successful, the response is saved to the report directory.
        """
        try:
            #body = {"input": self.prompt, "max_tokens":self.max_tokens}
            body = {"conversation_messages":[{"role":"user","content":self.prompt}],"max_tokens":self.max_tokens}
            headers = {'Content-Type': 'application/json'}

            request_start_time = int(time.time() * 1e3)
            ttft, itl, metrics, chunks = 0.0, [], {}, []
            start_time = time.perf_counter()
            most_recent_timestamp = start_time

            # Send POST request
            response = self.client.post(
                url=f":{self.chat_endpoint}",
                headers=headers,
                json=body,
                stream=True,
                verify=True
            )

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
                request_end_time = int(time.time() * 1e3)
            else:
                metrics["ERROR_CODE"] = response.status_code            

            # Process response chunks
            answer = ""
            for chunk in chunks:
                without_data = chunk.decode("utf-8")[6:]
                answer += without_data

            # Save response and calculate metrics
            get_response(response={}, report_dir=ChatHwSize.report_dir, answer=answer)

            input_tokens = get_token_length(self.prompt)
            num_output_tokens = get_token_length(answer)
            
            metrics["LATENCY (ms)"] = sum(itl) * 1000
            metrics["TTFT (ms)"] = ttft * 1000
            metrics["ITL (ms)"] = ((sum(itl) - ttft) / (num_output_tokens - 1)) * 1000 if num_output_tokens > 1 else 0
            metrics["TPS"] = num_output_tokens / sum(itl) if sum(itl) > 0 else 0
            metrics["INPUT_TOKENS"] = input_tokens
            metrics["OUTPUT_TOKENS"] = num_output_tokens

            ChatHwSize.all_metrics.append(metrics)
            
        except Exception as e:
            print(f"Error during chat hardware sizing: {e}")


@events.quitting.add_listener
def collect_metrics(environment, **kwargs):
    """
    Collects and writes metrics after the test is completed.

    Args:
        environment (Environment): The Locust environment.
        **kwargs: Additional arguments.
    """
    print("Collecting metrics...")

    # Write metrics to files
    latencies, input_tokens, output_tokens, ttfts, itls, tpss = write_metrics(
        ChatHwSize.all_metrics, ChatHwSize.report_dir
    )
    write_chatqna_metrics_to_csv(
        ChatHwSize.report_dir, latencies, input_tokens, output_tokens, ttfts, itls, tpss, ChatHwSize.file_details
    )
  
    print(f"Chat API Hardware Sizing completed. Check reports here: {ChatHwSize.report_dir}.\n")


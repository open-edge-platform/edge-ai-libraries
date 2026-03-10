# Copyright (C) 2024 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from locust import task, constant, events, HttpUser
import os
import time
from common.utils import get_response, write_chatqna_metrics_to_csv, write_metrics
from src.chat_question_and_answer_core.utilities.utils import get_token_length


@events.init_command_line_parser.add_listener
def add_custom_arguments(parser):
    """
    Adds custom command-line arguments for the Locust test.

    Args:
        parser (argparse.ArgumentParser): The argument parser to add arguments to.
    """
    parser.add_argument("--chat_endpoint", type=str, default="chat", help="Chat API endpoint.")
    parser.add_argument("--report_dir", type=str, default="reports", help="Directory to save reports.")
    parser.add_argument("--prompt", type=str, default="test prompt", help="Prompt for the chat API.")
    #parser.add_argument("--max_tokens", type=str, default="1024", help="Maximum output tokens.")


class StreamCoreHwSize(HttpUser):
    """
    Locust user class for testing the Stream Log API hardware sizing.
    """
    wait = constant(0.1)

    def on_start(self):
        """
        Initializes the test by setting up the report directory and other configurations.
        """
        self.chat_endpoint = self.environment.parsed_options.chat_endpoint
        self.prompt = self.environment.parsed_options.prompt
        report_dir = self.environment.parsed_options.report_dir
        #self.max_tokens = int(self.environment.parsed_options.max_tokens)

        # Setup report directory
        StreamCoreHwSize.report_dir = os.path.join(report_dir, "chat")
        os.makedirs(StreamCoreHwSize.report_dir, exist_ok=True)

        # Initialize metrics storage
        StreamCoreHwSize.all_metrics = []

        print("Locust started sending traffic to the Stream Log API...")

    @task
    def core_stream_log_hw_sizing(self):
        """
        Sends a POST request to the Stream Log API and tracks performance metrics.

        If the request is successful, metrics such as latency, TTFT, ITL, and TPS are calculated.
        """
        try:
            headers = {'Content-Type': 'application/json'}
            body = {"input": self.prompt, "stream":True}

            # Initialize metrics
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
            else:
                metrics["ERROR_CODE"] = response.status_code

            # Process response chunks
            answer = ""
            for chunk in chunks:
                without_data = chunk.decode("utf-8")[6:]
                answer += without_data

            # Save response and calculate metrics
            get_response(response={}, report_dir=StreamCoreHwSize.report_dir, answer=answer)

            input_tokens = get_token_length(self.prompt)
            num_output_tokens = get_token_length(answer)

            metrics["LATENCY (ms)"] = sum(itl) * 1000
            metrics["TTFT (ms)"] = ttft * 1000
            metrics["ITL (ms)"] = ((sum(itl) - ttft) / (num_output_tokens - 1)) * 1000 if num_output_tokens > 1 else 0
            metrics["TPS"] = num_output_tokens / sum(itl) if sum(itl) > 0 else 0
            metrics["INPUT_TOKENS"] = input_tokens
            metrics["OUTPUT_TOKENS"] = num_output_tokens

            StreamCoreHwSize.all_metrics.append(metrics)

        except Exception as e:
            print(f"Benchmarking failed with exception: {e}")


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
        StreamCoreHwSize.all_metrics, StreamCoreHwSize.report_dir
    )
    write_chatqna_metrics_to_csv(
        StreamCoreHwSize.report_dir, latencies, input_tokens, output_tokens, ttfts, itls, tpss
    )

    print(f"Stream Log API Hardware Sizing completed. Check reports here: {StreamCoreHwSize.report_dir}.\n")

# Copyright (C) 2024 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from locust import task, constant, events, HttpUser
import time
from common.utils import setup_document_upload, rest_api_metrics, safe_parse_string_to_dict
import os



@events.init_command_line_parser.add_listener
def add_custom_arguments(parser):
    """
    Adds custom command-line arguments for the Locust test.

    Args:
        parser (argparse.ArgumentParser): The argument parser to add arguments to.
    """
    parser.add_argument("--doc_endpoint", type=str, default="document", help="Document API endpoint.")
    parser.add_argument("--report_dir", type=str, default="reports", help="Directory to save reports.")
    parser.add_argument("--file_details", type=str, default="", help="Details of files to upload.")


class DocHwSize(HttpUser):
    """
    Locust user class for testing the Document API hardware sizing.
    """
    wait = constant(0.1)

    def on_start(self):
        """
        Initializes the test by setting up file uploads and creating the report directory.
        """
        self.document_endpoint = self.environment.parsed_options.doc_endpoint
        file_details = self.environment.parsed_options.file_details
        self.file_details = safe_parse_string_to_dict(file_details)
        report_dir = self.environment.parsed_options.report_dir

        # Setup file uploads
        self.upload_files = setup_document_upload(self.file_details)

        # Create report directory
        DocHwSize.report_dir = os.path.join(report_dir, "document")
        os.makedirs(DocHwSize.report_dir, exist_ok=True)

        # Initialize latency tracking
        DocHwSize.latencies = []

        print("Locust started sending traffic to the Document API...")

    @task
    def document_hw_sizing(self):
        """
        Sends a POST request to the Document API and tracks latency.

        If the request is successful, the latency is recorded. Otherwise, an error is logged.
        """
        try:
            request_start_time = int(time.time() * 1e3)
            response = self.client.post(url=f":{self.document_endpoint}", files=self.upload_files, catch_response=True)
            request_end_time = int(time.time() * 1e3)

            if response.status_code == 200:
                DocHwSize.latencies.append(request_end_time - request_start_time)
            else:
                print(f"Document upload request failed: {response.status_code}")
                DocHwSize.latencies.append(0)
        except Exception as e:
            print(f"Error during document hardware sizing: {e}")


@events.quitting.add_listener
def collect_metrics(environment, **kwargs):
    """
    Collects and writes metrics after the test is completed.

    Args:
        environment (Environment): The Locust environment.
        **kwargs: Additional arguments.
    """
    print("Collecting metrics...")

    try:
        rest_api_metrics(api_name="document", latencies=DocHwSize.latencies, report_dir=DocHwSize.report_dir)
        print(f"Document API Hardware Sizing completed. Check reports here: {DocHwSize.report_dir}.\n")
    except Exception as e:
        print(f"Error during metrics collection: {e}")

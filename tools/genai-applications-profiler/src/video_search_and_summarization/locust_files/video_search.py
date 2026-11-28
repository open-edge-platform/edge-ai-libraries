# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
Locust load test for Video Search API.

This module defines a Locust user class that simulates video upload,
embedding creation, and search requests for performance analysis.
"""

import itertools
import os
import time

from locust import HttpUser, events, task

from common.metrics import (
    convert_search_metrics_to_wsf_format,
    get_video_search_telemetry_kpis,
    save_video_summary_search_telemetry_kpis,
)
from common.utils import safe_parse_string_to_dict
from common.video import (
    embedding_video_file,
    upload_video_file,
    wait_for_search_to_complete,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_JSON_HEADERS = {"Content-Type": "application/json"}

# ---------------------------------------------------------------------------
# CLI argument registration
# ---------------------------------------------------------------------------


@events.init_command_line_parser.add_listener
def add_custom_arguments(parser):
    """
    Register custom command-line arguments for the Locust test.

    Args:
        parser (argparse.ArgumentParser): The argument parser to add arguments to.
    """
    parser.add_argument(
        "--search_endpoint", type=str, default="",
        help="Video search API endpoint.",
    )
    parser.add_argument(
        "--embedding_endpoint", type=str, default="",
        help="Video embedding API endpoint.",
    )
    parser.add_argument(
        "--upload_endpoint", type=str, default="",
        help="Video upload API endpoint.",
    )
    parser.add_argument(
        "--telemetry_endpoint", type=str, default="6016/telemetry",
        help="Video telemetry API endpoint.",
    )
    parser.add_argument(
        "--file_details", type=str, default="",
        help="Details of the video file to be uploaded.",
    )
    parser.add_argument(
        "--queries", type=str, default="",
        help="Queries for video search.",
    )
    parser.add_argument(
        "--report_dir", type=str, default="reports",
        help="Directory to save reports.",
    )


# ---------------------------------------------------------------------------
# Locust user
# ---------------------------------------------------------------------------


class VideoSearchHwSize(HttpUser):
    """
    Locust user for video search API hardware sizing.

    Lifecycle:
      on_start         — upload + embed all videos once, then start query cycle.
      search_video     — fire one search request and record KPIs.
      collect_metrics  — aggregate and persist results on exit.
    """

    # Shared result stores (single-user; initialised in on_start)
    search_metrics: list = []
    query_details: list = []
    report_dir: str = ""
    process_start_time: float = 0.0
    process_end_time: float = 0.0
    telemetry_response = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def on_start(self) -> None:
        """Set up endpoints, ingest videos, and prepare the query cycle."""
        opts = self.environment.parsed_options

        # Endpoint paths (instance-level; read once)
        self.search_endpoint = opts.search_endpoint
        self.telemetry_endpoint = opts.telemetry_endpoint

        # Full URLs built once
        self.search_url = f"{self.host}:{self.search_endpoint}"
        upload_url = f"{self.host}:{opts.upload_endpoint}"
        embedding_url = f"{self.host}:{opts.embedding_endpoint}"

        # Report directory
        VideoSearchHwSize.report_dir = os.path.join(opts.report_dir, "video_search")
        os.makedirs(VideoSearchHwSize.report_dir, exist_ok=True)

        # Parse inputs
        file_details = safe_parse_string_to_dict(opts.file_details)
        queries = safe_parse_string_to_dict(opts.queries)

        # --- Video ingestion: upload then create embeddings ---
        VideoSearchHwSize.process_start_time = time.time()
        for file_detail in file_details:
            filename = file_detail.get("name")
            filepath = file_detail.get("path")
            video_id = upload_video_file(upload_url, filename, filepath)
            if video_id is not None:
                embedding_video_file(embedding_url, video_id)
        VideoSearchHwSize.process_end_time = time.time()

        # Snapshot telemetry right after ingestion
        VideoSearchHwSize.telemetry_response = self.client.get(
            f":{self.telemetry_endpoint}"
        )

        # Infinite cycle so every task call gets the next query
        self.query_cycle = itertools.cycle(queries)

    # ------------------------------------------------------------------
    # Task
    # ------------------------------------------------------------------

    @task
    def search_video(self) -> None:
        """Submit one search request and record timing and query KPIs."""
        qry = next(self.query_cycle)
        search_time: float = 0.0
        query_metrics: dict = {}

        try:
            print("Sending search request...")
            response = self.client.post(
                f":{self.search_endpoint}",
                headers=_JSON_HEADERS,
                json=qry,
            )

            if response.status_code == 201:
                query_id = response.json().get("queryId")
                search_time, query_metrics = wait_for_search_to_complete(
                    self.search_url, query_id
                )
                print("Video search completed.")
            else:
                print(
                    f"Search failed with status {response.status_code}: "
                    f"{response.text}"
                )

        except Exception as exc:
            print(f"Video search failed: {exc}")

        # Always record metrics so every iteration is represented
        VideoSearchHwSize.query_details.append(query_metrics)
        VideoSearchHwSize.search_metrics.append(
            {**qry, "query_search_seconds": search_time}
        )


# ---------------------------------------------------------------------------
# Quitting event handler
# ---------------------------------------------------------------------------


@events.quitting.add_listener
def collect_metrics(environment, **kwargs) -> None:
    """Aggregate KPIs and write reports when Locust exits."""
    print("Collecting metrics...")
    metrics, telemetry_details = get_video_search_telemetry_kpis(
        VideoSearchHwSize.process_start_time,
        VideoSearchHwSize.process_end_time,
        VideoSearchHwSize.telemetry_response.json(),
        VideoSearchHwSize.search_metrics,
    )
    json_file = save_video_summary_search_telemetry_kpis(
        VideoSearchHwSize.report_dir,
        metrics,
        telemetry_details,
        VideoSearchHwSize.query_details,
    )
    convert_search_metrics_to_wsf_format(VideoSearchHwSize.report_dir, json_file)

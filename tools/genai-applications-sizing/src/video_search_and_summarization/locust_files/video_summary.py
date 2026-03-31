# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
Locust load test for Video Summary API.

This module defines a Locust user class that simulates video upload and
summarization requests, collecting telemetry KPIs for performance analysis.
"""

import os
import time

from locust import HttpUser, events, task

from common.metrics import (
    convert_summary_metrics_to_wsf_format,
    get_video_summary_telemetry_kpis,
    save_video_summary_search_telemetry_kpis,
)
from common.utils import safe_parse_string_to_dict
from common.video import (
    get_video_details,
    get_video_summary,
    upload_video_file,
    wait_for_video_summary_complete,
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
        "--summary_endpoint", type=str, default="",
        help="Video summary API endpoint.",
    )
    parser.add_argument(
        "--state_endpoint", type=str, default="",
        help="Video summary states API endpoint.",
    )
    parser.add_argument(
        "--upload_endpoint", type=str, default="",
        help="Video upload API endpoint.",
    )
    parser.add_argument(
        "--telemetry_endpoint", type=str, default="",
        help="Video telemetry API endpoint.",
    )
    parser.add_argument(
        "--filename", type=str, default="",
        help="Name of the video file to summarize.",
    )
    parser.add_argument(
        "--filepath", type=str, default="",
        help="Path to the video file to summarize.",
    )
    parser.add_argument(
        "--payload", type=str, default="",
        help="JSON payload for the summarization request.",
    )
    parser.add_argument(
        "--report_dir", type=str, default="reports",
        help="Directory to save reports.",
    )


# ---------------------------------------------------------------------------
# Locust user
# ---------------------------------------------------------------------------


class VideoSummaryHwSize(HttpUser):
    """
    Locust user for video summary API hardware sizing.

    Lifecycle:
      on_start        — resolve endpoints, parse payload, set up output dir.
      summarize_video — upload a video, submit summary, wait for completion,
                        then collect telemetry KPIs.
      collect_metrics — aggregate and persist results on exit.
    """

    # Shared result stores (single-user; initialised in on_start)
    report_dir: str = ""
    upload_url: str = ""
    states_url: str = ""
    filepath: str = ""
    sampling_params = None
    telemetry_details = None
    metrics: list = []

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def on_start(self) -> None:
        """Resolve all endpoint URLs, parse static inputs, and prep output dir."""
        opts = self.environment.parsed_options

        # Endpoint paths (instance-level; immutable after start)
        self.summary_endpoint = opts.summary_endpoint
        self.telemetry_endpoint = opts.telemetry_endpoint
        self.filename = opts.filename

        # Class-level state set once by the (single) user
        if not VideoSummaryHwSize.report_dir:
            VideoSummaryHwSize.filepath = opts.filepath
            VideoSummaryHwSize.upload_url = f"{self.host}:{opts.upload_endpoint}"
            VideoSummaryHwSize.states_url = f"{self.host}:{opts.state_endpoint}"
            report_dir = os.path.join(opts.report_dir, "video_summary")
            VideoSummaryHwSize.report_dir = report_dir
            os.makedirs(report_dir, exist_ok=True)

        # Parse and cache the request payload once per user instance
        self._payload = safe_parse_string_to_dict(opts.payload)
        VideoSummaryHwSize.sampling_params = self._payload.get("sampling")

    # ------------------------------------------------------------------
    # Task
    # ------------------------------------------------------------------

    @task
    def summarize_video(self) -> None:
        """Upload a video, request a summary, wait for completion, record KPIs."""
        video_properties = get_video_details(VideoSummaryHwSize.filepath)

        video_id = upload_video_file(
            VideoSummaryHwSize.upload_url,
            self.filename,
            VideoSummaryHwSize.filepath,
        )
        if video_id is None:
            print("Video upload failed — skipping this iteration.")
            return

        try:
            payload = {**self._payload, "videoId": video_id}

            # Submit summary request and track wall-clock time
            summary_start = time.time()
            response = self.client.post(
                f":{self.summary_endpoint}",
                headers=_JSON_HEADERS,
                json=payload,
            )
            summary_id = response.json().get("summaryPipelineId")
            print(f"Video summary started with ID: {summary_id}")

            # Poll until complete
            state_url = f"{VideoSummaryHwSize.states_url}/{summary_id}"
            video_summary_complete, summary_response = wait_for_video_summary_complete(
                state_url
            )
            if not video_summary_complete:
                print("Video summary did not complete successfully.")
                return

            summary_end = time.time()
            get_video_summary(
                VideoSummaryHwSize.report_dir, summary_response, summary_id
            )

            # Collect telemetry KPIs
            telemetry_response = self.client.get(
                f":{self.telemetry_endpoint}", headers=_JSON_HEADERS
            )
            if telemetry_response.status_code == 200:
                telemetry_kpis, VideoSummaryHwSize.telemetry_details = (
                    get_video_summary_telemetry_kpis(
                        summary_start,
                        summary_end,
                        telemetry_response.json(),
                        video_properties,
                    )
                )
                VideoSummaryHwSize.metrics.append(telemetry_kpis)
            else:
                print(
                    f"Failed to retrieve telemetry data. "
                    f"Status code: {telemetry_response.status_code}"
                )

        except Exception as exc:
            print(f"Video summarization failed: {exc}")


# ---------------------------------------------------------------------------
# Quitting event handler
# ---------------------------------------------------------------------------


@events.quitting.add_listener
def collect_metrics(environment, **kwargs) -> None:
    """Aggregate KPIs and write reports when Locust exits."""
    print("Collecting metrics...")

    if not VideoSummaryHwSize.metrics or VideoSummaryHwSize.telemetry_details is None:
        print("No metrics collected — skipping report generation.")
        return

    output_file = save_video_summary_search_telemetry_kpis(
        VideoSummaryHwSize.report_dir,
        VideoSummaryHwSize.metrics,
        VideoSummaryHwSize.telemetry_details,
    )
    convert_summary_metrics_to_wsf_format(
        VideoSummaryHwSize.report_dir,
        output_file,
        VideoSummaryHwSize.sampling_params,
    )

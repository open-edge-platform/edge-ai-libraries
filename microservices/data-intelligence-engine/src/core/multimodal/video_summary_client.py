# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
"""Asking the multi-level video understanding service what a clip shows.

The service is synchronous: `POST /v1/summary` holds the connection until the
model has finished. There is no job id, no cursor, and no partial result --
`SummarizationStatus` is `completed` or `failed` and nothing else. So the
caller owns the asynchrony (see `captioning.py`), and this module is a plain
request.

`levels=1` is what makes a short clip a *single* description. The summarizer
builds a hierarchy by default -- micro chunks, macro chunks, then a global
pass -- and with one level it takes the whole clip as one chunk and returns
the micro-level description directly. That is the same thing as "do not chunk
a short video", expressed in the service's own terms.
"""

from typing import Any, Dict, Optional

import config


class VideoSummaryError(RuntimeError):
    """The service could not describe the clip."""


class VideoSummaryClient:
    """A caption for a clip, from the understanding service."""

    def __init__(
        self,
        base_url: Optional[str] = None,
        task: Optional[str] = None,
        timeout: Optional[float] = None,
    ):
        self.base_url = (base_url or config.VIDEO_SUMMARY_BASE_URL or "").rstrip("/")
        self.task = task or config.VIDEO_SUMMARY_TASK
        self.timeout = timeout if timeout is not None else config.VIDEO_SUMMARY_TIMEOUT

    @property
    def configured(self) -> bool:
        """Whether there is a service to ask.

        Unconfigured is a supported state, not an error: a clip still gets its
        vector and its file-name caption, and the pipeline runs without the
        service being up.
        """
        return bool(self.base_url)

    def caption(self, video_path: str, prompt: Optional[str] = None) -> str:
        """One description of the whole clip at `video_path`."""
        if not self.configured:
            raise VideoSummaryError("No video summary base URL is configured")
        import httpx  # noqa: PLC0415

        payload: Dict[str, Any] = {
            "video": video_path,
            "task": self.task,
            # No temporal dependency to carry: there is only one chunk.
            "method": "SIMPLE",
            "processor_kwargs": {"levels": 1, "level_sizes": [-1]},
        }
        if prompt:
            payload["prompt"] = prompt
        try:
            response = httpx.post(
                f"{self.base_url}/v1/summary", json=payload, timeout=self.timeout
            )
            response.raise_for_status()
            body = response.json()
        except Exception as error:  # noqa: BLE001 - every transport failure reads alike here
            raise VideoSummaryError(f"Video summary request failed: {type(error).__name__}: {error}") from error

        summary = str(body.get("summary") or "").strip()
        status = str(body.get("status") or "").lower()
        # The service reports a model-level failure two ways: in `status`, and
        # by returning the error as the summary text with a 200. Checking only
        # the first would store "Error: ..." as a caption and index it.
        if status == "failed" or summary.startswith("Error:"):
            raise VideoSummaryError(f"Video summary service could not summarize the clip: {summary or status}")
        if not summary:
            raise VideoSummaryError("Video summary service returned an empty summary")
        return summary


__all__ = ["VideoSummaryClient", "VideoSummaryError"]

# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

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
        """Whether there is a service to ask; unconfigured is a supported state."""
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
        except Exception as error:  # noqa: BLE001
            raise VideoSummaryError(f"Video summary request failed: {type(error).__name__}: {error}") from error

        summary = str(body.get("summary") or "").strip()
        status = str(body.get("status") or "").lower()
        # A model-level failure may also arrive as a 200 whose summary starts with "Error:".
        if status == "failed" or summary.startswith("Error:"):
            raise VideoSummaryError(f"Video summary service could not summarize the clip: {summary or status}")
        if not summary:
            raise VideoSummaryError("Video summary service returned an empty summary")
        return summary


__all__ = ["VideoSummaryClient", "VideoSummaryError"]

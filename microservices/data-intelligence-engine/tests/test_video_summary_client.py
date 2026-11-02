# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
"""The client for the video summary service, as far as it can be tested here."""

import pytest

from core.multimodal.video_summary_client import VideoSummaryClient, VideoSummaryError


def test_an_unconfigured_client_reports_itself_unconfigured():
    assert not VideoSummaryClient(base_url="").configured


def test_an_unconfigured_client_refuses_to_call():
    with pytest.raises(VideoSummaryError, match="No video summary base URL"):
        VideoSummaryClient(base_url="").caption("/x.mp4")

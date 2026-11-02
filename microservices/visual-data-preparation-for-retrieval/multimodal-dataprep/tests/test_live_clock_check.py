# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Tests for the live-stream camera clock-skew diagnostic."""

from __future__ import annotations

import logging
import time
from email.utils import formatdate

import httpx
import pytest

from src.core.live import clock_check
from src.core.live.clock_check import ClockSkew, log_clock_skew, probe_camera_clock


def _response(headers: dict) -> httpx.Response:
    return httpx.Response(401, headers=headers)


@pytest.fixture
def fake_head(monkeypatch):
    """Patch httpx.head, returning a recorder of the URLs requested."""
    calls = []

    def _install(result):
        def _head(url, **kwargs):
            calls.append((url, kwargs))
            if isinstance(result, Exception):
                raise result
            return result

        monkeypatch.setattr(clock_check.httpx, "head", _head)
        return calls

    return _install


def _date_header(epoch: float) -> dict:
    return {"Date": formatdate(epoch, usegmt=True)}


class TestProbeCameraClock:
    def test_returns_none_when_url_has_no_host(self, fake_head):
        assert probe_camera_clock("not a url") is None

    def test_returns_none_when_http_fails(self, fake_head):
        fake_head(httpx.ConnectError("refused"))
        assert probe_camera_clock("rtsp://cam-1:554/live") is None

    def test_returns_none_when_date_header_absent(self, fake_head):
        fake_head(_response({"Server": "webserver"}))
        assert probe_camera_clock("rtsp://cam-1:554/live") is None

    def test_returns_none_when_date_header_unparsable(self, fake_head):
        fake_head(_response({"Date": "not-a-date"}))
        assert probe_camera_clock("rtsp://cam-1:554/live") is None

    def test_synchronised_camera_reports_near_zero_drift(self, fake_head):
        fake_head(_response(_date_header(time.time())))
        skew = probe_camera_clock("rtsp://cam-1:554/live")
        assert skew is not None
        assert abs(skew.drift_seconds) <= 1.0
        assert skew.timezone_offset_seconds == 0
        assert not skew.timezone_mislabelled

    def test_detects_drift_ahead_of_host(self, fake_head):
        fake_head(_response(_date_header(time.time() + 53)))
        skew = probe_camera_clock("rtsp://cam-1:554/live")
        assert skew is not None
        assert skew.drift_seconds == pytest.approx(53, abs=1.5)
        assert not skew.timezone_mislabelled

    def test_detects_drift_behind_host(self, fake_head):
        fake_head(_response(_date_header(time.time() - 120)))
        skew = probe_camera_clock("rtsp://cam-1:554/live")
        assert skew is not None
        assert skew.drift_seconds == pytest.approx(-120, abs=1.5)

    def test_local_time_labelled_gmt_is_not_read_as_huge_drift(self, fake_head):
        """The real Hikvision behaviour: +05:30 local time stamped as GMT.

        Naive parsing yields a 5.5-hour skew; the genuine drift is 53 seconds.
        """
        fake_head(_response(_date_header(time.time() + 5.5 * 3600 + 53)))
        skew = probe_camera_clock("rtsp://cam-1:554/live")
        assert skew is not None
        assert skew.timezone_mislabelled
        assert skew.timezone_offset_seconds == int(5.5 * 3600)
        assert skew.drift_seconds == pytest.approx(53, abs=1.5)
        assert skew.raw_difference_seconds == pytest.approx(5.5 * 3600 + 53, abs=1.5)

    def test_probes_host_over_http_without_credentials(self, fake_head):
        calls = fake_head(_response(_date_header(time.time())))
        probe_camera_clock("rtsp://admin:secret-pw@cam-1:554/Streaming/Channels/101")
        url, kwargs = calls[0]
        assert url == "http://cam-1/"
        assert "secret-pw" not in url
        assert "auth" not in kwargs
        assert kwargs["timeout"] > 0

    def test_ignores_proxy_environment(self, fake_head):
        """The camera is a LAN device; a proxy would answer with its own clock."""
        calls = fake_head(_response(_date_header(time.time())))
        probe_camera_clock("rtsp://cam-1:554/live")
        assert calls[0][1]["trust_env"] is False

    def test_proxied_environment_does_not_produce_false_skew(self, monkeypatch, fake_head):
        """Regression: HTTP_PROXY once routed the probe to a proxy returning 403."""
        monkeypatch.setenv("HTTP_PROXY", "http://proxy.example.com:912")
        fake_head(_response(_date_header(time.time() + 53)))
        skew = probe_camera_clock("rtsp://cam-1:554/live")
        assert skew is not None
        assert skew.drift_seconds == pytest.approx(53, abs=1.5)

    def test_ipv6_host_is_bracketed(self, fake_head):
        calls = fake_head(_response(_date_header(time.time())))
        probe_camera_clock("rtsp://[2001:db8::1]:554/live")
        assert calls[0][0] == "http://[2001:db8::1]/"


class TestLogClockSkew:
    URL = "rtsp://admin:secret-pw@cam-1:554/Streaming/Channels/101"

    def test_warns_when_drift_exceeds_threshold(self, fake_head, caplog):
        fake_head(_response(_date_header(time.time() + 53)))
        with caplog.at_level(logging.WARNING):
            log_clock_skew(self.URL, "stream-abc", warn_threshold=2.0)
        assert any(r.levelno == logging.WARNING for r in caplog.records)
        assert "stream-abc" in caplog.text

    def test_does_not_warn_when_camera_is_synchronised(self, fake_head, caplog):
        fake_head(_response(_date_header(time.time())))
        with caplog.at_level(logging.WARNING):
            log_clock_skew(self.URL, "stream-abc", warn_threshold=2.0)
        assert not [r for r in caplog.records if r.levelno >= logging.WARNING]

    def test_warns_on_mislabelled_timezone_even_when_drift_is_small(self, fake_head, caplog):
        fake_head(_response(_date_header(time.time() + 5.5 * 3600)))
        with caplog.at_level(logging.WARNING):
            log_clock_skew(self.URL, "stream-abc", warn_threshold=2.0)
        assert any(r.levelno == logging.WARNING for r in caplog.records)

    def test_never_logs_credentials(self, fake_head, caplog):
        fake_head(_response(_date_header(time.time() + 53)))
        with caplog.at_level(logging.DEBUG):
            log_clock_skew(self.URL, "stream-abc", warn_threshold=2.0)
        assert "secret-pw" not in caplog.text
        assert "admin:" not in caplog.text

    def test_unreachable_camera_is_silent_at_warning_level(self, fake_head, caplog):
        fake_head(httpx.ConnectError("refused"))
        with caplog.at_level(logging.WARNING):
            log_clock_skew(self.URL, "stream-abc", warn_threshold=2.0)
        assert not [r for r in caplog.records if r.levelno >= logging.WARNING]

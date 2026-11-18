# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import subprocess
import unittest
from unittest.mock import MagicMock, patch

import rtsp_utils
from rtsp_utils import (
    GST_DISCOVERER_BIN,
    RTSP_URL_MAX_LENGTH,
    clear_probe_cache,
    parse_discoverer_output,
    probe_rtsp_codec,
    redact_rtsp_url,
    validate_rtsp_url,
)

DISCOVERER_H264_OUTPUT = """Analyzing rtsp://mediamtx:8554/test
Done discovering rtsp://mediamtx:8554/test

Properties:
  Duration: 99:99:99.999999999
  Seekable: no
  Live: yes
  Tags:
      video codec: H.264 (Constrained Baseline Profile)
  unknown #0: application/x-rtp, media=(string)video, payload=(int)96, encoding-name=(string)H264
    video #1: video/x-h264, stream-format=(string)avc, alignment=(string)au, width=(int)640, height=(int)480
      Tags:
        video codec: H.264 (Constrained Baseline Profile)
"""

DISCOVERER_ERROR_OUTPUT = """Analyzing rtsp://mediamtx:8554/missing
Done discovering rtsp://mediamtx:8554/missing
An error was encountered while discovering the file
 Could not open resource for reading and writing.
"""


class TestValidateRtspUrl(unittest.TestCase):
    def test_valid_urls(self):
        for url in [
            "rtsp://mediamtx:8554/stream",
            "rtsp://192.168.1.10/live/ch0",
            "rtsp://192.168.1.10:554/Streaming/Channels/101?transportmode=unicast&profile=Profile_1",
            "rtsp://[fe80::1]:554/stream",
            "rtsp://host/path%20encoded;param=1",
        ]:
            with self.subTest(url=url):
                self.assertEqual(validate_rtsp_url(url), url)

    def test_strips_surrounding_whitespace(self):
        self.assertEqual(
            validate_rtsp_url("  rtsp://host/stream \n"), "rtsp://host/stream"
        )

    def test_rejects_pipeline_injection(self):
        for url in [
            "rtsp://host/stream ! filesink location=/tmp/x",
            "rtsp://host/stream!fakesink",
            'rtsp://host/"stream"',
            "rtsp://host/'stream'",
            "rtsp://host/a\tb",
            "rtsp://host/a\nb",
            "rtsp://host/a,b",
            "rtsp://host/$(id)",
            "rtsp://host/a\\b",
        ]:
            with self.subTest(url=url):
                with self.assertRaises(ValueError):
                    validate_rtsp_url(url)

    def test_rejects_wrong_scheme(self):
        for url in [
            "http://host/stream",
            "rtsps://host/stream",
            "RTSP://host/stream",
            "file:///etc/passwd",
            "/dev/video0",
        ]:
            with self.subTest(url=url):
                with self.assertRaises(ValueError):
                    validate_rtsp_url(url)

    def test_rejects_credentials(self):
        with self.assertRaises(ValueError) as ctx:
            validate_rtsp_url("rtsp://user:secret@host/stream")
        self.assertNotIn("secret", str(ctx.exception))
        with self.assertRaises(ValueError):
            validate_rtsp_url("rtsp://user@host/stream")

    def test_rejects_missing_host_and_bad_port(self):
        for url in ["rtsp://", "rtsp:///stream", "rtsp://host:99999/stream"]:
            with self.subTest(url=url):
                with self.assertRaises(ValueError):
                    validate_rtsp_url(url)

    def test_rejects_empty_and_non_string(self):
        with self.assertRaises(ValueError):
            validate_rtsp_url("")
        with self.assertRaises(ValueError):
            validate_rtsp_url("   ")
        with self.assertRaises(ValueError):
            validate_rtsp_url(None)  # type: ignore[arg-type]

    def test_rejects_too_long(self):
        url = "rtsp://host/" + "a" * RTSP_URL_MAX_LENGTH
        with self.assertRaises(ValueError):
            validate_rtsp_url(url)


class TestRedactRtspUrl(unittest.TestCase):
    def test_removes_query_and_fragment(self):
        self.assertEqual(
            redact_rtsp_url("rtsp://host:554/path?token=abc#frag"),
            "rtsp://host:554/path",
        )


class TestParseDiscovererOutput(unittest.TestCase):
    def test_h264(self):
        self.assertEqual(parse_discoverer_output(DISCOVERER_H264_OUTPUT), "h264")

    def test_h265_and_jpeg(self):
        self.assertEqual(
            parse_discoverer_output("    video #1: video/x-h265, width=(int)1920"),
            "h265",
        )
        self.assertEqual(
            parse_discoverer_output("    video #0: image/jpeg, width=(int)1920"),
            "MJPG",
        )

    def test_error_output(self):
        self.assertIsNone(parse_discoverer_output(DISCOVERER_ERROR_OUTPUT))

    def test_unsupported_codec(self):
        self.assertIsNone(
            parse_discoverer_output("    video #1: video/x-vp8, width=(int)640")
        )


class TestProbeRtspCodec(unittest.TestCase):
    def setUp(self):
        clear_probe_cache()

    def tearDown(self):
        clear_probe_cache()

    @patch("rtsp_utils.subprocess.run")
    def test_probe_success_and_cache(self, mock_run):
        mock_run.return_value = MagicMock(stdout=DISCOVERER_H264_OUTPUT)

        self.assertEqual(probe_rtsp_codec("rtsp://mediamtx:8554/test"), "h264")
        self.assertEqual(probe_rtsp_codec("rtsp://mediamtx:8554/test"), "h264")

        mock_run.assert_called_once()
        args, kwargs = mock_run.call_args
        argv = args[0]
        self.assertEqual(argv[0], GST_DISCOVERER_BIN)
        self.assertEqual(argv[-1], "rtsp://mediamtx:8554/test")
        self.assertNotIn("shell", kwargs)
        self.assertIn("timeout", kwargs)

    @patch("rtsp_utils.subprocess.run")
    def test_probe_failure_is_cached(self, mock_run):
        mock_run.return_value = MagicMock(stdout=DISCOVERER_ERROR_OUTPUT)

        self.assertIsNone(probe_rtsp_codec("rtsp://mediamtx:8554/missing"))
        self.assertIsNone(probe_rtsp_codec("rtsp://mediamtx:8554/missing"))
        mock_run.assert_called_once()

    @patch("rtsp_utils.subprocess.run")
    def test_cache_expires(self, mock_run):
        mock_run.return_value = MagicMock(stdout=DISCOVERER_H264_OUTPUT)
        with patch.object(rtsp_utils, "RTSP_PROBE_CACHE_TTL_S", 0):
            probe_rtsp_codec("rtsp://mediamtx:8554/test")
            probe_rtsp_codec("rtsp://mediamtx:8554/test")
        self.assertEqual(mock_run.call_count, 2)

    @patch("rtsp_utils.subprocess.run")
    def test_probe_timeout(self, mock_run):
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="x", timeout=1)
        self.assertIsNone(probe_rtsp_codec("rtsp://mediamtx:8554/test"))

    @patch("rtsp_utils.subprocess.run")
    def test_discoverer_missing(self, mock_run):
        mock_run.side_effect = FileNotFoundError()
        self.assertIsNone(probe_rtsp_codec("rtsp://mediamtx:8554/test"))

    @patch("rtsp_utils.subprocess.run")
    def test_invalid_url_is_not_probed(self, mock_run):
        self.assertIsNone(probe_rtsp_codec("rtsp://host/a ! fakesink"))
        mock_run.assert_not_called()


if __name__ == "__main__":
    unittest.main()

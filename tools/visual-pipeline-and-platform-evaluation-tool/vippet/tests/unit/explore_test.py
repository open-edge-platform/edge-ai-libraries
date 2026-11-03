import unittest
from unittest.mock import MagicMock, patch

import httpx

from explore import GstInspector


class TestGstInspector(unittest.TestCase):
    def setUp(self):
        # Reset the singleton instance before each test
        GstInspector._instance = None

    def tearDown(self):
        # Reset the singleton instance after each test
        GstInspector._instance = None

    @patch("explore.subprocess.run")
    def test_singleton(self, mock_run):
        mock_run.return_value = MagicMock(stdout="", stderr="", returncode=0)
        a = GstInspector()
        b = GstInspector()
        self.assertIs(a, b)

    @patch("explore.subprocess.run")
    def test_get_elements(self, mock_run):
        # Simulate gst-inspect-1.0 output
        mock_run.return_value = MagicMock(
            stdout=(
                "va:  vaav1dec: VA-API AV1 Decoder in Intel(R) Gen Graphics\n"
                "va:  vaav1enc: VA-API AV1 Encoder in Intel(R) Gen Graphics\n"
                "va:  vacompositor: VA-API Video Compositor in Intel(R) Gen Graphics\n"
            ),
            stderr="",
            returncode=0,
        )
        inspector = GstInspector()
        elements = inspector.get_elements()
        expected = [
            ("va", "vaav1dec", "VA-API AV1 Decoder in Intel(R) Gen Graphics"),
            ("va", "vaav1enc", "VA-API AV1 Encoder in Intel(R) Gen Graphics"),
            ("va", "vacompositor", "VA-API Video Compositor in Intel(R) Gen Graphics"),
        ]
        # Check that every expected element is in the returned elements
        for exp in expected:
            self.assertIn(exp, elements)

        # Also check that the number of elements matches
        self.assertEqual(len(elements), len(expected))


@patch("explore._EXECUTION_BACKEND", "dlsps2")
class TestGstInspectorDlsps2(unittest.TestCase):
    def setUp(self):
        GstInspector._instance = None

    def tearDown(self):
        GstInspector._instance = None

    @patch("explore.subprocess.run")
    @patch("explore.httpx.get")
    def test_elements_come_from_dlsps2(self, mock_get, mock_run):
        mock_get.return_value = httpx.Response(
            200,
            json=[
                {"name": "vah264dec", "plugin": "va", "description": "VA H.264"},
                {"name": "gvadetect", "plugin": "gva", "description": "Detect"},
            ],
            request=httpx.Request("GET", "http://dlsps/elements"),
        )

        elements = GstInspector().get_elements()

        self.assertEqual(
            elements,
            [("gva", "gvadetect", "Detect"), ("va", "vah264dec", "VA H.264")],
        )
        self.assertTrue(mock_get.call_args.args[0].endswith("/elements"))
        mock_run.assert_not_called()

    @patch("explore.subprocess.run")
    @patch("explore.httpx.get")
    def test_falls_back_to_local_gst_inspect(self, mock_get, mock_run):
        mock_get.side_effect = httpx.ConnectError("refused")
        mock_run.return_value = MagicMock(
            stdout="va:  vah264dec: VA H.264\n", stderr="", returncode=0
        )

        with self.assertLogs("GstInspector", level="WARNING"):
            elements = GstInspector().get_elements()

        self.assertEqual(elements, [("va", "vah264dec", "VA H.264")])

    @patch("explore.subprocess.run")
    @patch("explore.httpx.get")
    def test_empty_dlsps2_list_falls_back(self, mock_get, mock_run):
        mock_get.return_value = httpx.Response(
            200, json=[], request=httpx.Request("GET", "http://dlsps/elements")
        )
        mock_run.return_value = MagicMock(
            stdout="va:  vah264dec: VA H.264\n", stderr="", returncode=0
        )

        elements = GstInspector().get_elements()

        self.assertEqual(elements, [("va", "vah264dec", "VA H.264")])


if __name__ == "__main__":
    unittest.main()

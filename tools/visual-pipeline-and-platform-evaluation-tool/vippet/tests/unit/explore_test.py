import unittest
from unittest.mock import patch

import httpx

from explore import GstInspector

_REQUEST = httpx.Request("GET", "http://dlsps/elements")


def _elements_response(elements: list[dict]) -> httpx.Response:
    return httpx.Response(200, json=elements, request=_REQUEST)


@patch("explore.ELEMENTS_RETRY_DELAY_S", 0)
class TestGstInspector(unittest.TestCase):
    def setUp(self):
        GstInspector._instance = None

    def tearDown(self):
        GstInspector._instance = None

    @patch("explore.httpx.get")
    def test_singleton(self, mock_get):
        mock_get.return_value = _elements_response([])
        a = GstInspector()
        b = GstInspector()
        self.assertIs(a, b)

    @patch("explore.httpx.get")
    def test_elements_come_from_dlsps2(self, mock_get):
        mock_get.return_value = _elements_response(
            [
                {"name": "vah264dec", "plugin": "va", "description": "VA H.264"},
                {"name": "gvadetect", "plugin": "gva", "description": "Detect"},
            ]
        )

        elements = GstInspector().get_elements()

        self.assertEqual(
            elements,
            [("gva", "gvadetect", "Detect"), ("va", "vah264dec", "VA H.264")],
        )
        self.assertTrue(mock_get.call_args.args[0].endswith("/elements"))
        self.assertEqual(mock_get.call_count, 1)

    @patch("explore.httpx.get")
    def test_retries_until_the_server_answers(self, mock_get):
        mock_get.side_effect = [
            httpx.ConnectError("refused"),
            _elements_response([]),
            _elements_response(
                [{"name": "vah264dec", "plugin": "va", "description": "VA H.264"}]
            ),
        ]

        with self.assertLogs("GstInspector", level="ERROR"):
            elements = GstInspector().get_elements()

        self.assertEqual(elements, [("va", "vah264dec", "VA H.264")])
        self.assertEqual(mock_get.call_count, 3)

    @patch("explore.httpx.get")
    def test_unreachable_server_leaves_list_empty_and_reads_again(self, mock_get):
        mock_get.side_effect = httpx.ConnectError("refused")

        with self.assertLogs("GstInspector", level="ERROR") as cm:
            inspector = GstInspector()
            self.assertEqual(inspector.get_elements(), [])

        self.assertTrue(any("No GStreamer elements" in m for m in cm.output))
        attempts = mock_get.call_count

        mock_get.side_effect = None
        mock_get.return_value = _elements_response(
            [{"name": "gvadetect", "plugin": "gva", "description": "Detect"}]
        )
        self.assertEqual(inspector.get_elements(), [("gva", "gvadetect", "Detect")])
        self.assertEqual(mock_get.call_count, attempts + 1)

    @patch("explore.httpx.get")
    def test_malformed_response_counts_as_no_elements(self, mock_get):
        mock_get.return_value = _elements_response([{"name": "x"}])

        with self.assertLogs("GstInspector", level="ERROR"):
            self.assertEqual(GstInspector().get_elements(), [])


if __name__ == "__main__":
    unittest.main()

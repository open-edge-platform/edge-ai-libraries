import unittest
from unittest.mock import MagicMock, patch

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


if __name__ == "__main__":
    unittest.main()

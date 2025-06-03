import unittest
from unittest import mock

from app import (create_interface, generate_stream_data, read_latest_metrics)


class TestApp(unittest.TestCase):
    def test_create_interface(self):
        # Since implementation is unknown, just check it returns something non-None
        result = create_interface()
        self.assertIsNotNone(result)

    def test_read_latest_valid(self):
        timestamp = 1748629754000000000
        mock_data = (
            f"cpu usage_user=1.0 {timestamp}\n"
            f"mem used_percent=1.0 {timestamp}\n"
            f"pkg_cur_power val=1.0 {timestamp}\n"
            f"gpu_cur_power val=1.0 {timestamp}\n"
            f"temp ,temp=1.0 {timestamp}\n"
            f"gpu_frequency value=1.0 {timestamp}\n"
            f"cpu_frequency_avg frequency=1.0 {timestamp}\n"
            f"gpu engine=render usage=1.0 {timestamp}\n"
            f"gpu engine=copy usage=1.0 {timestamp}\n"
            f"gpu engine=video-enhance usage=1.0 {timestamp}\n"
            f"gpu engine=video usage=1.0 {timestamp}\n"
            f"gpu engine=compute usage=1.0 {timestamp}\n"
        )
        with mock.patch(
            "builtins.open", mock.mock_open(read_data=mock_data)
        ) as mock_file:
            result = read_latest_metrics()
            expected = [1.0 for _ in range(12)]
            self.assertEqual(result, expected)

    def test_read_latest_invalid(self):
        timestamp = 1748629754000000000
        mock_data = (
            f"cpu usage_user=null {timestamp}\n"
            f"mem used_percent=null {timestamp}\n"
            f"pkg_cur_power val=null {timestamp}\n"
            f"gpu_cur_power val=null {timestamp}\n"
            f"temp ,temp=null {timestamp}\n"
            f"gpu_frequency value=null {timestamp}\n"
            f"cpu_frequency_avg frequency=null {timestamp}\n"
            f"gpu engine=render usage=null {timestamp}\n"
            f"gpu engine=copy usage=null {timestamp}\n"
            f"gpu engine=video-enhance usage=null {timestamp}\n"
            f"gpu engine=video usage=null {timestamp}\n"
            f"gpu engine=compute usage=null {timestamp}\n"
        )
        with mock.patch(
            "builtins.open", mock.mock_open(read_data=mock_data)
        ) as mock_file:
            result = read_latest_metrics()
            expected = [None for _ in range(12)]
            self.assertEqual(result, expected)

    def test_generate_stream_data(self):
        mock_data = [1.0 for _ in range(12)]
        with mock.patch("app.read_latest_metrics", return_value=mock_data):
            for i in range(13):
                stream = generate_stream_data(i)
                self.assertIsNotNone(stream)


if __name__ == "__main__":
    unittest.main()

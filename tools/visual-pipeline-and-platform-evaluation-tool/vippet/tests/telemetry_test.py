import unittest
from unittest import mock

from pipelines.pipeline_page import charts  # noqa: E402
from telemetry import Telemetry  # noqa: E402


class TestTelemetry(unittest.TestCase):
    def setUp(self):
        # No need to patch here, already patched above
        pass

    def test_read_latest_valid(self):
        timestamp = 1748629754000000000
        mock_data = (
            f"cpu usage_user=1.0 {timestamp}\n"
            f"mem used_percent=1.0 {timestamp}\n"
            f"pkg_cur_power gpu_id=1 val=1.0 {timestamp}\n"
            f"gpu_cur_power gpu_id=1 val=1.0 {timestamp}\n"
            f"temp ,temp=1.0 {timestamp}\n"
            f"gpu_frequency,gpu_id=1 value=1.0 {timestamp}\n"
            f"cpu_frequency_avg frequency=1.0 {timestamp}\n"
            f"gpu engine=render,gpu_id=1 usage=1.0 {timestamp}\n"
            f"gpu engine=copy,gpu_id=1 usage=1.0 {timestamp}\n"
            f"gpu engine=video-enhance,gpu_id=1 usage=1.0 {timestamp}\n"
            f"gpu engine=video,gpu_id=1 usage=1.0 {timestamp}\n"
            f"gpu engine=compute,gpu_id=1 usage=1.0 {timestamp}\n"
        )
        # Patch charts to include a GPU chart with gpu_id=1
        from chart import Chart, ChartType

        gpu_chart = Chart(
            "Test GPU Chart", "Utilization", ChartType.DGPU_ENGINE_UTILIZATION, gpu_id=1
        )
        cpu_chart = Chart("Test CPU Chart", "Utilization", ChartType.CPU_UTILIZATION)
        mem_chart = Chart("Test MEM Chart", "Utilization", ChartType.MEMORY_UTILIZATION)
        patched_charts = [cpu_chart, mem_chart, gpu_chart]
        with mock.patch("pipelines.pipeline_page.charts", patched_charts):
            with mock.patch("builtins.open", mock.mock_open(read_data=mock_data)):
                telemetry = Telemetry(patched_charts)
                result = telemetry.read_latest_metrics()
                # Check that all expected keys exist and have value 1.0 or None
                self.assertIsInstance(result, dict)
                # CPU/mem/core_temp/cpu_freq always present
                for key in ["cpu_user", "mem_used_percent", "core_temp", "cpu_freq"]:
                    self.assertEqual(result[key], 1.0)
                # GPU metrics for gpu_id=1
                for key in [
                    "gpu_package_power_1",
                    "gpu_power_1",
                    "gpu_freq_1",
                    "gpu_render_1",
                    "gpu_ve_1",
                    "gpu_video_1",
                    "gpu_copy_1",
                    "gpu_compute_1",
                ]:
                    self.assertEqual(result[key], 1.0)

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
        with mock.patch("builtins.open", mock.mock_open(read_data=mock_data)):
            telemetry = Telemetry(charts)
            result = telemetry.read_latest_metrics()
            self.assertIsInstance(result, dict)
            for v in result.values():
                self.assertTrue(v is None or v == "null")

    def test_generate_stream_data(self):
        # Prepare a metrics dict with all keys set to 1.0 for all charts
        metrics = {}
        for chart in charts:
            if chart.gpu_id is not None:
                for key in [
                    "gpu_package_power",
                    "gpu_power",
                    "gpu_freq",
                    "gpu_render",
                    "gpu_ve",
                    "gpu_video",
                    "gpu_copy",
                    "gpu_compute",
                ]:
                    metrics[f"{key}_{chart.gpu_id}"] = 1.0

        # Always present keys
        for key in ["cpu_user", "mem_used_percent", "core_temp", "cpu_freq"]:
            metrics[key] = 1.0

        with (
            mock.patch.object(Telemetry, "read_latest_metrics", return_value=metrics),
            mock.patch("builtins.open", mock.mock_open(read_data="1.0\n")),
        ):
            telemetry = Telemetry(charts)
            streams = telemetry.generate_stream_data()
            self.assertEqual(len(streams), len(charts))
            for stream in streams:
                self.assertIsNotNone(stream)


if __name__ == "__main__":
    unittest.main()

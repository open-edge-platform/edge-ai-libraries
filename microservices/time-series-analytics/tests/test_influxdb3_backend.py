# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import unittest
from unittest.mock import Mock, call, patch

from influxdb3_backend import InfluxDB3Backend


class InfluxDB3BackendTests(unittest.TestCase):
    def setUp(self):
        self.backend = InfluxDB3Backend(
            base_url="http://core:8181",
            token="test-token",
            database="datain",
        )

    @patch("influxdb3_backend.requests.request")
    def test_write_line_protocol_uses_v3_endpoint_and_token(self, request):
        request.return_value = Mock(status_code=204)

        self.backend.write_line_protocol("wind-turbine-data wind_speed=8.83 123")

        self.assertEqual(request.call_args.args, ("POST", "http://core:8181/api/v3/write_lp"))
        self.assertEqual(request.call_args.kwargs["params"], {"db": "datain", "precision": "nanosecond"})
        self.assertEqual(request.call_args.kwargs["headers"]["Authorization"], "Bearer test-token")

    @patch("influxdb3_backend.requests.request")
    def test_stream_config_creates_table_trigger_and_disables_batch(self, request):
        request.return_value = Mock(status_code=200, text="")

        with patch.dict("os.environ", {"INFLUXDB3_UDF_PLUGIN_DIR": "", "INFLUXDB3_TRIGGER_SPEC": ""}):
            result = self.backend.configure_udf(
                {"udfs": {"name": "windturbine_anomaly_detector", "models": "model.pkl"}},
                sample_app="wind-turbine-anomaly-detection",
            )

        self.assertEqual(result["trigger_specification"], "table:point_data")
        calls = request.call_args_list
        self.assertIn(
            call(
                "POST",
                "http://core:8181/api/v3/configure/processing_engine_trigger/disable",
                params={"db": "datain", "trigger_name": "windturbine_anomaly_detector_batch"},
                json=None,
                data=None,
                headers=unittest.mock.ANY,
                timeout=30,
            ),
            calls,
        )
        create_call = next(
            item for item in calls
            if item.args[0] == "POST" and item.args[1].endswith("processing_engine_trigger")
        )
        self.assertEqual(create_call.kwargs["json"]["trigger_specification"], "table:point_data")
        self.assertEqual(
            create_call.kwargs["json"]["plugin_filename"],
            "wind-turbine-anomaly-detection/udfs/windturbine_anomaly_detector",
        )
        self.assertEqual(create_call.kwargs["json"]["trigger_arguments"]["model_path"],
                         "/tmp/wind-turbine-anomaly-detection/models/model.pkl")

    @patch("influxdb3_backend.requests.request")
    def test_batch_config_uses_twenty_minute_schedule(self, request):
        request.return_value = Mock(status_code=200, text="")

        result = self.backend.configure_udf(
            {"udfs": {"name": "windturbine_anomaly_detector_batch"}},
            sample_app="wind-turbine-anomaly-detection",
        )

        self.assertEqual(result["trigger_specification"], "every:20m")

    @patch("influxdb3_backend.requests.request")
    def test_stream_config_honors_sample_plugin_and_trigger_overrides(self, request):
        request.return_value = Mock(status_code=200, text="")

        with patch.dict(
            "os.environ",
            {
                "INFLUXDB3_UDF_PLUGIN_DIR": "influx3_windturbine",
                "INFLUXDB3_TRIGGER_SPEC": "table:wind-turbine-data",
            },
        ):
            result = self.backend.configure_udf(
                {"udfs": {"name": "windturbine_anomaly_detector"}},
                sample_app="wind-turbine-anomaly-detection",
            )

        create_call = next(
            item for item in request.call_args_list
            if item.args[0] == "POST" and item.args[1].endswith("processing_engine_trigger")
        )
        self.assertEqual(result["trigger_specification"], "table:wind-turbine-data")
        self.assertEqual(
            create_call.kwargs["json"]["plugin_filename"],
            "wind-turbine-anomaly-detection/udfs/influx3_windturbine",
        )


if __name__ == "__main__":
    unittest.main()
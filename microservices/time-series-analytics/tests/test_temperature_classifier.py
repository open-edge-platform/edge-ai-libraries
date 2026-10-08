# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from udfs.temperature_classifier import process_writes


class InfluxDB3Local:
    def __init__(self):
        self.info_messages = []
        self.warning_messages = []

    def info(self, message):
        self.info_messages.append(message)

    def warn(self, *message):
        self.warning_messages.append(message)


def test_temperature_classifier_logs_only_out_of_range_values():
    local = InfluxDB3Local()
    process_writes(
        local,
        [{
            "table_name": "point_data",
            "rows": [
                {"temperature": 19},
                {"temperature": 20},
                {"temperature": 25},
                {"temperature": 26},
            ],
        }],
    )

    assert local.info_messages == [
        "Temperature 19 is outside the range 20-25.",
        "Temperature 26 is outside the range 20-25.",
    ]
    assert local.warning_messages == []


def test_temperature_classifier_warns_on_invalid_data_and_ignores_other_tables():
    local = InfluxDB3Local()
    process_writes(
        local,
        [
            {"table_name": "other", "rows": [{"temperature": 50}]},
            {"table_name": "point_data", "rows": [{"temperature": "hot"}]},
        ],
    )

    assert local.info_messages == []
    assert local.warning_messages == [("Invalid temperature data received", "hot")]
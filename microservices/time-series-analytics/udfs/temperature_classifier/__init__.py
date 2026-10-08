# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

INPUT_TABLE = "point_data"
MIN_TEMPERATURE = 20
MAX_TEMPERATURE = 25


def process_writes(influxdb3_local, table_batches, args=None):
    for table_batch in table_batches:
        if table_batch.get("table_name") != INPUT_TABLE:
            continue
        for row in table_batch.get("rows", []):
            temperature = row.get("temperature")
            if not isinstance(temperature, (int, float)):
                influxdb3_local.warn("Invalid temperature data received", temperature)
            elif temperature < MIN_TEMPERATURE or temperature > MAX_TEMPERATURE:
                influxdb3_local.info(
                    f"Temperature {temperature} is outside the range "
                    f"{MIN_TEMPERATURE}-{MAX_TEMPERATURE}."
                )
# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import json
import os
from pathlib import Path

import requests


class InfluxDB3Error(RuntimeError):
    pass


def udf_plugin_directory(udf_name):
    return os.getenv("INFLUXDB3_UDF_PLUGIN_DIR") or udf_name.removesuffix("_batch")


class InfluxDB3Backend:
    def __init__(self, base_url=None, token=None, database=None):
        self.base_url = (base_url or os.getenv("INFLUXDB3_URL", "http://localhost:8181")).rstrip("/")
        self.token = token or self._read_token()
        self.database = database or os.getenv("INFLUXDB_DBNAME", "datain")
        self.retention_period = os.getenv("INFLUXDB3_RETENTION_PERIOD", "1h")

    @staticmethod
    def _read_token():
        token = os.getenv("INFLUXDB3_AUTH_TOKEN")
        if token:
            return token

        token_path = os.getenv("INFLUXDB3_ADMIN_TOKEN_FILE", "/run/secrets/admin-token")
        try:
            with open(token_path, "r", encoding="utf-8") as token_file:
                token = json.load(token_file).get("token")
        except (OSError, json.JSONDecodeError) as error:
            raise InfluxDB3Error(f"Unable to load InfluxDB 3 admin token from {token_path}") from error
        if not token:
            raise InfluxDB3Error(f"No token found in {token_path}")
        return token

    def request(self, method, path, *, params=None, json_body=None, data=None, timeout=30):
        try:
            response = requests.request(
                method,
                f"{self.base_url}{path}",
                params=params,
                json=json_body,
                data=data,
                headers={
                    "Authorization": f"Bearer {self.token}",
                    "Content-Type": "application/json" if json_body is not None else "text/plain",
                },
                timeout=timeout,
            )
        except requests.RequestException as error:
            raise InfluxDB3Error(f"InfluxDB 3 request failed: {error}") from error
        return response

    def check_health(self):
        response = self.request("GET", "/health", timeout=3)
        if response.status_code != 200:
            raise InfluxDB3Error(f"InfluxDB 3 health check failed: HTTP {response.status_code}")
        return response

    def write_line_protocol(self, line_protocol, database=None, precision="nanosecond"):
        response = self.request(
            "POST",
            "/api/v3/write_lp",
            params={"db": database or self.database, "precision": precision},
            data=line_protocol,
        )
        if response.status_code != 204:
            raise InfluxDB3Error(f"InfluxDB 3 write failed: HTTP {response.status_code}: {response.text}")
        return response

    def ensure_database(self, database=None):
        name = database or self.database
        response = self.request(
            "POST",
            "/api/v3/configure/database",
            json_body={"db": name, "retention_period": self.retention_period},
        )
        if response.status_code not in (200, 409):
            raise InfluxDB3Error(f"InfluxDB 3 database setup failed: HTTP {response.status_code}: {response.text}")

    def _trigger_call(self, method, path, *, params=None, json_body=None, allow_missing=False):
        response = self.request(method, path, params=params, json_body=json_body)
        if allow_missing and response.status_code == 404:
            return response
        if response.status_code not in (200, 201, 204):
            raise InfluxDB3Error(f"InfluxDB 3 trigger setup failed: HTTP {response.status_code}: {response.text}")
        return response

    def configure_udf(self, config, sample_app=None):
        udf_config = config.get("udfs") or {}
        udf_name = udf_config.get("name")
        if not isinstance(udf_name, str) or not udf_name:
            raise InfluxDB3Error("The udfs.name config value is required")

        is_batch = udf_name.endswith("_batch")
        base_name = udf_name.removesuffix("_batch") if is_batch else udf_name
        trigger_name = udf_name
        alternate_name = base_name if is_batch else f"{base_name}_batch"
        trigger_specification = "every:20m" if is_batch else os.getenv(
            "INFLUXDB3_TRIGGER_SPEC"
        ) or "table:point_data"
        sample_app = sample_app or os.getenv("SAMPLE_APP", udf_name)
        plugin_directory = udf_plugin_directory(udf_name)
        plugin_filename = f"{sample_app}/udfs/{plugin_directory}"

        self.ensure_database()

        requirements_path = Path("/tmp") / sample_app / "udfs" / plugin_directory / "requirements.txt"
        if requirements_path.is_file():
            response = self.request(
                "POST",
                "/api/v3/configure/plugin_environment/install_requirements",
                json_body={"requirements_location": str(requirements_path)},
                timeout=int(os.getenv("INFLUXDB3_PACKAGE_INSTALL_TIMEOUT", "1800")),
            )
            if response.status_code != 200:
                raise InfluxDB3Error(
                    f"InfluxDB 3 dependency installation failed: HTTP {response.status_code}: {response.text}"
                )

        for name in (alternate_name, trigger_name):
            self._trigger_call(
                "POST",
                "/api/v3/configure/processing_engine_trigger/disable",
                params={"db": self.database, "trigger_name": name},
                allow_missing=True,
            )
            self._trigger_call(
                "DELETE",
                "/api/v3/configure/processing_engine_trigger",
                params={"db": self.database, "trigger_name": name, "force": "true"},
                allow_missing=True,
            )

        trigger_arguments = {}
        model_name = udf_config.get("models")
        if model_name:
            trigger_arguments["model_path"] = str(Path("/tmp") / sample_app / "models" / model_name)
        device = udf_config.get("device")
        if device:
            device_value = str(device).lower()
            trigger_arguments["device"] = "auto" if device_value == "cpu" else device_value
        mqtt_config = (config.get("alerts") or {}).get("mqtt") or {}
        if mqtt_config:
            trigger_arguments.update({
                "mqtt_host": str(mqtt_config.get("mqtt_broker_host", "ia-mqtt-broker")),
                "mqtt_port": str(mqtt_config.get("mqtt_broker_port", 1883)),
                "mqtt_topic": "alerts/wind_turbine",
                "mqtt_qos": "1",
            })
        opcua_config = (config.get("alerts") or {}).get("opcua") or {}
        if opcua_config:
            trigger_arguments["opcua_url"] = os.getenv(
                "INFLUXDB3_OPCUA_ALERT_URL",
                "http://ia-time-series-analytics-microservice:5000/opcua_alerts",
            )

        self._trigger_call(
            "POST",
            "/api/v3/configure/processing_engine_trigger",
            json_body={
                "db": self.database,
                "disabled": True,
                "plugin_filename": plugin_filename,
                "trigger_name": trigger_name,
                "trigger_specification": trigger_specification,
                "trigger_arguments": trigger_arguments,
                "trigger_settings": {"error_behavior": "log", "run_async": False},
            },
        )
        self._trigger_call(
            "POST",
            "/api/v3/configure/processing_engine_trigger/enable",
            params={"db": self.database, "trigger_name": trigger_name},
        )
        return {"trigger_name": trigger_name, "trigger_specification": trigger_specification}
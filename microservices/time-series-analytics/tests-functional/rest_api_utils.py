#
# Apache v2 license
# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
#

import pytest
import requests
import time
import subprocess
import json
import os
import copy

# Read the config.json file
TS_DIR = os.path.join(os.getcwd(), "..")
with open(os.path.join(TS_DIR, "config.json")) as f:
    config_file = json.load(f)
print(config_file)

def run_command(command):
    """Run a shell command and return the output."""
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"Command failed: {command}\n{result.stderr}")
    return result

## REST API Tests

# Get health check /health endpoint
def health_check(port):
    """
    Test the health check endpoint of the Time Series Analytics service.
    """
    url = f"http://localhost:{port}/health"
    try:
        response = requests.get(url, timeout=10)
        assert response.status_code == 200
        assert response.json() == {"status": "kapacitor daemon is running"}
    except Exception as e:
        pytest.fail(f"Health check failed: {e}")

# Post the OPC UA alerts /opcua_alerts endpoint
def opcua_alerts(port):
    """
    Test the OPC UA alerts endpoint of the Time Series Analytics service.
    """
    alert_message = {"message": "Test alert"}
    try:
        url = f"http://localhost:{port}/opcua_alerts"
        response = requests.post(url, json=alert_message, timeout=10)
        assert response.status_code == 500
        assert response.json() == {'detail': '500: OPC UA alerts are not configured in the service'}
    except Exception as e:
        pytest.fail(f"Failed to post OPC UA alerts: {e}")

# Post valid input data to the /input endpoint
def input_endpoint(port):
    """
    Test the input endpoint of the Time Series Analytics service.
    """
    input_data = {
        "topic": "point_data",
        "tags": {
        },
        "fields": {
            "temperature": 30
        },
        "timestamp": 0
    }
    try:
        url = f"http://localhost:{port}/input"
        response = requests.post(url, json=input_data, timeout=10)
        assert response.status_code == 200
        assert response.json() == {"status": "success", "message": "Data sent to Time Series Analytics microservice"}
    except Exception as e:
        pytest.fail(f"Failed to post valid input data: {e}")

# Post invalid input data to the /input endpoint
def input_endpoint_invalid_data(port):
    """
    Test the input endpoint of the Time Series Analytics service.
    """
    input_data = {
        "topic": "point_data",
        "tags": {
        },
        "fields": {
            "temperature": "invalid_value"  # Invalid temperature value
        },
        "timestamp": 0
    }
    try:
        url = f"http://localhost:{port}/input"
        response = requests.post(url, json=input_data, timeout=10)
        assert response.status_code == 500
        assert "400: unable to parse 'point_data temperature=invalid_value" in response.json().get("detail", "")
    except Exception as e:
        pytest.fail(f"Failed to post invalid input data: {e}")
    input_data["fields"]["temperature"] = ""
    try:
        url = f"http://localhost:{port}/input"
        response = requests.post(url, json=input_data, timeout=10)
        assert response.status_code == 500
        assert "400: unable to parse 'point_data temperature=" in response.json().get("detail", "")
    except Exception as e:
        pytest.fail(f"Failed to post no input data: {e}")

# Post no input data to the /input endpoint
def input_endpoint_no_data(port):
    """
    Test the input endpoint of the Time Series Analytics service.
    """
    input_data = {
        "topic": "point_data",
        "tags": {
        },
        "fields": {
            "temperature": ""  # Invalid temperature value
        },
        "timestamp": 0
    }
    try:
        url = f"http://localhost:{port}/input"
        response = requests.post(url, json=input_data, timeout=10)
        assert response.status_code == 500
        assert "400: unable to parse 'point_data temperature=" in response.json().get("detail", "")
    except Exception as e:
        pytest.fail(f"Failed to post no input data: {e}")

# Get config data from the /config endpoint
def get_config_endpoint(port):
    """
    Test the config endpoint of the Time Series Analytics service.
    """
    url = f"http://localhost:{port}/config"
    try:
        response = requests.get(url, timeout=10)
        assert response.status_code == 200
        print("get config =", response.json())
        assert response.json() == config_file
    except Exception as e:
        pytest.fail(f"Failed to get config data: {e}")

# Post config data to the /config endpoint
def post_config_endpoint(port, command):
    """
    Test the config endpoint of the Time Series Analytics service.
    """
    url = f"http://localhost:{port}/config"
    try:
        response = requests.post(url, json=config_file, timeout=10)
        assert response.status_code == 200
        assert response.json() == {"status": "success", "message": "Configuration updated successfully"}
        time.sleep(10)  # Wait for the configuration to be applied
        output = run_command(command)
        output = output.stdout + output.stderr
        assert "Kapacitor daemon process has exited and was reaped." in output
    except Exception as e:
        pytest.fail(f"Failed to post config data: {e}")

# Test concurrent API requests
def concurrent_api_requests(port):
    """
    Test concurrent API requests to the Time Series Analytics service.
    """
    url = f"http://localhost:{port}"
    input_data = {
        "topic": "point_data",
        "tags": {},
        "fields": {"temperature": 30},
        "timestamp": 0
    }
    config_file_alerts = copy.deepcopy(config_file)
    config_file_alerts["alerts"] = {}
    opcua_alert = {"message": "Test alert"}
    endpoints = ['/health', '/config', '/opcua_alerts', '/input' ]
    print("config file alert", config_file_alerts)
    print("config file", config_file)
    def get_request(endpoint):
        try:
            response = requests.get(url + endpoint, timeout=10)
            return response.status_code, response.text
        except Exception as e:
            return None, str(e)
    
    def post_request(endpoint, data):
        try:
            response = requests.post(url + endpoint, json=data, timeout=10)
            return response.status_code, response.json()
        except Exception as e:
            return None, str(e)

    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=5) as executor:
        try:
            future_get_health = executor.submit(get_request, endpoints[0])
            future_get_config = executor.submit(get_request, endpoints[1])
            
            # Schedule the POST request
            future_post_alert = executor.submit(post_request, endpoints[2], opcua_alert)
            future_post_input = executor.submit(post_request, endpoints[3], input_data)
            future_post_config = executor.submit(post_request, endpoints[1], config_file)

            # Retrieve results
            get_health_result = future_get_health.result()
            get_config_result = future_get_config.result()
            post_alert_result = future_post_alert.result()

            print(f"GET /health: {get_health_result}")
            print(f"GET /config: {get_config_result}")
            print(f"POST /opcua_alerts: {post_alert_result}")
            print(f"POST /input: {future_post_input.result()}")
            print(f"POST /config: {future_post_config.result()}")

            health_status_code = [200, 500, 503]
            health_status_json = [{"status": "kapacitor daemon is running"}, {"detail": "500: Kapacitor daemon is not running"}, {"status":"Port not accessible and kapacitor daemon not running"}]
            assert get_health_result[0] in health_status_code
            assert json.loads(get_health_result[1]) in health_status_json
            assert get_config_result[0] == 200
            assert json.loads(get_config_result[1]) == config_file or json.loads(get_config_result[1]) == config_file_alerts
            assert post_alert_result[0] == 500
            assert post_alert_result[1] == {'detail': '500: OPC UA alerts are not configured in the service'}
            assert future_post_input.result()[0] == 200 or future_post_input.result()[0] == 500
            assert future_post_input.result()[1] == {"status": "success", "message": "Data sent to Time Series Analytics microservice"} or \
                future_post_input.result()[1] == {'detail': '500: Kapacitor daemon is not running'}
            assert future_post_config.result()[0] == 200
            assert future_post_config.result()[1] == {"status": "success", "message": "Configuration updated successfully"}
        except Exception as e:
            pytest.fail(f"Concurrent API requests failed: {e}")

# Post invalid config data to the /config endpoint
def post_invalid_config_endpoint(port, command):
    """
    Test the config endpoint of the Time Series Analytics service.
    """
    url = f"http://localhost:{port}/config"
    invalid_config_data = copy.deepcopy(config_file)
    invalid_config_data["udfs"]["name"] = "udf_classifier"
    try:
        response = requests.post(url, json=invalid_config_data, timeout=10)
        assert response.status_code == 200
        assert response.json() == {"status": "success", "message": "Configuration updated successfully"}
        time.sleep(15)  # Wait for the configuration to be applied
        output = run_command(command)
        output = output.stdout + output.stderr
        assert "UDF deployment package directory udf_classifier does not exist. Please check and upload/copy the UDF deployment package." in output
    except Exception as e:
        pytest.fail(f"Failed to post config data: {e}")

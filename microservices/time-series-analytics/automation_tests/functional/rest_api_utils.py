#
# Apache v2 license
# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
#

import pytest
import requests
import time
import subprocess

def run_command(command):
    """Run a shell command and return the output."""
    result = subprocess.run(command, shell=True, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"Command failed: {command}\n{result.stderr}")
    return result.stdout.strip()

## REST API Tests

# Get health check /health endpoint
def health_check(port):
    """
    Test the health check endpoint of the Time Series Analytics service.
    """
    url = f"http://localhost:{port}/health"
    try:
        response = requests.get(url)
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
        response = requests.post(url, json=alert_message)
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
        response = requests.post(url, json=input_data)
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
        response = requests.post(url, json=input_data)
        assert response.status_code == 500
        assert "400: unable to parse 'point_data temperature=invalid_value" in response.json().get("detail", "")
    except Exception as e:
        pytest.fail(f"Failed to post invalid input data: {e}")
    

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
        response = requests.post(url, json=input_data)
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
    config_data = {
        "model_registry": {
            "enable": False,
            "version": "1.0"
        },
        "udfs": {
            "name": "temperature_classifier"
        }
    }
    try:
        response = requests.get(url)
        assert response.status_code == 200
        assert response.json() == config_data
    except Exception as e:
        pytest.fail(f"Failed to get config data: {e}")

# Post config data to the /config endpoint
def post_config_endpoint(port, cmd):
    """
    Test the config endpoint of the Time Series Analytics service.
    """
    url = f"http://localhost:{port}/config"
    config_data = {
    "model_registry": {
        "enable": False,
        "version": "1.0"
    },
    "udfs": {
        "name": "temperature_classifier"
    }
    }
    try:
        response = requests.post(url, json=config_data)
        assert response.status_code == 200
        assert response.json() == {"status": "success", "message": "Configuration updated successfully"}
        time.sleep(10)  # Wait for the configuration to be applied
        command = f"{cmd} 2>&1 | grep -i 'Kapacitor daemon process has exited and was reaped.'"
        output = run_command(command)
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
    config_data = {
        "model_registry": {
            "enable": False,
            "version": "1.0"
        },
        "udfs": {
            "name": "temperature_classifier"
        },
        "alerts": {}
    }
    opcua_alert = {"message": "Test alert"}
    endpoints = ['/health', '/config', '/opcua_alerts', '/input' ]

    def get_request(endpoint):
        try:
            response = requests.get(url + endpoint)
            return response.status_code, response.text
        except Exception as e:
            return None, str(e)
    
    def post_request(endpoint, data):
        try:
            response = requests.post(url + endpoint, json=data)
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
            future_post_config = executor.submit(post_request, endpoints[1], config_data)

            # Retrieve results
            get_health_result = future_get_health.result()
            get_config_result = future_get_config.result()
            post_alert_result = future_post_alert.result()

            print(f"GET /health: {get_health_result}")
            print(f"GET /config: {get_config_result}")
            print(f"POST /opcua_alerts: {post_alert_result}")
            print(f"POST /input: {future_post_input.result()}")
            print(f"POST /config: {future_post_config.result()}")

            assert get_health_result[0] == 200 or get_health_result[0] == 500
            assert get_health_result[1] == '{"status":"kapacitor daemon is running"}' or get_health_result[1] == '{"detail":"500: Kapacitor daemon is not running"}'
            assert get_config_result[0] == 200
            assert get_config_result[1] == '{"model_registry":{"enable":false,"version":"1.0"},"udfs":{"name":"temperature_classifier"},"alerts":{}}'
            assert post_alert_result[0] == 500
            assert post_alert_result[1] == {'detail': '500: OPC UA alerts are not configured in the service'}
            assert future_post_input.result()[0] == 200
            assert future_post_input.result()[1] == {"status": "success", "message": "Data sent to Time Series Analytics microservice"}
            assert future_post_config.result()[0] == 200
            assert future_post_config.result()[1] == {"status": "success", "message": "Configuration updated successfully"}
        except Exception as e:
            pytest.fail(f"Concurrent API requests failed: {e}")

# Post invalid config data to the /config endpoint
def post_invalid_config_endpoint(port, cmd):
    """
    Test the config endpoint of the Time Series Analytics service.
    """
    url = f"http://localhost:{port}/config"
    config_data = {
        "model_registry": {
            "enable": False,
            "version": "1.0"
        },
        "udfs": {
            "name": "udf_classifier"
        }
    }
    try:
        response = requests.post(url, json=config_data)
        assert response.status_code == 200
        assert response.json() == {"status": "success", "message": "Configuration updated successfully"}
        time.sleep(15)  # Wait for the configuration to be applied
        command = f"{cmd} 2>&1 | grep -i 'UDF deployment package directory udf_classifier does not exist. Please check and upload/copy the UDF deployment package.'"
        output = run_command(command)
        print(output)
        assert "UDF deployment package directory udf_classifier does not exist. Please check and upload/copy the UDF deployment package." in output
    except Exception as e:
        pytest.fail(f"Failed to post config data: {e}")

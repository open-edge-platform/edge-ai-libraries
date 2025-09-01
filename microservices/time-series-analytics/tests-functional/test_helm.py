#
# Apache v2 license
# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
#

import subprocess
import os
import pytest
import time
import shutil
import rest_api_utils as utils

NAMESPACE = "apps"
RELEASE_NAME = "time-series-analytics-microservice"
TS_HELM_PORT = 30002

cwd = os.getcwd()
print(f"Current working directory: {cwd}")
TS_DIR = os.path.join(cwd, "..")
HELM_DIR = os.path.join(TS_DIR, "helm")
if not os.path.exists(TS_DIR):
    pytest.skip("Time Series Analytics directory not found. Skipping tests.")


def helm_install(release_name, chart_path, namespace):
    """Install a Helm chart with specified parameters."""
    try:
        # Construct the Helm install command
        helm_command = [
            "helm", "install", release_name, chart_path,
            "-n", namespace, "--create-namespace"
        ]

        # Execute the Helm install command and capture output
        print(f"Installing Helm chart...")
        result = utils.run_command(helm_command)

        # Print the output for debugging purposes
        print(result.stdout)
        return True
    except subprocess.CalledProcessError as e:
        print(f"Failed to install Helm chart: Error: INSTALLATION FAILED: values don't meet the specifications of the schema(s) in the following chart(s): {e.stderr}")
        return False

def helm_uninstall(release_name, namespace):
    """Uninstall a Helm release with specified parameters."""
    try:
        # Construct the Helm uninstall command
        helm_command = [
            "helm", "uninstall", release_name,
            "-n", namespace
        ]

        # Execute the Helm uninstall command and capture output
        print(f"Uninstalling Helm release '{release_name}' from namespace '{namespace}'...")
        result = utils.run_command(helm_command)

        # Print the output for debugging purposes
        print(result.stdout)
        return True
    except subprocess.CalledProcessError as e:
        print(f"Failed to uninstall Helm release: Error: uninstall: Release not loaded: ts-wind-turbine-anomaly: release: not found: {e.stderr}")
        return False

def get_pod_names(namespace):
    """Fetch pod names in the given namespace."""
    try:
        command = ["kubectl", "get", "pods", "-n", namespace, "-o", "jsonpath={.items[*].metadata.name}"]
        print(f"Fetching pod names in namespace '{namespace}'...")
        result = utils.run_command(command)

        pod_names = result.stdout.strip().split()
        return pod_names
    except subprocess.CalledProcessError as e:
        print(f"Failed to fetch pod names: {e}")
        return []

@pytest.fixture(scope="function", autouse=True)
def helm_setup():
    """Fixture to set up and tear down Helm environment for each test."""

    os.chdir(TS_DIR)
    shutil.copy("config.json", os.path.join(HELM_DIR, "config.json"))

    # Install the Helm chart
    if not helm_install(RELEASE_NAME, HELM_DIR, NAMESPACE):
        pytest.fail("Helm installation failed.")
    time.sleep(30)  # Wait for the Helm release to be ready
    yield
    # Uninstall the Helm release
    if not helm_uninstall(RELEASE_NAME, NAMESPACE):
        pytest.fail("Helm uninstallation failed.")
    # Wait for pods to be terminated
    time.sleep(30)

def test_timeseries_microservice_start():
    """Start the Time Series Analytics Microservice."""
    # Check if pods are running
    pod_names = get_pod_names(NAMESPACE)
    print(f"Found pods in namespace '{NAMESPACE}': {pod_names}") 
    if not pod_names:
        pytest.fail("No pods found in the namespace.")

    print("Time Series Analytics Microservice started successfully.")

def test_timeseries_microservice_started_successfully():
    """Start the Time Series Analytics Microservice."""
    # Check if pods are running
    pod_names = get_pod_names(NAMESPACE)
    print(f"Found pods in namespace '{NAMESPACE}': {pod_names}") 
    if not pod_names:
        pytest.fail("No pods found in the namespace.")

    try:
        command = ["kubectl", "logs", "-n", NAMESPACE, pod_names[0]]
        output = utils.run_command(command)
        output = output.stdout + output.stderr
        print(output)
        assert "Kapacitor Initialized Successfully. Ready to Receive the Data..." in output
    except Exception as e:
        pytest.fail(f"Time Series Analytics Microservice did not start: {e}")

## REST API Tests

def test_health_check():
    # Get health check /health endpoint
    print("Testing health check endpoint in utils...")
    utils.health_check(TS_HELM_PORT)

# Post the OPC UA alerts /opcua_alerts endpoint
def test_opcua_alerts():
    """
    Test the OPC UA alerts endpoint of the Time Series Analytics service.
    """
    utils.opcua_alerts(TS_HELM_PORT)

# Post valid input data to the /input endpoint
def test_input_endpoint():
    """
    Test the input endpoint of the Time Series Analytics service.
    """
    utils.input_endpoint(TS_HELM_PORT)

# Post invalid input data to the /input endpoint
def test_input_endpoint_invalid_data():
    """
    Test the input endpoint of the Time Series Analytics service.
    """
    utils.input_endpoint_invalid_data(TS_HELM_PORT)
    utils.input_endpoint_no_data(TS_HELM_PORT)

def test_get_config_endpoint():
    """
    Test the config endpoint of the Time Series Analytics service.
    """
    utils.get_config_endpoint(TS_HELM_PORT)

# Post config data to the /config endpoint
def test_post_config_endpoint():
    """
    Test the config endpoint of the Time Series Analytics service.
    """
    podnames = get_pod_names(NAMESPACE)
    print(f"Found pods in namespace '{NAMESPACE}': {podnames}")
    if not podnames:
        pytest.fail("No pods found in the namespace.")
    cmd = ["kubectl", "logs", "-n", NAMESPACE, podnames[0]]
    utils.post_config_endpoint(TS_HELM_PORT, cmd)

# Test concurrent API requests
def test_concurrent_api_requests():
    """
    Test concurrent API requests to the Time Series Analytics service.
    """
    utils.concurrent_api_requests(TS_HELM_PORT)

# Post config data to the /config endpoint
def test_post_invalid_config_endpoint():
    """
    Test the config endpoint of the Time Series Analytics service.
    """
    podnames = get_pod_names(NAMESPACE)
    print(f"Found pods in namespace '{NAMESPACE}': {podnames}")
    if not podnames:
        pytest.fail("No pods found in the namespace.")
    cmd = ["kubectl", "logs", "-n", NAMESPACE, podnames[0]]
    utils.post_invalid_config_endpoint(TS_HELM_PORT, cmd)

def test_temperature_input():
    """
    Test to check if the temperature simulator script runs without error.
    """
    os.chdir(TS_DIR)
    command = ["timeout", "20", "python3", "simulator/temperature_input.py", "--port", str(TS_HELM_PORT)]
    try:
        print("Starting temperature simulator...")
        # Run the simulator for 20 seconds, then terminate
        subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        time.sleep(10)
        print("Temperature simulator started successfully.")
        pod_names = get_pod_names(NAMESPACE)
        print(f"Found pods in namespace '{NAMESPACE}': {pod_names}") 
        if not pod_names:
            pytest.fail("No pods found in the namespace.")
        command = ["kubectl", "logs", "-n", NAMESPACE, pod_names[0]]
        time.sleep(10)  # Wait for the simulator to produce output
        print("Checking Time Series Analytics Microservice logs for temperature data...")
        output = utils.run_command(command)
        output = output.stdout + output.stderr
        assert "is outside the range 20-25." in output
    except RuntimeError as e:
        pytest.fail(f"Time Series Analytics Microservice failed for the temperature input data: {e}")

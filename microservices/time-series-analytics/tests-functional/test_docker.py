#
# Apache v2 license
# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
#

import subprocess
import os
import pytest
import time
import rest_api_utils as utils

CONTAINER_NAME = "ia-time-series-analytics-microservice"
TS_DOCKER_PORT = 5000

cwd = os.getcwd()
TS_DIR = os.path.join(cwd, "..")
print(f"Current working directory: {cwd}")
if not os.path.exists(TS_DIR):
    pytest.skip("Time Series Analytics directory not found. Skipping tests.")

def build_docker_image():
    """Build the Docker image for the Time Series Analytics service."""
    print("Building Docker image...")
    os.chdir(os.path.join(TS_DIR, "docker"))
    command = ["docker", "compose", "build", "--no-cache"]
    output = utils.run_command(command)
    print(output.stdout.strip())

def docker_compose_up():
    """Start the Docker containers using docker-compose."""
    print("Starting Docker containers...")
    os.chdir(os.path.join(TS_DIR, "docker"))
    command = ["docker", "compose", "up", "-d"]
    output = utils.run_command(command)
    print(output.stdout.strip())

def docker_compose_down():
    """Stop and remove the Docker containers."""
    print("Stopping Docker containers...")
    os.chdir(os.path.join(TS_DIR, "docker"))
    command = ["docker", "compose", "down", "-v"]
    output = utils.run_command(command)
    print(output.stdout.strip())

def docker_ps():
    """List the running Docker containers."""
    print("Listing running Docker containers...")
    command = ["docker", "ps"]
    output = utils.run_command(command)
    print(output.stdout.strip())

@pytest.fixture(scope="function", autouse=True)
def setup_docker_environment():
    """Setup Docker environment before running tests."""
    print("Setting up Docker environment...")
    docker_compose_down()
    # Build the Docker image only once at the start of the session
    if not getattr(setup_docker_environment, "_image_built", False):
        build_docker_image()
        setattr(setup_docker_environment, "_image_built", True)
    docker_compose_up()
    print("Started container")
    time.sleep(30)  # Wait for containers to start
    print("yielding control to tests...")
    yield
    # Stop docker containers
    print("Bringing down Docker container...")
    docker_compose_down()
    time.sleep(5)

def test_timeseries_microservice_started_successfully():
    """
    Test to check if the required Docker container is running.
    """
    command = ["docker", "ps", "--filter", f"name={CONTAINER_NAME}", "--format", "{{.Names}}"]
    try:
        output = utils.run_command(command)
        assert CONTAINER_NAME in output.stdout.strip()
    except Exception as e:
        pytest.fail(f"Failed to check if Time Series Analytics Microservice is running: {e}")

# Test to check if Time Series Analytics Microservice is built and running
def test_test_timeseries_microservice_start():
    """
    Test to check if 'Time Series Analytics Microservice Initialized Successfully. Ready to Receive the Data...' 
    is present in the Time Series Analytics Microservice container logs.
    """
    try:
        command = ["docker", "logs", CONTAINER_NAME]
        time.sleep(45)  # Wait for the container to initialize
        output = subprocess.run(command, check=False, capture_output=True, text=True)
        print(output.stdout)
        output = output.stdout + output.stderr
        assert "Kapacitor Initialized Successfully. Ready to Receive the Data..." in output
    except Exception as e:
        pytest.fail(f"Failed to check Time Series Analytics Microservice initialization: {e}")

## REST API Tests

def test_health_check():
    # Get health check /health endpoint
    print("Testing health check endpoint in utils...")
    utils.health_check(TS_DOCKER_PORT)

# Post the OPC UA alerts /opcua_alerts endpoint
def test_opcua_alerts():
    """
    Test the OPC UA alerts endpoint of the Time Series Analytics service.
    """
    utils.opcua_alerts(TS_DOCKER_PORT)

# Post valid input data to the /input endpoint
def test_input_endpoint():
    """
    Test the input endpoint of the Time Series Analytics service.
    """
    utils.input_endpoint(TS_DOCKER_PORT)

# Post invalid input data to the /input endpoint
def test_input_endpoint_invalid_data():
    """
    Test the input endpoint of the Time Series Analytics service.
    """
    utils.input_endpoint_invalid_data(TS_DOCKER_PORT)
    utils.input_endpoint_no_data(TS_DOCKER_PORT)

def test_get_config_endpoint():
    """
    Test the config endpoint of the Time Series Analytics service.
    """
    utils.get_config_endpoint(TS_DOCKER_PORT)

# Post config data to the /config endpoint
def test_post_config_endpoint():
    """
    Test the config endpoint of the Time Series Analytics service.
    """
    cmd = ["docker", "logs", CONTAINER_NAME]
    utils.post_config_endpoint(TS_DOCKER_PORT, cmd)

# Test concurrent API requests
def test_concurrent_api_requests():
    """
    Test concurrent API requests to the Time Series Analytics service.
    """
    utils.concurrent_api_requests(TS_DOCKER_PORT)

# Post config data to the /config endpoint
def test_post_invalid_config_endpoint():
    """
    Test the config endpoint of the Time Series Analytics service.
    """
    cmd = ["docker", "logs", CONTAINER_NAME]
    utils.post_invalid_config_endpoint(TS_DOCKER_PORT, cmd)

def test_temperature_input():
    """
    Test to check if the temperature simulator script runs without error.
    """
    os.chdir(TS_DIR)
    command = ["pip3", "install", "-r", "simulator/requirements.txt"]
    utils.run_command(command)
    command = ["timeout", "20", "python3", "simulator/temperature_input.py", "--port", str(TS_DOCKER_PORT)]
    try:
        print("Starting temperature simulator...")
        # Run the simulator for 20 seconds, then terminate
        subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        time.sleep(10)
        print("Temperature simulator started successfully.")
        command = ["docker", "logs", CONTAINER_NAME]
        time.sleep(10)  # Wait for the simulator to produce output
        print("Checking Time Series Analytics Microservice logs for temperature data...")
        output = subprocess.run(command, check=False, capture_output=True, text=True)
        output = output.stdout + output.stderr
        assert "is outside the range 20-25." in output
    except RuntimeError as e:
        pytest.fail(f"Time Series Analytics Microservice failed for the temperature input data: {e}")

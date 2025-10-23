import pytest


# Mock device list
mock_device_list = ["CPU", "GPU"]

# Mock metadata for each device
mock_device_properties_map = {
    "CPU": {
        "FULL_DEVICE_NAME": "Intel(R) Core(TM) Ultra 7 165HL",
        "DEVICE_TYPE": "Type.INTEGRATED",
        "DEVICE_ARCHITECTURE": "intel64",
        "NUM_STREAMS": 1,
        "PERFORMANCE_HINT": "PerformanceMode.LATENCY"
    },
    "GPU": {
        "FULL_DEVICE_NAME": "Intel(R) Arc(TM) Graphics (iGPU)",
        "DEVICE_TYPE": "Type.INTEGRATED",
        "DEVICE_ARCHITECTURE": "GPU: vendor=0x8086 arch=v12.71.4",
        "GPU_EXECUTION_UNITS_COUNT": 128,
        "PERFORMANCE_HINT": "PerformanceMode.LATENCY"
    }
}

def test_get_devices(test_client, mocker, skip_if_not_openvino):
    """
    Tests the `/devices` endpoint to ensure it returns a list of available devices.
    This test mocks the `OpenVINOBackend.get_available_devices` method to return a predefined device list,
    sends a GET request to the `/devices` endpoint, and verifies the response.
    Args:
        test_client: A test client instance for making HTTP requests to the application.
        mocker: A pytest-mock fixture for patching objects during the test.
        skip_if_not_openvino: A fixture to skip the test if OpenVINO is not available.
    Asserts:
        - The response status code is 200.
        - The response JSON contains a "devices" key.
        - The value of "devices" is a list.
    """

    mocker.patch('app.openvino_backend.OpenVINOBackend.get_available_devices', return_value=mock_device_list)
    response = test_client.get("/devices")
    assert response.status_code == 200
    assert "devices" in response.json()
    assert isinstance(response.json()["devices"], list)


@pytest.mark.parametrize("device", list(mock_device_properties_map.keys()))
def test_get_device_properties(test_client, mocker, device, skip_if_not_openvino):
    """
    Tests the retrieval of device properties from the OpenVINO backend API endpoint.
    This test mocks the OpenVINO backend's methods to provide a controlled list of devices and their properties.
    It then sends a GET request to the `/devices/{device}` endpoint and verifies that the response contains
    the expected device properties.
    Args:
        test_client: The test client fixture used to make HTTP requests to the API.
        mocker: The pytest-mock fixture used to patch methods in the OpenVINO backend.
        device (str): The device identifier to query properties for.
        skip_if_not_openvino: Fixture to skip the test if OpenVINO is not available.
    Asserts:
        - The response status code is 200.
        - The response JSON contains the keys "FULL_DEVICE_NAME", "DEVICE_TYPE", and "PERFORMANCE_HINT".
    """

    expected_properties = mock_device_properties_map[device]
    mocker.patch('app.openvino_backend.OpenVINOBackend.get_available_devices', return_value=mock_device_list)
    mocker.patch('app.openvino_backend.OpenVINOBackend.get_device_property', return_value=expected_properties)

    response = test_client.get(f"/devices/{device}")
    assert response.status_code == 200
    data = response.json()

    # Check a few key fields
    assert "FULL_DEVICE_NAME" in data
    assert "DEVICE_TYPE" in data
    assert "PERFORMANCE_HINT" in data


def test_invalid_device(test_client, mocker, skip_if_not_openvino):
    """
    Tests the API endpoint for handling requests to an invalid device.
    This test mocks the available devices and verifies that a GET request to a non-existent device
    returns a 404 status code and the appropriate error message.
    Args:
        test_client: The test client used to make HTTP requests to the API.
        mocker: The pytest-mock fixture used to patch methods or objects.
        skip_if_not_openvino: Fixture to skip the test if OpenVINO is not available.
    Asserts:
        - The response status code is 404.
        - The response JSON contains the correct error message indicating the device was not found and listing available devices.
    """

    invalid_device_id = "invalid_device"

    mocker.patch('app.openvino_backend.OpenVINOBackend.get_available_devices', return_value=mock_device_list)

    response = test_client.get(f"/devices/{invalid_device_id}")
    assert response.status_code == 404
    assert response.json() == {
        "detail": "Device invalid_device not found. Available devices: ['CPU', 'GPU']"
    }
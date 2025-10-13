from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from .openvino_backend import OpenVINOBackend
from http import HTTPStatus
from .logger import logger

router = APIRouter()

@router.get("/devices", tags=["Device API"], summary="Get available devices list")
async def get_devices():
    """
    Retrieves the list of available devices.

    Returns:
        dict: A dictionary containing the list of available devices under the key "devices".

    Raises:
        HTTPException: If an error occurs while retrieving the devices, an HTTP 500 error is raised with the exception details.
    """

    try:
        devices = OpenVINOBackend.get_available_devices()

        return {"devices": devices}

    except Exception as e:
        logger.exception("Error getting devices list.")
        raise HTTPException(status_code=HTTPStatus.INTERNAL_SERVER_ERROR, detail=str(e))


@router.get("/devices/{device}", tags=["Device API"], summary="Get device property")
async def get_device_info(device: str = ""):
    """
    Retrieves information about a specified device.

    Args:
        device (str): The name of the device to retrieve information for. Defaults to an empty string.

    Returns:
        JSONResponse: A JSON response containing the properties of the specified device.

    Raises:
        HTTPException: If the device is not found among available devices or if an error occurs while retrieving device properties.
    """

    try:
        available_devices = OpenVINOBackend.get_available_devices()

        if device not in available_devices:
            raise ValueError(f"Device {device} not found. Available devices: {available_devices}")
        device_props = OpenVINOBackend.get_device_property(device)

        return JSONResponse(content=device_props)

    except ValueError as e:
        logger.exception("Device not found.")
        # Handle the exception specifically for device not found
        raise HTTPException(status_code=HTTPStatus.NOT_FOUND, detail=str(e))

    except Exception as e:
        logger.exception("Error getting properties for device.")
        raise HTTPException(status_code=HTTPStatus.INTERNAL_SERVER_ERROR, detail=str(e))

from typing import List
from fastapi import APIRouter

import api.api_schemas as schemas
from device import DeviceDiscovery

router = APIRouter()


@router.get("", operation_id="get_devices", response_model=List[schemas.Device])
def get_devices():
    device_list = DeviceDiscovery().list_devices()
    return [
        schemas.Device(
            device_name=device.device_name,
            full_device_name=device.full_device_name,
            device_type=device.device_type,
            device_family=device.device_family,
            gpu_id=getattr(device, "gpu_id", None),
        )
        for device in device_list
    ]

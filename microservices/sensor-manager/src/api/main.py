# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from src.api.routes import health, sensors
from src.core.camera_manager import CameraManager
from src.core.config import Settings
from src.core.onvif import ONVIFCameraDiscovery
from src.core.usb import USBCameraDiscovery

API_PREFIX = "/api/v1"

settings = Settings.from_env()
# force=True: onvif-zeep calls logging.basicConfig() on import.
logging.basicConfig(
    level=settings.log_level,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    force=True,
)
# zeep DEBUG output contains full SOAP envelopes, including WS-Security tokens.
logging.getLogger("zeep").setLevel(logging.WARNING)


@asynccontextmanager
async def lifespan(app: FastAPI):
    onvif_discovery = ONVIFCameraDiscovery(interval_s=settings.onvif_discovery_interval_s)
    if settings.onvif_discovery_enabled:
        onvif_discovery.start()
    app.state.camera_manager = CameraManager(USBCameraDiscovery(), onvif_discovery)
    try:
        yield
    finally:
        onvif_discovery.stop()


app = FastAPI(
    title="Sensor Manager API",
    description="Discovery and description of USB and ONVIF network cameras.",
    version="1.0.0",
    lifespan=lifespan,
)
app.include_router(health.router, prefix=API_PREFIX, tags=["health"])
app.include_router(sensors.router, prefix=f"{API_PREFIX}/sensors", tags=["sensors"])

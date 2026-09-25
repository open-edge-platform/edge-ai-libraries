# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional, Union


class InternalCameraType(str, Enum):
    USB = "USB"
    NETWORK = "NETWORK"


@dataclass
class InternalV4L2FormatSize:
    width: int
    height: int
    fps_list: List[float]


@dataclass
class InternalV4L2Format:
    fourcc: str
    sizes: List[InternalV4L2FormatSize]


@dataclass
class InternalV4L2BestCapture:
    fourcc: str
    width: int
    height: int
    fps: float


@dataclass
class InternalUSBCameraDetails:
    device_path: str
    best_capture: Optional[InternalV4L2BestCapture] = None


@dataclass
class InternalCameraProfileInfo:
    name: str
    rtsp_url: Optional[str] = None
    resolution: Optional[str] = None
    encoding: Optional[str] = None
    framerate: Optional[int] = None
    bitrate: Optional[int] = None


@dataclass
class InternalNetworkCameraDetails:
    ip: str
    port: int
    profiles: List[InternalCameraProfileInfo] = field(default_factory=list)
    best_profile: Optional[InternalCameraProfileInfo] = None


@dataclass
class InternalCamera:
    device_id: str
    device_name: str
    device_type: InternalCameraType
    details: Union[InternalUSBCameraDetails, InternalNetworkCameraDetails]

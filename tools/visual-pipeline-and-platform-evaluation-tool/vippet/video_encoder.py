import logging
import os
import re
import threading
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from explore import GstInspector
from utils import slugify_text

# Constants for encoder device types
ENCODER_DEVICE_CPU = "CPU"
ENCODER_DEVICE_GPU = "GPU"

# Default live stream server configuration
DEFAULT_LIVE_STREAM_SERVER_HOST = "mediamtx"
DEFAULT_LIVE_STREAM_SERVER_PORT = "8554"

# Read live stream server config from environment variables
LIVE_STREAM_SERVER_HOST: str = os.environ.get(
    "LIVE_STREAM_SERVER_HOST", DEFAULT_LIVE_STREAM_SERVER_HOST
)
LIVE_STREAM_SERVER_PORT: str = os.environ.get(
    "LIVE_STREAM_SERVER_PORT", DEFAULT_LIVE_STREAM_SERVER_PORT
)

# Standard h264 encoder configurations for file output.
# Maps device type to list of (search_element, full_element_string) tuples.
# The first available encoder in the list is used.
#
# Bitrate units differ across encoders:
#   - VAAPI encoders (vah264lpenc, vah264enc): bitrate in kbps
#   - openh264enc: bitrate in bps
ENCODER_CONFIG: Dict[str, List[Tuple[str, str]]] = {
    ENCODER_DEVICE_GPU: [
        ("vah264lpenc", "vah264lpenc"),  # bitrate in kbps (default)
        ("vah264enc", "vah264enc"),  # bitrate in kbps (default)
    ],
    ENCODER_DEVICE_CPU: [
        (
            "openh264enc",
            "openh264enc bitrate=16000000 complexity=low",
        ),  # bitrate in bps (16 Mbps)
    ],
}

# Low-latency h264 encoder configurations for live-streaming output.
# Uses settings optimized for RTSP streaming to media server.
#
# Bitrate units differ across encoders:
#   - VAAPI encoders (vah264lpenc, vah264enc): bitrate in kbps
#   - openh264enc: bitrate in bps
STREAMING_ENCODER_CONFIG: Dict[str, List[Tuple[str, str]]] = {
    ENCODER_DEVICE_GPU: [
        (
            "vah264lpenc",
            "vah264lpenc bitrate=16000 target-usage=4 max-qp=30",  # 16000 kbps = 16 Mbps
        ),
        (
            "vah264enc",
            "vah264enc bitrate=16000 target-usage=4 max-qp=30",  # 16000 kbps = 16 Mbps
        ),
    ],
    ENCODER_DEVICE_CPU: [
        (
            "openh264enc",
            "openh264enc bitrate=16000000 complexity=low usage-type=camera slice-mode=auto gop-size=25",  # 16000000 bps = 16 Mbps
        ),
    ],
}

logger = logging.getLogger("video_encoder")


class VideoEncoder:
    """
    Thread-safe singleton video encoder manager for GStreamer pipelines.

    Implements singleton pattern using __new__ with double-checked locking.
    Create instances with VideoEncoder() to get the shared singleton instance.

    This class handles video encoding operations including:
    - Selecting appropriate h264 encoders based on device capabilities
    - Replacing fakesink elements with video output or live-streaming
    - Managing encoder configurations for CPU and GPU devices
    """

    _instance: Optional["VideoEncoder"] = None
    _lock = threading.Lock()

    def __new__(cls) -> "VideoEncoder":
        if cls._instance is None:
            with cls._lock:
                # Double-checked locking
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        """
        Initialize VideoEncoder with GStreamer inspector.
        Protected against multiple initialization.
        """
        # Protect against multiple initialization
        if hasattr(self, "_initialized"):
            return
        self._initialized = True

        self.logger = logging.getLogger("VideoEncoder")
        self.gst_inspector = GstInspector()

        # Count standalone fakesink elements (excludes embedded cases like video-sink=fakesink).
        # Pattern matches 'fakesink' when preceded by start-of-string/whitespace/'!', extending to next '!' or end-of-string.
        fakesink_pattern = r"(?:(?<=^)|(?<=[\s!]))fakesink[^!]*(?=!)|(?:(?<=^)|(?<=[\s!]))fakesink[^!]*$"
        self.re_pattern = re.compile(fakesink_pattern)

    def create_video_output_subpipeline(
        self,
        output_dir: str,
        encoder_device: str,
    ) -> str:
        """
        Create a sub-pipeline string for replacing a single fakesink with video encoder and file sink.

        This method generates a GStreamer sub-pipeline containing all required elements
        (h264 encoder, parser, muxer, and filesink) to replace one fakesink element.

        The output file is always named "main_output.mp4" and placed in the given output directory.

        Note: This method is only used for file output (output_mode=file), which does not
        support looping. Standard encoders are always used.

        Args:
            output_dir: Directory path where the main output file will be placed.
            encoder_device: Target encoder device. Must be one of the module constants:
                - ENCODER_DEVICE_CPU ("CPU"): Use CPU-based encoder
                - ENCODER_DEVICE_GPU ("GPU"): Use GPU-based encoder (VAAPI)

        Returns:
            Sub-pipeline string for replacing fakesink.

        Raises:
            ValueError: If encoder_device is invalid or no suitable encoder is found
        """
        # Select the best available h264 encoder element based on device type and
        # installed GStreamer plugins (e.g., vah264enc for GPU, openh264enc for CPU)
        encoder_element = self._select_element(encoder_device, streaming=False)

        if encoder_element is None:
            self.logger.error(
                f"Failed to select encoder element for encoder_device: {encoder_device}"
            )
            raise ValueError(
                f"No suitable encoder found for encoder_device: {encoder_device}"
            )

        # Fixed output filename placed in the pipeline output directory
        output_path = str(Path(output_dir) / "main_output.mp4")

        # Create sub-pipeline string with all required elements for replacing fakesink
        video_output_subpipeline = (
            f"{encoder_element} ! h264parse ! mp4mux ! filesink location={output_path}"
        )

        self.logger.debug(
            f"Created video output sub-pipeline: {video_output_subpipeline}"
        )

        return video_output_subpipeline

    def create_live_stream_output_subpipeline(
        self,
        pipeline_id: str,
        encoder_device: str,
        job_id: str,
    ) -> Tuple[str, str]:
        """
        Create a sub-pipeline string for replacing a single fakesink with live-streaming output.

        This method generates a GStreamer sub-pipeline containing all required elements
        (h264 encoder, parser, and RTSP client sink) to replace one fakesink element.

        This method is used when output_mode is LIVE_STREAM. It uses low-latency
        streaming h264 encoders optimized for RTSP streaming to media server.

        Args:
            pipeline_id: Pipeline ID used to generate unique stream name
            encoder_device: Target encoder device. Must be one of the module constants:
                - ENCODER_DEVICE_CPU ("CPU"): Use CPU-based encoder
                - ENCODER_DEVICE_GPU ("GPU"): Use GPU-based encoder (VAAPI)
            job_id: Unique job identifier used to generate unique stream name

        Returns:
            Tuple of (sub-pipeline string, live stream URL)

        Raises:
            ValueError: If encoder_device is invalid or no suitable encoder is found
        """
        # Generate stream name from pipeline ID and job_id
        stream_name = f"stream-{pipeline_id}-{job_id}"
        stream_name = slugify_text(stream_name)

        # Build live stream URL
        stream_url = (
            f"rtsp://{LIVE_STREAM_SERVER_HOST}:{LIVE_STREAM_SERVER_PORT}/{stream_name}"
        )

        # Select the best available h264 streaming encoder element based on device type
        # and installed GStreamer plugins (e.g., vah264enc for GPU, openh264enc for CPU)
        encoder_element = self._select_element(encoder_device, streaming=True)

        if encoder_element is None:
            self.logger.error(
                f"Failed to select encoder element for encoder_device: {encoder_device}"
            )
            raise ValueError(
                f"No suitable encoder found for encoder_device: {encoder_device}"
            )

        # Create sub-pipeline string with all required elements for replacing fakesink
        live_stream_output_subpipeline = f"{encoder_element} ! h264parse ! rtspclientsink protocols=tcp location={stream_url}"

        self.logger.debug(
            f"Created live stream output sub-pipeline: {live_stream_output_subpipeline}"
        )
        return live_stream_output_subpipeline, stream_url

    def _select_element(
        self,
        encoder_device: str,
        streaming: bool = False,
    ) -> Optional[str]:
        """
        Select an appropriate h264 encoder element from available GStreamer elements.

        Uses ENCODER_CONFIG or STREAMING_ENCODER_CONFIG based on the streaming flag.

        Args:
            encoder_device: Target encoder device. Must be one of the module constants:
                - ENCODER_DEVICE_CPU ("CPU"): Use CPU-based encoder
                - ENCODER_DEVICE_GPU ("GPU"): Use GPU-based encoder (VAAPI)
            streaming: If True, use low-latency streaming encoder config.
                If False, use standard file output encoder config.

        Returns:
            Selected encoder element string with properties, or None if not found

        Raises:
            ValueError: If encoder_device is not a valid constant value
        """
        # Validate encoder_device
        valid_devices = {ENCODER_DEVICE_CPU, ENCODER_DEVICE_GPU}
        if encoder_device not in valid_devices:
            raise ValueError(
                f"Invalid encoder_device: {encoder_device}. "
                f"Must be one of: {', '.join(valid_devices)}"
            )

        config = STREAMING_ENCODER_CONFIG if streaming else ENCODER_CONFIG
        pairs = config.get(encoder_device, [])

        if not pairs:
            self.logger.warning(
                f"No encoder pairs found for encoder_device: {encoder_device}"
            )
            return None

        for search, result in pairs:
            for element in self.gst_inspector.elements:
                if element[1] == search:
                    self.logger.debug(f"Selected encoder element: {result}")
                    return result

        self.logger.warning(
            f"No matching encoder element found for encoder_device: {encoder_device}"
        )

        return None

import logging
from pathlib import Path
import re
import os
import threading
from typing import Dict, List, Optional, Tuple

from explore import GstInspector
from utils import generate_unique_filename
from videos import VideosManager, OUTPUT_VIDEO_DIR

# Constants for encoder device types
ENCODER_DEVICE_CPU = "CPU"
ENCODER_DEVICE_GPU = "GPU"

# Default codec for encoding
DEFAULT_CODEC = "h264"

# Placeholder for vaapi_suffix to be replaced at runtime
VAAPI_SUFFIX_PLACEHOLDER = "{vaapi_suffix}"

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

logger = logging.getLogger("video_encoder")


class VideoEncoder:
    """
    Thread-safe singleton video encoder manager for GStreamer pipelines.

    Implements singleton pattern using __new__ with double-checked locking.
    Create instances with VideoEncoder() to get the shared singleton instance.

    This class handles video encoding operations including:
    - Selecting appropriate encoders based on device capabilities
    - Replacing fakesink elements with video output or live-streaming
    - Managing encoder configurations for different codecs
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
        Initialize VideoEncoder with GStreamer inspector and encoder configurations.
        Protected against multiple initialization.
        """
        # Protect against multiple initialization
        if hasattr(self, "_initialized"):
            return
        self._initialized = True

        self.logger = logging.getLogger("VideoEncoder")
        self.gst_inspector = GstInspector()
        self.videos_manager = VideosManager()

        # Count standalone fakesink elements (excludes embedded cases like video-sink=fakesink).
        # Pattern matches 'fakesink' when preceded by start-of-string/whitespace/'!', extending to next '!' or end-of-string.
        fakesink_pattern = r"(?:(?<=^)|(?<=[\s!]))fakesink[^!]*(?=!)|(?:(?<=^)|(?<=[\s!]))fakesink[^!]*$"
        self.re_pattern = re.compile(fakesink_pattern)

        # Define encoder configurations for different codecs
        # Standard encoders for file output (no looping support needed)
        self.encoder_configs = {
            "h264": {
                ENCODER_DEVICE_GPU: [
                    ("vah264lpenc", "vah264lpenc"),
                    ("vah264enc", "vah264enc"),
                ],
                ENCODER_DEVICE_CPU: [
                    ("x264enc", "x264enc bitrate=16000 speed-preset=superfast"),
                ],
            },
            "h265": {
                ENCODER_DEVICE_GPU: [
                    ("vah265lpenc", "vah265lpenc"),
                    ("vah265enc", "vah265enc"),
                ],
                ENCODER_DEVICE_CPU: [
                    ("x265enc", "x265enc bitrate=16000 speed-preset=superfast"),
                ],
            },
        }

        # Low-latency encoders for live-streaming (used only for live_stream output mode)
        self.streaming_encoder_configs = {
            "h264": {
                ENCODER_DEVICE_GPU: [
                    # vah264lpenc doesn't support tune property
                    (
                        "vah264lpenc",
                        "vah264lpenc bitrate=16000 target-usage=4 max-qp=30",
                    ),
                    # vah264enc doesn't support tune property
                    ("vah264enc", "vah264enc bitrate=16000 target-usage=4 max-qp=30"),
                ],
                ENCODER_DEVICE_CPU: [
                    (
                        "x264enc",
                        "x264enc tune=zerolatency bitrate=16000 speed-preset=superfast key-int-max=25 bframes=0",
                    ),
                ],
            },
            "h265": {
                ENCODER_DEVICE_GPU: [
                    # vah265lpenc doesn't support tune property
                    (
                        "vah265lpenc",
                        "vah265lpenc bitrate=16000 target-usage=4 max-qp=30",
                    ),
                    # vah265enc doesn't support tune property
                    ("vah265enc", "vah265enc bitrate=16000 target-usage=4 max-qp=30"),
                ],
                ENCODER_DEVICE_CPU: [
                    (
                        "x265enc",
                        "x265enc tune=zerolatency bitrate=16000 speed-preset=superfast key-int-max=25",
                    ),
                ],
            },
        }

    def select_element(
        self,
        field_dict: Dict[str, List[Tuple[str, str]]],
        encoder_device: str,
    ) -> Optional[str]:
        """
        Select an appropriate encoder element from available GStreamer elements.

        Args:
            field_dict: Dictionary mapping device types to lists of (search, result) tuples
            encoder_device: Target encoder device. Must be one of the module constants:
                - ENCODER_DEVICE_CPU ("CPU"): Use CPU-based encoder
                - ENCODER_DEVICE_GPU ("GPU"): Use GPU-based encoder (VAAPI)

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

        pairs = field_dict.get(encoder_device, [])

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

    def _detect_codec_from_input(self, input_video_filenames: list[str]) -> str:
        """
        Detect codec from input video files.

        Args:
            input_video_filenames: List of input video filenames

        Returns:
            Detected codec name, defaults to "h264" if it cannot be determined
        """
        if not input_video_filenames:
            self.logger.warning(
                f"No input video filenames provided, defaulting to {DEFAULT_CODEC}"
            )
            return DEFAULT_CODEC

        # Detect codec from the first input video
        video = self.videos_manager.get_video(input_video_filenames[0])
        detected_codec = video.codec if video and video.codec else DEFAULT_CODEC

        self.logger.debug(
            f"Detected codec: {detected_codec} from {input_video_filenames[0]}"
        )
        return detected_codec

    def _validate_codec(self, codec: str) -> None:
        """
        Validate that codec is supported.

        Args:
            codec: Codec name to validate

        Raises:
            ValueError: If codec is not supported
        """
        if codec not in self.encoder_configs:
            supported = ", ".join(self.encoder_configs.keys())
            raise ValueError(f"Unsupported codec: {codec}. Supported: {supported}")

    def create_video_output_subpipeline(
        self,
        pipeline_id: str,
        encoder_device: str,
        input_video_filenames: list[str],
    ) -> Tuple[str, str]:
        """
        Create a sub-pipeline string for replacing a single fakesink with video encoder and file sink.

        This method generates a GStreamer sub-pipeline containing all required elements
        (encoder, parser, muxer, and filesink) to replace one fakesink element.

        Note: This method is only used for file output (output_mode=file), which does not
        support looping. Standard encoders are always used.

        Args:
            pipeline_id: Pipeline ID used to generate unique output filename
            encoder_device: Target encoder device. Must be one of the module constants:
                - ENCODER_DEVICE_CPU ("CPU"): Use CPU-based encoder
                - ENCODER_DEVICE_GPU ("GPU"): Use GPU-based encoder (VAAPI)
            input_video_filenames: List of input video filenames to detect codec

        Returns:
            Tuple of (sub-pipeline string, output file path)

        Raises:
            ValueError: If codec is not supported, encoder_device is invalid,
                or no suitable encoder is found
        """
        # Detect codec from input video files (h264, h265, etc.)
        codec = self._detect_codec_from_input(input_video_filenames)
        self._validate_codec(codec)

        # Get encoder configuration for the detected codec (GPU/CPU variants) for file output (no looping support)
        encoder_config = self.encoder_configs[codec]

        # Select the best available encoder element based on device type and
        # installed GStreamer plugins (e.g., vah264enc for GPU, x264enc for CPU)
        encoder_element = self.select_element(
            encoder_config,
            encoder_device,
        )

        if encoder_element is None:
            self.logger.error(
                f"Failed to select encoder element for codec: {codec} and encoder_device: {encoder_device}"
            )
            raise ValueError(
                f"No suitable encoder found for codec: {codec} and encoder_device: {encoder_device}"
            )

        # Generate unique output path
        output_filename = generate_unique_filename(f"pipeline_output_{pipeline_id}.mp4")
        output_path = str(Path(OUTPUT_VIDEO_DIR) / output_filename)

        # Create sub-pipeline string with all required elements for replacing fakesink
        video_output_subpipeline = f"{encoder_element} ! {codec}parse ! mp4mux ! filesink location={output_path}"

        self.logger.debug(
            f"Created video output sub-pipeline: {video_output_subpipeline} (codec: {codec})"
        )

        return video_output_subpipeline, output_path

    def create_live_stream_output_subpipeline(
        self,
        pipeline_id: str,
        encoder_device: str,
        input_video_filenames: list[str],
    ) -> Tuple[str, str]:
        """
        Create a sub-pipeline string for replacing a single fakesink with live-streaming output.

        This method generates a GStreamer sub-pipeline containing all required elements
        (encoder, parser, and RTSP client sink) to replace one fakesink element.

        This method is used when output_mode is LIVE_STREAM. It uses low-latency
        streaming encoders optimized for RTSP streaming to media server.

        Args:
            pipeline_id: Pipeline ID used to generate unique stream name
            encoder_device: Target encoder device. Must be one of the module constants:
                - ENCODER_DEVICE_CPU ("CPU"): Use CPU-based encoder
                - ENCODER_DEVICE_GPU ("GPU"): Use GPU-based encoder (VAAPI)
            input_video_filenames: List of input video filenames to detect codec

        Returns:
            Tuple of (sub-pipeline string, live stream URL)

        Raises:
            ValueError: If codec is not supported, encoder_device is invalid,
                or no suitable encoder is found
        """
        # Generate stream name from pipeline ID
        stream_name = f"stream_{pipeline_id}"

        # Build live stream URL
        stream_url = (
            f"rtsp://{LIVE_STREAM_SERVER_HOST}:{LIVE_STREAM_SERVER_PORT}/{stream_name}"
        )

        # Detect codec from input video files (h264, h265, etc.)
        codec = self._detect_codec_from_input(input_video_filenames)
        self._validate_codec(codec)

        # Select streaming encoder configuration
        encoder_config = self.streaming_encoder_configs.get(codec, {})
        if not encoder_config:
            self.logger.warning(
                f"No streaming encoder config for codec {codec}, falling back to standard encoder"
            )
            encoder_config = self.encoder_configs[codec]

        # Select the best available encoder element based on device type and
        # installed GStreamer plugins (e.g., vah264enc for GPU, x264enc for CPU)
        encoder_element = self.select_element(encoder_config, encoder_device)

        if encoder_element is None:
            self.logger.error(
                f"Failed to select encoder element for codec: {codec} and encoder_device: {encoder_device}"
            )
            raise ValueError(
                f"No suitable encoder found for codec: {codec} and encoder_device: {encoder_device}"
            )

        # Create sub-pipeline string with all required elements for replacing fakesink
        live_stream_output_subpipeline = (
            f"{encoder_element} ! {codec}parse ! "
            f"rtspclientsink protocols=tcp location={stream_url}"
        )

        self.logger.debug(
            f"Created live stream output sub-pipeline: {live_stream_output_subpipeline} (codec: {codec})"
        )
        return live_stream_output_subpipeline, stream_url

import logging
from pathlib import Path
import sys
from typing import Dict, List, Optional, Tuple

from explore import GstInspector
from utils import generate_unique_filename
from videos import get_videos_manager, OUTPUT_VIDEO_DIR

# Constants for encoder device types
ENCODER_DEVICE_CPU = "CPU"
ENCODER_DEVICE_GPU = "GPU"

# Default codec for encoding
DEFAULT_CODEC = "h264"

# Placeholder for vaapi_suffix to be replaced at runtime
VAAPI_SUFFIX_PLACEHOLDER = "{vaapi_suffix}"


logger = logging.getLogger("video_encoder")
videos_manager = get_videos_manager()

# Singleton instance for VideoEncoder
_video_encoder_instance: Optional["VideoEncoder"] = None


def get_video_encoder() -> "VideoEncoder":
    """
    Returns the singleton instance of VideoEncoder.
    If it cannot be created, logs an error and exits the application.
    """
    global _video_encoder_instance
    if _video_encoder_instance is None:
        try:
            _video_encoder_instance = VideoEncoder()
        except Exception as e:
            logger.error(f"Failed to initialize VideoEncoder: {e}")
            sys.exit(1)
    return _video_encoder_instance


class VideoEncoder:
    """
    Video encoder manager for GStreamer pipelines.

    This class handles video encoding operations including:
    - Selecting appropriate encoders based on device capabilities
    - Replacing fakesink elements with video output
    - Managing encoder configurations for different codecs
    """

    def __init__(self):
        """Initialize VideoEncoder with GStreamer inspector and encoder configurations."""
        self.logger = logging.getLogger("VideoEncoder")
        self.gst_inspector = GstInspector()

        # Define encoder configurations for different codecs
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
            Detected codec name, defaults to "h264" if cannot be determined
        """
        if not input_video_filenames:
            self.logger.warning(
                f"No input video filenames provided, defaulting to {DEFAULT_CODEC}"
            )
            return DEFAULT_CODEC

        # Detect codec from the first input video
        video = videos_manager.get_video(input_video_filenames[0])
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

    def replace_fakesink_with_video_output(
        self,
        pipeline_id: str,
        pipeline_str: str,
        encoder_device: str,
        input_video_filenames: list[str],
    ) -> Tuple[str, List[str]]:
        """
        Replace all fakesink instances in pipeline string with video encoder and file sink.

        Args:
            pipeline_id: Pipeline ID used to generate unique output filenames
            pipeline_str: GStreamer pipeline string containing fakesink(s)
            encoder_device: Target encoder device. Must be one of the module constants:
                - ENCODER_DEVICE_CPU ("CPU"): Use CPU-based encoder
                - ENCODER_DEVICE_GPU ("GPU"): Use GPU-based encoder (VAAPI)
            input_video_filenames: List of input video filenames to detect codec

        Returns:
            Tuple of (modified pipeline string, list of output paths)

        Raises:
            ValueError: If codec is not supported, encoder_device is invalid,
                or no suitable encoder is found
        """
        # Detect codec from input video files (h264, h265, etc.)
        codec = self._detect_codec_from_input(input_video_filenames)
        self._validate_codec(codec)

        # Get encoder configuration for the detected codec (GPU/CPU variants)
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

        # Count fakesink instances
        fakesink_count = pipeline_str.count("fakesink")

        if fakesink_count == 0:
            self.logger.warning("No fakesink found in pipeline string")
            return pipeline_str, []

        output_paths = []
        result = pipeline_str

        # Replace each fakesink with unique output path
        for i in range(fakesink_count):
            # Generate unique output path for each fakesink
            output_filename = generate_unique_filename(
                f"pipeline_output_{pipeline_id}.mp4"
            )
            output_path = str(Path(OUTPUT_VIDEO_DIR) / output_filename)
            output_paths.append(output_path)

            # Replace first occurrence of fakesink
            video_output_str = f"{encoder_element} ! {codec}parse ! mp4mux ! filesink location={output_path}"
            result = result.replace("fakesink", video_output_str, 1)

        self.logger.info(
            f"Replaced {fakesink_count} fakesink(s) with video output(s): {output_paths} using codec: {codec}"
        )
        return result, output_paths

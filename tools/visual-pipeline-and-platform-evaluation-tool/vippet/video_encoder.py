import logging
from pathlib import Path
import sys
from typing import Dict, List, Optional, Tuple

from explore import GstInspector
from api.api_schemas import EncoderDeviceConfig
from utils import generate_unique_filename
from videos import get_videos_manager, OUTPUT_VIDEO_DIR

# Keys for device selection
GPU_0 = "GPU_0"
GPU_N = "GPU_N"
OTHER = "OTHER"

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
                GPU_0: [
                    ("vah264lpenc", "vah264lpenc"),
                    ("vah264enc", "vah264enc"),
                ],
                GPU_N: [
                    (
                        f"varenderD{VAAPI_SUFFIX_PLACEHOLDER}h264lpenc",
                        f"varenderD{VAAPI_SUFFIX_PLACEHOLDER}h264lpenc",
                    ),
                    (
                        f"varenderD{VAAPI_SUFFIX_PLACEHOLDER}h264enc",
                        f"varenderD{VAAPI_SUFFIX_PLACEHOLDER}h264enc",
                    ),
                ],
                OTHER: [
                    ("x264enc", "x264enc bitrate=16000 speed-preset=superfast"),
                ],
            },
            "h265": {
                GPU_0: [
                    ("vah265lpenc", "vah265lpenc"),
                    ("vah265enc", "vah265enc"),
                ],
                GPU_N: [
                    (
                        f"varenderD{VAAPI_SUFFIX_PLACEHOLDER}h265lpenc",
                        f"varenderD{VAAPI_SUFFIX_PLACEHOLDER}h265lpenc",
                    ),
                    (
                        f"varenderD{VAAPI_SUFFIX_PLACEHOLDER}h265enc",
                        f"varenderD{VAAPI_SUFFIX_PLACEHOLDER}h265enc",
                    ),
                ],
                OTHER: [
                    ("x265enc", "x265enc bitrate=16000 speed-preset=superfast"),
                ],
            },
        }

    def select_gpu(self, device: str | None) -> Tuple[int, Optional[str]]:
        """
        Parse device name and determine GPU ID and VAAPI suffix.

        Args:
            device: Device name (e.g., "GPU", "GPU.0", "GPU.1", "CPU")

        Returns:
            Tuple of (gpu_id, vaapi_suffix)
            - gpu_id: 0 for first GPU, >0 for other GPUs, -1 for non-GPU
            - vaapi_suffix: VAAPI device suffix for multi-GPU systems
        """
        gpu_id = -1
        vaapi_suffix = None

        # Determine gpu_id and vaapi_suffix
        # If there is only one GPU, device name is just GPU
        # If there is more than one GPU, device names are like GPU.0, GPU.1, ...
        if device == "GPU":
            gpu_id = 0
        elif device is not None and device.startswith("GPU."):
            try:
                gpu_index = int(device.split(".")[1])
                if gpu_index == 0:
                    gpu_id = 0
                elif gpu_index > 0:
                    vaapi_suffix = str(128 + gpu_index)
                    gpu_id = gpu_index
            except (IndexError, ValueError):
                self.logger.warning(f"Failed to parse GPU index from device: {device}")
                gpu_id = -1
        else:
            gpu_id = -1

        return gpu_id, vaapi_suffix

    def select_element(
        self,
        field_dict: Dict[str, List[Tuple[str, str]]],
        encoder_device: EncoderDeviceConfig,
        vaapi_suffix: Optional[str],
    ) -> Optional[str]:
        """
        Select an appropriate encoder element from available GStreamer elements.

        Args:
            field_dict: Dictionary mapping device types to lists of (search, result) tuples
            encoder_device: Encoder device configuration
            vaapi_suffix: VAAPI device suffix for multi-GPU systems

        Returns:
            Selected encoder element string with properties, or None if not found
        """
        key = OTHER
        if encoder_device.device_name == "GPU":
            if encoder_device.gpu_id == 0:
                key = GPU_0
            elif encoder_device.gpu_id is not None and encoder_device.gpu_id > 0:
                key = GPU_N

        pairs = field_dict.get(key, [])
        # Add OTHER pairs as fallback if key is not OTHER
        if key != OTHER:
            pairs = pairs + field_dict.get(OTHER, [])

        if not pairs:
            self.logger.warning(f"No encoder pairs found for key: {key}")
            return None

        for search, result in pairs:
            if search == "":  # to support optional parameters
                return result

            if VAAPI_SUFFIX_PLACEHOLDER in search or VAAPI_SUFFIX_PLACEHOLDER in result:
                suffix = vaapi_suffix if vaapi_suffix is not None else ""
                search = search.replace(VAAPI_SUFFIX_PLACEHOLDER, suffix)
                result = result.replace(VAAPI_SUFFIX_PLACEHOLDER, suffix)

            for element in self.gst_inspector.elements:
                if element[1] == search:
                    self.logger.debug(f"Selected encoder element: {result}")
                    return result

        self.logger.warning(
            f"No matching encoder element found for device: {encoder_device.device_name}"
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
        encoder_device: EncoderDeviceConfig,
        input_video_filenames: list[str],
    ) -> Tuple[str, List[str]]:
        """
        Replace all fakesink instances in pipeline string with video encoder and file sink.

        Args:
            pipeline_id: Pipeline ID used to generate unique output filenames
            pipeline_str: GStreamer pipeline string containing fakesink(s)
            encoder_device: Encoder device configuration
            input_video_filenames: List of input video filenames to detect codec

        Returns:
            Tuple of (modified pipeline string, list of output paths)

        Raises:
            ValueError: If codec is not supported or no suitable encoder is found
        """
        codec = self._detect_codec_from_input(input_video_filenames)
        self._validate_codec(codec)

        encoder_config = self.encoder_configs[codec]
        gpu_id, vaapi_suffix = self.select_gpu(encoder_device.device_name)

        encoder_element = self.select_element(
            encoder_config,
            encoder_device,
            vaapi_suffix,
        )

        if encoder_element is None:
            self.logger.error(
                f"Failed to select encoder element for device: {encoder_device.device_name}"
            )
            raise ValueError(
                f"No suitable encoder found for device: {encoder_device.device_name}"
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

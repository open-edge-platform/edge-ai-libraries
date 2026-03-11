import logging
import threading
from typing import Dict, List, Optional, Tuple

from explore import GstInspector

# Decoder device constants
DECODER_DEVICE_CPU = "CPU"
DECODER_DEVICE_GPU = "GPU"

# Normalize various fourcc/encoding strings to a canonical codec name
FOURCC_TO_CODEC = {
    "MJPG": "mjpg",
    "MJPEG": "mjpg",
    "JPEG": "mjpg",
    "jpeg": "mjpg",
    "H264": "h264",
    "h264": "h264",
    "H.264": "h264",
    "avc": "h264",
    "avc1": "h264",
    "H265": "h265",
    "h265": "h265",
    "H.265": "h265",
    "HEVC": "h265",
    "hevc": "h265",
}

# Fourcc codes that represent raw (uncompressed) video — no decoder needed
RAW_FOURCC_CODES = {
    "YUYV",
    "YUY2",
    "NV12",
    "UYVY",
    "I420",
    "YV12",
    "RGB3",
    "BGR3",
    "RGBP",
    "GREY",
    "GRAY",
    "BA81",
    "RGGB",
    "RG10",
    "RG12",
}

# GStreamer caps prefix for capsfilter after v4l2src
FOURCC_TO_CAPS_PREFIX = {
    "MJPG": "image/jpeg",
    "MJPEG": "image/jpeg",
    "JPEG": "image/jpeg",
    "H264": "video/x-h264",
    "H.264": "video/x-h264",
    "H265": "video/x-h265",
    "HEVC": "video/x-h265",
    "H.265": "video/x-h265",
    "YUYV": "video/x-raw,format=YUY2",
    "YUY2": "video/x-raw,format=YUY2",
    "NV12": "video/x-raw,format=NV12",
    "UYVY": "video/x-raw,format=UYVY",
    "I420": "video/x-raw,format=I420",
}

logger = logging.getLogger("video_decoder")


class VideoDecoder:
    """Thread-safe singleton for selecting GStreamer decoder elements.

    Uses GstInspector to check which decoder elements are available
    in the current GStreamer installation. Selects the best decoder
    based on the input codec and target inference device.

    Follows the same singleton pattern as VideoEncoder.
    """

    _instance: Optional["VideoDecoder"] = None
    _lock = threading.Lock()

    def __new__(cls) -> "VideoDecoder":
        if cls._instance is None:
            with cls._lock:
                # Double-checked locking
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        """Initialize VideoDecoder with GStreamer inspector and decoder configurations.
        Protected against multiple initialization.
        """
        # Protect against multiple initialization
        if hasattr(self, "_initialized"):
            return
        self._initialized = True

        self.logger = logging.getLogger("VideoDecoder")
        self.gst_inspector = GstInspector()

        # Decoder configurations: codec -> device -> list of (search, result) tuples
        # First match wins (preferred element listed first)
        self.decoder_configs: Dict[str, Dict[str, List[Tuple[str, str]]]] = {
            "h264": {
                DECODER_DEVICE_GPU: [
                    ("vah264dec", "vah264dec"),
                    ("avdec_h264", "avdec_h264"),
                ],
                DECODER_DEVICE_CPU: [
                    ("avdec_h264", "avdec_h264"),
                ],
            },
            "h265": {
                DECODER_DEVICE_GPU: [
                    ("vah265dec", "vah265dec"),
                    ("avdec_h265", "avdec_h265"),
                ],
                DECODER_DEVICE_CPU: [
                    ("avdec_h265", "avdec_h265"),
                ],
            },
            "mjpg": {
                DECODER_DEVICE_GPU: [
                    ("vajpegdec", "vajpegdec"),
                    ("avdec_mjpeg", "avdec_mjpeg"),
                ],
                DECODER_DEVICE_CPU: [
                    ("avdec_mjpeg", "avdec_mjpeg"),
                ],
            },
        }

    def select_element(
        self,
        field_dict: Dict[str, List[Tuple[str, str]]],
        decoder_device: str,
    ) -> Optional[str]:
        """Select an appropriate decoder element from available GStreamer elements.

        Iterates candidate tuples (search, result) for the given device and
        checks if the search element exists in GstInspector.elements.

        Args:
            field_dict: Dictionary mapping device types to lists of (search, result) tuples.
            decoder_device: Target decoder device (DECODER_DEVICE_CPU or DECODER_DEVICE_GPU).

        Returns:
            Selected decoder element string, or None if not found.
        """
        pairs = field_dict.get(decoder_device, [])

        if not pairs:
            self.logger.warning(
                f"No decoder pairs found for decoder_device: {decoder_device}"
            )
            return None

        for search, result in pairs:
            for element in self.gst_inspector.elements:
                if element[1] == search:
                    self.logger.debug(f"Selected decoder element: {result}")
                    return result

        self.logger.warning(
            f"No matching decoder element found for decoder_device: {decoder_device}"
        )
        return None

    def select_decoder(self, codec: str, target_device: str) -> Optional[str]:
        """Select the best available decoder element for a codec and device.

        Args:
            codec: Codec string (raw fourcc like "MJPG", or normalized like "h264").
                Normalized via FOURCC_TO_CODEC. If raw format, returns None.
            target_device: Target inference device ("CPU", "GPU", "NPU").
                NPU maps to GPU for decoder selection.

        Returns:
            Decoder element name (e.g., "vah264dec"), or None if:
            - fourcc is a raw format (no decoding needed)
            - fourcc is unknown (caller should keep decodebin3)
            - no decoder element is available
        """
        if not codec:
            self.logger.warning("Empty codec string, cannot select decoder")
            return None

        # Check if raw format first (no decoder needed)
        if self.is_raw_format(codec):
            self.logger.debug(f"Raw format '{codec}', no decoder needed")
            return None

        # Normalize codec string
        normalized = FOURCC_TO_CODEC.get(codec)
        if normalized is None:
            self.logger.warning(f"Unknown codec '{codec}', cannot select decoder")
            return None

        # Map NPU to GPU for decoder selection (VA-API decoders live on GPU)
        device = target_device.upper()
        if device == "NPU":
            device = DECODER_DEVICE_GPU

        # Map to our two supported device constants
        if device not in {DECODER_DEVICE_CPU, DECODER_DEVICE_GPU}:
            self.logger.warning(
                f"Unknown device '{target_device}', defaulting to CPU for decoder"
            )
            device = DECODER_DEVICE_CPU

        # Look up decoder config for the normalized codec
        config = self.decoder_configs.get(normalized)
        if config is None:
            self.logger.warning(f"No decoder config for codec '{normalized}'")
            return None

        return self.select_element(config, device)

    def build_caps_string(
        self, fourcc: str, width: int, height: int, fps: float
    ) -> Optional[str]:
        """Build a GStreamer caps string for a v4l2src capsfilter.

        Args:
            fourcc: V4L2 fourcc code (e.g., "MJPG", "YUYV").
            width: Frame width in pixels.
            height: Frame height in pixels.
            fps: Frame rate (will be rounded to int for framerate=N/1).

        Returns:
            Caps string like "image/jpeg,width=1920,height=1080,framerate=30/1",
            or None if fourcc is not in FOURCC_TO_CAPS_PREFIX.
        """
        prefix = FOURCC_TO_CAPS_PREFIX.get(fourcc)
        if prefix is None:
            self.logger.warning(f"No caps prefix for fourcc '{fourcc}'")
            return None

        fps_int = int(round(fps))
        caps = f"{prefix},width={width},height={height},framerate={fps_int}/1"
        self.logger.debug(f"Built caps string: {caps}")
        return caps

    def is_raw_format(self, fourcc: str) -> bool:
        """Check if a fourcc code represents a raw (uncompressed) video format.

        Args:
            fourcc: Fourcc code string (e.g., "YUYV", "NV12").

        Returns:
            True if the fourcc is a raw format, False otherwise.
        """
        return fourcc.upper() in RAW_FOURCC_CODES if fourcc else False

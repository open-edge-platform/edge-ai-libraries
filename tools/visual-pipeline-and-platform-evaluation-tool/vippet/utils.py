import hashlib
import logging
import re
import time
import uuid
from datetime import datetime
from pathlib import Path


logger = logging.getLogger("utils")


def generate_unique_id(prefix: str) -> str:
    """
    Generate a unique ID based on a prefix name and an 8-character hash suffix.

    The hash is generated using the prefix, current timestamp, and a counter
    to ensure uniqueness even for rapid successive calls with the same prefix.

    Args:
        prefix: The prefix string to use for the ID.

    Returns:
        str: A unique identifier in the format "{prefix}-{hash}" where hash is 8 characters.

    Example:
        >>> generate_unique_id("pipeline")
        'pipeline-a3f5d9e1'
    """
    # Combine prefix with current time in nanoseconds for uniqueness
    unique_string = f"{prefix}-{time.time_ns()}"

    # Generate SHA256 hash and take first 8 characters
    hash_object = hashlib.sha256(unique_string.encode())
    hash_suffix = hash_object.hexdigest()[:8]

    return f"{prefix}-{hash_suffix}"


def make_tee_names_unique(
    pipeline_str: str, pipeline_index: int, stream_index: int
) -> str:
    """
    Replace all tee names in the pipeline string with unique names based on pipeline and stream indices.

    GStreamer pipelines may contain multiple tees with different names (e.g., tee name=t0, tee name=t1).
    Each tee is referenced later in the pipeline (e.g., t0., t1.).
    This function ensures each tee gets a unique name to avoid conflicts when combining multiple pipelines.

    Args:
        pipeline_str: The GStreamer pipeline string containing tee elements.
        pipeline_index: The index of the pipeline in the run specification list.
        stream_index: The index of the stream within the pipeline.

    Returns:
        str: The pipeline string with all tee names replaced with unique identifiers.

    Example:
        Input:  "... tee name=t0 ! queue t0. ! ..."
        Output: "... tee name=t100 ! queue t100. ! ..."
    """
    logger.debug(
        f"Making tee names unique for pipeline_index={pipeline_index}, stream_index={stream_index}"
    )

    # Find all unique tee names in the pipeline using regex
    # Pattern matches "tee name=<name>" where <name> is typically t0, t1, t2, etc.
    tee_pattern = r"tee\s+name=(\w+)"
    tee_matches = re.finditer(tee_pattern, pipeline_str)

    # Collect all unique tee names
    tee_names = set()
    for match in tee_matches:
        tee_names.add(match.group(1))

    if tee_names:
        logger.debug(f"Found {len(tee_names)} unique tee(s): {sorted(tee_names)}")
    else:
        logger.debug("No tee elements found in pipeline")
        return pipeline_str

    # Replace each tee name with a unique identifier
    # Using an index in addition to digits from the original name prevents
    # collisions when multiple tees have names without digits or share
    # the same digit pattern.
    for idx, original_name in enumerate(sorted(tee_names)):
        # Extract digits from original name (e.g., "t0" -> "0", "t1" -> "1")
        original_digits = "".join(filter(str.isdigit, original_name))
        # Create unique name: t{pipeline_index}{stream_index}{idx}{original_digits}
        new_name = f"t{pipeline_index}{stream_index}{idx}{original_digits}"

        # Replace "tee name=<original_name>" with "tee name=<new_name>"
        pipeline_str = re.sub(
            rf"tee\s+name={re.escape(original_name)}(?=\s|!)",
            f"tee name={new_name}",
            pipeline_str,
        )

        # Replace references to the tee (e.g., "t0." becomes "t1000.")
        pipeline_str = re.sub(
            rf"\b{re.escape(original_name)}\.", f"{new_name}.", pipeline_str
        )

    logger.debug("Tee name replacement completed successfully")
    return pipeline_str


def generate_unique_filename(filename: str) -> str:
    """
    Generate a unique filename by appending a timestamp and suffix before the file extension.

    Args:
        filename: Original filename (e.g., "video.mp4").

    Returns:
        str: Unique filename with timestamp and suffix (e.g., "video_20231012_153045_abc123.mp4").
    """
    # Extract stem and extension
    path = Path(filename)
    stem = Path(path.name).stem
    ext = path.suffix

    if not ext:
        ext = ".mp4"  # default extension

    # Generate timestamp and short unique suffix
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    suffix = uuid.uuid4().hex[:6]

    # Construct new filename
    new_filename = f"{stem}_{timestamp}_{suffix}{ext}"

    return new_filename


def normalize_device_name_for_url(device_name: str) -> str:
    """
    Normalize a device name to be URL-safe.

    Converts the device name to lowercase, replaces spaces with underscores,
    and removes all characters that are not alphanumeric or underscores.
    This ensures the device name can be safely used in URL paths without
    requiring percent-encoding.

    Args:
        device_name: The original device name (e.g., "Thronmax StreamGo Webcam: Thron").

    Returns:
        str: URL-safe device name (e.g., "thronmax_streamgo_webcam__thron").

    Example:
        >>> normalize_device_name_for_url("Thronmax StreamGo Webcam: Thron")
        'thronmax_streamgo_webcam__thron'
        >>> normalize_device_name_for_url("HD Pro Webcam C920")
        'hd_pro_webcam_c920'
    """
    # Convert to lowercase and replace spaces with underscores
    normalized = device_name.lower().replace(" ", "_")
    # Remove all characters not allowed in URL paths (keep only alphanumeric and underscores)
    normalized = "".join(c if c.isalnum() or c == "_" else "_" for c in normalized)
    return normalized


def is_yolov10_model(model_path: str) -> bool:
    """
    Checks if the given model path corresponds to a YOLO v10 model.

    Args:
        model_path (str): Path to the model file.

    Returns:
        bool: True if the model is a YOLO v10 model, False otherwise.
    """
    return "yolov10" in model_path.lower()

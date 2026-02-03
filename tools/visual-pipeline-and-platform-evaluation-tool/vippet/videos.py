import json
import logging
import os
import shutil
import time
import threading
import urllib.request
import urllib.error
from dataclasses import dataclass
from typing import Dict, List, Optional

import cv2
import yaml

from pipeline_runner import PipelineRunner

# Allowed video file extensions (lowercase, without dot)
VIDEO_EXTENSIONS = (
    "mp4",
    "mkv",
    "mov",
    "avi",
    "ts",
    "264",
    "avc",
    "h265",
    "hevc",
)

# Default directories for input and output videos
OUTPUT_VIDEO_DIR = "/videos/output"
INPUT_VIDEO_DIR = "/videos/input"

# Read RECORDINGS_PATH from environment variable
RECORDINGS_PATH: str = os.path.normpath(
    os.environ.get("RECORDINGS_PATH", INPUT_VIDEO_DIR)
)

# Path to default recordings YAML file
DEFAULT_RECORDINGS_FILE = "/videos/default_recordings.yaml"

logger = logging.getLogger("videos")


@dataclass
class VideoFileInfo:
    """
    Holds raw video file information extracted from cv2.VideoCapture.
    """

    width: int
    height: int
    fps: float
    frame_count: int
    fourcc: int

    @property
    def codec(self) -> str:
        """
        Convert fourcc code to codec string (h264/h265).
        """
        codec_str = (
            "".join([chr((self.fourcc >> 8 * i) & 0xFF) for i in range(4)])
            .strip()
            .lower()
        )
        if "avc" in codec_str:
            return "h264"
        if "hevc" in codec_str:
            return "h265"
        return codec_str

    @property
    def duration(self) -> float:
        """
        Calculate duration in seconds from frame_count and fps.
        """
        return self.frame_count / self.fps if self.fps > 0 else 0.0


class Video:
    """
    Represents a single video file and its metadata.
    """

    def __init__(
        self,
        filename: str,
        width: int,
        height: int,
        fps: float,
        frame_count: int,
        codec: str,
        duration: float,
    ) -> None:
        """
        Initializes the Video instance.

        Args:
            filename: Name of the video file.
            width: Frame width in pixels.
            height: Frame height in pixels.
            fps: Frames per second.
            frame_count: Total number of frames.
            codec: Video codec (e.g., 'h264', 'h265').
            duration: Duration in seconds.
        """
        self.filename = filename
        self.width = width
        self.height = height
        self.fps = fps
        self.frame_count = frame_count
        self.codec = codec
        self.duration = duration

    def to_dict(self) -> dict:
        """
        Serializes the Video object to a dictionary.
        """
        return {
            "filename": self.filename,
            "width": self.width,
            "height": self.height,
            "fps": self.fps,
            "frame_count": self.frame_count,
            "codec": self.codec,
            "duration": self.duration,
        }

    @staticmethod
    def from_dict(data: dict) -> "Video":
        """
        Deserializes a Video object from a dictionary.
        """
        return Video(
            filename=data["filename"],
            width=data["width"],
            height=data["height"],
            fps=data["fps"],
            frame_count=data["frame_count"],
            codec=data["codec"],
            duration=data["duration"],
        )


class VideosManager:
    """
    Thread-safe singleton that manages all video files and their metadata in the RECORDINGS_PATH directory.

    Implements singleton pattern using __new__ with double-checked locking.
    Create instances with VideosManager() to get the shared singleton instance.

    Initialization performs three phases:
    1. Download videos from default_recordings.yaml (if not already present)
    2. Scan and load all video files with their metadata (JSON cache)
    3. Convert all non-TS videos to TS format for looping support

    Raises:
        RuntimeError: If RECORDINGS_PATH is not a valid directory.
    """

    _instance: Optional["VideosManager"] = None
    _lock = threading.Lock()

    def __new__(cls) -> "VideosManager":
        if cls._instance is None:
            with cls._lock:
                # Double-checked locking
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self) -> None:
        """
        Initializes the VideosManager.
        - Validates RECORDINGS_PATH exists
        - Downloads videos from default_recordings.yaml if not already present
        - Scans directory and loads video metadata
        - Ensures all TS conversions exist

        Protected against multiple initialization.

        Raises:
            RuntimeError: If RECORDINGS_PATH is not a valid directory.
        """
        # Protect against multiple initialization
        if hasattr(self, "_initialized"):
            return
        self._initialized = True

        logger.debug(
            f"Initializing VideosManager with RECORDINGS_PATH={RECORDINGS_PATH}"
        )
        if not os.path.isdir(RECORDINGS_PATH):
            raise RuntimeError(
                f"RECORDINGS_PATH '{RECORDINGS_PATH}' does not exist or is not a directory."
            )

        self._videos: Dict[str, Video] = {}

        # Phase 1: Download videos from default_recordings.yaml
        self._download_default_videos()

        # Phase 2: Scan and load all video files with metadata
        self._scan_and_load_all_videos()

        # Phase 3: Ensure all TS conversions exist
        self._ensure_all_ts_conversions()

    def _download_default_videos(self) -> None:
        """
        Downloads videos defined in default_recordings.yaml if not already present.
        Skips downloading if the YAML file does not exist.
        """
        if not os.path.isfile(DEFAULT_RECORDINGS_FILE):
            logger.error(
                f"Default recordings file '{DEFAULT_RECORDINGS_FILE}' not found, skipping downloads."
            )
            return

        recordings = self._load_recordings_yaml(DEFAULT_RECORDINGS_FILE)
        if not recordings:
            logger.debug("No recordings found in default_recordings.yaml.")
            return

        logger.debug(
            f"Checking {len(recordings)} video(s) from default_recordings.yaml..."
        )

        for recording in recordings:
            url = recording.get("url")
            filename = recording.get("filename")

            if not url or not filename:
                logger.warning(
                    f"Invalid recording entry in default_recordings.yaml: "
                    f"url='{url}', filename='{filename}'. Skipping."
                )
                continue

            self._download_video(url, filename)

    @staticmethod
    def _load_recordings_yaml(yaml_path: str) -> List[dict]:
        """
        Loads recordings list from a YAML file.

        Args:
            yaml_path: Path to the YAML file.

        Returns:
            List of recording dictionaries with 'url' and 'filename' keys.
            Returns empty list on error.
        """
        try:
            with open(yaml_path, "r") as f:
                data = yaml.safe_load(f)

            if not isinstance(data, list):
                logger.error(
                    f"Invalid format in '{yaml_path}': expected list, got {type(data).__name__}."
                )
                return []

            return data
        except Exception as e:
            logger.error(f"Failed to load recordings YAML '{yaml_path}': {e}")
            return []

    def _download_video(self, url: str, filename: str) -> Optional[str]:
        """
        Downloads a single video from URL if not already present.

        Args:
            url: URL of the video to download.
            filename: Target filename for the downloaded video.

        Returns:
            Path to the downloaded file, or None on error.
        """
        target_path = os.path.join(RECORDINGS_PATH, filename)

        # Skip if file already exists
        if os.path.isfile(target_path):
            logger.debug(f"Video '{filename}' already exists, skipping download.")
            return target_path

        # Download to temp file first, then move to target
        tmp_path = f"/tmp/{filename}"

        logger.info(f"Downloading '{filename}' from {url}...")
        t0 = time.perf_counter()

        try:
            # Create request with timeout (600 seconds for large files)
            request = urllib.request.Request(
                url,
                headers={
                    "User-Agent": "Mozilla/5.0"
                },  # Some servers require User-Agent
            )

            with urllib.request.urlopen(request, timeout=600) as response:
                # Check for HTTP errors (urlopen raises for 4xx/5xx with default handler)
                if response.status != 200:
                    logger.error(
                        f"Failed to download '{filename}': HTTP {response.status}"
                    )
                    return None

                # Download to temp file in chunks (8KB chunks)
                chunk_size = 8192
                with open(tmp_path, "wb") as f:
                    while True:
                        chunk = response.read(chunk_size)
                        if not chunk:
                            break
                        f.write(chunk)

            # Move from temp to target location
            if not self._move_file(tmp_path, target_path):
                return None

            t1 = time.perf_counter()
            file_size = (
                os.path.getsize(target_path) if os.path.isfile(target_path) else 0
            )
            logger.info(
                f"Downloaded '{filename}' ({file_size / (1024 * 1024):.1f} MB) "
                f"in {t1 - t0:.1f} seconds."
            )
            return target_path

        except urllib.error.HTTPError as e:
            logger.error(f"Failed to download '{filename}': HTTP {e.code} - {e.reason}")
            self._cleanup_file(tmp_path)
            return None
        except urllib.error.URLError as e:
            logger.error(f"Failed to download '{filename}': URL error - {e.reason}")
            self._cleanup_file(tmp_path)
            return None
        except TimeoutError:
            logger.error(f"Download timeout for '{filename}' from {url}")
            self._cleanup_file(tmp_path)
            return None
        except Exception as e:
            logger.error(f"Failed to download '{filename}': {e}")
            self._cleanup_file(tmp_path)
            return None

    @staticmethod
    def _move_file(src: str, dst: str) -> bool:
        """
        Moves a file from src to dst.

        Args:
            src: Source file path.
            dst: Destination file path.

        Returns:
            True if successful, False otherwise.
        """
        try:
            shutil.move(src, dst)
            return True
        except Exception as e:
            logger.error(f"Failed to move '{src}' to '{dst}': {e}")
            return False

    @staticmethod
    def _cleanup_file(path: str) -> None:
        """
        Removes a file if it exists. Used for cleanup on error.

        Args:
            path: Path to the file to remove.
        """
        try:
            if os.path.isfile(path):
                os.remove(path)
        except OSError:
            pass  # Ignore cleanup errors

    def _scan_and_load_all_videos(self) -> None:
        """
        Scans the RECORDINGS_PATH directory for video files and loads/extracts metadata.
        Populates the _videos map with Video objects.
        """
        logger.debug(f"Scanning directory '{RECORDINGS_PATH}' for video files.")

        for entry in os.listdir(RECORDINGS_PATH):
            file_path = os.path.join(RECORDINGS_PATH, entry)
            if not os.path.isfile(file_path):
                continue

            ext = entry.lower().rsplit(".", 1)[-1]
            if ext not in VIDEO_EXTENSIONS:
                continue

            video = self._ensure_video_metadata(file_path)
            if video is not None:
                self._videos[entry] = video

    def _ensure_video_metadata(self, file_path: str) -> Optional[Video]:
        """
        Ensures metadata exists for a single video file.
        Loads from JSON cache if available, otherwise extracts from video and saves to JSON.

        Args:
            file_path: Full path to the video file.

        Returns:
            Video object if successful, None if video cannot be processed.
        """
        filename = os.path.basename(file_path)
        json_path = f"{file_path}.json"

        # Try to load from JSON cache
        if os.path.isfile(json_path):
            video = self._load_video_from_json(json_path, filename)
            if video is not None:
                return video

        # Extract metadata from video file
        logger.debug(f"Extracting metadata from video file '{filename}'.")
        t0 = time.perf_counter()

        file_info = self._extract_video_file_info(file_path)
        if file_info is None:
            logger.warning(f"Cannot open video file '{filename}', skipping.")
            return None

        if file_info.codec not in ("h264", "h265"):
            logger.warning(
                f"Video '{filename}' has unsupported codec '{file_info.codec}', skipping."
            )
            return None

        video = Video(
            filename=filename,
            width=file_info.width,
            height=file_info.height,
            fps=file_info.fps,
            frame_count=file_info.frame_count,
            codec=file_info.codec,
            duration=file_info.duration,
        )

        # Save metadata to JSON
        self._save_video_to_json(video, json_path)
        t1 = time.perf_counter()
        logger.debug(
            f"Extracted and saved metadata for '{filename}'. Took {t1 - t0:.6f} seconds."
        )

        return video

    @staticmethod
    def _extract_video_file_info(file_path: str) -> Optional[VideoFileInfo]:
        """
        Extracts video file information using cv2.VideoCapture.

        Args:
            file_path: Full path to the video file.

        Returns:
            VideoFileInfo if successful, None if file cannot be opened.
        """
        cap = cv2.VideoCapture(file_path)
        if not cap.isOpened():
            return None

        try:
            return VideoFileInfo(
                width=int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)),
                height=int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)),
                fps=float(cap.get(cv2.CAP_PROP_FPS)),
                frame_count=int(cap.get(cv2.CAP_PROP_FRAME_COUNT)),
                fourcc=int(cap.get(cv2.CAP_PROP_FOURCC)),
            )
        finally:
            cap.release()

    @staticmethod
    def _load_video_from_json(json_path: str, filename: str) -> Optional[Video]:
        """
        Loads Video metadata from a JSON file.

        Args:
            json_path: Path to the JSON metadata file.
            filename: Video filename for logging.

        Returns:
            Video object if successful, None on error.
        """
        try:
            t0 = time.perf_counter()
            with open(json_path, "r") as f:
                data = json.load(f)
            video = Video.from_dict(data)
            t1 = time.perf_counter()
            logger.debug(
                f"Loaded metadata for '{filename}' from JSON. Took {t1 - t0:.6f} seconds."
            )
            return video
        except Exception as e:
            logger.warning(f"Failed to load JSON metadata for '{filename}': {e}")
            return None

    @staticmethod
    def _save_video_to_json(video: Video, json_path: str) -> None:
        """
        Saves Video metadata to a JSON file.

        Args:
            video: Video object to save.
            json_path: Path to the JSON metadata file.
        """
        try:
            with open(json_path, "w") as f:
                json.dump(video.to_dict(), f, indent=2)
        except Exception as e:
            logger.warning(f"Failed to write JSON metadata for '{video.filename}': {e}")

    def _ensure_all_ts_conversions(self) -> None:
        """
        Ensures all non-TS videos have corresponding TS files for looping support.
        Iterates through all loaded videos and converts if needed.
        """
        logger.debug("Ensuring all TS conversions exist.")

        for filename in list(self._videos.keys()):
            ext = filename.lower().rsplit(".", 1)[-1]
            if ext in ("ts", "m2ts"):
                continue

            file_path = os.path.join(RECORDINGS_PATH, filename)
            self.ensure_ts_file(file_path)

    def ensure_ts_file(self, source_path: str) -> Optional[str]:
        """
        Ensures a TS file exists for the given video file.
        If TS file does not exist, converts the source video to TS format.
        Also ensures TS file has metadata JSON.

        This method is public because it's used by graph.py to ensure TS file
        exists before using it in looping playback.

        Args:
            source_path: Full path to the source video file.

        Returns:
            Path to the TS file if successful, None on error.
        """
        source_filename = os.path.basename(source_path)
        ext = source_filename.lower().rsplit(".", 1)[-1]

        # If already TS, return as-is
        if ext in ("ts", "m2ts"):
            return source_path

        # Build TS path
        ts_filename = f"{os.path.splitext(source_filename)[0]}.ts"
        ts_path = os.path.join(RECORDINGS_PATH, ts_filename)

        # Check if TS file already exists
        if os.path.isfile(ts_path):
            # Ensure TS file has metadata
            self._ensure_ts_metadata(ts_path, ts_filename)
            return ts_path

        # Get source video info for codec detection
        source_video = self._videos.get(source_filename)
        if source_video is None:
            # Try to extract info from source file
            file_info = self._extract_video_file_info(source_path)
            if file_info is None:
                logger.warning(
                    f"Cannot open source video '{source_filename}' for TS conversion."
                )
                return None
            codec = file_info.codec
        else:
            codec = source_video.codec

        # Perform conversion
        success = self._convert_to_ts(source_path, ts_path, ext, codec)
        if not success:
            return None

        # Ensure TS file has metadata
        self._ensure_ts_metadata(ts_path, ts_filename)

        return ts_path

    def _ensure_ts_metadata(self, ts_path: str, ts_filename: str) -> None:
        """
        Ensures metadata JSON exists for a TS file.
        If not already in _videos, loads or creates metadata.

        Args:
            ts_path: Full path to the TS file.
            ts_filename: TS filename.
        """
        if ts_filename in self._videos:
            return

        video = self._ensure_video_metadata(ts_path)
        if video is not None:
            self._videos[ts_filename] = video

    @staticmethod
    def _convert_to_ts(source_path: str, ts_path: str, ext: str, codec: str) -> bool:
        """
        Converts a video file to TS format using GStreamer pipeline.

        Args:
            source_path: Full path to the source video.
            ts_path: Full path to the output TS file.
            ext: Source file extension (without dot).
            codec: Video codec (h264/h265).

        Returns:
            True if conversion successful, False otherwise.
        """
        if codec not in ("h264", "h265"):
            logger.warning(
                f"Video '{source_path}' has unsupported codec '{codec}' for TS conversion, skipping."
            )
            return False

        demuxer = VideosManager._get_demuxer_for_extension(ext)
        if demuxer is None and not VideosManager._is_raw_stream_extension(ext):
            logger.warning(
                f"No demuxer configured for '.{ext}' files. Skipping conversion for '{source_path}'."
            )
            return False

        parser = "h264parse" if codec == "h264" else "h265parse"
        caps = (
            "video/x-h264,stream-format=byte-stream"
            if codec == "h264"
            else "video/x-h265,stream-format=byte-stream"
        )

        source_filename = os.path.basename(source_path)
        ts_filename = os.path.basename(ts_path)
        logger.info(
            f"Converting '{source_filename}' to '{ts_filename}' using GStreamer."
        )

        try:
            runner = PipelineRunner(mode="normal", max_runtime=0.0)
            if demuxer:
                pipeline_command = (
                    f"filesrc location={source_path} ! {demuxer} ! {parser} ! {caps} "
                    f"! mpegtsmux ! filesink location={ts_path}"
                )
            else:
                pipeline_command = (
                    f"filesrc location={source_path} ! {parser} ! {caps} "
                    f"! mpegtsmux ! filesink location={ts_path}"
                )
            runner.run(pipeline_command)
            return True
        except Exception as e:
            logger.error(f"Failed to convert '{source_filename}' to TS: {e}")
            return False

    @staticmethod
    def _get_demuxer_for_extension(extension: str) -> Optional[str]:
        """
        Returns an appropriate GStreamer demuxer for a given file extension.

        Args:
            extension: File extension (without dot).

        Returns:
            Demuxer element name or None if not found.
        """
        demuxers = {
            "mp4": "qtdemux",
            "mov": "qtdemux",
            "mkv": "matroskademux",
            "avi": "avidemux",
            "flv": "flvdemux",
        }
        return demuxers.get(extension)

    @staticmethod
    def _is_raw_stream_extension(extension: str) -> bool:
        """
        Returns True when the extension represents a raw elementary stream.

        Args:
            extension: File extension (without dot).

        Returns:
            True if raw stream extension, False otherwise.
        """
        return extension in {"264", "avc", "h265", "hevc"}

    def get_ts_path(self, filename: str) -> Optional[str]:
        """
        Return the .ts path for the given video filename/path.
        Ensures the TS file exists before returning.

        If the input already has a .ts or .m2ts extension, it is returned unchanged.
        If the extension is unsupported, returns None.
        Handles both filenames and full paths.

        Args:
            filename: Video filename or full path.

        Returns:
            Full path to the TS file, or None on error.
        """
        if not filename:
            return None

        directory = os.path.dirname(filename)
        basename = os.path.basename(filename)

        base, ext_with_dot = os.path.splitext(basename)
        ext = ext_with_dot.lower().lstrip(".")
        if ext not in VIDEO_EXTENSIONS:
            logger.warning("Unsupported video extension '.%s' for %s", ext, filename)
            return None

        # Build source path
        if directory:
            source_path = filename
        else:
            source_path = os.path.join(RECORDINGS_PATH, basename)

        # If already TS, ensure metadata exists and return as-is
        if ext in ("ts", "m2ts"):
            self._ensure_ts_metadata(source_path, basename)
            return source_path

        # Ensure TS file exists
        return self.ensure_ts_file(source_path)

    def get_all_videos(self) -> Dict[str, Video]:
        """
        Returns a dictionary mapping filenames to Video objects for all videos.
        """
        return dict(self._videos)

    def get_video(self, filename: str) -> Optional[Video]:
        """
        Returns the Video object for the given filename, or None if not found.

        Args:
            filename: Name of the video file.

        Returns:
            The Video object if found, else None.
        """
        return self._videos.get(filename)

    def get_video_filename(self, path: str) -> Optional[str]:
        """
        Returns the Video filename for the given path, or None if not found.

        Args:
            path: Path to the video file (can be full path or just filename).

        Returns:
            The Video filename if found, else None.
        """
        # Extract just the filename from the path
        filename = os.path.basename(os.path.normpath(path))

        if filename in self._videos:
            return filename

        return None

    def get_video_path(self, filename: str) -> Optional[str]:
        """
        Returns the path for the given Video filename, or None if not found.

        Args:
            filename: The Video filename.

        Returns:
            Path to the Video filename if found, else None.
        """
        if filename not in self._videos:
            return None

        return os.path.join(RECORDINGS_PATH, filename)

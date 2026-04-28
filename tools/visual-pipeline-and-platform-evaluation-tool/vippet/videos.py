import json
import logging
import os
import shutil
import time
import threading
import urllib.request
import urllib.error
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Literal, Optional, Tuple

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

# Type alias for the video source (origin on disk).
VideoSourceKind = Literal["auto", "uploaded"]

# Input videos live in two sibling sub-directories so auto-downloaded and
# user-uploaded content never collide on disk:
#   - AUTO_VIDEO_DIR      - videos auto-downloaded from default_recordings.yaml
#   - UPLOADED_VIDEO_DIR  - videos uploaded by the user via the API
# Both are independently configurable. Defaults match the shared volume
# layout declared in compose.yml.
_OUTPUT_VIDEO_DIR = "/videos/output"
_AUTO_VIDEO_DIR = "/videos/input/auto"
_UPLOADED_VIDEO_DIR = "/videos/input/uploaded"

# Read paths from environment variables, falling back to defaults.
OUTPUT_VIDEO_DIR: str = os.path.normpath(
    os.environ.get("OUTPUT_VIDEO_DIR", _OUTPUT_VIDEO_DIR)
)
AUTO_VIDEO_DIR: str = os.path.normpath(
    os.environ.get("AUTO_VIDEO_DIR", _AUTO_VIDEO_DIR)
)
UPLOADED_VIDEO_DIR: str = os.path.normpath(
    os.environ.get("UPLOADED_VIDEO_DIR", _UPLOADED_VIDEO_DIR)
)

# Path to the default recordings YAML file. Configurable via the
# DEFAULT_RECORDINGS_FILE environment variable; falls back to the shared
# default shipped with the image.
DEFAULT_RECORDINGS_FILE: str = os.environ.get(
    "DEFAULT_RECORDINGS_FILE",
    "/videos/default_recordings.yaml",
)

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

    The ``source`` field records whether the video was auto-downloaded or
    uploaded by the user. The ``path`` field is the location of the file
    relative to the 'auto' / 'uploaded' directories
    (for example ``auto/people.mp4`` or ``uploaded/myclip.mp4``).
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
        source: VideoSourceKind = "auto",
        path: str = "",
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
            source: Where the video came from ('auto' or 'uploaded').
            path: Path of the file prefixed with its source directory name,
                  for example 'auto/people.mp4' or 'uploaded/myclip.mp4'.
                  An empty value signals that the caller could not determine
                  the location yet; the authoritative value is always
                  restored during the directory scan.
        """
        self.filename = filename
        self.width = width
        self.height = height
        self.fps = fps
        self.frame_count = frame_count
        self.codec = codec
        self.duration = duration
        self.source: VideoSourceKind = source
        self.path = path

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
            "source": self.source,
            "path": self.path,
        }

    @staticmethod
    def from_dict(data: dict) -> "Video":
        """
        Deserializes a Video object from a dictionary.

        ``source`` and ``path`` are tolerated as missing in the on-disk JSON
        so minor schema drift between reads and writes does not break
        loading. Missing values default to 'auto' and an empty string
        respectively; the caller is expected to overwrite them with the
        authoritative values discovered during the directory scan.
        """
        source = data.get("source", "auto")
        if source not in ("auto", "uploaded"):
            source = "auto"
        return Video(
            filename=data["filename"],
            width=data["width"],
            height=data["height"],
            fps=data["fps"],
            frame_count=data["frame_count"],
            codec=data["codec"],
            duration=data["duration"],
            source=source,  # type: ignore[arg-type]
            path=data.get("path", ""),
        )


class VideosManager:
    """
    Thread-safe singleton that manages all video files and their metadata
    across ``AUTO_VIDEO_DIR`` and ``UPLOADED_VIDEO_DIR``.

    Implements singleton pattern using __new__ with double-checked locking.
    Create instances with VideosManager() to get the shared singleton instance.

    Initialization performs three phases:
    1. Download videos from default_recordings.yaml into AUTO_VIDEO_DIR
       (if not already present).
    2. Scan AUTO_VIDEO_DIR and UPLOADED_VIDEO_DIR and load all video files
       with their metadata (JSON cache).
    3. Convert all non-TS videos to TS format for looping support. The TS
       file is written next to the source video (same subdirectory).

    Filenames must be unique across 'auto' and 'uploaded'. This invariant is
    enforced at upload time by the ``/videos/upload`` endpoint; if a
    duplicate is somehow present on disk during scan the uploaded copy wins.

    Raises:
        RuntimeError: If either AUTO_VIDEO_DIR or UPLOADED_VIDEO_DIR cannot
        be created at startup.
    """

    _instance: Optional["VideosManager"] = None
    _lock = threading.Lock()
    # Serialises the final commit inside register_uploaded_video() so two
    # concurrent uploads that slipped past filename_exists() cannot both
    # move their temp file into the same target path.
    _upload_lock = threading.Lock()

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
        - Creates AUTO_VIDEO_DIR and UPLOADED_VIDEO_DIR if missing
        - Downloads videos from default_recordings.yaml into AUTO_VIDEO_DIR
        - Scans both sub-directories and loads video metadata
        - Ensures all TS conversions exist next to their sources

        Protected against multiple initialization.

        Raises:
            RuntimeError: If either sub-directory cannot be created.
        """
        # Protect against multiple initialization
        if hasattr(self, "_initialized"):
            return
        self._initialized = True

        logger.debug(
            f"Initializing VideosManager with AUTO_VIDEO_DIR={AUTO_VIDEO_DIR}, "
            f"UPLOADED_VIDEO_DIR={UPLOADED_VIDEO_DIR}"
        )

        # Ensure the 'auto' and 'uploaded' subdirectories exist. They are
        # created on every startup so deployments that only mount the shared
        # volume (without pre-creating the subdirs) still work.
        self._ensure_subdirs()

        # In-memory caches. ``_videos`` is the authoritative map from
        # filename to Video metadata. ``_video_paths`` maps the same
        # filename to the absolute on-disk path so callers can resolve
        # either the 'auto' or 'uploaded' location without having to know
        # which subdir the file lives in.
        self._videos: Dict[str, Video] = {}
        self._video_paths: Dict[str, str] = {}

        # Phase 1: Download videos from default_recordings.yaml into AUTO_VIDEO_DIR
        self._download_default_videos()

        # Phase 2: Scan and load all video files with metadata
        self._scan_and_load_all_videos()

        # Phase 3: Ensure all TS conversions exist next to their sources
        self._ensure_all_ts_conversions()

    @staticmethod
    def _ensure_subdirs() -> None:
        """
        Ensure AUTO_VIDEO_DIR and UPLOADED_VIDEO_DIR exist on disk with
        mode 0o755.

        ``os.makedirs(mode=...)`` alone is subject to the process umask and
        does not touch already-existing directories, so we follow up with
        an explicit ``os.chmod`` to guarantee the mode regardless of the
        umask and regardless of who created the directory originally. Any
        OS error is re-raised as RuntimeError since the application cannot
        function without these folders.
        """
        for subdir in (AUTO_VIDEO_DIR, UPLOADED_VIDEO_DIR):
            try:
                os.makedirs(subdir, mode=0o755, exist_ok=True)
                # Enforce the mode explicitly - os.makedirs() respects the
                # umask and leaves existing directories untouched.
                os.chmod(subdir, 0o755)
            except OSError as e:
                raise RuntimeError(
                    f"Failed to create video subdirectory '{subdir}': {e}"
                ) from e

    def _download_default_videos(self) -> None:
        """
        Downloads videos defined in default_recordings.yaml if not already present.
        Skips downloading if the YAML file does not exist. All downloaded
        files are written to AUTO_VIDEO_DIR.
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
        Downloads a single video from URL into AUTO_VIDEO_DIR if not
        already present.

        Args:
            url: URL of the video to download.
            filename: Target filename for the downloaded video.

        Returns:
            Path to the downloaded file, or None on error.
        """
        target_path = os.path.join(AUTO_VIDEO_DIR, filename)

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
        Scans the 'auto' and 'uploaded' subdirectories for video files and
        loads/extracts metadata. Populates ``_videos`` and ``_video_paths``.

        If the same filename appears in both subdirectories (which the
        upload endpoint actively prevents) the 'uploaded' copy wins so that
        user intent is preserved and a warning is logged.
        """
        # Scan 'auto' first so that any duplicate in 'uploaded' overrides it.
        for subdir, source in (
            (AUTO_VIDEO_DIR, "auto"),
            (UPLOADED_VIDEO_DIR, "uploaded"),
        ):
            if not os.path.isdir(subdir):
                logger.warning(
                    f"Video subdirectory '{subdir}' is missing, skipping scan."
                )
                continue

            logger.debug(f"Scanning directory '{subdir}' for video files.")

            for entry in os.listdir(subdir):
                file_path = os.path.join(subdir, entry)
                if not os.path.isfile(file_path):
                    continue

                ext = entry.lower().rsplit(".", 1)[-1]
                if ext not in VIDEO_EXTENSIONS:
                    continue

                if entry in self._videos:
                    logger.warning(
                        f"Duplicate video filename '{entry}' found in '{subdir}'. "
                        f"Overriding the previous '{self._videos[entry].source}' entry."
                    )

                video = self._ensure_video_metadata(file_path, source)  # type: ignore[arg-type]
                if video is not None:
                    self._videos[entry] = video
                    self._video_paths[entry] = file_path

    def _ensure_video_metadata(
        self, file_path: str, source: VideoSourceKind
    ) -> Optional[Video]:
        """
        Ensures metadata exists for a single video file.
        Loads from JSON cache if available, otherwise extracts from video and
        saves to JSON. The ``source`` and ``path`` fields are always
        overwritten with authoritative values derived from ``file_path``.

        Args:
            file_path: Full path to the video file.
            source: Origin of the video ('auto' or 'uploaded').

        Returns:
            Video object if successful, None if video cannot be processed.
        """
        filename = os.path.basename(file_path)
        json_path = f"{file_path}.json"
        # Build a short relative path of the form '<source>/<filename>' that
        # the API surfaces to clients (they prefix it with their static asset
        # root). Derived from ``source`` + ``filename`` so it stays valid
        # regardless of where AUTO_VIDEO_DIR and UPLOADED_VIDEO_DIR live on
        # disk.
        rel_path = f"{source}/{filename}"

        # Try to load from JSON cache
        if os.path.isfile(json_path):
            video = self._load_video_from_json(json_path, filename)
            if video is not None:
                # Overwrite any stale source/path in cached metadata so the
                # in-memory view always matches the actual on-disk location.
                video.source = source
                video.path = rel_path
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
            source=source,
            path=rel_path,
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
            frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            if frame_count <= 0:
                frame_count = 0  # Avoid negative or zero frame counts

            return VideoFileInfo(
                width=int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)),
                height=int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)),
                fps=float(cap.get(cv2.CAP_PROP_FPS)),
                frame_count=frame_count,
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
        The TS companion lives next to the source video (same subdirectory).
        """
        logger.debug("Ensuring all TS conversions exist.")

        for filename in list(self._videos.keys()):
            ext = filename.lower().rsplit(".", 1)[-1]
            if ext in ("ts", "m2ts"):
                continue

            file_path = self._video_paths.get(filename)
            if file_path is None:
                continue

            self.ensure_ts_file(file_path)

    def ensure_ts_file(self, source_path: str) -> Optional[str]:
        """
        Ensures a TS file exists for the given video file.
        If TS file does not exist, converts the source video to TS format.
        Also ensures TS file has metadata JSON and is registered in the
        internal filename -> path map. The TS file is written in the same
        directory as ``source_path``.

        This method is public because it's used by graph.py to ensure TS file
        exists before using it in looping playback.

        Args:
            source_path: Full path to the source video file.

        Returns:
            Path to the TS file if successful, None on error.
        """
        source_filename = os.path.basename(source_path)
        source_dir = os.path.dirname(source_path)
        ext = source_filename.lower().rsplit(".", 1)[-1]

        # If already TS, return as-is
        if ext in ("ts", "m2ts"):
            return source_path

        # Build TS path alongside the source file (same subdir -> so that
        # 'auto' videos get their TS in 'auto' and 'uploaded' videos get
        # theirs in 'uploaded').
        ts_filename = f"{os.path.splitext(source_filename)[0]}.ts"
        ts_path = os.path.join(source_dir, ts_filename)

        # Check if TS file already exists
        if os.path.isfile(ts_path):
            # Ensure TS file has metadata and is registered in our maps.
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
        If not already in _videos, loads or creates metadata and registers the
        TS file in both ``_videos`` and ``_video_paths``.

        Args:
            ts_path: Full path to the TS file.
            ts_filename: TS filename.
        """
        if ts_filename in self._videos:
            # Always refresh the path map in case the TS file was moved
            # between subdirs (for example after a user upload).
            self._video_paths[ts_filename] = ts_path
            return

        # Derive the source (auto/uploaded) from the parent directory of the
        # TS file itself so the metadata matches where it physically lives.
        source: VideoSourceKind = self._source_for_path(ts_path)

        video = self._ensure_video_metadata(ts_path, source)
        if video is not None:
            self._videos[ts_filename] = video
            self._video_paths[ts_filename] = ts_path

    @staticmethod
    def _source_for_path(file_path: str) -> VideoSourceKind:
        """
        Decides whether a given absolute file path belongs to the 'auto' or
        'uploaded' subtree. Defaults to 'auto' for paths that do not match
        either location (should not happen in practice).
        """
        parent = os.path.dirname(os.path.abspath(file_path))
        if os.path.abspath(parent) == os.path.abspath(UPLOADED_VIDEO_DIR):
            return "uploaded"
        return "auto"

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
        Handles both filenames and full paths; when a bare filename is given
        the source location is resolved via the internal filename -> path map
        (so callers do not need to know whether the video lives under
        'auto/' or 'uploaded/').

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

        # Build source path.
        if directory:
            # Caller already gave us a full path - trust it.
            source_path = filename
        else:
            # Resolve the real location from the map; fall back to
            # AUTO_VIDEO_DIR for recordings listed in the yaml that have
            # not been downloaded yet.
            source_path = self._video_paths.get(basename) or os.path.join(
                AUTO_VIDEO_DIR, basename
            )

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
        Returns the absolute path for the given Video filename, or None if
        not known. The returned path points to the real location (inside
        ``AUTO_VIDEO_DIR`` or ``UPLOADED_VIDEO_DIR``), which lets callers
        keep working without knowing which sub-directory holds the file.

        Args:
            filename: The Video filename.

        Returns:
            Full absolute path to the Video file if known, else None.
        """
        if filename not in self._videos:
            return None

        # The map is populated whenever a Video is inserted into ``_videos``
        # so the missing-entry case below should not fire in practice.
        return self._video_paths.get(filename)

    def filename_exists(self, filename: str) -> bool:
        """
        Returns True when a file with the given basename already exists under
        either AUTO_VIDEO_DIR or UPLOADED_VIDEO_DIR.

        This is used by the upload endpoint (and the
        ``/videos/check-video-input-exists`` endpoint) to prevent filename
        collisions that would otherwise break the shared _videos map.

        Args:
            filename: Basename to check (no directory component).

        Returns:
            True if the file exists in either subdirectory, False otherwise.
        """
        if not filename:
            return False

        # Defend against path traversal by considering only the basename.
        basename = os.path.basename(filename)

        # Fast path: in-memory map covers every file we have scanned.
        if basename in self._video_paths:
            return True

        # Fallback to a disk check - catches files that appeared after the
        # last scan (e.g. a manual copy into the shared volume).
        for subdir in (AUTO_VIDEO_DIR, UPLOADED_VIDEO_DIR):
            if os.path.isfile(os.path.join(subdir, basename)):
                return True

        return False

    def register_uploaded_video(
        self, temp_path: str, target_filename: str
    ) -> Tuple[Video, Optional[Video]]:
        """
        Finalises a user upload by moving an already-validated temporary file
        into UPLOADED_VIDEO_DIR, generating its metadata JSON, producing a TS
        companion next to it (with its own metadata JSON), and registering
        both entries in the internal ``_videos`` / ``_video_paths`` maps.

        The caller is responsible for performing extension, size, container
        and codec checks before invoking this method. On failure the target
        files are cleaned up so the shared folder is left in a consistent
        state.

        Args:
            temp_path: Absolute path to the validated temporary file.
            target_filename: Final basename to use inside UPLOADED_VIDEO_DIR.

        Returns:
            Tuple ``(original_video, ts_video)``. ``ts_video`` is None when
            TS conversion is not applicable (e.g. the upload is already a
            .ts file).

        Raises:
            RuntimeError: If the final file cannot be moved into place, the
                metadata cannot be generated, or the TS conversion fails.
        """
        basename = os.path.basename(target_filename)
        target_path = os.path.join(UPLOADED_VIDEO_DIR, basename)

        # Serialise the commit so two concurrent uploads that both passed
        # filename_exists() earlier cannot race to move their temp files
        # into the same ``target_path``. The atomic ``O_CREAT | O_EXCL``
        # reservation below turns the filename check + move into a single
        # critical section per target path.
        with self._upload_lock:
            # Atomically reserve ``target_path``. If the file (or a
            # reservation from a concurrent upload) already exists, abort
            # before touching anything on disk.
            try:
                fd = os.open(
                    target_path,
                    os.O_CREAT | os.O_EXCL | os.O_WRONLY,
                    0o644,
                )
                os.close(fd)
            except FileExistsError as exc:
                raise RuntimeError(
                    f"A video with filename '{basename}' already exists."
                ) from exc

            # Move the validated temp file into its final location. shutil.move
            # is used because the temp dir and the shared volume can live on
            # different filesystems. We just created an empty placeholder
            # at ``target_path`` above; shutil.move replaces it atomically
            # on POSIX (same filesystem) or overwrites it otherwise.
            if not self._move_file(temp_path, target_path):
                # Drop the placeholder we created so a retry can succeed.
                self._cleanup_file(target_path)
                raise RuntimeError(
                    f"Failed to move uploaded file '{basename}' into place."
                )

            # The streaming temp file is created with mode 0600 for safety, which
            # prevents the UI's nginx (running as a different user in its own
            # container) from reading the final video and serving it back to the
            # browser. Relax the mode to 0644 - matching the other files produced
            # during post-upload processing - so the UI can render the preview.
            try:
                os.chmod(target_path, 0o644)
            except OSError as exc:
                logger.warning(f"Could not set permissions on '{target_path}': {exc}")

        # Generate the metadata JSON for the original file.
        original_video = self._ensure_video_metadata(target_path, "uploaded")
        if original_video is None:
            # _ensure_video_metadata already logged the reason.
            self._cleanup_uploaded_artifacts(target_path)
            raise RuntimeError(
                f"Failed to extract metadata for uploaded video '{basename}'."
            )

        # Register the original in the in-memory maps so it is queryable
        # while the TS conversion below is still running. Any failure in the
        # TS step rolls the entry back (see below) to keep the folder in a
        # consistent state.
        self._videos[basename] = original_video
        self._video_paths[basename] = target_path

        # If the upload is already a transport stream there is nothing to do.
        ext = basename.lower().rsplit(".", 1)[-1]
        if ext in ("ts", "m2ts"):
            return original_video, None

        # Create the TS companion next to the original. ``ensure_ts_file``
        # handles the conversion, creates the TS JSON and registers the TS
        # entry in both maps.
        ts_path = self.ensure_ts_file(target_path)
        if ts_path is None or not os.path.isfile(ts_path):
            # Roll back to keep the folder in a consistent state.
            self._videos.pop(basename, None)
            self._video_paths.pop(basename, None)
            self._cleanup_uploaded_artifacts(target_path)
            raise RuntimeError(
                f"Failed to create TS companion for uploaded video '{basename}'."
            )

        ts_filename = os.path.basename(ts_path)
        ts_video = self._videos.get(ts_filename)
        return original_video, ts_video

    def _cleanup_uploaded_artifacts(self, target_path: str) -> None:
        """
        Remove every artifact belonging to a failed upload: the original
        file, its metadata JSON, and (if present) the TS file and TS JSON.
        Missing files are ignored - this is purely best-effort cleanup.
        """
        basename = os.path.basename(target_path)
        base, _ = os.path.splitext(basename)
        target_dir = os.path.dirname(target_path)
        ts_path = os.path.join(target_dir, f"{base}.ts")

        for path in (
            target_path,
            f"{target_path}.json",
            ts_path,
            f"{ts_path}.json",
        ):
            self._cleanup_file(path)


def collect_video_outputs_from_dirs(
    pipeline_dirs: dict[str, str],
) -> dict[str, list[str]]:
    """
    Scan pipeline output directories and collect video files.

    For each pipeline directory, lists all files directly in that directory,
    filters by VIDEO_EXTENSIONS, and ensures any file named "main_output.*"
    appears at the end of the list.

    Args:
        pipeline_dirs: Mapping from pipeline ID to directory path.

    Returns:
        Mapping from pipeline ID to sorted list of video file paths.
        Files named "main_output" are placed at the end of each list.
    """
    result: dict[str, list[str]] = {}

    for pipeline_id, dir_path in pipeline_dirs.items():
        if not os.path.isdir(dir_path):
            logger.warning("Pipeline output directory does not exist: %s", dir_path)
            result[pipeline_id] = []
            continue

        video_files: list[str] = []
        main_output_files: list[str] = []

        for entry in sorted(os.listdir(dir_path)):
            full_path = os.path.join(dir_path, entry)
            if not os.path.isfile(full_path):
                continue

            # Check extension against VIDEO_EXTENSIONS
            entry_path = Path(entry)
            ext = entry_path.suffix.lower().lstrip(".")
            if ext not in VIDEO_EXTENSIONS:
                continue

            # Separate main_output files to append them at the end
            stem = entry_path.stem
            if stem == "main_output":
                main_output_files.append(full_path)
            else:
                video_files.append(full_path)

        # main_output files go at the end
        video_files.extend(main_output_files)
        result[pipeline_id] = video_files

    return result

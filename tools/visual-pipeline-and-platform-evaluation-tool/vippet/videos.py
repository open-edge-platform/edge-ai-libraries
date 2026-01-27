import json
import logging
import os
import sys
import time
from typing import Dict, Optional

import cv2

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

logger = logging.getLogger("videos")

# Singleton instance for VideosManager
_videos_manager_instance: Optional["VideosManager"] = None


def get_videos_manager() -> "VideosManager":
    """
    Returns the singleton instance of VideosManager.
    If it cannot be created, logs an error and exits the application.
    """
    global _videos_manager_instance
    if _videos_manager_instance is None:
        try:
            _videos_manager_instance = VideosManager()
        except Exception as e:
            logger.error(f"Failed to initialize VideosManager: {e}")
            sys.exit(1)
    return _videos_manager_instance


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
            filename (str): Name of the video file.
            width (int): Frame width in pixels.
            height (int): Frame height in pixels.
            fps (float): Frames per second.
            frame_count (int): Total number of frames.
            codec (str): Video codec (e.g., 'h264', 'h265').
            duration (float): Duration in seconds.
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
    Manages all video files and their metadata in the RECORDINGS_PATH directory.
    Singleton pattern.
    """

    def __init__(self) -> None:
        """
        Initializes the VideosManager, scans the directory, and loads video metadata.
        Raises RuntimeError if RECORDINGS_PATH is not a valid directory.
        """
        logger.debug(
            f"Initializing VideosManager with RECORDINGS_PATH={RECORDINGS_PATH}"
        )
        if not os.path.isdir(RECORDINGS_PATH):
            raise RuntimeError(
                f"RECORDINGS_PATH '{RECORDINGS_PATH}' does not exist or is not a directory."
            )

        self._videos: Dict[str, Video] = {}
        self._scan_and_load_videos()

    def _scan_and_load_videos(self) -> None:
        """
        Scans the RECORDINGS_PATH directory for video files, extracts or loads metadata,
        and populates the videos map.
        """
        logger.debug(f"Scanning directory '{RECORDINGS_PATH}' for video files.")
        self._convert_non_ts_videos()
        for entry in os.listdir(RECORDINGS_PATH):
            file_path = os.path.join(RECORDINGS_PATH, entry)
            if not os.path.isfile(file_path):
                continue
            ext = entry.lower().rsplit(".", 1)[-1]
            if ext not in VIDEO_EXTENSIONS:
                continue

            json_path = f"{file_path}.json"
            if os.path.isfile(json_path):
                # Load metadata from JSON
                try:
                    t0 = time.perf_counter()
                    with open(json_path, "r") as f:
                        data = json.load(f)
                    video = Video.from_dict(data)
                    self._videos[entry] = video
                    t1 = time.perf_counter()
                    logger.debug(
                        f"Loaded metadata for '{entry}' from JSON. Took {t1 - t0:.6f} seconds."
                    )
                    continue
                except Exception as e:
                    logger.warning(f"Failed to load JSON metadata for '{entry}': {e}")

            # If JSON metadata does not exist, extract from video file and save
            logger.debug(f"Extracting metadata from video file '{entry}'.")
            t0 = time.perf_counter()
            cap = cv2.VideoCapture(file_path)
            if not cap.isOpened():
                logger.warning(f"Cannot open video file '{entry}', skipping.")
                continue
            width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            fps = float(cap.get(cv2.CAP_PROP_FPS))
            frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            cap.release()

            codec = self._detect_video_codec(file_path)
            if codec not in ("h264", "h265"):
                logger.warning(
                    f"Video '{entry}' has unsupported codec '{codec}', skipping."
                )
                continue

            duration = frame_count / fps if fps > 0 else 0.0

            video = Video(
                filename=entry,
                width=width,
                height=height,
                fps=fps,
                frame_count=frame_count,
                codec=codec,
                duration=duration,
            )

            self._videos[entry] = video

            # Save metadata to JSON
            try:
                with open(json_path, "w") as f:
                    json.dump(video.to_dict(), f, indent=2)
                t1 = time.perf_counter()
                logger.debug(
                    f"Saved metadata for '{entry}' to JSON. Took {t1 - t0:.6f} seconds."
                )
            except Exception as e:
                logger.warning(f"Failed to write JSON metadata for '{entry}': {e}")

    def get_ts_path(self, filename: str) -> Optional[str]:
        """
        Return the .ts filename/path for the given video filename/path.

        If the input already has a .ts or .m2ts extension, it is returned unchanged.
        If the extension is unsupported, returns None.
        Handles both filenames and full paths.
        """
        if not filename:
            return None

        directory = os.path.dirname(filename)
        basename = os.path.basename(filename)

        base, ext = os.path.splitext(basename)
        ext = ext.lower().lstrip(".")
        if ext not in VIDEO_EXTENSIONS:
            logger.warning("Unsupported video extension '.%s' for %s", ext, filename)
            return None

        if ext in ("ts", "m2ts"):
            return filename

        ts_filename = base + ".ts"
        return os.path.join(directory, ts_filename) if directory else ts_filename

    def _convert_non_ts_videos(self) -> None:
        """
        Convert supported non-TS videos to .ts format using PipelineRunner.

        This ensures that looping playback can use multifilesrc/tsdemux.
        """
        runner = PipelineRunner(mode="normal", max_runtime=0.0)

        for entry in os.listdir(RECORDINGS_PATH):
            file_path = os.path.join(RECORDINGS_PATH, entry)
            if not os.path.isfile(file_path):
                continue

            ext = entry.lower().rsplit(".", 1)[-1]
            if ext not in VIDEO_EXTENSIONS:
                continue

            if ext in ("ts", "m2ts"):
                continue

            ts_filename = f"{os.path.splitext(entry)[0]}.ts"
            ts_path = os.path.join(RECORDINGS_PATH, ts_filename)
            if os.path.isfile(ts_path):
                continue

            demuxer = self._get_demuxer_for_extension(ext)
            if demuxer is None and not self._is_raw_stream_extension(ext):
                logger.warning(
                    f"No demuxer configured for '.{ext}' files. Skipping conversion for '{entry}'."
                )
                continue

            codec = self._detect_video_codec(file_path)
            if codec not in ("h264", "h265"):
                logger.warning(
                    f"Video '{entry}' has unsupported codec '{codec}' for TS conversion, skipping."
                )
                continue

            parser = "h264parse" if codec == "h264" else "h265parse"
            caps = (
                "video/x-h264,stream-format=byte-stream"
                if codec == "h264"
                else "video/x-h265,stream-format=byte-stream"
            )

            logger.info(f"Converting '{entry}' to '{ts_filename}' using GStreamer.")
            try:
                if demuxer:
                    pipeline_command = (
                        f"filesrc location={file_path} ! {demuxer} ! {parser} ! {caps} "
                        f"! mpegtsmux ! filesink location={ts_path}"
                    )
                else:
                    pipeline_command = (
                        f"filesrc location={file_path} ! {parser} ! {caps} "
                        f"! mpegtsmux ! filesink location={ts_path}"
                    )
                runner.run(pipeline_command)
            except Exception as e:
                logger.error(f"Failed to convert '{entry}' to TS: {e}")

    @staticmethod
    def _get_demuxer_for_extension(extension: str) -> Optional[str]:
        """
        Returns an appropriate GStreamer demuxer for a given file extension.
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
        """
        return extension in {"264", "avc", "h265", "hevc"}

    @staticmethod
    def _detect_video_codec(file_path: str) -> str:
        """
        Detect the video codec (h264/h265) using OpenCV.
        """
        cap = cv2.VideoCapture(file_path)
        if not cap.isOpened():
            return ""
        fourcc = int(cap.get(cv2.CAP_PROP_FOURCC))
        cap.release()
        codec_str = (
            "".join([chr((fourcc >> 8 * i) & 0xFF) for i in range(4)]).strip().lower()
        )
        if "avc" in codec_str:
            return "h264"
        if "hevc" in codec_str:
            return "h265"
        return codec_str

    def get_all_videos(self) -> Dict[str, Video]:
        """
        Returns a dictionary mapping filenames to Video objects for all videos.
        """
        return dict(self._videos)

    def get_video(self, filename: str) -> Optional[Video]:
        """
        Returns the Video object for the given filename, or None if not found.

        Args:
            filename (str): Name of the video file.

        Returns:
            Optional[Video]: The Video object if found, else None.
        """
        return self._videos.get(filename)

    def get_video_filename(self, path: str) -> Optional[str]:
        """
        Returns the Video filename for the given path, or None if not found.

        Args:
            path (str): Path to the video file.

        Returns:
            str: The Video filename if found, else None.
        """
        filename = os.path.basename(os.path.normpath(path))

        if filename not in self._videos:
            return None

        return filename

    def get_video_path(self, filename: str) -> Optional[str]:
        """
        Returns the path for the given Video filename, or None if not found.

        Args:
            filename (str): The Video filename.

        Returns:
            str: Path to the Video filename if found, else None.
        """
        if filename not in self._videos:
            return None

        return os.path.join(RECORDINGS_PATH, filename)

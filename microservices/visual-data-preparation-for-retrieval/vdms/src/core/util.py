# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import datetime
import io
import json
import pathlib
from typing import Dict, List, Optional, Tuple

import cv2
import yaml
from tzlocal import get_localzone

from src.common import DataPrepException, Strings, logger, settings
from src.core.minio_client import MinioClient


def sanitize_input(input: str) -> str | None:
    """Takes an string input and strips whitespaces. Returns None if
    string is empty else returns the string.
    """
    input = str.strip(input)
    if len(input) == 0:
        return None

    return input


def read_config(config_file: str | pathlib.Path, type: str = "yaml") -> dict | None:
    """Takes a yaml/json file path as input. Parses and returns
    the file content as dictionary.
    """
    path = pathlib.Path(config_file)
    config: dict = {}

    try:
        with open(path.absolute(), "r") as f:
            if type == "yaml" or path.suffix.lower() == "yaml":
                config = yaml.safe_load(f)
            elif type == "json" or path.suffix.lower() == "json":
                config = json.load(f)

    except Exception as ex:
        logger.error(f"Error while reading config file: {ex}")
        config = None

    return config


def get_minio_client() -> MinioClient:
    """Get a configured Minio client instance.

    Returns:
        MinioClient: A configured Minio client

    Raises:
        Exception: If Minio client configuration is missing
    """
    if (
        not settings.MINIO_ENDPOINT
        or not settings.MINIO_ACCESS_KEY
        or not settings.MINIO_SECRET_KEY
    ):
        logger.error("Minio configuration is incomplete")
        raise Exception(Strings.minio_conn_error)

    try:
        return MinioClient(
            endpoint=settings.MINIO_ENDPOINT,
            access_key=settings.MINIO_ACCESS_KEY,
            secret_key=settings.MINIO_SECRET_KEY,
            secure=settings.MINIO_SECURE,
        )
    except Exception as ex:
        logger.error(f"Failed to initialize Minio client: {ex}")
        raise DataPrepException(status_code=500, msg=Strings.minio_conn_error)


def get_video_from_minio(
    bucket_name: str, video_id: str, video_name: Optional[str] = None
) -> Tuple[io.BytesIO, str]:
    """Get video data from Minio storage.

    Args:
        bucket_name (str): The bucket containing the video
        video_id (str): The directory (video_id) containing the video
        video_name (Optional[str], optional): Specific video filename. If None, first video found is used.

    Returns:
        Tuple[io.BytesIO, str]: Tuple containing the video data and the video filename

    Raises:
        DataPrepException: If video not found or other Minio error occurs
    """
    try:
        minio_client = get_minio_client()

        # Determine the object name
        object_name = None
        if video_name:
            # If video_name is provided, use it directly
            object_name = f"{video_id}/{video_name}"
        else:
            # Otherwise, find the first video in the directory
            object_name = minio_client.get_video_in_directory(bucket_name, video_id)

        if not object_name:
            logger.error(f"No video found in directory {video_id}")
            raise DataPrepException(status_code=404, msg=Strings.video_id_not_found)

        # Get the video data
        data = minio_client.download_video_stream(bucket_name, object_name)
        if not data:
            logger.error(f"Failed to download video {object_name}")
            raise DataPrepException(status_code=404, msg=Strings.minio_file_not_found)

        # Extract just the filename part
        filename = pathlib.Path(object_name).name

        return data, filename
    except DataPrepException as ex:
        # Re-raise DataPrepException directly
        raise ex
    except Exception as ex:
        logger.error(f"Error getting video from Minio: {ex}")
        raise DataPrepException(status_code=500, msg=Strings.minio_error)


def get_video_fps_and_frames(video_local_path: pathlib.Path) -> tuple[float, int]:
    """
    Open the video file and get fps and total frames in video

    Args:
        video_local_path (Path) : Path of the video file

    Returns:
        fps, frames (tuple) : A tuple containing float fps and total num of frames (int)
            in the video.
    """
    cap = cv2.VideoCapture(str(video_local_path))
    if not cap.isOpened():
        raise Exception(Strings.video_open_error)

    fps: float = cap.get(cv2.CAP_PROP_FPS)
    total_frames: int = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    cap.release()

    return fps, total_frames

def extract_video_metadata(
    temp_video_path: pathlib.Path,
    bucket_name: str,
    video_id: str,
    video_filename: str,
    chunk_duration: int,
    clip_duration: int,
    tags: List[str] | str = [],
) -> Dict:
    """
    Generates metadata for a video.

    Args:
        temp_video_path (pathlib.Path): Path to the video file on disk
        bucket_name (str): Bucket name where the video is stored
        video_id (str): Directory (video_id) containing the video
        video_filename (str): Name of the video file
        chunk_duration (int): Duration of chunks in seconds
        clip_duration (int): Duration of clips in seconds

    Returns:
        metadata (dict): The generated metadata as a python dict
    """
    metadata = {}
    logger.info("Extracting video metadata...")

    date_time = datetime.datetime.now()
    local_timezone = get_localzone()
    time = date_time.strftime("%H:%M:%S")
    hours, minutes, seconds = map(float, time.split(":"))
    date = date_time.strftime("%Y-%m-%d")
    year, month, day = map(int, date.split("-"))

    # Construct the path to the video in Minio
    video_minio_path = f"{video_id}/{video_filename}"
    video_rel_url = f"/v1/dataprep/videos/download?video_id={video_id}&bucket_name={bucket_name}"
    video_url = f"http://{settings.APP_HOST}:{settings.APP_PORT}{video_rel_url}"

    fps, total_frames = get_video_fps_and_frames(temp_video_path)

    if clip_duration is not None and chunk_duration is not None and clip_duration <= chunk_duration:
        interval_count = 0
        for start_frame, end_frame, start_time, end_time in calculate_intervals(
            fps, total_frames, chunk_duration, clip_duration
        ):
            # Generate key based on video name and interval count
            keyname: str = f"{video_id}_{interval_count}"
            metadata[keyname] = {
                "timestamp": start_time,
                "video_id": video_id,
                "video": video_filename,
                "interval_num": interval_count,
                "date": date,
                "year": year,
                "month": month,
                "day": day,
                "time": time,
                "hours": hours,
                "minutes": minutes,
                "seconds": seconds,
            }

            # Localize the current time to the local timezone of the machine
            current_time_local = date_time.replace(tzinfo=datetime.timezone.utc).astimezone(
                local_timezone
            )
            # Convert the localized time to ISO 8601 format with timezone offset
            iso_date_time = current_time_local.isoformat()
            metadata[keyname]["date_time"] = {"_date": str(iso_date_time)}

            # If tags is a list, convert it to a comma-separated string
            if isinstance(tags, List):
                tags: str = ",".join(tags) if tags else ""

            # Put other metadata into current key
            metadata[keyname].update(
                {
                    "clip_duration": end_time - start_time,
                    "fps": int(fps),
                    "frames_in_clip": end_frame - start_frame,
                    "total_frames": total_frames,
                    "video_temp_path": str(temp_video_path),
                    "video_remote_path": video_minio_path,
                    "bucket_name": bucket_name,
                    "video_url": video_url,
                    "video_rel_url": video_rel_url,
                    "tags": tags,
                }
            )

            interval_count += 1

    return metadata


def save_metadata_at_temp(metadata_temp_path: str, metadata: dict) -> pathlib.Path:
    """
    Dumps the metadata dictionary in json format in a temporary file.

    Args:
        metadata_temp_path (str) : Temporary path where metadata json needs to be saved
        metadata (dict) :  the metadata content as python dict

    Returns:
        metadata_file (Path) : Path of the metadata file location
    """
    metadata_path = pathlib.Path(metadata_temp_path)
    metadata_path.mkdir(parents=True, exist_ok=True)
    metadata_file = metadata_path / settings.METADATA_FILENAME

    logger.info("Saving video metadata to a temporary file...")
    with open(metadata_file, "w") as f:
        json.dump(metadata, f, indent=4)

    logger.info("Metadata saved!")
    return metadata_file


def calculate_intervals(
    fps: float, total_frames: int, chunk_duration: int, clip_duration: int
) -> List[Tuple[int, int, float, float]]:
    """Calculates and returns the starting/ending frame number and
    start and finish time for a clip inside a video chunk.

    Args:
        fps (float) : Frames/sec value for the video
        total_frames (int) : Total number of frames in the video
        chunk_duration (int) : Duration of current chunk of video being processed
        clip_duration (int) : Duration of the clip of interest inside the video chunk

    Returns:
        intervals (list of tuples) : A list containing start frame num, ending frame num, start time and end time
            of the clip in the video chunk being processed.
    """
    intervals = []

    chunk_frames = int(chunk_duration * fps)
    clip_frames = int(clip_duration * fps)

    # Run a loop through starting frame to end frame of full video, one chunk at a time
    for start_frame in range(0, total_frames, chunk_frames):
        end_frame = min(start_frame + clip_frames, total_frames)
        start_time = start_frame / fps
        end_time = end_frame / fps
        intervals.append((start_frame, end_frame, start_time, end_time))

    return intervals


def store_video_metadata(
    bucket_name: str,
    video_id: str,
    video_filename: str,
    temp_video_path: pathlib.Path,
    chunk_duration: int,
    clip_duration: int,
    metadata_temp_path: str,
    tags: List[str] | str = [],
) -> pathlib.Path:
    """
    Store video metadata in dictionary and dump it in a temporary metadata file

    Args:
        bucket_name (str): Bucket name where the video is stored
        video_id (str): Directory containing the video
        video_filename (str): Video filename
        temp_video_path (pathlib.Path): Temporary path to the video file
        chunk_duration (int): Duration of chunks in seconds
        clip_duration (int): Duration of clips in seconds
        metadata_temp_path (str): Path to store metadata

    Returns:
        metadata_file_path (Path): Path of the metadata file location
    """
    metadata: dict = extract_video_metadata(
        temp_video_path=temp_video_path,
        bucket_name=bucket_name,
        video_id=video_id,
        video_filename=video_filename,
        chunk_duration=chunk_duration,
        clip_duration=clip_duration,
        tags=tags,
    )
    metadata_file_path: pathlib.Path = save_metadata_at_temp(metadata_temp_path, metadata)

    return metadata_file_path

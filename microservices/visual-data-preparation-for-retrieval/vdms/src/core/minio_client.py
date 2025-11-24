# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import io
import pathlib
from http import HTTPStatus
from typing import List, Optional, Tuple

from minio import Minio
from minio.error import S3Error

from src.common import DataPrepException, Strings, logger


class MinioClient:
    """Singleton class for Minio Client operations.
    Provides methods to interact with Minio object storage.
    """

    _instance = None

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance.client = None
        return cls._instance

    def __init__(self, endpoint: str, access_key: str, secret_key: str, secure: bool = False):
        """Initialize Minio client if not already initialized.

        Args:
            endpoint (str): Minio server endpoint (host:port)
            access_key (str): Minio access key
            secret_key (str): Minio secret key
            secure (bool, optional): Whether to use HTTPS. Defaults to False.
        """
        if not self.client:
            try:
                self.client = Minio(
                    endpoint, access_key=access_key, secret_key=secret_key, secure=secure
                )
                logger.info(f"Minio client initialized with endpoint: {endpoint}")
            except Exception as ex:
                logger.error(f"Error initializing Minio client: {ex}")
                raise Exception(Strings.minio_conn_error)

    def ensure_bucket_exists(self, bucket_name: str):
        """Check if the specified bucket exists and create it if it doesn't.

        Args:
            bucket_name (str): The name of the bucket to check/create

        Raises:
            Exception: If bucket creation fails or check fails
        """
        try:
            if not self.client.bucket_exists(bucket_name):
                logger.warning(f"Bucket '{bucket_name}' does not exist, creating it...")
                self.client.make_bucket(bucket_name)
                logger.info(f"Successfully created bucket '{bucket_name}'")
            else:
                logger.debug(f"Bucket '{bucket_name}' already exists")
        except S3Error as ex:
            # If bucket name is invalid throw an error which goes as API error response
            if ex.code == "InvalidBucketName":
                raise ValueError(f"Invalid bucket name '{bucket_name}'")

            logger.error(f"Error with bucket operations: {ex}")
            raise Exception(f"Error while ensuring bucket {bucket_name} exists.")

    def list_videos(self, bucket_name: str, prefix: str = "") -> List[str]:
        """List all video files in the specified bucket with the given prefix.

        Args:
            bucket_name (str): The bucket to search in
            prefix (str, optional): Directory prefix to search in. Defaults to "".

        Returns:
            List[str]: List of video filenames

        Raises:
            Exception: If listing objects fails
        """
        try:
            # Ensure prefix ends with a "/" if not empty
            if prefix and not prefix.endswith("/"):
                prefix += "/"

            # List all objects in the bucket with the given prefix
            objects = self.client.list_objects(bucket_name, prefix=prefix, recursive=True)

            # Filter for .mp4 files only
            video_files = []
            for obj in objects:
                if obj.object_name.lower().endswith(".mp4"):
                    # Return only the filename part without the prefix
                    path = pathlib.Path(obj.object_name)
                    video_files.append(path.name)

            return video_files
        except S3Error as ex:
            logger.error(f"Error listing objects in bucket {bucket_name}: {ex}")
            raise Exception(f"Error listing videos in bucket {bucket_name}: {ex}")

    def list_video_directories(self, bucket_name: str) -> List[Tuple[str, List[str]]]:
        """List all directories in the bucket and find video files in each.
        Each directory is treated as a video_id folder.

        Args:
            bucket_name (str): The bucket to search in

        Returns:
            List[Tuple[str, List[str]]]: List of tuples (video_id, list of video files in that directory)

        Raises:
            Exception: If listing objects fails
        """
        try:
            # First get all objects to identify directories
            all_objects = list(self.client.list_objects(bucket_name, recursive=True))

            # Extract unique directories (video_ids)
            directories = set()
            for obj in all_objects:
                path = pathlib.Path(obj.object_name)
                if len(path.parts) > 1:  # Has at least one directory component
                    directories.add(path.parts[0])

            # For each directory, find videos
            result = []
            for directory in directories:
                videos = []
                for obj in all_objects:
                    if obj.object_name.startswith(
                        f"{directory}/"
                    ) and obj.object_name.lower().endswith(".mp4"):
                        videos.append(pathlib.Path(obj.object_name).name)

                if videos:  # Only include directories that have videos
                    result.append((directory, videos))

            return result
        except S3Error as ex:
            logger.error(f"Error listing directories in bucket {bucket_name}: {ex}")
            raise Exception(f"Error listing video directories in bucket {bucket_name}: {ex}")

    def get_video_in_directory(
        self, bucket_name: str, video_id: str, return_prefix: bool = True
    ) -> Optional[str]:
        """Get the first video file found in the specified directory.

        Args:
            bucket_name (str): The bucket to search in
            video_id (str): The directory (video_id) to search in

        Returns:
            Optional[str]: Full object name of the first video found, or None if no videos found

        Raises:
            Exception: If listing objects fails
        """
        try:
            # Ensure video_id ends with "/"
            prefix = f"{video_id}/" if not video_id.endswith("/") else video_id

            # List all objects in the directory
            objects = self.client.list_objects(bucket_name, prefix=prefix, recursive=True)

            # Find the first .mp4 file
            for obj in objects:
                obj_name = obj.object_name
                if obj_name.lower().endswith(".mp4"):

                    if not return_prefix:
                        # return the object name without the prefix
                        obj_name = (
                            obj_name[len(prefix) :] if obj_name.startswith(prefix) else obj_name
                        )

                    return obj_name

            return None
        except S3Error as ex:
            logger.error(f"Error getting video in directory {video_id}: {ex}")
            raise Exception(f"Error getting video in directory {video_id}: {ex}")

    def download_video_stream(self, bucket_name: str, object_name: str) -> Optional[io.BytesIO]:
        """Download a video file as a stream.

        Args:
            bucket_name (str): The bucket containing the video
            object_name (str): The object name (path) of the video

        Returns:
            Optional[io.BytesIO]: BytesIO stream containing the video data

        Raises:
            Exception: If getting the object fails
        """
        try:
            response = self.client.get_object(bucket_name, object_name)
            data = io.BytesIO()
            for d in response.stream(32 * 1024):
                data.write(d)
            data.seek(0)
            response.close()
            response.release_conn()
            return data
        except S3Error as ex:
            logger.error(f"Error downloading video {object_name} from bucket {bucket_name}: {ex}")
            raise Exception(f"Error downloading video: {ex}")

    def get_object_size(self, bucket_name: str, object_name: str) -> int:
        """Get the size of an object in bytes.

        Args:
            bucket_name (str): The bucket containing the object
            object_name (str): The object name

        Returns:
            int: Size of the object in bytes

        Raises:
            Exception: If getting the object stats fails
        """
        try:
            obj_stat = self.client.stat_object(bucket_name, object_name)
            return obj_stat.size
        except S3Error as ex:
            logger.error(f"Error getting size of {object_name} from bucket {bucket_name}: {ex}")
            raise Exception(f"Error getting object size: {ex}")

    def list_all_videos(self, bucket_name: str) -> List[dict]:
        """List all videos in the bucket with one video per video_id directory.

        Args:
            bucket_name (str): The bucket to search in

        Returns:
            List[dict]: List of dictionaries with video information including video_id, video_name,
                        video_path and creation_ts

        Raises:
            Exception: If listing objects fails
        """
        try:
            # Get all objects in the bucket
            all_objects = list(self.client.list_objects(bucket_name, recursive=True))

            # Find video files (expecting one video per directory)
            result = []
            for obj in all_objects:
                # Check if it's a video file (.mp4)
                if obj.object_name.lower().endswith(".mp4"):
                    # Parse the path to get video_id and video_name
                    path = pathlib.Path(obj.object_name)

                    # Only process if the path has a directory structure (video_id/filename)
                    if len(path.parts) > 1:
                        video_id = path.parts[0]
                        video_name = path.name

                        # Get metadata including creation timestamp
                        metadata = self.get_object_metadata(bucket_name, obj.object_name)

                        video_info = {
                            "video_id": video_id,
                            "video_name": video_name,
                            "video_path": obj.object_name,
                            "creation_ts": metadata["creation_time"],
                        }

                        result.append(video_info)

            return result

        except S3Error as ex:
            logger.error(f"Error listing videos in bucket {bucket_name}: {ex}")
            raise Exception(f"Error listing videos in bucket {bucket_name}: {ex}")

    def validate_object_name(self, video_id: str, video_name: str) -> bool:
        """Validate video_id and video_name based on Minio object naming rules.

        Args:
            video_id (str): The video ID (directory part)
            video_name (str): The video filename

        Returns:
            bool: True if valid, False otherwise
        """
        try:
            logger.debug(f"Validating object name: video_id={video_id}, video_name={video_name}")

            # Check for empty strings
            if not video_id or not video_name:
                return False

            # Check if video_name has a valid video extension (.mp4)
            if not video_name.lower().endswith(".mp4"):
                return False

            # Check for invalid characters in object names (basic check)
            invalid_chars = ["\\", "?", "#", "..", "/"]
            for char in invalid_chars:
                if char in video_id or char in video_name:
                    return False

            # Check total length (Minio has a 1024 character limit for object names)
            object_name = f"{video_id}/{video_name}"
            if len(object_name) > 1024:
                return False

            return True
        except Exception as ex:
            logger.error(f"Error validating object name: {ex}")
            return False

    def object_exists(self, bucket_name: str, video_id: str, video_name: str) -> bool:
        """Check if an object exists in the bucket.

        Args:
            bucket_name (str): The bucket to check in
            video_id (str): The video ID (directory part)
            video_name (str): The video filename

        Returns:
            bool: True if the object exists, False otherwise
        """
        try:
            object_name = f"{video_id}/{video_name}"
            self.client.stat_object(bucket_name, object_name)
            return True
        except S3Error:
            return False
        except Exception as ex:
            logger.error(f"Error checking if object exists: {ex}")
            return False

    def get_object_metadata(self, bucket_name: str, object_name: str) -> dict:
        """Get metadata information for an object, including creation timestamp.

        Args:
            bucket_name (str): The bucket containing the object
            object_name (str): The object name (path)

        Returns:
            dict: Dictionary with metadata information including creation timestamp

        Raises:
            Exception: If getting object stats fails
        """
        try:
            obj_stat = self.client.stat_object(bucket_name, object_name)
            return {
                "size": obj_stat.size,
                "creation_time": obj_stat.last_modified.isoformat(),
                "etag": obj_stat.etag,
                "content_type": obj_stat.content_type,
            }
        except S3Error as ex:
            logger.error(
                f"Error getting metadata for {object_name} from bucket {bucket_name}: {ex}"
            )
            raise Exception(f"Error getting object metadata: {ex}")

    def upload_video(self, bucket_name: str, object_name: str, data, file_size=None) -> None:
        """Upload a video file to Minio storage.

        Args:
            bucket_name (str): The bucket to upload to
            object_name (str): The object name including path (e.g., "video_id/filename.mp4")
            data: File-like object containing the video data
            file_size (int, optional): The size of the file in bytes. If not provided,
                                       it will be determined from the data object.

        Raises:
            Exception: If uploading the file fails or bucket doesn't exist
        """
        try:
            # Check if the bucket exists
            self.ensure_bucket_exists(bucket_name)

            # Upload the file
            self.client.put_object(
                bucket_name=bucket_name,
                object_name=object_name,
                data=data,
                length=file_size,
                content_type="video/mp4",
            )

            logger.info(f"Video uploaded successfully as {object_name} in bucket {bucket_name}")
        except S3Error as ex:
            logger.error(f"Error uploading video to Minio: {ex}")
            raise Exception(f"Error uploading video to Minio: {ex}")

    def save_metadata_file(
        self,
        bucket_name: str,
        metadata_content: bytes,
        video_id: str,
        filename: str = "metadata.json",
    ) -> str:
        """Save metadata file to minio.

        Args:
            bucket_name (str): The bucket to save to
            metadata_content (bytes): The content to save
            video_id (str): The directory (video_id) to save in
            filename (str, optional): The filename. Defaults to "metadata.json".

        Returns:
            str: The full object name of the saved file

        Raises:
            Exception: If putting the object fails or bucket doesn't exist
        """
        try:
            # Check if the bucket exists
            self.ensure_bucket_exists(bucket_name)

            # Prepare object name
            object_name = f"{video_id}/{filename}"

            # Create BytesIO object
            data = io.BytesIO(metadata_content)
            length = len(metadata_content)

            # Upload the file
            self.client.put_object(
                bucket_name=bucket_name,
                object_name=object_name,
                data=data,
                length=length,
                content_type="application/json",
            )

            logger.info(f"Metadata file saved as {object_name} in bucket {bucket_name}")
            return object_name
        except S3Error as ex:
            logger.error(f"Error saving metadata file: {ex}")
            raise Exception(f"Error saving metadata file: {ex}")

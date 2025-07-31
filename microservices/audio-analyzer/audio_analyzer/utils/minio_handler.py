# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import traceback
from pathlib import Path
from typing import Optional, Tuple

from minio import Minio
from minio.error import S3Error

from audio_analyzer.core.settings import settings
from audio_analyzer.utils.logger import logger


class MinioHandler:
    """
    Handler for MinIO operations.
    Provides functionality to interact with MinIO object storage for
    video retrieval and transcript storage.
    """

    _client: Optional[Minio] = None

    @classmethod
    def get_client(cls) -> Minio:
        """
        Get or create a MinIO client using the settings.

        Returns:
            Minio: A MinIO client instance
        """
        if cls._client is None:
            try:
                logger.debug(f"Creating MinIO client with endpoint: {settings.MINIO_ENDPOINT}")
                cls._client = Minio(
                    settings.MINIO_ENDPOINT,
                    access_key=settings.MINIO_ACCESS_KEY,
                    secret_key=settings.MINIO_SECRET_KEY,
                    secure=settings.MINIO_SECURE,
                )
                logger.info("MinIO client created successfully")
            except Exception as e:
                logger.error(f"Failed to create MinIO client: {e}")
                logger.debug(f"Error details: {traceback.format_exc()}")
                raise RuntimeError(f"Failed to create MinIO client: {e}")
        
        return cls._client

    @classmethod
    def ensure_bucket_exists(cls, bucket_name: str) -> bool:
        """
        Check if a bucket exists without creating it.
        
        Args:
            bucket_name: Name of the bucket to check
            
        Returns:
            bool: True if bucket exists, False otherwise
        """
        client = cls.get_client()
        
        try:
            if client.bucket_exists(bucket_name):
                logger.debug(f"Bucket {bucket_name} exists")
                return True
            else:
                logger.warning(f"Bucket {bucket_name} does not exist")
                return False
        except Exception as e:
            logger.error(f"Failed to check if bucket {bucket_name} exists: {e}")
            logger.debug(f"Error details: {traceback.format_exc()}")
            return False

    @classmethod
    async def get_video_from_minio(cls, bucket_name: str, video_id: str, video_name: str) -> Tuple[Path, Optional[str]]:
        """
        Retrieve a video file from MinIO and save it to the local filesystem.

        Args:
            bucket_name: Name of the bucket where the video is stored
            video_id: Prefix/ID of the video object in the bucket
            video_name: Name of the video file

        Returns:
            Tuple[Path, Optional[str]]: Path to the downloaded file and error message if any
        """
        client = cls.get_client()
        
        # Construct the object name with the video_id prefix and video_name
        object_name = f"{video_id}/{video_name}" if video_id else video_name
        
        # Generate a local file path to save the video to
        local_path = Path(settings.UPLOAD_DIR) / video_name
        
        try:
            logger.info(f"Retrieving video {object_name} from bucket {bucket_name}")
            
            if not client.bucket_exists(bucket_name):
                error_msg = f"Bucket {bucket_name} does not exist"
                logger.error(error_msg)
                return None, error_msg

            client.fget_object(bucket_name, object_name, str(local_path))
            
            logger.debug(f"Video downloaded successfully to {local_path}")
            return local_path, None
            
        except S3Error as e:
            error_msg = f"S3 error retrieving video: {e}"
            logger.error(error_msg)
            logger.debug(f"Error details: {traceback.format_exc()}")
            return None, error_msg
        except Exception as e:
            error_msg = f"Error retrieving video: {e}"
            logger.error(error_msg)
            logger.debug(f"Error details: {traceback.format_exc()}")
            return None, error_msg

    @classmethod
    def save_transcript_to_minio(
        cls, 
        file_path: Path, 
        bucket_name: str, 
        object_name: str
    ) -> Tuple[bool, Optional[str]]:
        """
        Upload a transcript file to MinIO.

        Args:
            file_path: Path to the local transcript file
            bucket_name: Name of the bucket to upload to
            object_name: Name to use for the object in the bucket

        Returns:
            Tuple[bool, Optional[str]]: Success status and error message if any
        """
        client = cls.get_client()
        
        try:
            logger.info(f"Uploading transcript {file_path} to MinIO bucket {bucket_name}")
            
            if not cls.ensure_bucket_exists(bucket_name):
                error_msg = f"Failed to ensure bucket {bucket_name} exists"
                logger.error(error_msg)
                return False, error_msg
                
            client.fput_object(
                bucket_name,
                object_name,
                str(file_path),
                content_type="text/plain" if file_path.suffix == '.txt' else "text/srt"
            )
            
            logger.debug(f"Transcript uploaded successfully to {bucket_name}/{object_name}")
            return True, None
            
        except S3Error as e:
            error_msg = f"S3 error uploading transcript: {e}"
            logger.error(error_msg)
            logger.debug(f"Error details: {traceback.format_exc()}")
            return False, error_msg
        except Exception as e:
            error_msg = f"Error uploading transcript: {e}"
            logger.error(error_msg)
            logger.debug(f"Error details: {traceback.format_exc()}")
            return False, error_msg
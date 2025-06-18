# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import pathlib
from io import BytesIO

from minio import Minio
from minio.error import S3Error


class MinioClient:
    """Creates a singleton Minio Client Object and contains helper methods
    to work with Minio Server.
    """

    client = None

    file_ext = {
        "frame": "jpeg",
        "metadata": "json"
    }

    @classmethod
    def get_client(cls, minio_server: str, access_key: str, secret_key: str) -> Minio:
        """Returns an object of Minio Client if none exists already"""
        try:
            if not cls.client:
                cls.client = Minio(
                    minio_server,
                    access_key,
                    secret_key,
                    secure=False,
                )
            return cls.client
        except S3Error as ex:
            raise ex

    @staticmethod
    def get_destination_file(video_id: str, chunk_id: int, frame_id: int, file_type: str = "frame") -> str:
        """Creates a destination file name with following format:
        For frame:
            chunk_<chunk_id>_frame_<frame_id>.jpg
        For metadata:
            chunk_<chunk_id>_frame_<frame_id>.json

        Returns:
            destination_file_name (str) : File name used to store data on Minio Server
        """
        
        try:
            file_ext = MinioClient.file_ext[file_type]
        except KeyError:
            raise Exception("File type not supported.")
        
        file_path = pathlib.Path(video_id) / file_type

        # Extract primary name and extension from given file name
        file_name = f"chunk_{chunk_id}_frame_{frame_id}.{file_ext}"
        destination_file_name = str(file_path / file_name)
        
        return destination_file_name
    
    @staticmethod
    def save_object(client: Minio, bucket_name: str, object_name: str, data: BytesIO, length: int = 0) -> None:
        """ Save the provided data as a resource on minio at the given bucket name.
        """

        if not length:
            length = data.tell()
            data.seek(0)
            
        try:
            client.put_object(
                bucket_name=bucket_name,
                object_name=object_name,
                data=data,
                length=length,
                content_type="application/octet-stream"
            )

        except S3Error as err:
            raise Exception(f"Error ocurred during saving to bucket: {err}")



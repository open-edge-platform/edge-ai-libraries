# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import pathlib
import random
import string

from minio import Minio
import shortuuid
from minio.error import S3Error

from minio_store.util import Settings

settings = Settings()


class DataStore:
    """Creates a singleton Minio Client Object and contains helper methods
    to work with Minio Server.
    """

    client = None

    @classmethod
    def get_client(cls):
        """Returns an object of Minio Client if none exists already"""
        try:
            if not cls.client:
                minio_server = f"{settings.MINIO_HOST}:{settings.MINIO_API_PORT}"
                cls.client = Minio(
                    minio_server,
                    access_key=settings.MINIO_ACCESS_KEY,
                    secret_key=settings.MINIO_SECRET_KEY,
                    secure=False,
                )
                print("Create new instance of MINIO client")
            return cls.client
        except S3Error as ex:
            raise ex

    @staticmethod
    def get_destination_file(file_name: str) -> str:
        """Creates a destination file name with following format:
        <prefix>_<orig-file-name>_<suffix>_<file-extension>

        Args:
            file_name (str) : File name with extension for a source file being uploaded.

        Returns:
            destination_file_name (str) : File name used to store data on Minio Server
        """
        suffix = str(shortuuid.uuid())
        prefix = settings.OBJECT_PREFIX

        # Replace any whitespace in filename
        file_name = file_name.replace(" ", "-")
        # Extract primary name and extension from given file name
        file_path = pathlib.Path(file_name)
        f_primary_name, f_ext = file_path.stem, file_path.suffix
        parent_path = file_name.replace(f"{f_primary_name}{f_ext}", "")
        
        destination_file_name = f"{parent_path}{prefix}_{f_primary_name}_{suffix}{f_ext}"
        return destination_file_name

# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from boto3.session import Session
from botocore.exceptions import NoCredentialsError, ClientError
from fastapi import UploadFile, HTTPException
from http import HTTPStatus
from .logger import logger
from .config import Settings
import pathlib
import shortuuid

config = Settings()

class DataStore:

    client = None
    bucket = config.DEFAULT_BUCKET

    @classmethod
    def get_client(cls):
        """
        Retrieves or initializes an S3 client using boto3.
        This method creates a boto3 session and initializes an S3 client
        if it has not already been created. The client is configured to
        connect to a MinIO server using credentials and endpoint details
        from the configuration.

        Returns:
            botocore.client.S3: An S3 client instance.

        Raises:
            NoCredentialsError: If AWS credentials are not available.
            Exception: For any other exceptions that occur during client initialization.
        """
        try:
            if cls.client is None:
                # Create a boto3 session
                session = Session(
                    aws_access_key_id=config.MINIO_ACCESS_KEY,
                    aws_secret_access_key=config.MINIO_SECRET_KEY,
                )

                cls.client = session.client(
                    service_name='s3',
                    endpoint_url=f'http://{config.MINIO_HOST}:{config.MINIO_API_PORT}',
                )

            return cls.client

        except NoCredentialsError as ex:
            logger.error("Credentials not available")
            raise ex

        except Exception as ex:
            raise ex

    @classmethod
    def bucket_exists(cls, bucket_name):
        """
        Checks if an bucket exists.
        This method attempts to determine the existence of an bucket by
        performing a `head_bucket` operation using the S3 client. If the bucket
        exists, the method returns True. If the bucket does not exist or an
        error occurs, it returns False or raises an exception.

        Args:
            bucket_name (str): The name of the S3 bucket to check.

        Returns:
            bool: True if the bucket exists, False otherwise.

        Raises:
            Exception: If an unexpected error occurs during the operation.
        """
        try:
            client = cls.get_client()
            client.head_bucket(Bucket=bucket_name)
            return True

        except ClientError:
            # An error occurred (404) when calling the HeadBucket operation: Not Found"
            # Return False if the bucket does not exist
            return False

        except Exception as e:
            logger.error(f'Error checking bucket existence: {e}')
            raise e

    @classmethod
    def create_bucket(cls, bucket_name):
        """
        Creates an bucket if it does not already exist.

        Args:
            bucket_name (str): The name of the bucket to create.

        Raises:
            Exception: If an error occurs during the bucket creation process.
        """

        try:
            client = cls.get_client()
            if not cls.bucket_exists(bucket_name):
                client.create_bucket(Bucket=bucket_name)
                logger.info(f'Bucket {bucket_name} not exist. Created it successfully.')

        except Exception as e:
            logger.error(f'Error creating bucket: {e}')
            raise e

    @classmethod
    def get_document_size(cls, bucket=bucket, file_name=None):
        """
        Retrieves the size of a specified document in a given bucket.

        Args:
            bucket (str): The name of the bucket where the document is stored.
            file_name (str, optional): The name of the file whose size is to be retrieved.

        Returns:
            int: The size of the file in bytes.

        Raises:
            HTTPException: If the bucket does not exist or is empty.
            FileNotFoundError: If the specified file does not exist in the bucket.
            Exception: For any other errors encountered during the operation.
        """
        try:
            client = cls.get_client()

            # Check if the bucket exists, if not create it
            if not cls.bucket_exists(bucket):
                raise HTTPException(status_code=HTTPStatus.NOT_FOUND, detail=f"Bucket {bucket} does not exist.")

            # Check if the bucket is empty
            response = client.list_objects_v2(Bucket=bucket)
            if 'Contents' not in response or len(response['Contents']) == 0:
                logger.error(f'Bucket {bucket} is empty.')
                raise HTTPException(status_code=HTTPStatus.NOT_FOUND, detail="No files present in the bucket!")

            # Get the size of the file
            response = client.head_object(Bucket=bucket, Key=file_name)
            file_size = response['ContentLength']

            return file_size

        except ClientError as e:
            if e.response['Error']['Code'] == '404':
                logger.error(f"The object {file_name} does not exist.")
                raise FileNotFoundError(f"The object {file_name} does not exist.")
            else:
                logger.error(f"Error deleting file: {e}")
                raise e

        except Exception as e:
            logger.error(f"Error getting file size: {e}")
            raise e

    @classmethod
    def get_document(cls, bucket=bucket):
        """
        Retrieves a list of document keys from the specified bucket. If the bucket does not exist, it is created.

        Args:
            bucket (str): The name of the bucket to retrieve documents from.

        Returns:
            list: A list of document keys (filenames) in the specified bucket. Returns an empty list if no files are found.

        Raises:
            Exception: If an error occurs while retrieving documents.
        """
        try:
            client = cls.get_client()

            # Check if the bucket exists, if not create it
            if not cls.bucket_exists(bucket):
                cls.create_bucket(bucket)

            response = client.list_objects_v2(Bucket=bucket)
            if 'Contents' in response:
                files = [obj['Key'] for obj in response['Contents']]
            else:
                logger.info("No files found.")
                files = []

            return files

        except Exception as ex:
            logger.error(f"Error retrieving documents: {ex}")
            raise ex

    @classmethod
    def upload_document(cls, file_object: UploadFile, bucket=bucket, object_name=None):
        """
        Uploads a document to the specified bucket in the object storage.
        This method checks if the specified bucket exists, creates it if necessary,
        and uploads the provided file object to the bucket. If no object name is
        provided, a destination file name is generated.

        Args:
            file_object (UploadFile): The file object to be uploaded.
            bucket (str, optional): The name of the bucket where the file will be uploaded.
                Defaults to the `bucket` variable.
            object_name (str, optional): The name of the object in the bucket.
                If None, a destination file name is generated.

        Returns:
            dict: A dictionary containing the bucket name and the uploaded file's object name.

        Raises:
            Exception: If an error occurs during the upload process.
        """
        try:
            client = cls.get_client()
            file_name = file_object.filename

            # Check if the bucket exists, if not create it
            if not cls.bucket_exists(bucket):
                cls.create_bucket(bucket)

            if object_name is None:
                object_name = cls.get_destination_file(file_name)

            client.put_object(Bucket=bucket,
                              Key=object_name,
                              Body=file_object.file
            )

            logger.info(f"File {file_name} uploaded successfully.")

            return {"bucket": bucket, "file": object_name}

        except Exception as e:
            logger.error (f"Error uploading file: {e}")
            raise e

    @classmethod
    def delete_document(cls, bucket=bucket, file_name=None, delete_all=False):
        """
        Deletes a document from an bucket. Supports deleting a specific file or all files in the bucket.

        Args:
            bucket (str): The name of the S3 bucket.
            file_name (str, optional): The name of the file to delete. Required if `delete_all` is False.
            delete_all (bool, optional): If True, deletes all files in the bucket. Defaults to False.

        Raises:
            HTTPException: If the bucket does not exist or is empty.
            ValueError: If `file_name` is not provided when `delete_all` is False.
            FileNotFoundError: If the specified file does not exist in the bucket.
            ClientError: If an error occurs while interacting with the S3 client.
            Exception: For any other unexpected errors.
        """
        try:
            client = cls.get_client()

            # Check if the bucket exists, if not return error
            if not cls.bucket_exists(bucket):
                raise HTTPException(status_code=HTTPStatus.NOT_FOUND, detail=f"Bucket {bucket} does not exist.")

            # Check if the bucket is empty
            response = client.list_objects_v2(Bucket=bucket)
            if 'Contents' not in response or len(response['Contents']) == 0:
                logger.error(f'Bucket {bucket} is empty.')
                raise HTTPException(status_code=HTTPStatus.NOT_FOUND, detail="No files present in the bucket!")

            if delete_all:
                # Collect all objects key
                objects_to_delete = [{'Key': obj['Key']} for obj in response['Contents']]

                # Delete objects in a single request
                # S3 API provides the delete_objects method, which allows to delete multiple objects in a single request.
                # This method can delete up to 1,000 objects per request
                # TODO: If more than 1000 objects, we need to handle pagination and delete in batches of 1000.
                client.delete_objects(Bucket=bucket, Delete={'Objects': objects_to_delete})

                logger.info("All files deleted successfully.")
            elif file_name:
                client.head_object(Bucket=bucket, Key=file_name)
                client.delete_object(Bucket=bucket, Key=file_name)
                logger.info(f"File {file_name} deleted successfully.")
            else:
                raise ValueError("Invalid Arguments: file_name is required if delete_all is False.")

        except ClientError as e:
            if e.response['Error']['Code'] == '404':
                logger.error(f"The object {file_name} does not exist.")
                raise FileNotFoundError(f"The object {file_name} does not exist.")
            else:
                logger.error(f"Error deleting file: {e}")
                raise e

        except Exception as e:
            logger.error(f"Error deleting file: {e}")
            raise e

    @classmethod
    async def download_document(cls, bucket=bucket, file_name=None):
        """
        Downloads a document from the specified bucket.
        This method retrieves an object from the given bucket using the specified file name.
        If the bucket does not exist, an HTTPException is raised. If the object does not exist,
        a FileNotFoundError is raised.

        Args:
            bucket (str): The name of the bucket to download the document from.
            file_name (str, optional): The name of the file to download. Defaults to None.

        Returns:
            bytes: The content of the downloaded file.

        Raises:
            HTTPException: If the specified bucket does not exist.
            FileNotFoundError: If the specified file does not exist in the bucket.
            ClientError: If an error occurs while interacting with the client.
            Exception: For any other unexpected errors.
        """
        try:
            client = cls.get_client()

            # Check if the bucket exists, if not create it
            if not cls.bucket_exists(bucket):
                raise HTTPException(status_code=HTTPStatus.NOT_FOUND, detail=f"Bucket {bucket} does not exist.")

            response = client.get_object(Bucket=bucket, Key=file_name)
            return response['Body']

        except ClientError as e:
            if e.response['Error']['Code'] == '404' or e.response['Error']['Code'] == 'NoSuchKey':
                logger.error(f"The object {file_name} does not exist.")
                raise FileNotFoundError(f"The object {file_name} does not exist.")
            else:
                logger.error(f"Error downloading file: {e}")
                raise e

        except Exception as e:
            logger.error(f"Error downloading file: {e}")
            raise e

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
        prefix = config.OBJECT_PREFIX

        # Replace any whitespace in filename
        file_name = file_name.replace(" ", "-")
        # Extract primary name and extension from given file name
        file_path = pathlib.Path(file_name)
        f_primary_name, f_ext = file_path.stem, file_path.suffix
        parent_path = file_name.replace(f"{f_primary_name}{f_ext}", "")

        destination_file_name = f"{parent_path}{prefix}_{f_primary_name}_{suffix}{f_ext}"
        return destination_file_name

"""This class provides a means of accessing Minio Object Storage to store model artifacts."""
import os
from io import BytesIO
import urllib3
import minio
from utils.logging_config import logger
from utils.app_utils import get_bool


class MinioManager():
    """A class for managing interactions with minio object storage"""
    _minio_client = None

    def __new__(cls):
        if not hasattr(cls, 'instance'):
            logger.debug("Created a new MinioManager object")
            cls.instance = super(MinioManager, cls).__new__(cls)
        else:
            logger.debug("Used existing MinioManager object")

        cls.instance.bucket_name = os.environ["MINIO_BUCKET_NAME"]
        return cls.instance

    def connect_to_obj_storage(self):
        """
        Connect to minio object storage via localhost or container name
        """
        try:
            is_https_mode_enabled = get_bool(os.getenv("ENABLE_HTTPS_MODE", "True"), ignore_empty=True)
            hostname = os.environ["MINIO_HOSTNAME"]
            server_port = os.environ["MINIO_SERVER_PORT"]
            h_client = None
            use_secure_conn = False
            check_cert = False

            if self._minio_client is None:
                if is_https_mode_enabled:
                    use_secure_conn = True
                    check_cert = True
                    h_client=urllib3.PoolManager(
                        cert_reqs='CERT_REQUIRED',
                        ca_certs= os.getenv("CA_CERT"))

                self._minio_client = minio.Minio(f'{hostname}:{server_port}',
                                        access_key=os.environ["MINIO_ACCESS_KEY"],
                                        secret_key=os.environ["MINIO_SECRET_KEY"],
                                        cert_check=check_cert,
                                        secure=use_secure_conn,
                                        http_client=h_client)

                logger.debug(f"Connected to MinIO service at : {hostname} via secure connection: {bool(h_client)}")

        except Exception as error:
            logger.error(f"MinIO server connection failed.\n{error}")

    def get_object(self, object_name) -> bytes:
        """Get an object from storage

        Args:
            object_name (str): The name of the object.
            The name could include the prefix directory and the name of the object.

        Returns:
            bytes: The bytes of the object.
        """
        self.connect_to_obj_storage()

        # Get the object from Minio
        response = self._minio_client.get_object(self.bucket_name, object_name)
        # Create a BytesIO object to hold the object data
        bytes_io = BytesIO()
        bytes_io.write(response.read())

        # Close connection
        response.close()
        response.release_conn()

        # Return the object data
        return bytes_io.getvalue()


    def store_data(self, prefix_dir: str, file_name: str, file_path: str = None, file_object = None):
        """store files in object storage"""
        model_os_file_url = ""
        self.connect_to_obj_storage()

        if not self._minio_client.bucket_exists(self.bucket_name):
            self._minio_client.make_bucket(self.bucket_name)

        if file_path:
            _ = self._minio_client.fput_object(bucket_name=self.bucket_name,
                                                object_name=prefix_dir+"/"+file_name,
                                                file_path=file_path)

        elif file_object:
            _ = self._minio_client.put_object(bucket_name=self.bucket_name, object_name=prefix_dir+"/"+file_name, data=file_object, length=os.fstat(file_object.fileno()).st_size)

        # Get the object's file path.
        model_os_file_url = f"minio://{self.bucket_name}/{prefix_dir}/{file_name}"

        return model_os_file_url

    def delete_data(self, prefix_dir: str, file_name: str) -> bool:
        """_summary_

        Args:
            prefix_dir (str): _description_
            file_name (str): _description_

        Returns:
            bool: Is the file deleted successfully
        """
        self.connect_to_obj_storage()

        try:
            # Delete an object
            self._minio_client.remove_object(
                bucket_name=self.bucket_name, object_name=prefix_dir+"/"+file_name)
            return True
        except minio.error.S3Error as err:
            logger.error(f"{err.__class__.__name__}\n{err.message}")
            return False
        except minio.error.InvalidResponseError as err:
            logger.error(f"{err.__class__.__name__}\n{err}")
            return False

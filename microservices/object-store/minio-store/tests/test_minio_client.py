# third-party installed packages
import pytest
from minio import Minio
from minio.error import S3Error

# application packages
from minio_store.store import DataStore


def test_minio_client_exception():
    with pytest.raises(Exception):
        DataStore.get_client("test")


def test_minio_client_s3error(mocker):
    mocker.patch.object(S3Error, "__init__", return_value=None)
    mocker.patch.object(Minio, "__init__", side_effect=S3Error)
    with pytest.raises(S3Error):
        DataStore.client = None
        DataStore.get_client()


def test_store_client_fixture(store_client):
    assert isinstance(store_client, Minio)

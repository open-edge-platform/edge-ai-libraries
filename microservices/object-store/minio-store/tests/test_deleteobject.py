# python built-in packages
from http import HTTPStatus

# third-party installed packages
from minio import Minio
from minio.error import S3Error

# application packages
from tests.conftest import verify_and_get_uploaded_file


def test_delete_data(test_client, test_file):
    # Upload sample file in default bucket
    response = test_client.post("/data", files=test_file)
    assert response.status_code == HTTPStatus.CREATED

    # Get uploaded filename
    uploaded_file = verify_and_get_uploaded_file(response)

    # Try deleting without any params
    response = test_client.delete(url="/data", params={})
    assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY

    # Delete the uploaded file
    response = test_client.delete(url="/data", params={"file_name": uploaded_file})
    assert response.status_code == HTTPStatus.NO_CONTENT


def test_delete_in_new_bucket(test_client, test_file, new_bucket):
    # Upload test file in a new bucket
    response = test_client.post(f"/data?bucket_name={new_bucket}", files=test_file)
    assert response.status_code == HTTPStatus.CREATED

    # Get the uploaded file and delete it
    uploaded_file = verify_and_get_uploaded_file(response)
    response = test_client.delete(
        url="/data", params={"bucket_name": new_bucket, "file_name": uploaded_file}
    )
    assert response.status_code == HTTPStatus.NO_CONTENT


def test_delete_all_new_bucket(test_client, test_file, new_bucket):
    # Upload a test file in same bucket
    response = test_client.post(f"/data?bucket_name={new_bucket}", files=test_file)
    assert response.status_code == HTTPStatus.CREATED

    # Delete all files in bucket
    response = test_client.delete(
        url="/data", params={"bucket_name": new_bucket, "delete_all": True}
    )
    assert response.status_code == HTTPStatus.NO_CONTENT

    # Test delete from an empty bucket
    response = test_client.delete(
        url="/data", params={"bucket_name": new_bucket, "delete_all": True}
    )
    assert response.status_code == HTTPStatus.NOT_FOUND


def test_delete_invalid_bucket(test_client):
    response = test_client.delete(
        url="/data", params={"bucket_name": "invalid", "delete_all": True}
    )
    assert response.status_code == HTTPStatus.NOT_FOUND


def test_delete_data_exception(test_client, mocker, new_bucket):
    mocker.patch.object(Minio, "list_objects", side_effect=Exception)
    response = test_client.delete(
        url="/data", params={"bucket_name": new_bucket, "delete_all": True}
    )
    assert response.status_code == HTTPStatus.INTERNAL_SERVER_ERROR


def test_delete_s3error_filenotfound(test_client):
    # Test NoSuchKey Error by deleting a non existing file
    response = test_client.delete(url="/data", params={"file_name": "invalid"})
    assert response.status_code == HTTPStatus.NOT_FOUND


def test_delete_generic_s3error(test_client, mocker, new_bucket):
    # Test BadGateway error due to S3Error exception
    mocker.patch.object(S3Error, "__init__", return_value=None)
    mocker.patch.object(Minio, "list_objects", side_effect=S3Error)
    mocker.patch("minio.error.S3Error.code", new="")
    response = test_client.delete(
        url="/data", params={"bucket_name": new_bucket, "delete_all": True}
    )
    assert response.status_code == HTTPStatus.BAD_GATEWAY


def test_delete_error_list(test_client, mocker, new_bucket):
    mocker.patch.object(Minio, "list_objects", return_value=[{"object_name": "test"}])
    mocker.patch.object(Minio, "remove_objects", return_value=["error"])
    response = test_client.delete(
        url="/data", params={"bucket_name": new_bucket, "delete_all": True}
    )
    assert response.status_code == HTTPStatus.BAD_GATEWAY


def test_delete_from_invalid_bucket(test_client):
    # Empty bucket names
    response = test_client.delete(url="/data", params={"bucket_name": ""})
    assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY

    response = test_client.delete(url="/data", params={"bucket_name": " "})
    assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY

    # bucket name shorter than 3 chars
    response = test_client.delete(url="/data", params={"bucket_name": "nv"})
    assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY

    # Non-existing bucket
    response = test_client.delete(url="/data", params={"bucket_name": "invalid-bucket"})
    assert response.status_code == HTTPStatus.BAD_REQUEST

    # Unsupported bucket name: Underscores are not allowed as bucket name in s3 API
    response = test_client.delete(url="/data", params={"bucket_name": "invalid_bucket"})
    assert response.status_code == HTTPStatus.BAD_GATEWAY

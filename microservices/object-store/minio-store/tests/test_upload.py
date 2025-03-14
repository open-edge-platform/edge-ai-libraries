# Python built-in packages
from http import HTTPStatus

# third-party installed packages
from minio import Minio
from minio.error import S3Error

# application packages
from tests.conftest import verify_and_get_uploaded_file


def test_upload_data(test_client, test_file):
    uploaded_files = []

    # Upload a file in default bucket
    response = test_client.post("/data", files=test_file)
    assert response.status_code == HTTPStatus.CREATED

    uploaded_files.append(verify_and_get_uploaded_file(response))

    # Upload a file in default bucket with a new name
    destination_filename = "new-name.yaml"
    response = test_client.post(
        f"/data?dest_file_name={destination_filename}",
        files=test_file,
    )
    assert response.status_code == HTTPStatus.CREATED

    uploaded_files.append(verify_and_get_uploaded_file(response))

    # Delete the uploaded files from default bucket
    for file in uploaded_files:
        response = test_client.delete(url="/data", params={"file_name": file})
        assert response.status_code == HTTPStatus.NO_CONTENT


def test_upload_invalid_bucket(test_client, test_file):
    response = test_client.post(f"/data?bucket_name=", files=test_file)
    assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY

    response = test_client.post(f"/data?bucket_name=  ", files=test_file)
    assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY

    response = test_client.post(f"/data?bucket_name=nv", files=test_file)
    assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY

    response = test_client.post(f"/data?bucket_name=invalid_bucket", files=test_file)
    assert response.status_code == HTTPStatus.BAD_GATEWAY


def test_upload_new_bucket(test_client, test_file, new_bucket):
    # Upload file in a new bucket
    response = test_client.post(f"/data?bucket_name={new_bucket}", files=test_file)
    assert response.status_code == HTTPStatus.CREATED

    # Upload file in a new bucket with new name
    destination_filename = "new-name.yaml"
    response = test_client.post(
        f"/data?bucket_name={new_bucket}&dest_file_name={destination_filename}",
        files=test_file,
    )
    assert response.status_code == HTTPStatus.CREATED

    # Delete all files in the new bucket
    response = test_client.delete(
        url="/data", params={"bucket_name": new_bucket, "delete_all": True}
    )
    assert response.status_code == HTTPStatus.NO_CONTENT


def test_upload_data_exception(test_client, test_file, mocker, new_bucket):
    mocker.patch.object(Minio, "put_object", side_effect=Exception)
    response = test_client.post(f"/data?bucket_name={new_bucket}", files=test_file)
    assert response.status_code == HTTPStatus.INTERNAL_SERVER_ERROR


def test_upload_data_s3error(test_client, test_file, mocker, new_bucket):
    mocker.patch.object(S3Error, "__init__", return_value=None)
    mocker.patch.object(Minio, "put_object", side_effect=S3Error)
    response = test_client.post(f"/data?bucket_name={new_bucket}", files=test_file)
    assert response.status_code == HTTPStatus.BAD_GATEWAY

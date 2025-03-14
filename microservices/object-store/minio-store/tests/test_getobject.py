# python built-in packages
from http import HTTPStatus

# third-party installed packages
from minio import Minio

# application packages
from tests.conftest import verify_and_get_uploaded_file


def test_get_data(test_client, test_file):
    # Upload sample file in default bucket
    response = test_client.post("/data", files=test_file)
    assert response.status_code == HTTPStatus.CREATED

    # Get the uploaded file detail
    uploaded_file = verify_and_get_uploaded_file(response)

    # Get list of files in default bucket
    response = test_client.get("/data")
    assert response.status_code == HTTPStatus.OK

    # Delete the uploaded file
    response = test_client.delete(url="/data", params={"file_name": uploaded_file})
    assert response.status_code == HTTPStatus.NO_CONTENT


def test_get_data_from_new_bucket(test_client, test_file, new_bucket):
    # Upload a sample file in a new bucket
    response = test_client.post(f"/data?bucket_name={new_bucket}", files=test_file)
    assert response.status_code == HTTPStatus.CREATED

    # Get all files in the new bucket
    response = test_client.get(f"/data?bucket_name={new_bucket}")
    assert response.status_code == HTTPStatus.OK

    # Delete all files in the new bucket
    response = test_client.delete(
        url="/data", params={"bucket_name": new_bucket, "delete_all": True}
    )
    assert response.status_code == HTTPStatus.NO_CONTENT


def test_bucket_not_exist(test_client):
    response = test_client.get("/data?bucket_name=invalid_bucket")
    assert response.status_code == HTTPStatus.NOT_FOUND


def test_get_from_invalid_bucket(test_client):
    # Providing an invalid or unsupported bucket names
    response = test_client.get("/data?bucket_name=in")
    assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY

    response = test_client.get("/data?bucket_name=")
    assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY

    response = test_client.get("/data?bucket_name=  ")
    assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY

    # Underscore is not allowed in bucket names
    response = test_client.get("/data?bucket_name=invalid_bucket")
    assert response.status_code == HTTPStatus.BAD_GATEWAY


def test_get_data_custom_exception(test_client, mocker):
    mocker.patch.object(Minio, "bucket_exists", return_value=False)
    response = test_client.get("/data?bucket_name=test")
    assert response.status_code == HTTPStatus.BAD_REQUEST


def test_get_data_exception(test_client, mocker):
    mocker.patch.object(Minio, "list_objects", side_effect=Exception)
    response = test_client.get("/data")
    assert response.status_code == HTTPStatus.INTERNAL_SERVER_ERROR

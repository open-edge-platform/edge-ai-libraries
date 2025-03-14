# Python built-in packages
import pathlib

# third-party installed packages
import pytest
from fastapi.testclient import TestClient

# application packages
from minio_store.app import app
from minio_store.store import DataStore
from minio_store.util import Settings


settings = Settings()


def verify_and_get_uploaded_file(response) -> str:
    result = response.json()
    assert "files" in result
    assert len(result["files"]) != 0
    uploaded_file = result["files"][0]
    return uploaded_file


@pytest.fixture(scope="module")
def new_bucket():
    return f"{settings.OBJECT_PREFIX}.bucket.new"


# TODO mock file creation instead of actual file creation and removal
@pytest.fixture(scope="module")
def test_file():
    test_file_dir = pathlib.Path(__file__).parent.resolve()
    test_file = pathlib.Path.joinpath(test_file_dir, "sample-file.yaml")

    with open(test_file, "wb") as file:
        file.write(b"gar: bage")

    yield {"file": ("filename", open(test_file, "rb"))}

    # Remove file when control returns after yielding
    pathlib.Path.unlink(test_file)


@pytest.fixture(scope="module")
def store_client():
    yield DataStore.get_client()


@pytest.fixture(scope="module")
def test_client(store_client, new_bucket):
    """A fixture to help send HTTP REST requests to API endpoints."""

    client = TestClient(app)
    yield client
    store_client.remove_bucket(new_bucket)

import pytest
import sys
import os
sys.path.append(os.getcwd())
print(sys.path)
from fastapi.testclient import TestClient
import pathlib
from main import app

@pytest.fixture(scope="module")
def test_client():
    client = TestClient(app)
    yield client


@pytest.fixture(scope="module")
def test_file():
    test_file_dir = pathlib.Path(__file__).parent.resolve()
    test_file = pathlib.Path.joinpath(test_file_dir,"sample-file.txt")

    with open(test_file, "wb") as file:
        file.write(b"This is a sample file")

    yield {"files": ("sample-file.txt", open(test_file, "rb"))}

    # Remove file when control returns after yielding
    test_file.unlink(test_file)


@pytest.fixture(scope="module")
def test_db():
    from db_config import get_db_connection_pool
    pool = get_db_connection_pool()
    yield pool

@pytest.fixture(scope="module")
def mock_cursor():
    class MockCursor:
        def execute(self, query, params):
            self.query = query
            self.params = params

        def fetchall(self):
            return [("test_result",)]

        def close(self):
            pass

        def __enter__(self):
            return self

        def __exit__(self, _exc_type, _exc_val, _exc_tb):
            pass

        @property
        def rowcount(self):
            return 1

    return MockCursor

@pytest.fixture(scope="module")
def mock_connection(mock_cursor):
    class MockConnection:
        def cursor(self):
            return mock_cursor()

        def commit(self):
            pass

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc_val, exc_tb):
            pass

    return MockConnection

@pytest.fixture(scope="module")
def mock_pool(mock_connection):
    class MockPool:
        def connection(self):
            return mock_connection()
    return MockPool



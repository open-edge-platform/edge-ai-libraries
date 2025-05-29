import pytest
import sys
import os
sys.path.append(os.getcwd())
print(sys.path)
from fastapi.testclient import TestClient
import pathlib
from app.main import app

@pytest.fixture(scope="module")
def test_client():
    """
    Fixture to provide a test client for the application.
    This fixture creates an instance of TestClient using the application
    object (`app`) and yields it for use in test cases. The test client
    allows for simulating HTTP requests to the application during testing.
    Yields:
        TestClient: An instance of the test client for the application.
    """

    client = TestClient(app)
    yield client


@pytest.fixture(scope="module")
def test_file():
    """
    Fixture to create a temporary sample file for testing purposes.
    This fixture creates a file named "sample-file.txt" in the same directory
    as the test script. The file contains the text "This is a sample file".
    The file path is yielded to the test function, and the file is deleted
    after the test completes.
    Yields:
        dict: A dictionary containing the file path of the created sample file
              under the key "file_path".
    """

    test_file_dir = pathlib.Path(__file__).parent.resolve()
    test_file_path = pathlib.Path.joinpath(test_file_dir, "sample-file.txt")

    with open(test_file_path, "wb") as file:
        file.write(b"This is a sample file")

    yield {"file_path": test_file_path}

    # Remove file when control returns after yielding
    test_file_path.unlink()


@pytest.fixture(scope="module")
def mock_pool():
    """
    Creates a mock database connection pool for testing purposes.
    This mock pool simulates a database connection pool and provides
    mock implementations of connection and cursor objects. It is useful
    for unit testing code that interacts with a database without requiring
    an actual database connection.
    Returns:
        MockPool: A mock connection pool object with methods to simulate
        database connections and cursors.
    Mock Classes:
        - MockPool: Simulates a database connection pool.
            - connection(): Returns a MockConnection object.
        - MockConnection: Simulates a database connection.
            - cursor(): Returns a MockCursor object.
            - commit(): Simulates committing a transaction.
            - __enter__(): Enables use in a context manager.
            - __exit__(): Enables use in a context manager.
        - MockCursor: Simulates a database cursor.
            - execute(query, params): Simulates executing a SQL query.
            - fetchall(): Returns a list of mock query results.
            - close(): Simulates closing the cursor.
            - __enter__(): Enables use in a context manager.
            - __exit__(): Enables use in a context manager.
            - rowcount: A property that returns the number of rows in the mock result set.
    """

    class MockCursor:
        def execute(self, query, params):
            self.query = query
            self.params = params

        def fetchall(self):
            return [
                ("source/file1.txt", "bucket1"),
                ("source/file2.txt", "bucket2")
            ]

        def close(self):
            pass

        def __enter__(self):
            return self

        def __exit__(self, _exc_type, _exc_val, _exc_tb):
            pass

        @property
        def rowcount(self):
            return 2

    class MockConnection:
        def cursor(self):
            return MockCursor()

        def commit(self):
            pass

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc_val, exc_tb):
            pass

    class MockPool:
        def connection(self):
            return MockConnection()

    return MockPool()

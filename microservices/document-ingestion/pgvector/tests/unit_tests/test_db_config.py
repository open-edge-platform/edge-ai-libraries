from app.db_config import get_db_connection_pool, pool_execution
from unittest.mock import patch

def test_get_db_connection_pool(mock_pool):
    """
    Tests the `get_db_connection_pool` function to ensure it returns a valid
    database connection pool.
    Args:
        mock_pool: Mock object representing the database connection pool.
    Asserts:
        The returned pool is not None.
    """

    pool = get_db_connection_pool()
    assert pool is not None


def test_pool_execution_select(mock_pool):
    """
    Tests the `pool_execution` function to ensure it executes a SELECT query
    correctly and returns the expected results.
    Args:
        mock_pool (Mock): A mocked database connection pool used to simulate
            database interactions.
    Raises:
        AssertionError: If the result of `pool_execution` does not match the
            expected result.
    """

    query = "SELECT * FROM test_table"
    expected_result = [("source/file1.txt", "bucket1"), ("source/file2.txt", "bucket2")]

    with patch("app.db_config.get_db_connection_pool", return_value=mock_pool):
        result = pool_execution(query)
        assert result == expected_result


def test_pool_execution_delete(mock_pool):
    """
    Tests the `pool_execution` function to ensure it executes a DELETE query
    correctly and returns the expected results.
    Args:
        mock_pool (Mock): A mocked database connection pool used to simulate
            database interactions.
    Raises:
        AssertionError: If the result of `pool_execution` does not match the
            expected result.
    """

    query = "DELETE FROM test_table WHERE id = 1"
    expected_result = [("Deletion query was executed successfully affected rows", 2)]

    with patch("app.db_config.get_db_connection_pool", return_value=mock_pool):
        result = pool_execution(query)
        assert result == expected_result


def test_pool_execution_exception(mock_pool):
    """
    Test case for the `pool_execution` function to verify its behavior when an exception
    occurs during query execution.
    This test simulates a scenario where the database connection pool raises an exception
    while attempting to execute an invalid query. It ensures that the `pool_execution`
    function handles the exception gracefully and returns `None`.
    Args:
        mock_pool: A mock object representing the database connection pool.
    Asserts:
        - The result of `pool_execution` is `None` when an exception is raised during
          query execution.
    """

    query = "INVALID QUERY"

    with patch("app.db_config.get_db_connection_pool", return_value=mock_pool):
        with patch("app.db_config.ConnectionPool.connection", side_effect=Exception("Error executing query")):
            result = pool_execution(query)
            assert result is None

import pytest
from db_config import get_db_connection_pool, pool_execution

def test_get_db_connection_pool():
    pool = get_db_connection_pool()
    assert pool is not None

def test_pool_execution(monkeypatch,mock_pool):
    monkeypatch.setattr("db_config.get_db_connection_pool", mock_pool)
    result = pool_execution("SELECT * FROM langchain_pg_embedding")
    assert result == [('test_result',)]

def test_pool_execution_delete(monkeypatch,mock_pool):
    monkeypatch.setattr("db_config.get_db_connection_pool", mock_pool)
    result = pool_execution("DELETE FROM langchain_pg_embedding WHERE id = %s", (1,))
    assert result == [('Deletion query was executed successfuly affected rows', 1)]

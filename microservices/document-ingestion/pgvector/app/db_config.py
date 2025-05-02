# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from .config import Settings
from .logger import logger
from typing import Optional, List
from urllib.parse import urlparse
from psycopg_pool import ConnectionPool

config = Settings()
connection_pool = None


def get_db_connection_pool() -> ConnectionPool:
    """
    Retrieves a singleton database connection pool. If the connection pool does not
    already exist, it initializes one using the connection string from the configuration.

    Returns:
        ConnectionPool: The database connection pool instance, or None if an error occurs
        during initialization.

    Raises:
        Exception: Logs an error if there is an issue creating the connection pool.
    """

    global connection_pool
    if connection_pool is None:
        try:
            result = urlparse(config.PG_CONNECTION_STRING)
            username = result.username
            password = result.password
            database = result.path[1:]
            hostname = result.hostname
            port = result.port

            connection_pool = ConnectionPool(
                f"user={username} password={password} host={hostname} port={port} dbname={database}"
            )
        except Exception as e:
            logger.error(f"Error creating connection pool: {e}")
            return None
    return connection_pool


def pool_execution(query, params=None) -> Optional[List[tuple]]:
    """
    Executes a SQL query using a connection from the database connection pool.

    Args:
        query (str): The SQL query to be executed.
        params (tuple, optional): The parameters to be used with the SQL query. Defaults to None.

    Returns:
        list of tuple or None:
            - If the query is a SELECT statement, returns a list of tuples
            containing the query results.
            - If the query is a DELETE statement, returns an list of tuple
            containing message and deleted params.
            - If query fails, returns None.
    """
    try:
        pool = get_db_connection_pool()
        with pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(query, params)
                if query.strip().lower().startswith("select"):
                    result = cur.fetchall()
                elif query.strip().lower().startswith("delete"):
                    conn.commit()
                    result = [("Deletion query was executed successfully affected rows", cur.rowcount)]

            cur.close()

        logger.info(result)
        return result

    except Exception as e:
        logger.error(f"Error executing query: {e}")
        return None

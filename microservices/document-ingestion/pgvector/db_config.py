# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import logging
from urllib.parse import urlparse
from config import PG_CONNECTION_STRING
from psycopg_pool import ConnectionPool
from typing import Optional, List

logging.basicConfig(
    format="%(asctime)s: %(name)s: %(levelname)s: %(message)s", level=logging.INFO
)

connection_pool = None


def get_db_connection_pool() -> ConnectionPool:
    global connection_pool
    if connection_pool is None:
        try:
            result = urlparse(PG_CONNECTION_STRING)
            username = result.username
            password = result.password
            database = result.path[1:]
            hostname = result.hostname
            port = result.port

            connection_pool = ConnectionPool(
                f"user={username} password={password} host={hostname} port={port} dbname={database}"
            )
        except Exception as e:
            logging.error(f"Error creating connection pool: {e}")
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
                    result = [("Deletion query was executed successfuly affected rows", cur.rowcount)]
            
            cur.close()

        logging.info(result)
        return result

    except Exception as e:
        logging.error(f"Error executing query: {e}")
        return None

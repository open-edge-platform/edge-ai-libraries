# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import asyncio

from src.common.schema import QueryError, QueryRequest, QueryResultBlock
from src.common.logger import get_logger
from src.common.settings import settings
from src.retriever.service import execute_single_query


logger = get_logger()


async def execute_batch(
    requests: list[QueryRequest],
) -> tuple[list[QueryResultBlock], list[QueryError]]:
    """Execute a list of query requests with bounded concurrency.

    Returns successful result blocks and per-query errors separately so the
    caller can return partial results.
    """
    concurrency_limit = max(1, settings.BATCH_MAX_CONCURRENCY)
    if concurrency_limit != settings.BATCH_MAX_CONCURRENCY:
        logger.warning(
            "Invalid BATCH_MAX_CONCURRENCY=%s; defaulting to %s",
            settings.BATCH_MAX_CONCURRENCY,
            concurrency_limit,
        )
    semaphore = asyncio.Semaphore(concurrency_limit)

    async def _run_one(
        request_item: QueryRequest,
    ) -> tuple[QueryResultBlock | None, QueryError | None]:
        """Execute a single query request in a thread and capture failures."""
        query_id = request_item.query_id or request_item.query
        async with semaphore:
            try:
                result = await asyncio.to_thread(execute_single_query, request_item)
                return result, None
            except Exception as exc:
                logger.exception("Query execution failed for query_id=%s", query_id)
                return None, QueryError(
                    query_id=query_id,
                    code="QUERY_EXECUTION_ERROR",
                    message=str(exc),
                )

    outcomes = await asyncio.gather(*[_run_one(item) for item in requests])
    results: list[QueryResultBlock] = []
    errors: list[QueryError] = []

    for result, error in outcomes:
        if result:
            results.append(result)
        if error:
            errors.append(error)

    return results, errors

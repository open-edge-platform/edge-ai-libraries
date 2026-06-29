# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from datetime import datetime
import inspect
import logging
from typing import Any

from src.common.logger import get_logger
from src.common.schema import (
    AppliedFilters,
    FilterCondition,
    QueryRequest,
    QueryResultBlock,
    QueryResultItem,
    TimeRange,
    WhereClause,
)
from src.common.settings import settings
from src.retriever.filters import (
    build_filters,
)
from src.retriever.backend_factory import get_vectordb, clear_vectordb_cache
from src.retriever.embedding_client import EmbeddingAPI
from src.retriever.backends.registry import (
    BACKEND_PUSHDOWN_OPERATORS as BACKEND_NATIVE_PUSHDOWN_OPERATORS,
)


logger = get_logger()
TIME_FILTER_METADATA_FIELD = "created_at"


def _serialize_log_value(value: Any) -> Any:
    """Convert nested models into plain values suitable for debug logs."""
    if value is None:
        return None
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json", by_alias=True, exclude_none=True)
    if isinstance(value, dict):
        return {key: _serialize_log_value(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_serialize_log_value(item) for item in value]
    return value


def _filter_kwargs(params: inspect.BoundArguments, query_filter: Any) -> dict[str, Any]:
    """Return the correct keyword for the backend filter parameter.

    LangChain backends use either ``filter`` (FAISS, PGVector, VDMS) or
    ``expr`` (Milvus) as the filter parameter name.  Passing ``filter`` as
    a **kwarg to a method that expects ``expr`` causes pymilvus to receive
    ``filter`` twice and raise a ``TypeError``.  This helper inspects the
    method signature and returns the appropriate keyword dict.
    """
    sig_params = params.signature.parameters
    if "expr" in sig_params:
        return {"expr": query_filter}
    return {"filter": query_filter}


def _do_search(db: Any, query: str, resolved_top_k: int, fetch_k: int, query_filter: Any) -> list:
    """Call similarity_search_with_score, using fetch_k only when supported."""
    sig = inspect.signature(db.similarity_search_with_score)
    fkw = _filter_kwargs(sig.bind_partial(), query_filter)
    if "fetch_k" in sig.parameters:
        return db.similarity_search_with_score(
            query,
            k=resolved_top_k,
            fetch_k=fetch_k,
            **fkw,
        )
    return db.similarity_search_with_score(query, k=fetch_k, **fkw)


def _do_vector_search(db: Any, embedding: list[float], resolved_top_k: int, fetch_k: int, query_filter: Any) -> list:
    """Call similarity_search_with_score_by_vector with a pre-computed embedding."""
    sig = inspect.signature(db.similarity_search_with_score_by_vector)
    fkw = _filter_kwargs(sig.bind_partial(), query_filter)
    if "fetch_k" in sig.parameters:
        return db.similarity_search_with_score_by_vector(
            embedding,
            k=resolved_top_k,
            fetch_k=fetch_k,
            **fkw,
        )
    return db.similarity_search_with_score_by_vector(embedding, k=fetch_k, **fkw)


def _similarity_search_with_reconnect(
    db: Any,
    query: str,
    resolved_top_k: int,
    fetch_k: int,
    query_filter: Any,
) -> list:
    """Execute similarity search with a single reconnect retry on failure.

    If the backend raises any exception (e.g. broken TCP connection, gRPC error,
    SQLAlchemy disconnection), the cached client is evicted and a fresh instance
    is obtained before retrying once.  This ensures transient connection drops do
    not permanently break the service without requiring a process restart.
    """
    try:
        return _do_search(db, query, resolved_top_k, fetch_k, query_filter)
    except Exception as exc:
        logger.warning(
            "Backend query failed (%s: %s); evicting cache and retrying with fresh connection.",
            type(exc).__name__,
            exc,
        )
        clear_vectordb_cache()
        fresh_db = get_vectordb()
        return _do_search(fresh_db, query, resolved_top_k, fetch_k, query_filter)


def _vector_search_with_reconnect(
    db: Any,
    embedding: list[float],
    resolved_top_k: int,
    fetch_k: int,
    query_filter: Any,
) -> list:
    """Execute vector similarity search with a single reconnect retry on failure."""
    try:
        return _do_vector_search(db, embedding, resolved_top_k, fetch_k, query_filter)
    except Exception as exc:
        logger.warning(
            "Backend vector query failed (%s: %s); evicting cache and retrying with fresh connection.",
            type(exc).__name__,
            exc,
        )
        clear_vectordb_cache()
        fresh_db = get_vectordb()
        return _do_vector_search(fresh_db, embedding, resolved_top_k, fetch_k, query_filter)


def _extract_iso_datetime(metadata: dict[str, Any], field_name: str) -> datetime | None:
    """Extract and parse an ISO datetime from metadata field value."""
    raw_value = metadata.get(field_name)
    if isinstance(raw_value, dict):
        raw_value = raw_value.get("_date")
    if not raw_value:
        return None
    text = str(raw_value).replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def _normalize_string_list(value: Any) -> list[str]:
    """Normalize comma-delimited strings or arrays into non-empty string lists."""
    if isinstance(value, str):
        parts = value.split(",") if "," in value else [value]
        return [part.strip() for part in parts if part and part.strip()]
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    return []


def _coerce_comparable(value: Any) -> Any:
    """Normalize metadata values into comparable Python types."""
    if isinstance(value, dict) and "_date" in value:
        value = value.get("_date")
    if isinstance(value, str):
        timestamp_value = _extract_iso_datetime({"value": value}, "value")
        if timestamp_value is not None:
            return timestamp_value
    return value


def _evaluate_predicate(metadata: dict[str, Any], predicate: WhereClause) -> bool:
    """Evaluate one predicate clause from the primary `where` grammar."""
    field_name = predicate.field
    operator = predicate.op

    if not field_name or not operator:
        raise ValueError("Predicate evaluation requires both field and op")

    exists = field_name in metadata and metadata.get(field_name) is not None
    if operator == "exists":
        return exists
    if operator == "missing":
        return not exists

    metadata_value = _coerce_comparable(metadata.get(field_name))
    condition_value = predicate.value

    if operator == "eq":
        return metadata_value == _coerce_comparable(condition_value)

    if operator == "in":
        values = condition_value if isinstance(condition_value, list) else [condition_value]
        normalized_values = [_coerce_comparable(item) for item in values]
        if isinstance(metadata_value, list):
            return any(_coerce_comparable(item) in normalized_values for item in metadata_value)
        return metadata_value in normalized_values

    if operator == "contains":
        if isinstance(metadata_value, str) and isinstance(condition_value, str):
            return condition_value in metadata_value
        if isinstance(metadata_value, list):
            return any(str(item) == str(condition_value) for item in metadata_value)
        return False

    if operator == "starts_with":
        return isinstance(metadata_value, str) and isinstance(condition_value, str) and metadata_value.startswith(condition_value)

    if operator in {"contains_any", "contains_all"}:
        metadata_values = set(_normalize_string_list(metadata.get(field_name)))
        required_values = set(_normalize_string_list(condition_value))
        if not required_values:
            return False
        if operator == "contains_any":
            return bool(metadata_values.intersection(required_values))
        return required_values.issubset(metadata_values)

    comparable_value = _coerce_comparable(metadata_value)
    if comparable_value is None:
        return False

    try:
        if operator == "gt":
            return comparable_value > _coerce_comparable(condition_value)
        if operator == "gte":
            return comparable_value >= _coerce_comparable(condition_value)
        if operator == "lt":
            return comparable_value < _coerce_comparable(condition_value)
        if operator == "lte":
            return comparable_value <= _coerce_comparable(condition_value)
        if operator == "between":
            if not isinstance(condition_value, list) or len(condition_value) != 2:
                return False
            lower, upper = condition_value
            return _coerce_comparable(lower) <= comparable_value <= _coerce_comparable(upper)
    except TypeError:
        return False

    return False


def _evaluate_where_clause(metadata: dict[str, Any], where: WhereClause) -> bool:
    """Evaluate recursive `where` tree against metadata."""
    if where.all is not None:
        return all(_evaluate_where_clause(metadata, item) for item in where.all)
    if where.any is not None:
        return any(_evaluate_where_clause(metadata, item) for item in where.any)
    if where.not_ is not None:
        return not _evaluate_where_clause(metadata, where.not_)
    return _evaluate_predicate(metadata, where)


def _combine_all_clauses(clauses: list[WhereClause]) -> WhereClause | None:
    """Combine multiple clauses into a single conjunction clause."""
    if not clauses:
        return None
    if len(clauses) == 1:
        return clauses[0]
    return WhereClause(all=clauses)


def _legacy_filters_to_where(filters: dict[str, FilterCondition] | None) -> WhereClause | None:
    """Translate legacy generic filters payload into `where` clauses."""
    if not filters:
        return None
    clauses = [
        WhereClause(field=field_name, op=condition.op, value=condition.value)
        for field_name, condition in filters.items()
    ]
    return _combine_all_clauses(clauses)


def _normalize_request_where(query_request: QueryRequest) -> tuple[WhereClause | None, list[str]]:
    """Normalize alias filters into primary `where` format with warnings."""
    clauses: list[WhereClause] = []
    rewritten_clauses: list[str] = []

    if query_request.where is not None:
        clauses.append(query_request.where)

    if query_request.tags:
        clauses.append(WhereClause(field="tags", op="contains_any", value=query_request.tags))
        rewritten_clauses.append("tags -> where(field='tags', op='contains_any', value=<tags>)")

    if query_request.time_filter:
        clauses.append(
            WhereClause(
                field=TIME_FILTER_METADATA_FIELD,
                op="between",
                value=[query_request.time_filter.start, query_request.time_filter.end],
            )
        )
        rewritten_clauses.append(
            "time_filter -> where(field='created_at', op='between', value=[start, end])"
        )

    legacy_where = _legacy_filters_to_where(query_request.filters)
    if legacy_where is not None:
        clauses.append(legacy_where)
        rewritten_clauses.append("filters -> where(all=[legacy predicates])")

    return _combine_all_clauses(clauses), rewritten_clauses


def _collect_pushdown_predicates(
    where: WhereClause | None,
) -> tuple[list[WhereClause], list[str], list[str]]:
    """Collect only conjunctive predicate clauses safe for backend pushdown."""
    if where is None:
        return [], [], []

    predicates: list[WhereClause] = []
    warnings: list[str] = []
    dropped_clauses: list[str] = []

    def describe_clause(clause: WhereClause) -> str:
        if clause.field and clause.op:
            return f"{clause.field}:{clause.op}"
        if clause.any is not None:
            return "any(...)"
        if clause.not_ is not None:
            return "not(...)"
        if clause.all is not None:
            return "all(...)"
        return "unknown-clause"

    def collect(clause: WhereClause, in_all_context: bool) -> None:
        if clause.all is not None:
            for item in clause.all:
                collect(item, True)
            return
        if clause.any is not None or clause.not_ is not None:
            warnings.append(
                "Logical clauses 'any'/'not' are evaluated in fallback path and not pushed down to backend."
            )
            dropped_clauses.append(describe_clause(clause))
            return
        if clause.field and clause.op and in_all_context:
            predicates.append(clause)

    collect(where, True)
    return predicates, warnings, dropped_clauses


def _build_pushdown_filters(
    where: WhereClause | None,
) -> tuple[
    list[str] | None,
    TimeRange | None,
    dict[str, FilterCondition] | None,
    list[str],
    list[str],
]:
    """Build backend pushdown filters from safe subset of `where` predicates."""
    predicates, warnings, dropped_clauses = _collect_pushdown_predicates(where)
    pushdown_operators = set(
        BACKEND_NATIVE_PUSHDOWN_OPERATORS.get(settings.RETRIEVER_BACKEND, [])
    )
    tags: list[str] = []
    time_filter: TimeRange | None = None
    generic_filters: dict[str, FilterCondition] = {}

    for predicate in predicates:
        if predicate.field is None or predicate.op is None:
            raise ValueError("Pushdown predicates must include both field and op")
        field_name = predicate.field
        operator = predicate.op
        value = predicate.value

        if field_name == "tags":
            # tags is a list-typed field; scalar pushdown operators ($eq/$in) do not
            # correctly match list values across backends. All tags predicates are
            # evaluated in the fallback path which handles list fields via
            # _normalize_string_list. A warning is emitted so the over-fetch path
            # triggers enough candidates for accurate fallback evaluation.
            warnings.append(
                f"Predicate {field_name}:{operator} is evaluated in fallback path (list-typed field)."
            )
            dropped_clauses.append(f"{field_name}:{operator}")
            continue

        if (
            field_name == TIME_FILTER_METADATA_FIELD
            and operator == "between"
            and isinstance(value, list)
            and len(value) == 2
        ):
            start_value = _coerce_comparable(value[0])
            end_value = _coerce_comparable(value[1])
            if isinstance(start_value, datetime) and isinstance(end_value, datetime):
                if time_filter is None:
                    time_filter = TimeRange(start=start_value, end=end_value)
                else:
                    warnings.append(
                        "Multiple created_at between predicates found; only the first is pushed down."
                    )
                    dropped_clauses.append(f"{field_name}:{operator}")
                continue

        if operator in pushdown_operators:
            try:
                generic_filters[field_name] = FilterCondition(op=operator, value=value)
            except ValueError:
                warnings.append(
                    f"Predicate {field_name}:{operator} failed pushdown validation and will use fallback evaluation."
                )
                dropped_clauses.append(f"{field_name}:{operator}")
            continue

        warnings.append(
            f"Predicate {field_name}:{operator} is not backend-pushdown compatible and will be evaluated in fallback."
        )
        dropped_clauses.append(f"{field_name}:{operator}")

    normalized_tags = [tag for tag in dict.fromkeys(tags) if tag]
    return (
        normalized_tags or None,
        time_filter,
        generic_filters or None,
        warnings,
        dropped_clauses,
    )


def _get_query_label(query_request: QueryRequest) -> str:
    """Return a human-readable label for the query modality."""
    if query_request.query is not None:
        return query_request.query
    assert query_request.image is not None
    return f"[{query_request.image.type}]"


def execute_single_query(query_request: QueryRequest) -> QueryResultBlock:
    """Execute one semantic query against the active backend.

    Supports both text and image query modalities.  Text queries use the
    backend's built-in ``similarity_search_with_score`` which embeds
    internally.  Image queries compute the embedding vector explicitly
    via the embedding service and then call
    ``similarity_search_by_vector_with_score``.

    Backend-native filters are applied at query time, then a consistent
    fallback filter pass is applied to returned metadata to enforce behavior
    across heterogeneous backend filter implementations.
    """
    query_label = _get_query_label(query_request)
    resolved_query_id = query_request.query_id or query_label
    requested_top_k = (
        query_request.top_k if query_request.top_k is not None else settings.DEFAULT_TOP_K
    )
    resolved_top_k = max(1, min(requested_top_k, settings.MAX_TOP_K))

    normalized_where, rewritten_clauses = _normalize_request_where(query_request)
    (
        pushdown_tags,
        pushdown_time_filter,
        pushdown_filters,
        pushdown_warnings,
        dropped_clauses,
    ) = _build_pushdown_filters(normalized_where)
    warnings = [*rewritten_clauses, *pushdown_warnings]

    query_filter = build_filters(
        backend=settings.RETRIEVER_BACKEND,
        tags=pushdown_tags,
        time_filter=pushdown_time_filter,
        filters=pushdown_filters,
        property_name=TIME_FILTER_METADATA_FIELD,
    )

    fetch_k = resolved_top_k + 1
    if normalized_where is not None and (query_filter is None or warnings):
        fetch_k = min(settings.MAX_TOP_K, max(fetch_k, resolved_top_k * 5))
    fallback_filter_active = normalized_where is not None
    overfetch_active = fetch_k > resolved_top_k

    is_image_query = query_request.image is not None

    logger.info(
        "Executing query_id=%s modality=%s top_k=%d has_where=%s pushdown_tags=%s pushdown_time=%s pushdown_generic=%s warnings=%d",
        resolved_query_id,
        "image" if is_image_query else "text",
        resolved_top_k,
        bool(normalized_where),
        bool(pushdown_tags),
        bool(pushdown_time_filter),
        bool(pushdown_filters),
        len(warnings),
    )
    if logger.isEnabledFor(logging.DEBUG):
        logger.debug(
            "Final query execution inputs query_id=%s query=%r normalized_where=%r compiled_backend_filter=%r pushdown_tags=%r pushdown_time_filter=%r pushdown_generic_filters=%r top_k=%d fetch_k=%d fallback_filter_active=%s overfetch_active=%s warnings=%r",
            resolved_query_id,
            query_label,
            _serialize_log_value(normalized_where),
            _serialize_log_value(query_filter),
            _serialize_log_value(pushdown_tags),
            _serialize_log_value(pushdown_time_filter),
            _serialize_log_value(pushdown_filters),
            resolved_top_k,
            fetch_k,
            fallback_filter_active,
            overfetch_active,
            warnings or None,
        )

    db = get_vectordb()

    if is_image_query:
        embedding_client = EmbeddingAPI(
            api_url=settings.EMBEDDINGS_ENDPOINT,
            model_name=settings.EMBEDDING_MODEL_NAME,
        )
        image_embedding = embedding_client.embed_image(query_request.image)
        docs_with_score = _vector_search_with_reconnect(
            db=db,
            embedding=image_embedding,
            resolved_top_k=resolved_top_k,
            fetch_k=fetch_k,
            query_filter=query_filter,
        )
    else:
        docs_with_score = _similarity_search_with_reconnect(
            db=db,
            query=query_request.query,
            resolved_top_k=resolved_top_k,
            fetch_k=fetch_k,
            query_filter=query_filter,
        )

    items: list[QueryResultItem] = []
    for doc, score in docs_with_score:
        metadata = dict(doc.metadata)

        if normalized_where is not None and not _evaluate_where_clause(metadata, normalized_where):
            continue

        items.append(
            QueryResultItem(
                score=float(score),
                metadata=metadata,
                page_content=str(doc.page_content),
            )
        )

    items.sort(key=lambda item: item.score, reverse=True)
    items = items[:resolved_top_k]

    return QueryResultBlock(
        query_id=resolved_query_id,
        query=query_label,
        count=len(items),
        items=items,
        applied_filters=AppliedFilters(
            tags=query_request.tags,
            time_filter=query_request.time_filter,
            filters=query_request.filters,
            normalized_where=normalized_where,
            warnings=warnings or None,
            compiled_backend_filter=query_filter if query_request.explain_filters else None,
            dropped_or_rewritten_clauses=(
                [*rewritten_clauses, *dropped_clauses] if query_request.explain_filters else None
            ),
        ),
    )

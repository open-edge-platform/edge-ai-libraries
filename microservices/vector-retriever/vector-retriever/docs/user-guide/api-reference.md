# API Reference

Version: 1.0.0

<!--hide_directive```{eval-rst}
.. swagger-plugin:: api-docs/openapi.yaml
```hide_directive-->

This guide documents the HTTP endpoints exposed by the Vector Retriever microservice. The OpenAPI specification is the source of truth for request/response schemas.

## Endpoints

- `GET /health`
- `GET /ready`
- `POST /query`
- `GET /capabilities/filters`

## GET /health

Returns service liveness status.

## GET /ready

Returns service readiness. This endpoint checks backend initialization and returns `503` when dependencies are unavailable.

## POST /query

Batch query endpoint. Accepts a list of `QueryRequest` objects and returns per-query results plus per-query errors.

### Request body

```json
[
  {
    "query_id": "q1",
    "query": "red car",
    "where": {
      "all": [
        {"field": "tags", "op": "contains_any", "value": ["traffic"]},
        {
          "field": "created_at",
          "op": "between",
          "value": ["2026-03-01T00:00:00Z", "2026-03-22T23:59:59Z"]
        },
        {
          "field": "video_id",
          "op": "eq",
          "value": "traffic_001"
        }
      ]
    },
    "top_k": 20,
    "explain_filters": true
  }
]
```

Compatibility aliases remain supported for now (`tags`, `time_filter`, `filters`) and are normalized into `where`.

### Image query variants

Instead of a text `query`, you can supply an `image` object for visual similarity search.
The `image` field uses a discriminated union on the `type` property.

Image URL input:

```json
[
  {
    "query_id": "img-url-1",
    "image": {
      "type": "image_url",
      "image_url": "https://example.com/photo.jpg"
    },
    "top_k": 5
  }
]
```

Base64-encoded image input:

```json
[
  {
    "query_id": "img-b64-1",
    "image": {
      "type": "image_base64",
      "image_base64": "<base64-encoded-image-data>"
    },
    "top_k": 5
  }
]
```

> **_NOTE:_** `query` and `image` are mutually exclusive. Providing both in the same query block returns a `422` validation error. When using `image`, the response `query` field is set to `[image_url]` or `[image_base64]` to indicate the input modality.

### Quick contract reference

Top-level request fields:

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `query_id` | string | No | Optional per-query identifier. Defaults to the `query` text when omitted. |
| `query` | string | Conditional | User search text. Required unless `image` is provided. Mutually exclusive with `image`. |
| `image` | object | Conditional | Image input for visual similarity search. Required unless `query` is provided. Mutually exclusive with `query`. Uses discriminated union with `type` field (`image_url` or `image_base64`). |
| `top_k` | integer | No | Result count cap for this query. |
| `where` | object | No | Primary filter grammar object. |
| `explain_filters` | boolean | No | When true, response includes backend filter payload and rewrite details. |
| `tags` | string[] | No | Legacy alias; normalized to `where(field="tags", op="contains_any", value=[...])`. |
| `time_filter` | object | No | Legacy alias; normalized to `where(field="created_at", op="between", value=[start, end])`. |
| `filters` | map | No | Legacy alias map; normalized to equivalent `where` predicates. |

Safety limits:

| Limit | Value | Why it exists |
| --- | --- | --- |
| `max_where_depth` | 5 | Prevents deeply nested trees that are expensive and hard to debug. |
| `max_where_clauses` | 50 | Prevents oversized expressions from consuming excessive compute. |
| `max_where_list_size` | 100 | Prevents very large list scans for `in` and array operators. |

### Supported filter operators

- `eq`
- `in`
- `contains`
- `starts_with`
- `gt`
- `gte`
- `lt`
- `lte`
- `between`
- `contains_any`
- `contains_all`
- `exists`
- `missing`

### Dynamic-field safety rules

- Field name regex: `^[A-Za-z0-9_/\\-]{1,128}$`
- Max dynamic filter fields: `20`
- Max `where` depth: `5`
- Max `where` clauses: `50`
- Max list size for list operators: `100`
- Unknown fields are allowed if they satisfy validation rules

### Response body

```json
{
  "request_id": "uuid",
  "results": [
    {
      "query_id": "q1",
      "query": "red car",
      "count": 1,
      "items": [
        {
          "score": 0.91,
          "metadata": {
            "video_id": "traffic_001"
          },
          "page_content": "..."
        }
      ],
      "applied_filters": {
        "normalized_where": {
          "all": [
            {"field": "tags", "op": "contains_any", "value": ["traffic"]},
            {
              "field": "created_at",
              "op": "between",
              "value": ["2026-03-01T00:00:00Z", "2026-03-22T23:59:59Z"]
            }
          ]
        },
        "warnings": [
          "tags -> where(field='tags', op='contains_any', value=<tags>)"
        ],
        "compiled_backend_filter": {
          "tags": ["==", "traffic"]
        },
        "dropped_or_rewritten_clauses": [
          "tags -> where(field='tags', op='contains_any', value=<tags>)"
        ]
      }
    }
  ],
  "errors": []
}
```

`compiled_backend_filter` and `dropped_or_rewritten_clauses` are only returned when
`explain_filters=true`. Either field can still be `null` or empty when nothing was pushed down
or rewritten for that query.

Explain behavior summary:

| Response field | Populated when | Meaning |
| --- | --- | --- |
| `applied_filters.normalized_where` | Always when any filter input is present | Final interpreted `where` tree used for evaluation. |
| `applied_filters.warnings` | When normalization or pushdown notes exist | Human-readable notes about alias rewrites and pushdown limits. |
| `applied_filters.compiled_backend_filter` | `explain_filters=true` | Backend-native filter payload sent to vector store. |
| `applied_filters.dropped_or_rewritten_clauses` | `explain_filters=true` | Clauses rewritten from aliases or evaluated only in fallback path. |

### Pushdown, fallback, and over-fetch behavior

The service executes filtering in two stages:

1. Build backend pushdown filter from a safe subset of predicates.
2. Apply `where` again in the service fallback path against returned metadata.

This fallback stage is always the final source of truth for result inclusion.

When fallback risk is high (for example no backend filter was compiled, or warnings indicate
partial pushdown), the service over-fetches candidates before fallback evaluation. In practice,
`fetch_k` is increased beyond `top_k` (capped by `MAX_TOP_K`) to reduce false negatives.

Implications for `explain_filters=true`:

- `compiled_backend_filter` can still be `null` when no backend-native filter is produced.
- `dropped_or_rewritten_clauses` can be empty when no alias rewrite occurred and no clause
  was explicitly marked as dropped.
- `pushdown_operators` in capabilities indicate backend support class, but actual pushdown can
  still vary by field/operator combination and backend translator behavior.

## GET /capabilities/filters

Returns filter grammar capabilities and limits for each backend.

Optional query parameter:

- `backend`: scope to one backend (for example `backend=milvus`)

### Capabilities response example

```json
{
  "active_backend": "vdms",
  "backends": [
    {
      "backend": "vdms",
      "top_level_fields": ["query", "image", "top_k", "where"],
      "logical_blocks": ["all", "any", "not"],
      "supported_operators": ["eq", "in", "contains", "starts_with", "gt", "gte", "lt", "lte", "between", "contains_any", "contains_all", "exists", "missing"],
      "pushdown_operators": ["gte"],
      "known_fields": {
        "tags": "array<string>",
        "created_at": "datetime"
      },
      "max_where_depth": 5,
      "max_where_clauses": 50,
      "max_where_list_size": 100
    }
  ]
}
```

## Backend filter semantics

The API surface is uniform, but translation is backend-specific:

- `vdms`: translated to list-style VDMS filters
- `milvus`: translated to expression string (`expr`)
- `pgvector`: translated to document-style filter operators
- `faiss`: translated to dict-based metadata filters

## Supporting Resources

- [Overview](Overview.md)
- [Overview and Architecture](overview-architecture.md)
- [Get Started](get-started.md)
- [How to Build from Source](how-to-build-from-source.md)
- [Filter Grammar](filter-grammar.md)
- [OpenAPI Specification](api-docs/openapi.yaml)
- [System Requirements](system-requirements.md)
- [Add New Retriever Backend](add-new-retriever-backend.md)
- [Release Notes](release-notes.md)

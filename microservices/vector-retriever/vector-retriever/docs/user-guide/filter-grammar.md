# Filter Grammar

This page documents the primary filtering contract for Vector Retriever.

## Primary Filter Contract

Use `where` as the primary filter object.

Primary filter-related query fields are:

- `query` (text input, mutually exclusive with `image`)
- `image` (image input, mutually exclusive with `query`)
- `top_k`
- `where`

Other supported top-level fields:

- `query_id`
- `explain_filters`

Compatibility aliases are still accepted:

- `tags` maps to `where` predicate with `contains_any` on `tags`
- `time_filter` maps to `where` predicate with `between` on `created_at`
- `filters` maps to `where` predicates with legacy operators

If aliases are used, the response includes `applied_filters.normalized_where`. Unsupported or
non-pushdown clauses are still evaluated in the service fallback path; use
`explain_filters=true` to inspect backend-native filter compilation details.

## Pushdown and Over-fetch Notes

- Backend filtering is best-effort pushdown from a safe predicate subset.
- Final inclusion is always enforced by fallback evaluation of normalized `where` in the service.
- When pushdown is partial or unavailable, the service increases retrieval candidate size
  (`fetch_k`) before fallback evaluation to reduce false negatives.
- With `explain_filters=true`, `compiled_backend_filter` can still be `null` for queries where
  no backend-native filter payload is generated.

## Clause Types

Atomic predicate:

```json
{
  "field": "camera_id",
  "op": "eq",
  "value": "cam-a"
}
```

Logical blocks:

- `all`: all child clauses must match
- `any`: at least one child clause must match
- `not`: negate a child clause

## Operator Families

Text operators:

- `eq`, `in`, `contains`, `starts_with`

Numeric and time operators:

- `eq`, `gt`, `gte`, `lt`, `lte`, `between`

Array and tag operators:

- `contains_any`, `contains_all`

Existence operators:

- `exists`, `missing`

## Deterministic Semantics

- `between` is inclusive on both lower and upper bounds.
- Datetime values must be timezone-aware (for example `Z` suffix).
- Missing metadata fields evaluate as not present.
- `exists` means field key exists and value is not null.
- `missing` means field is absent or null.
- String comparisons are case-sensitive unless data is pre-normalized.
- Array operators compare normalized string values.

## Safety Limits

- Maximum where depth: `5`
  Prevents deeply nested logical trees that are costly to evaluate and hard to debug.
- Maximum where clauses: `50`
  Caps overall expression size so a single query cannot overwhelm filtering runtime.
- Maximum list size for list operators: `100`
  Applies to `in`, `contains_any`, and `contains_all` to avoid oversized list scans.

## 10 Examples by Use Case

### 1. Exact metadata match

```json
{
  "query": "vehicle at signal",
  "top_k": 10,
  "where": {"field": "video_id", "op": "eq", "value": "traffic_001"}
}
```

### 2. Multi-value field match

```json
{
  "query": "bus near stop",
  "where": {"field": "camera_id", "op": "in", "value": ["cam-a", "cam-b"]}
}
```

### 3. Prefix text search on metadata

```json
{
  "query": "incident report",
  "where": {"field": "event_label", "op": "starts_with", "value": "accident"}
}
```

### 4. Contains text in a metadata string

```json
{
  "query": "road closure",
  "where": {"field": "notes", "op": "contains", "value": "lane"}
}
```

### 5. Numeric lower bound

```json
{
  "query": "person near crosswalk",
  "where": {"field": "confidence", "op": "gte", "value": 0.7}
}
```

### 6. Numeric inclusive range

```json
{
  "query": "moving vehicle",
  "where": {"field": "timestamp", "op": "between", "value": [5, 20]}
}
```

### 7. Time window on created_at

```json
{
  "query": "pedestrian crossing",
  "where": {
    "field": "created_at",
    "op": "between",
    "value": ["2026-03-01T00:00:00Z", "2026-03-07T23:59:59Z"]
  }
}
```

### 8. Tag overlap using contains_any

```json
{
  "query": "traffic event",
  "where": {"field": "tags", "op": "contains_any", "value": ["traffic", "bus"]}
}
```

### 9. Combined all or any logic

```json
{
  "query": "urban traffic",
  "where": {
    "all": [
      {"field": "tags", "op": "contains_any", "value": ["traffic"]},
      {
        "any": [
          {"field": "camera_id", "op": "eq", "value": "cam-a"},
          {"field": "camera_id", "op": "eq", "value": "cam-b"}
        ]
      }
    ]
  }
}
```

### 10. Negation with not

```json
{
  "query": "vehicle",
  "where": {
    "all": [
      {"field": "tags", "op": "contains_any", "value": ["vehicle"]},
      {"not": {"field": "weather", "op": "eq", "value": "rain"}}
    ]
  }
}
```

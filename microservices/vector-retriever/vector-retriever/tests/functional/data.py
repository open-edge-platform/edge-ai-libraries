# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Shared functional test fixtures for backend filter-parity testing."""

DOCUMENTS = [
    {
        "page_content": "red car at intersection",
        "metadata": {
            "video_id": "vid-001",
            "camera_zone": "north",
            "description": "red car at intersection",
            "prefix": "alpha-route",
            "frame_number": 10,
            "bucket_name": "cam-a",
            "tags": ["traffic", "vehicle", "red"],
            "created_at": "2026-03-10T10:00:00+00:00",
            "optional_note": "doc has note",
        },
    },
    {
        "page_content": "blue bus near station",
        "metadata": {
            "video_id": "vid-002",
            "camera_zone": "south",
            "description": "blue bus near station",
            "prefix": "beta-route",
            "frame_number": 20,
            "bucket_name": "cam-b",
            "tags": ["traffic", "vehicle", "bus"],
            "created_at": "2026-03-15T12:00:00+00:00",
        },
    },
    {
        "page_content": "person with bicycle crossing",
        "metadata": {
            "video_id": "vid-003",
            "camera_zone": "east",
            "description": "person with bicycle crossing",
            "prefix": "alpha-bike",
            "frame_number": 30,
            "bucket_name": "cam-c",
            "tags": ["pedestrian", "bicycle"],
            "created_at": "2026-03-20T08:30:00+00:00",
            "optional_note": "pedestrian event",
        },
    },
    {
        "page_content": "delivery truck unloading",
        "metadata": {
            "video_id": "vid-004",
            "camera_zone": "west",
            "description": "delivery truck unloading",
            "prefix": "gamma-log",
            "frame_number": 40,
            "bucket_name": "cam-d",
            "tags": ["logistics", "vehicle"],
            "created_at": "2026-03-25T14:15:00+00:00",
        },
    },
    {
        "page_content": "traffic light malfunction",
        "metadata": {
            "video_id": "vid-005",
            "camera_zone": "north-east",
            "description": "traffic light malfunction",
            "prefix": "alpha-signal",
            "frame_number": 50,
            "bucket_name": "cam-a",
            "tags": ["traffic", "signal"],
            "created_at": "2026-04-01T09:45:00+00:00",
            "optional_note": "signal issue",
        },
    },
    {
        "page_content": "empty intersection at night",
        "metadata": {
            "video_id": "vid-006",
            "camera_zone": "south-west",
            "description": "empty intersection at night",
            "prefix": "delta-night",
            "frame_number": 60,
            "bucket_name": "cam-e",
            "tags": ["night", "traffic"],
            "created_at": "2026-04-05T20:10:00+00:00",
        },
    },
]


FILTER_CASES = [
    {
        "name": "op_eq",
        "payload": {"where": {"field": "video_id", "op": "eq", "value": "vid-001"}},
        "expected_ids": {"vid-001"},
    },
    {
        "name": "op_in",
        "payload": {
            "where": {"field": "camera_zone", "op": "in", "value": ["north", "east"]}
        },
        "expected_ids": {"vid-001", "vid-003"},
    },
    {
        "name": "op_contains",
        "payload": {
            "where": {"field": "description", "op": "contains", "value": "intersection"}
        },
        "expected_ids": {"vid-001", "vid-006"},
    },
    {
        "name": "op_starts_with",
        "payload": {"where": {"field": "prefix", "op": "starts_with", "value": "alpha"}},
        "expected_ids": {"vid-001", "vid-003", "vid-005"},
    },
    {
        "name": "op_gt",
        "payload": {"where": {"field": "frame_number", "op": "gt", "value": 40}},
        "expected_ids": {"vid-005", "vid-006"},
    },
    {
        "name": "op_gte",
        "payload": {"where": {"field": "frame_number", "op": "gte", "value": 40}},
        "expected_ids": {"vid-004", "vid-005", "vid-006"},
    },
    {
        "name": "op_lt",
        "payload": {"where": {"field": "frame_number", "op": "lt", "value": 30}},
        "expected_ids": {"vid-001", "vid-002"},
    },
    {
        "name": "op_lte",
        "payload": {"where": {"field": "frame_number", "op": "lte", "value": 30}},
        "expected_ids": {"vid-001", "vid-002", "vid-003"},
    },
    {
        "name": "op_between",
        "payload": {
            "where": {"field": "frame_number", "op": "between", "value": [20, 40]}
        },
        "expected_ids": {"vid-002", "vid-003", "vid-004"},
    },
    {
        "name": "op_contains_any",
        "payload": {
            "where": {"field": "tags", "op": "contains_any", "value": ["bicycle", "signal"]}
        },
        "expected_ids": {"vid-003", "vid-005"},
    },
    {
        "name": "op_contains_all",
        "payload": {
            "where": {"field": "tags", "op": "contains_all", "value": ["traffic", "vehicle"]}
        },
        "expected_ids": {"vid-001", "vid-002"},
    },
    {
        "name": "op_exists",
        "payload": {"where": {"field": "optional_note", "op": "exists"}},
        "expected_ids": {"vid-001", "vid-003", "vid-005"},
    },
    {
        "name": "op_missing",
        "payload": {"where": {"field": "optional_note", "op": "missing"}},
        "expected_ids": {"vid-002", "vid-004", "vid-006"},
    },
    {
        "name": "logical_compound",
        "payload": {
            "where": {
                "all": [
                    {"field": "frame_number", "op": "gte", "value": 20},
                    {
                        "any": [
                            {"field": "camera_zone", "op": "eq", "value": "east"},
                            {"field": "camera_zone", "op": "eq", "value": "west"},
                        ]
                    },
                    {
                        "not": {
                            "field": "tags",
                            "op": "contains_any",
                            "value": ["night"],
                        }
                    },
                ]
            }
        },
        "expected_ids": {"vid-003", "vid-004"},
    },
    {
        "name": "legacy_tags_and_time_filter",
        "payload": {
            "tags": ["traffic"],
            "time_filter": {
                "start": "2026-03-12T00:00:00+00:00",
                "end": "2026-04-02T00:00:00+00:00",
            },
        },
        "expected_ids": {"vid-002", "vid-005"},
    },
    {
        "name": "legacy_filters_map",
        "payload": {
            "filters": {
                "bucket_name": {"op": "in", "value": ["cam-a", "cam-b"]},
                "frame_number": {"op": "between", "value": [10, 20]},
            }
        },
        "expected_ids": {"vid-001", "vid-002"},
    },
    # --- standalone not at top level ---
    {
        "name": "logical_not_toplevel",
        "payload": {
            "where": {
                "not": {"field": "camera_zone", "op": "eq", "value": "north"}
            }
        },
        "expected_ids": {"vid-002", "vid-003", "vid-004", "vid-005", "vid-006"},
    },
    # --- zero-result filter ---
    {
        "name": "no_match",
        "payload": {
            "where": {"field": "video_id", "op": "eq", "value": "vid-999"}
        },
        "expected_ids": set(),
    },
    # --- time-only filter via where (datetime between) ---
    {
        "name": "op_time_between_where",
        "payload": {
            "where": {
                "field": "created_at",
                "op": "between",
                "value": ["2026-03-20T00:00:00+00:00", "2026-04-01T23:59:59+00:00"],
            }
        },
        "expected_ids": {"vid-003", "vid-004", "vid-005"},
    },
    # --- nested all inside all ---
    {
        "name": "nested_all",
        "payload": {
            "where": {
                "all": [
                    {
                        "all": [
                            {"field": "frame_number", "op": "gte", "value": 10},
                            {"field": "frame_number", "op": "lte", "value": 30},
                        ]
                    },
                    {"field": "bucket_name", "op": "eq", "value": "cam-c"},
                ]
            }
        },
        "expected_ids": {"vid-003"},
    },
]
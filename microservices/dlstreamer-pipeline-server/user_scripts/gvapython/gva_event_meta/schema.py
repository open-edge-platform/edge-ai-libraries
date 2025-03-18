#
# Apache v2 license
# Copyright (C) 2024 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
#

gva_event_schema = {
        "$schema": "https://json-schema.org/draft/2019-09/schema",
        "type": "array",
        "items": {
            "properties": {
                "event-type": {
                    "description": "Event type, known by caller",
                    "type": "string"
                },
                "related-objects": {
                    "description": ("Array of related detections, each refers "
                    "to index of associated detected object"),
                    "type": "array",
                    "items": {
                        "type": "integer"
                    }
                },
            },
            "required": [
                "event-type"
            ],
            "additionalProperties": True
        }
    }

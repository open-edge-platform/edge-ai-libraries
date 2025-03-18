#
# Apache v2 license
# Copyright (C) 2024 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
#

model_index_schema = {
                    "type": "object",
                        "additionalProperties": {
                            "type": "object",
                            "properties": {
                                "labels-file": {
                                        "type": ["string", "null"]
                                },
                                "model-proc": {
                                        "type": ["string", "null"]
                                }
                            }
                        }
                    }

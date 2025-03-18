#
# Apache v2 license
# Copyright (C) 2024 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
#

model_list_schema = {
        "type" : "array",
        "items" : {
            "oneOf": [
                {
                    "type" : "object",
                    "properties" : {
                        "model" : {"type" : "string"},
                        "alias" : {"type" : "string"},
                        "version" : {"type" : ["string", "integer"]},
                        "precision" : {
                            "type" : "array",
                            "items" : {"enum" : ["FP32", "FP16", "INT8",
                                                 "FP16-INT8", "FP32-INT8",
                                                 "FP32-INT1", "FP16-INT1", "INT1"]}
                        },
                        "model-proc" : {"type": "string"},
                        "labels-file": {"type": "string"},
                    },
                    "required" : ["model"],
                    "additionalProperties" : False
                },
                {
                    "type" : "string"
                }
            ]
        }
    }

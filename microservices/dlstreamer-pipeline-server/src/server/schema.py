#
# Apache v2 license
# Copyright (C) 2024 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
#

tags = {
    "type": "object",
    "filter": {
        "name": "metaconvert",
        "type": "video",
        "property": "tags",
        "format": "json"
    },
    "element": {
        "name": "metaconvert",
        "property": "tags",
        "format": "json"
    }
}

source = {
    "application":{
        "type": "object",
        "properties": {
            "type": {
                "type":"string",
                "enum":["application"]
            },
            "class":{
                "type":"string"
            },
            "element": {"enum": ["appsrc"], "default" : "appsrc"},
            "properties": {"type": "object",
                           "element": {"name": "source", "format": "element-properties"}},
            "capsfilter": {"type": "string"},
            "postproc": {"type": "string"}
        },
        "required":["type", "class"]
    },
    "uri": {
        "type": "object",
        "properties": {
            "type": {
                "type": "string",
                "enum": ["uri"]
            },
            "uri": {
                "type": "string",
                "format": "uri",
                "filter": [{"name": "metaconvert", "property": "source", "type": "video"},
                           {"name": "i", "property": "_INPUT_ARG_", "type": "input"}],
                "element": [{"name": "source",
                             "property": "uri"},
                            {"name": "metaconvert", "property": "source"}]},
            "element": {"enum": ["urisourcebin"], "default": "urisourcebin"},
            "properties": {"type": "object",
                           "element": {"name": "source", "format": "element-properties"}},
            "capsfilter": {"type": "string"},
            "postproc": {"type": "string"}
        },
        "required": ["type", "uri"]
    },
    "webcam": {
        "type": "object",
        "properties": {
            "type": {"type": "string", "enum": ["webcam"]},
            "device": {"type": "string",
                       "format": "path", "element": [{"name": "source", "property": "device"},
                                                     {"name": "metaconvert", "property": "source"}]},
            "element": {"enum": ["v4l2src"], "default": "v4l2src"},
            "properties": {"type": "object",
                           "element": {"name": "source", "format": "element-properties"}},
            "capsfilter": {"type": "string", "default": "image/jpeg"},
            "postproc": {"type": "string"}
        },
        "required": ["type", "device"]
    },
    "gst": {
        "type": "object",
        "properties": {
            "type": {"type": "string", "enum": ["gst"]},
            "element": {"type": "string"},
            "properties": {"type": "object",
                           "element": {"name": "source", "format": "element-properties"}},
            "capsfilter": {"type": "string"},
            "postproc": {"type": "string"}
        },
        "required": ["type", "element"]
    },
    "oneOf": [
        {
            "$ref": "#/uri"
        },
        {
            "$ref": "#/webcam"
        },
        {
            "$ref": "#/gst"
        },
        {
            "$ref": "#/application"
        }
    ]
}

destination = {
    "metadata": {
        "application": {
            "type":"object",
            "properties": {
                "type": {
                    "type":"string",
                    "enum":["application"]
                },
                "class": {
                    "type":"string"
                }
            },
            "required":["type", "class"]
        },
        "file": {
            "type": "object",
            "properties": {
                "type": {
                    "type": "string",
                    "enum": ["file"],
                    "element": {
                        "name": "destination",
                        "property": "method"
                    },
                    "filter": {
                        "name": "metapublish",
                        "type": "output",
                        "property": "method",
                        "values": [0]
                    }
                },
                "path": {
                    "type": "string",
                    "format": "path",
                    "filter": {
                        "name": "metapublish",
                        "type": "output",
                        "property": "_METAPUBLISH_ARG_"
                    },
                    "element": {
                        "name": "destination",
                        "property": "file-path"
                    }
                },
                "format": {
                    "type": "string",
                    "enum": [
                        "json-lines",
                        "json"
                    ],
                    "filter": {
                        "name": "metapublish",
                        "type": "output",
                        "property": "output_format",
                        "values": ["stream", "batch"]
                    },
                    "element": {
                        "name": "destination",
                        "property": "file-format"
                    }
                }
            },
            "required": ["type", "path"]
        },
        "mqtt": {
            "type": "object",
            "properties": {
                "type": {
                    "type": "string",
                    "enum": ["mqtt"],
                    "element": {"name": "destination", "property": "method"}
                },
                "host": {
                    "type": "string",
                    "element": {
                        "name": "destination",
                        "property": "address"
                    }
                },
                "topic": {
                    "type": "string",
                    "element": "destination"
                },
                "mqtt-client-id": {
                    "type": "string",
                    "element": "destination"
                },
                "timeout": {
                    "type": "integer",
                    "element": "destination"
                }
            },
            "required": [
                "host",
                "type",
                "topic"
            ]
        },
        "kafka": {
            "type": "object",
            "properties": {
                "type": {
                    "type": "string",
                    "enum": ["kafka"],
                    "element": {"name": "destination", "property": "method"},
                    "filter": {
                        "name": "metapublish",
                        "property": "method",
                        "values": [1],
                        "type": "output"
                    }
                },
                "host": {
                    "type": "string",
                    "description": "host:port to use as bootstrap server.",
                    "filter": {
                        "name": "metapublish",
                        "type": "output",
                        "property": "_METAPUBLISH_KAFKA_HOST_"
                    },
                    "element": {
                        "name": "destination",
                        "property": "address"
                    }
                },
                "topic": {
                    "type": "string",
                    "element": "destination",
                    "filter": {
                        "name": "metapublish",
                        "type": "output",
                        "property": "_METAPUBLISH_KAFKA_TOPIC_"
                    }
                }
            },
            "required": [
                "type",
                "host",
                "topic"
            ]
        },
        "oneOf": [
            {
                "$ref": "#/kafka"
            },
            {
                "$ref": "#/mqtt"
            },
            {
                "$ref": "#/file"
            },
            {
                "$ref": "#/application"
            }
        ]
    },
    "frame": {
    "anyOf": [
      {
        "type": "object",
        "oneOf": [
          {
            "type": "object",
            "properties": {
              "type": {
                "type": "string",
                "enum": ["rtsp"]
              },
              "path": {
                "type": "string",
                "minLength": 1,
                "pattern": "^[a-zA-Z0-9][a-zA-Z0-9_/-]*[a-zA-Z0-9]$"
              },
              "cache-length": {
                "type": "integer",
                "default": 30,
                "minimum": 0
              },
              "sync-with-source": {
                "type": "boolean",
                "default": True
              },
              "sync-with-destination": {
                "type": "boolean",
                "default": True
              },
              "encode-quality": {
                "type": "integer",
                "minimum": 0,
                "maximum": 100,
                "default": 85
              },
              "overlay": {
                "type": "boolean",
                "default": True
              }
            },
            "required": [
              "type",
              "path"
            ]
          },
          {
            "type": "object",
            "properties": {
              "type": {
                "type": "string",
                "enum": ["webrtc"]
              },
              "peer-id": {
                "type": "string",
                "minLength": 1,
                "pattern": "^[a-zA-Z0-9][a-zA-Z0-9_/-]*[a-zA-Z0-9]$"
              },
              "cache-length": {
                "type": "integer"
              },
              "sync-with-source": {
                "type": "boolean"
              },
              "sync-with-destination": {
                "type": "boolean"
              },
              "encode-cq-level": {
                "type": "integer"
              },
              "overlay": {
                "type": "boolean",
                "default": True
              }
            },
            "required": [
              "type",
              "peer-id"
            ]
          }
        ]
      },
      {
        "type": "array",
        "items": {
          "oneOf": [
            {
              "type": "object",
              "properties": {
                "type": {
                  "type": "string",
                  "enum": ["rtsp"]
                },
                "path": {
                  "type": "string",
                  "minLength": 1,
                  "pattern": "^[a-zA-Z0-9][a-zA-Z0-9_/-]*[a-zA-Z0-9]$"
                },
                "cache-length": {
                  "type": "integer",
                  "default": 30,
                  "minimum": 0
                },
                "sync-with-source": {
                  "type": "boolean",
                  "default": True
                },
                "sync-with-destination": {
                  "type": "boolean",
                  "default": True
                },
                "encode-quality": {
                  "type": "integer",
                  "minimum": 0,
                  "maximum": 100,
                  "default": 85
                },
                "overlay": {
                  "type": "boolean",
                  "default": True
                }
              },
              "required": [
                "type",
                "path"
              ]
            },
            {
              "type": "object",
              "properties": {
                "type": {
                  "type": "string",
                  "enum": ["webrtc"]
                },
                "peer-id": {
                  "type": "string",
                  "minLength": 1,
                  "pattern": "^[a-zA-Z0-9][a-zA-Z0-9_/-]*[a-zA-Z0-9]$"
                },
                "cache-length": {
                  "type": "integer"
                },
                "sync-with-source": {
                  "type": "boolean"
                },
                "sync-with-destination": {
                  "type": "boolean"
                },
                "encode-cq-level": {
                  "type": "integer"
                },
                "overlay": {
                  "type": "boolean"
                }
              },
              "required": [
                "type",
                "peer-id"
              ]
            }
          ]
        }
      }
    ]
  },
  "anyOf": [
    {
      "required": ["frame"]
    },
    {
      "required": ["metadata"]
    },
    {}
  ]
}

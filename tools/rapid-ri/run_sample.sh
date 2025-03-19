#!/bin/bash

curl http://localhost:8080/pipelines/user_defined_pipelines/car_plate_recognition_1 -X POST -H 'Content-Type: application/json' -d ' 
{
    "source": {
        "uri": "file:///home/pipeline-server/videos/cars_extended.mp4", 
        "type": "uri"
    },
    "destination": {
        "metadata": {
            "type": "mqtt",
            "host": "0.0.0.0:1883", 
            "topic": "object_detection_1",
            "timeout": 1000
        },
        "frame": {
            "type": "webrtc",
            "peer-id": "object_detection_1"
        }
    },
    "parameters": {
        "detection-device": "CPU"
    }
}'

curl http://localhost:8080/pipelines/user_defined_pipelines/car_plate_recognition_2 -X POST -H 'Content-Type: application/json' -d ' 
{
    "source": {
        "uri": "file:///home/pipeline-server/videos/cars_extended.mp4", 
        "type": "uri"
    },
    "destination": {
        "metadata": {
            "type": "mqtt",
            "host": "0.0.0.0:1883", 
            "topic": "object_detection_2",
            "timeout": 1000
        },
        "frame": {
            "type": "webrtc",
            "peer-id": "object_detection_2"
        }
    },
    "parameters": {
        "detection-device": "CPU"
    }
}'

curl http://localhost:8080/pipelines/user_defined_pipelines/car_plate_recognition_3 -X POST -H 'Content-Type: application/json' -d ' 
{
    "source": {
        "uri": "file:///home/pipeline-server/videos/cars_extended.mp4", 
        "type": "uri"
    },
    "destination": {
        "metadata": {
            "type": "mqtt",
            "host": "0.0.0.0:1883", 
            "topic": "object_detection_3",
            "timeout": 1000
        },
        "frame": {
            "type": "webrtc",
            "peer-id": "object_detection_3"
        }
    },
    "parameters": {
        "detection-device": "CPU"
    }
}'

curl http://localhost:8080/pipelines/user_defined_pipelines/car_plate_recognition_4 -X POST -H 'Content-Type: application/json' -d ' 
{
    "source": {
        "uri": "file:///home/pipeline-server/videos/cars_extended.mp4", 
        "type": "uri"
    },
    "destination": {
        "metadata": {
            "type": "mqtt",
            "host": "0.0.0.0:1883", 
            "topic": "object_detection_4",
            "timeout": 1000
        },
        "frame": {
            "type": "webrtc",
            "peer-id": "object_detection_4"
        }
    },
    "parameters": {
        "detection-device": "CPU"
    }
}'

curl http://localhost:8080/pipelines/user_defined_pipelines/car_plate_recognition_5 -X POST -H 'Content-Type: application/json' -d ' 
{
    "source": {
        "uri": "file:///home/pipeline-server/videos/cars_extended.mp4", 
        "type": "uri"
    },
    "destination": {
        "metadata": {
            "type": "mqtt",
            "host": "0.0.0.0:1883", 
            "topic": "object_detection_5",
            "timeout": 1000
        },
        "frame": {
            "type": "webrtc",
            "peer-id": "object_detection_5"
        }
    },
    "parameters": {
        "detection-device": "CPU"
    }
}'

curl http://localhost:8080/pipelines/user_defined_pipelines/car_plate_recognition_6 -X POST -H 'Content-Type: application/json' -d ' 
{
    "source": {
        "uri": "file:///home/pipeline-server/videos/cars_extended.mp4", 
        "type": "uri"
    },
    "destination": {
        "metadata": {
            "type": "mqtt",
            "host": "0.0.0.0:1883", 
            "topic": "object_detection_6",
            "timeout": 1000
        },
        "frame": {
            "type": "webrtc",
            "peer-id": "object_detection_6"
        }
    },
    "parameters": {
        "detection-device": "CPU"
    }
}'

curl http://localhost:8080/pipelines/user_defined_pipelines/car_plate_recognition_7 -X POST -H 'Content-Type: application/json' -d ' 
{
    "source": {
        "uri": "file:///home/pipeline-server/videos/cars_extended.mp4", 
        "type": "uri"
    },
    "destination": {
        "metadata": {
            "type": "mqtt",
            "host": "0.0.0.0:1883", 
            "topic": "object_detection_7",
            "timeout": 1000
        },
        "frame": {
            "type": "webrtc",
            "peer-id": "object_detection_7"
        }
    },
    "parameters": {
        "detection-device": "CPU"
    }
}'

curl http://localhost:8080/pipelines/user_defined_pipelines/car_plate_recognition_8 -X POST -H 'Content-Type: application/json' -d ' 
{
    "source": {
        "uri": "file:///home/pipeline-server/videos/cars_extended.mp4", 
        "type": "uri"
    },
    "destination": {
        "metadata": {
            "type": "mqtt",
            "host": "0.0.0.0:1883", 
            "topic": "object_detection_8",
            "timeout": 1000
        },
        "frame": {
            "type": "webrtc",
            "peer-id": "object_detection_8"
        }
    },
    "parameters": {
        "detection-device": "CPU"
    }
}'

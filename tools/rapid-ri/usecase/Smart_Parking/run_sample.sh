#!/bin/bash

curl http://localhost:8080/pipelines/user_defined_pipelines/yolov10_1 -X POST -H 'Content-Type: application/json' -d ' 
{
    "source": {
        "uri": "file:///home/pipeline-server/videos/new_video_1.mp4", 
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

curl http://localhost:8080/pipelines/user_defined_pipelines/yolov10_2 -X POST -H 'Content-Type: application/json' -d ' 
{
    "source": {
        "uri": "file:///home/pipeline-server/videos/new_video_2.mp4", 
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

curl http://localhost:8080/pipelines/user_defined_pipelines/yolov10_3 -X POST -H 'Content-Type: application/json' -d ' 
{
    "source": {
        "uri": "file:///home/pipeline-server/videos/new_video_3.mp4", 
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

curl http://localhost:8080/pipelines/user_defined_pipelines/yolov10_4 -X POST -H 'Content-Type: application/json' -d ' 
{
    "source": {
        "uri": "file:///home/pipeline-server/videos/new_video_4.mp4", 
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

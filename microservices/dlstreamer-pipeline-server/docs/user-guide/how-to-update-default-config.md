# How to update default config

## Prerequisite for tutorials

For tutorials that requires you to update the default configuration of EVAM, please follow the below instruction.

Ensure that you have a `[EVAM_WORKDIR]/configs/default/config.json` file with the below snippet in your workspace (`EVAM_WORKDIR`) on the host machine. The tutorials will take you through updating the configuration accordingly.
```sh
{
    "config": {
        "logging": {
            "C_LOG_LEVEL": "INFO",
            "PY_LOG_LEVEL": "INFO"
        },
        "pipelines": [
            {
                "name": "pallet_defect_detection",
                "source": "gstreamer",
                "queue_maxsize": 50,
                "pipeline": "{auto_source} name=source  ! decodebin ! videoconvert ! gvadetect name=detection model-instance-id=inst0 ! queue ! gvafpscounter ! gvametaconvert add-empty-results=true name=metaconvert ! gvametapublish name=destination ! appsink name=appsink",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "detection-properties": {
                             "element": {
                                "name": "detection",
                                "format": "element-properties"
                              }
                        }
                    }
                },
                "auto_start": false
            }
        ]
    }
}
```
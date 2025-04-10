# How to run User Defined Function (UDF) pipelines

## Steps
EVAM supports udfloader element which allow user to write an User Defined Function (UDF) that can transform video frames and/or manipulate metadata. You can do this by adding an element called 'udfloader'. You can try simple udfloader pipeline by replacing the following sections in [EVAM_WORKDIR]/configs/default/config.json with the following
Note: Follow instruction in the [Prerequisite section](./how-to-update-default-config.md#prerequisite-for-tutorials) to create a sample configuration file.

- replace `"pipeline"` section with  

    ```sh
    "pipeline": "{auto_source} name=source  ! decodebin ! videoconvert ! video/x-raw,format=RGB ! udfloader name=udfloader ! gvametaconvert add-empty-results=true name=metaconvert ! gvametapublish name=destination ! appsink name=appsink",
    ```

- replace `"properties"` section with  

    ```sh
    "properties": {
        "udfloader": {
            "element": {
                "name": "udfloader",
                "property": "config",
                "format": "json"
            },
            "type": "object"
        }
    }
    ```

- add `"udfs"` section in config (after `"parameters"`)  

    ```sh
    "udfs": {
        "udfloader": [
            {
                "name": "python.geti_udf.geti_udf",
                "type": "python",
                "device": "CPU",
                "visualize": "true",
                "deployment": "./resources/models/geti/pallet_defect_detection/deployment",
                "metadata_converter": "null"
            }
        ]
    }
    ```
Save the config.json and restart EVAM
Ensure that the changes made to the config.json are reflected in the container by volume mounting (as mentioned in this [document](./how-to-change-dlstreamer-pipeline.md)) it.

```sh
    cd [EVAM_WORKDIR]/docker/
    docker compose down
    docker compose up
```

Now to start this pipeline, run below Curl request

```sh
curl http://localhost:8080/pipelines/user_defined_pipelines/pallet_defect_detection -X POST -H 'Content-Type: application/json' -d '{
    "source": {
        "uri": "file:///home/pipeline-server/resources/videos/warehouse.avi",
        "type": "uri"
    },
    "destination": {
        "metadata": {
            "type": "file",
            "path": "/tmp/results.jsonl",
            "format": "json-lines"
        },
        "frame": {
            "type": "rtsp",
            "path": "pallet_defect_detection"
        }
    },
    "parameters": {
        "udfloader": {
            "udfs": [
                {
                    "name": "python.geti_udf.geti_udf",
                    "type": "python",
                    "device": "CPU",
                    "visualize": "true",
                    "deployment": "./resources/models/geti/pallet_defect_detection/deployment",
                    "metadata_converter": "null"
                }
            ]
        }
    }
}'
```

`Note` The `"udfloader"` config needs to be present in either config.json or in the curl command. It is not needed at both places. However, if specified at both places then the config in curl command will override the config present in config.json

We should see the metadata results in `/tmp/results.jsonl`

For more details on UDF, you can refer this [document](./advanced-guide/detailed_usage/udf/UDF_writing_guide.md)
# How to use image file as source over REST payload

- [Image file as source](#image-file-as-source)
    - [Async mode](#async-mode)
    - [Sync mode](#sync-mode)


## Image file as source

Pipeline requests can also be sent on demand for an image file source on an already queued pipeline. It is only supported for source type: `"image-ingestor"`. 

There are two steps to run image ingestor.
1. First, a pipeline is queued that loads the pipeline and configures the request type to be asynchronous or synchronous in order. This prepares the pipeline for the image requests to follow. This would set the pipeline to enter in `QUEUED` state and wait for requests.
2. Secondly, individual image requests are then sent to this queued pipeline to fetch the metadata or image blob, which can be either in the response or some other destination.

### Asynchronous vs Synchronous behavior
Image request can be run in 2 modes - *sync* and *async*. This configuration is set while pipeline is queued.

* `"sync":true`  config is used when we want the output to be displayed as response for post request
* `"sync":false`  config is used when we want to have more control on the output.

### Async mode

By default, image ingestor runs in async mode i.e. `sync` is `false`.
A sample config has been provided for this demonstration at `[WORKDIR]/edge-ai-libraries/microservices/dlstreamer-pipeline-server/configs/sample_image_ingestor/config.json`. We need to volume mount the sample config file in `docker-compose.yml` file. Refer below snippets:

```sh
    volumes:
      # Volume mount [WORKDIR]/edge-ai-libraries/microservices/dlstreamer-pipeline-server/configs/sample_image_ingestor/config.json to config file that DL Streamer Pipeline Server container loads.
      - "../configs/sample_image_ingestor/config.json:/home/pipeline-server/config.json"
```


Follow [this tutorial](how-to-change-dlstreamer-pipeline.md) to launch DL Streamer pipeline server with above config. 

Pipeline can be started by the following request. This would set the pipeline in queued state to wait for images requests. Here is a sample request to queue the pipeline in asynchronous mode i.e. `sync`:`false` (default if omitted)

`Note` that source is not needed to start the pipeline, only destination and other parameters. Destination is required only when "*sync*" config is set to false.

```sh
curl localhost:8080/pipelines/user_defined_pipelines/pallet_defect_detection -X POST -H 'Content-Type: application/json' -d '{
    "sync": false,
    "destination": {
        "metadata": {
            "type": "file",
            "path": "/tmp/results1.jsonl",
            "format": "json-lines"
        }
    },
    "parameters": {
        "detection-properties": {
            "model": "/home/pipeline-server/resources/models/geti/pallet_defect_detection/deployment/Detection/model/model.xml",
            "device": "CPU"
        }
    }
}'
```
Once the pipeline has started, we would receive an instance id (e.g. `9b041988436c11ef8e690242c0a82003`). We can use this instance id to send inference requests for images as shown below. Replace the `{instance_id}` to the id you would have received as a response from the previous POST request.

Note that only source section is needed for the image files to send infer requests. Make sure that DL Streamer pipeline server has access to the source file preferably by volume mounting in `docker-compose.yml`.

```sh
curl localhost:8080/pipelines/user_defined_pipelines/pallet_defect_detection/{instance_id} -X POST -H 'Content-Type: application/json' -d '{
    "source": {
        "path": "/home/pipeline-server/resources/images/classroom.jpg",
        "type": "file"
    }
}'
```
Note: The path in the above command `/home/pipeline-server/resources/images/classroom.jpg` is not a part of DL Streamer pipeline server docker image and is for the sake of explanation only. If you would like to actually use this path (classroom.jpg image), it is available in DL Streamer pipeline server's github repo, under the "resources" folder and should be appropriately volume mounted to DL Streamer pipeline server container in its docker compose file.
Example:
```sh
    volumes:
      - "../resources:/home/pipeline-server/resources/"  
```
Alternatively, you can appropriately volume mount a .jpg image of your choice.
To get you started, sample docker compose file is available [here](get-started.md#pull-the-image-and-start-container)

The output metadata will be available in the destination provided while queuing the pipeline, which is `/tmp/results.jsonl`.
Users can make as many request to the queued pipeline until the pipeline has been explicitly stopped.

### Sync mode

Another way of queuing a image ingestor pipeline is in synchronous mode. The pipeline destination should be compatible to support this mode i.e. the destination should be `appsink`.

- Change `"pipeline"` section in `[WORKDIR]/edge-ai-libraries/microservices/dlstreamer-pipeline-server/configs/sample_image_ingestor/config.json`. 

    ```sh
    "pipeline": "appsrc name=source  ! decodebin  ! videoconvert ! videoscale ! gvadetect name=detection ! queue ! gvametaconvert add-empty-results=true name=metaconvert ! appsink name=destination",
    ```
    
- We need to volume mount the `[WORKDIR]/edge-ai-libraries/microservices/dlstreamer-pipeline-server/configs/sample_image_ingestor/config.json` config file in `docker-compose.yml` file. Refer below snippets:

```sh
    volumes:
      # Volume mount [WORKDIR]/edge-ai-libraries/microservices/dlstreamer-pipeline-server/configs/sample_image_ingestor/config.json to config file that DL Streamer Pipeline Server container loads.
      - "../configs/sample_image_ingestor/config.json:/home/pipeline-server/config.json"
```

Follow [this tutorial](how-to-change-dlstreamer-pipeline.md) to launch DL Streamer pipeline server with above config. 

Pipeline for sync mode can be started by sending the following curl request 
```sh
curl localhost:8080/pipelines/user_defined_pipelines/pallet_defect_detection -X POST -H 'Content-Type: application/json' -d '{
    "sync": true,
    "parameters": {
        "detection-properties": {
            "model": "/home/pipeline-server/resources/models/geti/pallet_defect_detection/deployment/Detection/model/model.xml",
            "device": "CPU"
        }
    }
}'
```

Once the pipeline is queued, we will receive an instance id. Use this instance id to send inference requests for images as shown below. Have shared a sample request below. 

```sh
curl localhost:8080/pipelines/user_defined_pipelines/pallet_defect_detection/{instance_id} -X POST -H 'Content-Type: application/json' -d '{
    "source": {
        "path": "/home/pipeline-server/resources/images/classroom.jpg",
        "type": "file"
    },
    "publish_frame":true,
    "timeout":10
}'
```
Note: The path in the above command `/home/pipeline-server/resources/images/classroom.jpg` is not a part of DL Streamer pipeline server docker image and is for the sake of explanation only. If you would like to actually use this path (classroom.jpg image), it is available in DL Streamer pipeline server's github repo, under the "resources" folder and should be appropriately volume mounted to DL Streamer pipeline server container in its docker compose file.
Example:
```sh
    volumes:
      - "../resources:/home/pipeline-server/resources/"  
```
Alternatively, you can appropriately volume mount a .jpg image of your choice.
To get you started, sample docker compose file is available [here](get-started.md#pull-the-image-and-start-container)

Since the pipeline is queued for sync requests, the inference results will be shown in response for post request. Here is a sample response

```json
{
  "metadata": {
    "height": 480,
    "width": 820,
    "channels": 4,
    "source_path": "file:///root/image-examples/example.png",
    "caps": "video/x-raw, width=(int)820, height=(int)468",
    "OTHER_METADATA": {
      "other": "additional pipeline meta data"
    }
  },
  "blobs": "=8HJLhxhj77XHMHxilNKjbjhBbnkjkjBhbjLnjbKJ80n0090u9lmlnBJoiGjJKBK=76788GhjbhjK"
}
```

To learn more on different configurations supported by the request, you can refer [this section](api-reference.md) 
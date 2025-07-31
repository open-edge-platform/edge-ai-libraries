# Get Started

-   **Time to Complete:** 5 - 15 minutes
-   **Programming Language:** Python 3

## Prerequisites

* [System Requirements](./system-requirements.md)
  
## Quick try out
Follow the steps in this section to quickly pull the latest pre-built DL Streamer Pipeline Server docker image followed by running a sample usecase. 

### Pull the image and start container

- Pull the image with the latest tag from dockerhub registry

   For Ubuntu 22.04:
   ```sh
     docker pull intel/dlstreamer-pipeline-server:3.1.0-ubuntu22
   ```
   For Ubuntu 24.04:
   ```sh
     docker pull intel/dlstreamer-pipeline-server:3.1.0-ubuntu24
   ```

- Clone the Edge-AI-Libraries repository from open edge platform and change to the docker directory inside DL Streamer Pipeline Server project.

  ```sh
    cd [WORKDIR]
    git clone https://github.com/open-edge-platform/edge-ai-libraries.git
    cd edge-ai-libraries/microservices/dlstreamer-pipeline-server/docker
    ```

- Bring up the container

   ```sh
     docker compose up
   ```
   
### Run default sample

Once the container is up, we will send a pipeline request to DL Streamer pipeline server to run a detection model on a warehouse video. Both the model and video are provided as default sample in the docker image.

We will send the below curl request to run the inference.
It comprises of a source file path which is `warehouse.avi`, a destination, with metadata directed to a json fine in `/tmp/resuts.jsonl` and frames streamed over RTSP with id `pallet_defect_detection`. Additionally, we will also provide the GETi model path that would be used for detecting defective boxes on the video file.

Open another terminal and send the following curl request
``` sh
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
        "detection-properties": {
            "model": "/home/pipeline-server/resources/models/geti/pallet_defect_detection/deployment/Detection/model/model.xml",
            "device": "CPU"
        }
    }
}'
```

The REST request will return a pipeline instance ID, which can be used as an identifier to query later the pipeline status or stop the pipeline instance. For example, a6d67224eacc11ec9f360242c0a86003.

- To view the metadata, open another terminal and run the following command,
  ```sh
    tail -f /tmp/results.jsonl
  ```

- RTSP Stream will be accessible at `rtsp://<SYSTEM_IP_ADDRESS>:8554/pallet_defect_detection`.  Users can view this on any media player e.g. vlc (as a network stream), ffplay etc 

  ![sample frame RTSP stream](./images/sample-pallet-defect-detection.png)

To check the pipeline status and stop the pipeline send the following requests,

 - view the pipeline status that you triggered in the above step.
   ```sh
    curl --location -X GET http://localhost:8080/pipelines/status
   ```

 - stop a running pipeline instance, 
   ```sh
    curl --location -X DELETE http://localhost:8080/pipelines/{instance_id}
   ```

Now you have successfully run the DL Streamer Pipeline Server container, sent a curl request to start a pipeline within the microservice which runs the Geti based pallet defect detection model on a sample warehouse video. Then, you have also looked into the status of the pipeline to see if everything worked as expected and eventually stopped the pipeline as well.


## Legal Information
Intel, the Intel logo, and Xeon are trademarks of Intel Corporation in the U.S. and/or other countries.

GStreamer is an open source framework licensed under LGPL. See [GStreamer licensing](https://gstreamer.freedesktop.org/documentation/frequently-asked-questions/licensing.html)⁠. You are solely responsible for determining if your use of GStreamer requires any additional licenses. Intel is not responsible for obtaining any such licenses, nor liable for any licensing fees due, in connection with your use of GStreamer.

*Other names and brands may be claimed as the property of others.

## Advanced Setup Options

For alternative ways to set up the microservice, see:

- [How to Deploy with Helm](./how-to-deploy-with-helm.md)

## Troubleshooting

- **Using REST API in Image Ingestor mode has low first inference latency**

    This is an expected behavior observed only for the first inference. Subsequent inferences would be considerably faster. 
    For inference on GPU, the first inference might be even slower. Latency for up to 15 seconds have been observed for image requests inference on GPU.
    When in `sync` mode, we suggest users to provide a `timeout` with a value to accommodate for the first inference latency to avoid request time out. 
    Read [here](./advanced-guide/detailed_usage/rest_api/restapi_reference_guide.md#post-pipelinesnameversioninstance_id) to learn more about the API.


- **Axis RTSP camera freezes or pipeline stops**

    Restart the DL Streamer pipeline server container with the pipeline that has this rtsp source.


- **Deploying with Intel GPU K8S Extension on ITEP**

    If you're deploying a GPU based pipeline (example: with VA-API elements like `vapostproc`, `vah264dec` etc., and/or with `device=GPU` in `gvadetect` in `dlstreamer_pipeline_server_config.json`) with Intel GPU k8s Extension on ITEP, ensure to set the below details in the file `helm/values.yaml` appropriately in order to utilize the underlying GPU.
    ```sh
    gpu:
      enabled: true
      type: "gpu.intel.com/i915"
      count: 1
    ```

- **Deploying without Intel GPU K8S Extension**

    If you're deploying a GPU based pipeline (example: with VA-API elements like `vapostproc`, `vah264dec` etc., and/or with `device=GPU` in `gvadetect` in `dlstreamer_pipeline_server_config.json`) without Intel GPU k8s Extension, ensure to set the below details in the file `helm/values.yaml` appropriately in order to utilize the underlying GPU.
    ```sh
    privileged_access_required: true
    ```

- **Using RTSP/WebRTC streaming, S3_write or MQTT fails with GPU elements in pipeline**
 
    If you are using GPU elements in the pipeline, RTSP/WebRTC streaming, S3_write and MQTT will not work because these are expects CPU buffer. \
    Add `vapostproc ! video/x-raw` before appsink element or `jpegenc` element(in case you are using S3_write) in the GPU pipeline.
    ```sh
    # Sample pipeline
 
    "pipeline": "{auto_source} name=source ! parsebin ! vah264dec ! vapostproc ! video/x-raw(memory:VAMemory) ! gvadetect name=detection model-instance-id=inst0 ! queue ! gvafpscounter ! gvametaconvert add-empty-results=true name=metaconvert ! gvametapublish name=destination ! vapostproc ! video/x-raw ! appsink name=appsink"
    ```

- **RTSP streaming fails if you are using udfloader**
 
    If you are using udfloader<link> pipeline RTSP streaming will not work because RTSP pipeline does not support RGB, BGR or Mono format.
    If you are using `udfloader pipeline` or `RGB, BGR or GRAY8` format in the pipeline, add  `videoconvert ! video/x-raw, format=(string)NV12` before `appsink` element in pipeline.
    ```sh
    # Sample pipeline
 
    "pipeline": "{auto_source} name=source  ! decodebin ! videoconvert ! video/x-raw,format=RGB ! udfloader name=udfloader ! gvametaconvert add-empty-results=true name=metaconvert ! gvametapublish name=destination ! videoconvert ! video/x-raw, format=(string)NV12 ! appsink name=appsink"
    ```

- **Resolving Time Sync Issues in Prometheus**

    If you see the following warning in Prometheus, it indicates a time sync issue.

    **Warning: Error fetching server time: Detected xxx.xxx seconds time difference between your browser and the server.**

    You can following the below steps to synchronize system time using NTP.
    1. **Install systemd-timesyncd** if not already installed:
        ```bash
        sudo apt install systemd-timesyncd
        ```

    2. **Check service status**:
        ```bash
        systemctl status systemd-timesyncd
        ```

    3. **Configure an NTP server** (if behind a corporate proxy):
        ```bash
        sudo nano /etc/systemd/timesyncd.conf
        ```
        Add:
        ```ini
        [Time]
        NTP=corp.intel.com
        ```
        Replace `corp.intel.com` with a different ntp server that is supported on your network.

    4. **Restart the service**:
        ```bash
        sudo systemctl restart systemd-timesyncd
        ```

    5. **Verify the status**:
        ```bash
        systemctl status systemd-timesyncd
        ```

    This should resolve the time discrepancy in Prometheus.

## Known Issues

- **Running DL Streamer Pipeline Server on Ubuntu 24.04**

    User has to install `docker compose v2` to run DL Streamer Pipeline Server on Ubuntu 24.04.


## Contact Us

Please contact us at dlsps_support[at]intel[dot]com for more details or any support.

## Supporting Resources

* [Overview](Overview.md)
* [API Reference](api-reference.md)
* [System Requirements](system-requirements.md)

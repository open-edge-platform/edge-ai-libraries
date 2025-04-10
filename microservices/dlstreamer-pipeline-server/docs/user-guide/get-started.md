# Get Started

-   **Time to Complete:** 5 - 15 minutes
-   **Programming Language:** Python 3

## Prerequisites

Ensure that the following installations are present.

* unzip. It can be installed using `sudo apt-get install unzip`
*
  | OS  |  Python           |
  |-----|-------------------|
  |Ubuntu 22.04|      3.10  |
  
## Quick try out
Follow the steps in this section to quickly pull the latest pre-built Edge Video Analytics Microservice docker image followed by running a sample usecase. 

### Pull the image and start container

- Pull the image with the latest tag from dockerhub registry

   ```sh
     docker pull intel/edge-video-analytics-microservice:2.4.0
   ```

- Create `docker-compose.yml` file with below contents inside the docker folder within your work directory (`[EVAM_WORKDIR]/docker/`). `EVAM_WORKDIR` is your host machine workspace:

   ```yaml
    #
    # Copyright (C) 2024 Intel Corporation
    # SPDX-License-Identifier: Apache-2.0
    #

    services:
      edge-video-analytics-microservice:
        image: intel/edge-video-analytics-microservice:2.4.0
        hostname: edge-video-analytics-microservice
        container_name: edge-video-analytics-microservice
        read_only: true
        security_opt:
        - no-new-privileges
        privileged: false
        tty: true
        entrypoint: ["./run.sh"]
        ports:
          - '8080:8080'
          - '8554:8554'
        networks:
          - app_network
        environment:
          - ENABLE_RTSP=true
          - RTSP_PORT=8554
          - no_proxy=$no_proxy,${RTSP_CAMERA_IP}
          - http_proxy=$http_proxy
          - https_proxy=$https_proxy
          - RUN_MODE=EVA
          - GST_DEBUG=1
          # Default Detection and Classification Device
          - DETECTION_DEVICE=CPU
          - CLASSIFICATION_DEVICE=CPU
          - ADD_UTCTIME_TO_METADATA=true
          - LSFEATURE_NAME="EVAM"
          - HTTPS=false # Make it "true" to enable SSL/TLS secure mode, mount the generated certificates
          - MTLS_VERIFICATION=false # if HTTPS=true, enable/disable client certificate verification for mTLS
          # Model Registry Microservice
          - MR_VERIFY_CERT=/run/secrets/ModelRegistry_Server/ca-bundle.crt
          # Append pipeline name to a publisher topic
          - APPEND_PIPELINE_NAME_TO_PUBLISHER_TOPIC=false
          - REST_SERVER_PORT=8080
        volumes:
          # - "../configs/default/config.json:/home/pipeline-server/config.json"
          - vol_evam_pipeline_root:/var/cache/pipeline_root:uid=1999,gid=1999
          - "../certificates:/MqttCerts:ro"
          - "../Certificates/ssl_server/:/run/secrets/EdgeVideoAnalyticsMicroservice_Server:ro"
          - "../Certificates/model_registry/:/run/secrets/ModelRegistry_Server:ro"
          - "/run/udev:/run/udev:ro"
          - "/dev:/dev"
          - "/tmp:/tmp"
          - "./mr_models:/home/pipeline-server/mr_models:rw"
        group_add:
          - "109"
          - "110"
        device_cgroup_rules:
        - 'c 189:* rmw'
        - 'c 209:* rmw'
        - 'a 189:* rwm'
        devices:
        - "/dev:/dev"

    networks:
      app_network:
        driver: "bridge"

    volumes:
      vol_evam_pipeline_root:
        driver: local
        driver_opts:
          type: tmpfs
          device: tmpfs
   ```

- Bring up the container
   ```sh
     docker compose up
   ```
### Run default sample

Once the container is up, we will send a pipeline request to EVAM to run a detection model on a warehouse video. Both the model and video are provided as default sample in the docker image.

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

Now you have successfully run the Edge Video Analytics Microservice container, sent a curl request to start a pipeline within the microservice which runs the Geti based pallet defect detection model on a sample warehouse video. Then, you have also looked into the status of the pipeline to see if everything worked as expected and eventually stopped the pipeline as well.


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
    Read [here](./api-reference.md) to learn how to do that.


- **InactiveRpcError, StatusCode.DEADLINE_EXCEEDED**
    
    If DEADLINE_EXCEEDED errors are seen in the logs, most like the server is unreachable.

    Sample error
    ```sh
    2024-10-25 15:25:20,685 : ERROR : root : [edge_grpc_client.py] :send : in line : [109] : <_InactiveRpcError of RPC that terminated with:
            status = StatusCode.DEADLINE_EXCEEDED
            details = "Deadline Exceeded"
            debug_error_string = "UNKNOWN:Error received from peer  {created_time:"2024-10-25T15:25:20.684936173+00:00", grpc_status:4, grpc_message:"Deadline Exceeded"}"
    >
    ```
    
    Please check if that particular client services is up/accessible.     
    - Check if endpoints and ports are correct for both server and client(in EVAM client list).
    - Also check if the container name is added to EVAM's `no_proxy` environment variable in docker compose file.


- **Axis RTSP camera freezes or pipeline stops**

    Restart the EVAM container with the pipeline that has this rtsp source.


- **Inference on GPU backend fails in EVAM helm chart deployment**

    Add the below as specified in the comments and re-deploy helm chart.

    ```sh
      # Add this in EVAM's Deployment under the spec -> template -> spec section
      securityContext:
        supplementalGroups: [109,110]

      # Add this in EVAM's Deployment under the spec -> template -> spec -> containers section
      securityContext:
        privileged: true  # Required for direct access to /dev
    ```

- **Deploying with Intel GPU K8S Extension on ITEP**

    If you're deploying a GPU based pipeline (example: with VA-API elements like `vapostproc`, `vah264dec` etc., and/or with `device=GPU` in `gvadetect` in `evam_config.json`) with Intel GPU k8s Extension on ITEP, ensure to add the below under `containers` section in the Deployment present in the file `helm/templates/edge-video-analytics-microservice-deployment.yaml` in order to utilize the underlying GPU.
    ```sh
    resources:
        limits:
        gpu.intel.com/i915: 1
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

- **High CPU utilization in i9-13900K**

    Pipelines where encoding is done by supported publisher such as EVAM's gRPC publisher, CPU consumption spikes have been observed. Especially for CPUs with readily available CPU cores for fast inferencing and encoding, e.g. i9-13000K.
    Learn more [here](./advanced-guide/detailed_usage/publisher/grpc_publish_doc.md#known-issues).

- **Running EVAM on Ubuntu 24.04**

    User has to install `docker compose v2` to run EVAM on Ubuntu 24.04.


## Contact Us

Please contact us at evam_support[at]intel[dot]com for more details or any support.

## Supporting Resources

* [Overview](Overview.md)
* [API Reference](api-reference.md)
* [System Requirements](system-requirements.md)

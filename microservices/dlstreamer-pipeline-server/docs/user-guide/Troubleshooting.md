# Troubleshooting

- **Using REST API in Image Ingestor mode has low first inference latency**

    This is an expected behavior observed only for the first inference. Subsequent inferences would be considerably faster. 
    For inference on GPU, the first inference might be even slower. Latency for up to 15 seconds have been observed for image requests inference on GPU.
    When in `sync` mode, we suggest users to provide a `timeout` with a value to accommodate for the first inference latency to avoid request time out. 
    Read [here](../user-guide/detailed_usage/rest_api/restful_microservice_interfaces.md#post-pipelinesnameversioninstance_id) to learn how to do that.


- **USB basler does not work by default after finished installation.**

    When connected for the first time, if there is a problem connecting to USB Basler camera, please download pylon package and run setup_usb.sh.
    See installation instructions [here](../user-guide/detailed_usage/camera/genicam.md#gigeusb-basler-camera).


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

- **Disconnecting USB Camera has frames stuck**

    Try re-connecting the camera and restart the EVAM container.

- **Axis RTSP camera freezes or pipeline stops**

    Restart the EVAM container with the pipeline that has this rtsp source.

- **Duplicate watermarks overlayed on WebRTC stream**

    Please remove the `gvawatermark` element from your pipeline string present in `[EVAM_WORKDIR]/configs/default/config.json`. WebRTC pipeline already has a `gvawatermark` element present within EVAM. Hence, we need not specify it in `[EVAM_WORKDIR]/configs/default/config.json`.

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

- **Pixelated or blurry video in EVAM's output**

    In-case you see a pixelated or blurry video in EVAM's output, please ensure to insert the "avidemux" element before "h264parse" in-order to not see a pixelated or blurry video in EVAM's output. 
    Example:
    Wrong pipeline: `multifilesrc loop=TRUE location=/home/pipeline-server/resources/videos/<some-video>.avi name=source ! h264parse ! decodebin ! queue max-size-buffers=10 ! videoconvert ! gvadetect name=detection model-instance-id=inst0 ! queue ! gvawatermark ! gvafpscounter ! appsink name=destination`
    Correct pipeline: `multifilesrc loop=TRUE location=/home/pipeline-server/resources/videos/<some-video>.avi name=source ! avidemux ! h264parse ! decodebin ! queue max-size-buffers=10 ! videoconvert ! gvadetect name=detection model-instance-id=inst0 ! queue ! gvawatermark ! gvafpscounter ! appsink name=destination`

# Known Issues

- **High CPU utilization in i9-13900K**

    Pipelines where encoding is done by supported publisher such as EVAM's gRPC publisher, CPU consumption spikes have been observed. Especially for CPUs with readily available CPU cores for fast inferencing and encoding, e.g. i9-13000K.
    Learn more [here](../user-guide/detailed_usage/publisher/grpc_publish_doc.md#known-issues).

- **Pipeline instance creation error** 

    The creation of a pipeline instance that uses a model downloaded from the model registry microservice during EVAM's startup process may fail if the `auto_start` property is set to `true` in the config.json. This issue is due to missing files at the path specified via the `deployment` property.
    
    **Workaround:** 
    1. Monitor the terminal for the "Deployment directory (`{deployment}`) created for the `{pipeline['name']}` pipeline." log message.
    1. Once the message is logged, send a POST request to the `/pipelines/{name}/{version}` endpoint with the relevant request body to create a pipeline instance.

    **Note:** This workaround is a temporary measure. Our team is actively working on a solution to automatically create a pipeline instance after successfully downloading the model files.

# Contact Us

Please contact us at evam_support[at]intel[dot]com for more details or any support.

# Publishers

- [RTSP Streaming](#rtsp-streaming)
- [WebRTC](#webrtc-streaming)
- [MQTT Publishing](#mqtt-publishing)
    - [Publish Metadata via gvametapublish](#publish-metadata-via-gvametapublish)
    - [Publish Frame and Metadata via gvapython](#publish-framemetadata-via-gvapython)
    - [Publish Frame and Metadata post pipeline execution](#publish-frame-and-metadata-post-pipeline-execution)
- [OPCUA Publishing](#opcua-publishing)
- [S3 frame publishing](#s3-frame-publishing)

Processed metadata/frame from the video analytics pipeline can be published to various destinations over RTSP, WebRTC, MQTT. 

## RTSP Streaming
To send frames over RTSP for streaming, refer to this [doc](../rest_api/customizing_pipeline_requests.md#rtsp).

## WebRTC Streaming
To send frames over WebRTC for streaming, refer to this [doc](../rest_api/customizing_pipeline_requests.md#webrtc).

## MQTT Publishing

### Publish metadata via gvametapublish
To publish metadata to MQTT message broker via REST Request refer to this [doc](../rest_api/customizing_pipeline_requests.md#mqtt).

### Publish frame/metadata via gvapython
To publish frame/metadata to MQTT message broker using `gvapython` element in the DL Streamer pipeline, refer to the steps described in this [doc](gvapython_mqtt_publish.md).

### Publish Frame and Metadata post pipeline execution
To publish frame/metadata to MQTT message broker post pipeline execution, refer to this [doc](eis_mqtt_publish_doc.md).


## OPCUA Publishing
To send frames and metadata over OPC UA, refer to this [doc](opcua_publish_doc.md).

## S3 frame publishing
To store frames from media source and publish the metadata to MQTT, refer to this [doc](s3_frame_storage.md).

```{toctree}
:maxdepth: 5
:hidden:
gvapython_mqtt_publish.md
mqtt_publish.md
opcua_publish_doc.md
s3_frame_storage.md
```
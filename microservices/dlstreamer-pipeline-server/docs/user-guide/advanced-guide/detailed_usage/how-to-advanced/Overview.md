# How To Advanced
This section refers to few advanced features and tutorials provided by DL Streamer Pipeline Server.

- [Model Update](#model-update)
- [Object tracking](#object-tracking)
- [Enable HTTPS for DL Streamer Pipeline Server](#dlstreamer-pipeline-server-https)
- [Performance Analysis](#performance-analysis)
- [Get tensor vector data](#get-tensor-vector-data)
- [Multistream pipelines with shared model instance](#multistream-pipelines-with-shared-model-instance)
- [Cross stream batching](#cross-stream-batching)
- [Enable Open Telemetry](#enable-open-telemetry)
- [Working with other services](#working-with-other-services)

## Model Update
To update models while a pipeline instance is running, refer this [doc](./model_update/dlstreamer_pipeline_server_model_update.md)

## Object tracking
To learn about object tracking refer this [doc](./object_tracking/object_tracking.md)

## DL Streamer Pipeline Server https
To enable secure REST API, refer this [doc](./https/dlstreamer_pipeline_server_https.md)

## Performance Analysis
To learn about performance metrics using GST tracers and logging, refer this [doc](./performance/processing-latency.md)

## Get tensor vector data
To learn how to get tensor data during inference, refer this [doc](./get-tensor-vector-data.md)

## Multistream pipelines with shared model instance
To learn how to share models with multiple pipelines for performance, refer this [doc](./multistream-pipelines.md)

## Cross stream batching
To learn about cross stream batching feature, refer this [doc](./cross-stream-batching.md)

## Enable Open Telemetry
To enable Open Telemetry and capture various runtime statistics, refer this [doc](./enable-open-telemetry.md)

## Working with other services
To learn how DL Streamer Pipeline Server interacts with other microservices such as Model Registry, refer this [doc](./work-with-other-services.md)

<!--hide_directive
```{toctree}
:maxdepth: 5
:hidden:
model_update/dlstreamer_pipeline_server_model_update.md
object_tracking/object_tracking.md
https/dlstreamer_pipeline_server_https.md
performance/processing-latency.md
performance/core-pinning.md
get-tensor-vector-data.md
multistream-pipelines.md
cross-stream-batching.md
enable-open-telemetry.md
work-with-other-services.md
```
hide_directive-->

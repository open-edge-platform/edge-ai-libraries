# Performance Analysis (Latency)

This guide will help you add environment variables to enable `GST TRACER` logs and store results in a file. By analyzing these logs, you can monitor pipeline performance metrics, identify potential bottlenecks, and optimize the pipeline for better efficiency.

## Steps to enable GST TRACER logging
1. Add the following environment variables to the `dlstreamer-pipeline-server` service in the `docker-compose.yml file`
    1. GST_DEBUG
    2. GST_TRACERS
    3. GST_DEBUG_FILE

    **Example**
    ```yaml
    services:
      dlstreamer-pipeline-server:
        image: ${DLSTREAMER_PIPELINE_SERVER_IMAGE}
        environment:
          ...
          - GST_DEBUG=GST_TRACER:7
          - GST_TRACERS=latency(flags=pipeline+element)
          - GST_DEBUG_FILE=/tmp/trace.log
          ...
        volumes:
          - "/tmp:/tmp"
    ```
   - `GST_DEBUG: "GST_TRACER:7"` indicates that GStreamer is set to log trace messages at level 7 during a pipeline's execution.
   - `GST_TRACERS="latency(flags=pipeline+element)"` instructs GStreamer to enable the latency tracer. `flags=pipeline+element` specifies that the tracer should measure latency for both the entire pipeline and individual elements within it.
   - `GST_DEBUG_FILE: /tmp/trace.log` specifies the file where the logs will be written.

2. Start the Docker containers
    ```shell
    docker compose up -d
    ```

3. Start a pipeline instance using the `POST` [/pipelines/{name}/{version}](../../rest_api/restapi_reference_guide.md#post-pipelinesnameversion) endpoint
    *  Refer to the "Send a REST request to run the default Pallet Defect Detection pipeline" step in the [Get Started Guide](../../../../get-started.md#run-default-sample) for an example.

4. View the logs
   * The `GST TRACER` logs are written to the `trace.log` file in the `tmp` directory. Since the `tmp` directory in the container is mounted to the local `tmp` directory, you can view the logs on your host machine.
   * To view the contents of the file, use `cat trace.log`
   * To follow the logs being written real-time, use `tail -f trace.log`


***The specific format of the output depends on the configuration of the tracer module and the elements in the pipeline.***


### Sample Log Output

**Example 1**
```shell

dlstreamer-pipeline-server  | 0:00:46.656237192     8 0x79923c07dc00 TRACE             GST_TRACER :0:: latency, src-element-id=(string)0x79923c0b0400, src-element=(string)filesrc0, src=(string)src, sink-element-id=(string)0x79923c09eab0, sink-element=(string)appsink, sink=(string)sink, time=(guint64)1024721082, ts=(guint64)46656191434;
dlstreamer-pipeline-server  | 0:00:46.689262368     8 0x79923c07dc00 TRACE             GST_TRACER :0:: latency, src-element-id=(string)0x79923c0b0400, src-element=(string)filesrc0, src=(string)src, sink-element-id=(string)0x79923c09eab0, sink-element=(string)appsink, sink=(string)sink, time=(guint64)1057383023, ts=(guint64)46689234596;
```
Each line represents latency measurement for each frame in the pipeline.

**Timestamp** (e.g. `0:00:46.656237192`): The absolute time when the event occurred, formatted as hours:minutes:seconds.nanoseconds.

**Process ID and Thread ID** (e.g. `8 0x79923c07dc00`): The process ID and thread ID of the GStreamer process.

**Log Level** (e.g. `TRACE`): The severity level of the log message.

**Module Name and Message** (e.g. `GST_TRACER :0:: latency`): The module (GST_TRACER) and the type of event (latency).

**Event Details:**
* **src-element-id**: A unique identifier for the source element.
* **src-element**: The name of the source element.
* **sink-element-id**: A unique identifier of the sink element.
* **sink-element**: The name of the sink element.
* **time**: The measured latency in nanoseconds.
* **ts**: The presentation timestamp (PTS) of the media data associated with the event.

By analyzing the **time** and **ts** values, you can determine the latency introduced by each element in the pipeline.

For example, the first line in Example 1 shows that the pipeline latency between the source element (`filesrc0`) and the sink element (`appsink`) for the processed frame is 1024721082 nanoseconds. 

**Example 2**
```shell
dlstreamer-pipeline-server  | 0:00:40.767839514     8 0x768638a17f80 TRACE             GST_TRACER :0:: element-latency, element-id=(string)0x76866409c390, element=(string)detection, src=(string)src, time=(guint64)367077652, ts=(guint64)40767813690;
dlstreamer-pipeline-server  | 0:00:40.767934165     8 0x76866407f000 TRACE             GST_TRACER :0:: element-latency, element-id=(string)0x5b49140daeb0, element=(string)metaconvert, src=(string)src, time=(guint64)146978, ts=(guint64)40767919715;
```
Each line represents a latency measurement for a specific GStreamer element.

**Timestamp** (e.g. `0:00:40.767839514`): The absolute time when the event occurred, formatted as hours:minutes:seconds.nanoseconds.

**Process ID and Thread ID** (e.g. `8 0x768638a17f80`): The process ID and thread ID of the GStreamer process.

**Log Level** (e.g. `TRACE`): The severity level of the log message

**Module Name and Message** (e.g. `GST_TRACER :0:: element-latency`): The module (GST_TRACER) and the type of event (element-latency).

**Event Details**:
* **element-id**: A unique identifier for the GStreamer element.
* **element**: The name of the GStreamer element.
* **src**: The source element connected to this element.
* **time**: The latency measurement in nanoseconds.
* **ts**: The presentation timestamp (PTS) of the media data associated with the event.

By analyzing the **time** and **ts** values, you can determine the latency introduced by each element in the pipeline.

For example, the first line in Example 2 shows that the `detection` element experienced a latency of 367077652 nanoseconds between the source element and itself.

## Learn More

For more information on the Gstreamer tracing and debug log levels, refer to the following links:
- <https://gstreamer.freedesktop.org/documentation/tutorials/basic/debugging-tools.html?gi-language=python>
- <https://gstreamer.freedesktop.org/documentation/additional/design/tracing.html?gi-language=python>
- <https://gstreamer.freedesktop.org/documentation/additional/design/tracing.html?gi-language=python#print-processing-latencies-for-each-element>

## Known Issues
**Issue:** The trace.log file will be overwritten every time a pipeline related operation is executed. 
* **Workaround:** Copy the log file as needed. 

**Issue:** The pipeline latency measurement does not work when `gvametapublish` element is in the pipeline. 
* **Workaround:** Leverage element latency.
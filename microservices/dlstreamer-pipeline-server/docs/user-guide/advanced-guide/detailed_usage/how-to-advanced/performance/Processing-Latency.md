# Performance Analysis (Latency)

This guide will help you add environment variables to enable GST TRACER logs and store results in a file. This is useful for monitoring and reviewing performance metrics associated to a pipeline.

## Steps to enable GST TRACER logging
1. Add the following environment variables to the `edge-video-analytics-microservice` service in the `docker-compose.yml file`
    1. GST_DEBUG
    2. GST_TRACERS
    3. GST_DEBUG_FILE

    **Example**
    ```yaml
    services:
      edge-video-analytics-microservice:
        image: intel/edge-video-analytics-microservice:2.3.0
        environment:
          ...
          - GST_DEBUG="GST_TRACER:7"
          - GST_TRACERS="latency(flags=pipeline+element)"
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
0:00:00.448010362   156 0x7450580085e0 TRACE             GST_TRACER :0:: latency_tracer_element, name=(string)decodebin0, frame_latency=(double)0.150333, avg=(double)0.150333, min=(double)0.150333, max=(double)0.150333, frame_num=(uint)1, is_bin=(boolean)1;
0:00:00.448093150   156 0x7450580085e0 TRACE             GST_TRACER :0:: latency_tracer_element, name=(string)decodebin0, frame_latency=(double)0.217534, avg=(double)0.183933, min=(double)0.150333, max=(double)0.217534, frame_num=(uint)2, is_bin=(boolean)1;
0:00:00.448142353   156 0x7450580085e0 TRACE             GST_TRACER :0:: latency_tracer_element, name=(string)decodebin0, frame_latency=(double)0.257956, avg=(double)0.208608, min=(double)0.150333, max=(double)0.257956, frame_num=(uint)3, is_bin=(boolean)1;
```
Each line represents a latency measurement for a single frame processed by the "decodebin0" element

**Timestamp** (e.g. `0:00:00.448010362`): The absolute time when the event occurred, formatted as hours:minutes:seconds.nanoseconds.

**Process ID and Thread ID** (e.g. `156 0x7450580085e0`): The process ID and thread ID of the GStreamer process.

**Log Level** (e.g. `TRACE`): The severity level of the log message.

**Module Name and Message** (e.g. `GST_TRACER :0:: latency_tracer_element`): The module (GST_TRACER) and the type of event (latency_tracer_element).

**Event Details:**
* **name:** The name of the GStreamer element (decodebin0).
* **frame_latency:** The latency of the current frame in seconds.
* **avg:** The average frame latency so far.
* **min:** The minimum frame latency observed so far.
* **max:** The maximum frame latency observed so far.
* **frame_num:** The number of frames processed so far.
* **is_bin:** Whether the element is a bin (a container for other elements).

By analyzing these measurements, you can identify potential performance bottlenecks and optimize the pipeline accordingly. 


**Example 2**
```shell
0:00:47.287321118 899463 0x7ffa84006400 TRACE             GST_TRACER :0:: element-latency, element-id=(string)0x55b7dbeaae40, element=(string)udfloader, src=(string)src, time=(guint64)24455257, ts=(guint64)47287280464;
0:00:47.287422389 899463 0x7ffa84006400 TRACE             GST_TRACER :0:: element-latency, element-id=(string)0x55b7dbec6e40, element=(string)metaconvert, src=(string)src, time=(guint64)111264, ts=(guint64)47287391728;
0:00:47.287477618 899463 0x7ffa84006400 TRACE             GST_TRACER :0:: element-latency, element-id=(string)0x7ffb1c0b4150, element=(string)gvametapublishfile0, src=(string)src, time=(guint64)66145, ts=(guint64)47287457873;
```
Each line represents a latency measurement for a specific GStreamer element.

**Timestamp** (e.g. `0:00:47.287321118`): The absolute time when the event occurred, formatted as hours:minutes:seconds.nanoseconds.

**Process ID and Thread ID** (e.g. `899463 0x7ffa84006400`): The process ID and thread ID of the GStreamer process.

**Log Level** (e.g. `TRACE`): The severity level of the log message

**Module Name and Message** (e.g. `GST_TRACER :0:: element-latency`): The module (GST_TRACER) and the type of event (element-latency).

**Event Details**:
* **element-id**: A unique identifier for the GStreamer element.
* **element**: The name of the GStreamer element.
* **src**: The source element connected to this element.
* **time**: The relative time of the event within the GStreamer pipeline.
* **ts**: The presentation timestamp (PTS) of the media data associated with the event.

By analyzing the **time** and **ts** values, you can determine the latency introduced by each element in the pipeline.

For example, the first line in Example 2 shows that the "udfloader" element experienced a latency of 24455257 nanoseconds between the source element and itself.


## Learn More

For more information on the Gstreamer tracing and debug log levels, refer to the following links:
- <https://gstreamer.freedesktop.org/documentation/tutorials/basic/debugging-tools.html?gi-language=python>
- <https://gstreamer.freedesktop.org/documentation/additional/design/tracing.html?gi-language=python>
- <https://gstreamer.freedesktop.org/documentation/additional/design/tracing.html?gi-language=python#print-processing-latencies-for-each-element>
- <https://dlstreamer.github.io/dev_guide/latency_tracer.html>

## Known Issues
**Issue:** The trace.log file will be overwritten every time a pipeline related operation is executed. 
* **Workaround:** Copy the log file as needed. 

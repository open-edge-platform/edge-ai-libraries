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
          - GST_TRACERS=latency_tracer(flags=element+pipeline)
          - GST_DEBUG_FILE=/tmp/trace.log
          ...
        volumes:
          - "/tmp:/tmp"
    ```
   - `GST_DEBUG=GST_TRACER:7` indicates that GStreamer is set to log trace messages at level 7 during a pipeline's execution.
   - `GST_TRACERS=latency_tracer(flags=element+pipeline)` instructs GStreamer to enable the DL Streamer latency tracer. `flags=element+pipeline` specifies that the tracer should measure latency for both the entire pipeline and individual elements within it.
   - `GST_DEBUG_FILE=/tmp/trace.log` specifies the file where the logs will be written.

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
  Latency tracer is the functionality provided by DL Streamer. Please refer to the [DL Streamer Latency Tracer](https://docs.openedgeplatform.intel.com/dev/edge-ai-libraries/dlstreamer/dev_guide/latency_tracer.html) documentation for available configuration options and detailed description of latency logs interpretation.

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
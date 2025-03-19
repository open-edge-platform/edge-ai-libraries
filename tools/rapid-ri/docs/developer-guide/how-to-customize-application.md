# Customize Application

### Rapid RI Folder Structure

This section provides an overview of each folder and its purpose within the project:

1. **grafana:**

    - Contains configurations and dashboards for Grafana to monitor system metrics and application performance.
    - `dashboards.yml`: Configuration file that defines the pre-provisioned dashboards in Grafana.
    - `grafana.ini`: Primary configuration file for Grafana specifying server, database, and security settings.
    - `visualizer.json`: JSON configuration for the main Grafana panel layout and settings.
    - `visualizer_sub_1.json`: JSON configuration for a sub-panel or specific subset of visualizations in Grafana.
    - `visualizer_sub_2.json`: JSON configuration for another sub-panel or dashboard with unique visualizations.

    For more Info: [Grafana Technical Documentation](https://grafana.com/docs/)

2. **mosquitto:**

    - Contains configurations for the MQTT broker (Mosquitto), which is used to handle communication between components.
    - `mosquitto.conf`: Primary configuration file that defines settings such as listening ports and IP bindings, authentication, topics allowed for publishing and subscribing, logging settings, and QoS levels for messages.

    For more Info: [MQTT Official Documentation](https://mqtt.org/getting-started/)

3. **node-red:**

    - Holds the Node-RED flows and configurations for setting up the visual programming environment for workflows.
    - `core/`: Core Node-RED node definitions and logic files.
    - `examples/`: Example flows or configurations for various Node-RED functionalities.
    - `icons/`: Custom or default icons used for visualizing nodes in the Node-RED UI.
    - `index.js`: The entry point or primary script for defining and loading Node-RED nodes.
    - `locales/`: Localization files for translating Node-RED UI and nodes to different languages.
    - `package.json`: Metadata for the Node-RED package, including dependencies and versioning.

    For more Info: [Node-RED Official Documentation](https://nodered.org/docs/)

4. **evam:**
    - This directory provides the Intel Deep Learning Streamer (Intel DL Streamer) pipelines to perform object detection on an input URI source and send the ingested frames and inference results to MQTT.
    - `config.json`: Define sources (e.g., camera or video file), processing elements (e.g., model inference), and sinks (e.g., results storage, visualization).
    - `models/`: Contains pre-trained AI/ML models used for video analytics tasks (e.g., object detection, classification, tracking). Models are usually in formats like .xml (OpenVINO IR format), .bin, or .onnx.
    - `videos/`: Contains sample video files for testing and validation purposes. Place videos here for pipeline input if using a file-based source in configurations.

    For more Info: [EVAM Official Documentation](https://docs.edgeplatform.intel.com/edge-video-analytics-microservice/2.3.0/user-guide/Overview.html)

## How to customize the Video Analytics Pipeline

### Update the Pipeline
Edge Video Analytics Service uses the DLStreamer tool to configure the pipeline. It has preprocessing, inference, and post-processing steps. You can configure the pipeline according to the requirements.

Update the `config.json` file to configure the pipeline.

Here is the current pipeline configuration:

```json
{
"pipeline": "{auto_source} name=source  ! decodebin ! gvadetect name=detection model=/home/pipeline-server/models/yolov10s/yolov10s.xml ! queue ! gvawatermark ! gvametaconvert add-empty-results=true name=metaconvert ! gvametapublish name=destination ! gvafpscounter ! appsink name=appsink"

}
```

### Pipeline Explanation

 - `auto_source`: This element automatically selects the appropriate source element based on the input provided.
 - `decodebin`: This element automatically detects the format of the input stream and decodes it.
 - `gvadetect`: This element performs object detection using the specified model (`yolov10s.xml`) on the CPU. The `pre-process-backend=ie` indicates that the inference engine is used for preprocessing.
 - `queue`: This element is used to separate different processing stages to ensure smooth data flow.
 - `gvawatermark`: This element overlays detection results on the video frames.
 - `gvametaconvert`: This element converts metadata to a specified format. The `add-empty-results=true` parameter ensures that frames without detections are also processed.
 - `gvametapublish`: This element publishes the metadata to the specified destination.
 - `gvafpscounter`: This element calculates and displays the frames per second (FPS) of the pipeline.
 - `appsink`: This element acts as a sink for the processed video frames.

For more information, refer to the [DLStreamer Elements](https://dlstreamer.github.io/elements/elements.html).

### Update the Data Source

The `/home/frameworks.ai.ai-suite-for-vision/tools/rapid_ri/evam/config.json` allows defining the source of the data for the pipeline. The source can be dynamically updated during runtime or pre-configured for automatic execution when the containers are launched.

1. **Auto Source**

    The `{auto_source}` configuration dynamically selects the input based on the provided URI during runtime using a curl command.

2. **RTSP Stream**

    This allows streaming video directly from an RTSP server when the containers start.

    Pipeline example:

    ```json
    "pipeline": "rtspsrc location=\"rtsp://192.168.2.96:8554/live.sdp\" latency=100 name=source ! rtph264depay ! h264parse ! decodebin ! videoconvert ! video/x-raw,format=BGR ! udfloader name=udfloader ! appsink name=destination"
    ```

    - `rtspsrc`: Fetches the video stream from the given RTSP URL.
    - `location`: Replace this with the desired RTSP URL.
    - `latency`: Configures the network buffer latency (default: 100 ms).

3. **File Source**

    Specify a static file in the JSON file so that the pipeline processes the file automatically when the containers start.

    Pipeline example:
    ```json
    "pipeline": "filesrc location=\"/path/to/video.mp4\" ! decodebin ! videoconvert ! video/x-raw,format=BGR ! udfloader name=udfloader ! appsink name=destination"
    ```
    - `filesrc`: Reads video data from a local file.
    - `location`: Replace with the full path to the video file.

### Update the Model

#### Using Existing Models

To use a different model in the pipeline, locate the **gvadetect** element in `frameworks.ai.ai-suite-for-vision/tools/rapid_ri/evam/config.json` that includes the model parameter that points to the model file being used.

Pipeline example:
```json
"pipeline": "[auto_source] ! decodebin ! videoscale ! video/x-raw,width=1280,height=720 ! gvadetect model=/home/pipeline-server/models/yolov10s/yolov10s.xml ! gvaconvert name=metaconvert ! gvametapublish name=destination ! appsink"
```

Replace the **yolov10s** with another model supported in the environment. Make sure the new model files are present in the directory `evam/models/`.

## Configure Node-RED for Different Alerts

Access Node-RED interface at [http://localhost:1880](http://localhost:1880). If accessing remotely, update the localhost to the host's IP address.

1. **MQTT In Node:**
    - Drag an MQTT In node onto the workspace.
    - Configure the MQTT In node to subscribe to the topic where EVAM publishes messages (e.g., `evam/objects`).
    - Set the MQTT broker details (e.g., `localhost`, port `1883`).

2. **Function Node:**
    - Drag a Function node onto the workspace.
    - Connect the MQTT In node to the Function node.
    - Configure the Function node with JavaScript logic to extract objects from the incoming MQTT messages.

    Example Function node code:
    ```javascript
    // Extract objects from the incoming MQTT message
    var message = msg.payload;
    var objects = message.objects; // Assuming the objects are in the 'objects' field
    msg.payload = objects;
    return msg;
    ```

3. **Debug Node:**
    - Drag a Debug node onto the workspace.
    - Connect the Function node to the Debug node.
    - Configure the Debug node to print the extracted objects to the debug console.

4. **MQTT Out Node:**
    - Drag an MQTT Out node onto the workspace.
    - Connect the Function node to the MQTT Out node.
    - Configure the MQTT Out node to publish the extracted objects to a new MQTT topic (e.g., `evam/processed_objects`).
    - Set the MQTT broker details (e.g., `localhost`, port `1883`).

5. **Connect and Deploy:**
    - Connect the nodes to form a flow:
        - MQTT In node -> Function node -> Debug node
        - Function node -> MQTT Out node
    - Click **Deploy** in the top-right corner to save and start the flow.

6. **Testing:**
    - Ensure that EVAM is publishing messages to the configured MQTT topic.
    - Monitor the Node-RED debug console to see the extracted objects printed by the Debug node.
    - Verify that the extracted objects are being published to the new MQTT topic.


The current Node Red flow looks like below, 

![Node Red Flow](/tools/rapid_ri/docs/developer-guide/_static/node-red.png)

This setup will capture MQTT messages from EVAM, extract the objects using the Function node, and print the objects using the Debug node.

## Customize Grafana Panels

1. **Access Grafana:**
    Open a browser and navigate to 
    [http://localhost:3000](http://localhost:3000).
    Log in with the following credentials:
    - **Username:** `admin`
    - **Password:** `admin`
    - If accessing remotely, update the localhost to the host's IP address.


2. **Navigate to Dashboard:**
    
    Go to the Dashboards tab on the left-hand side.
    Select an existing dashboard or click on **New** to create a new one.

3. **Customize Panels:**
    
    - **Add a new panel:**
            - In the dashboard, click on **Add a new panel**.
            - Configure the panel:
                    - **Query:** Select the data source and write the query.
                    - **Visualization:** Choose visualization type (e.g., Graph, Table, etc.).
                    - **Options:** Adjust panel-specific settings like colors, thresholds, or unit formatting.
                    - **Title:** Update the title to reflect the purpose of the panel.
    - **Edit an existing panel:**
            - Hover over an existing panel and click the **Edit** button (pencil icon).
            - Modify the panel settings such as data source, visualization type, panel title, and description.
            - Click **Apply** to save changes.

4. **Save the Dashboard:**
    
    After making changes, click **Save** dashboard (disk icon at the top).
    Provide a meaningful name for the dashboard.
    Save it with or without versioning.


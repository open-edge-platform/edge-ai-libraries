# Rapid RI
Framework to develop Vision AI based solutions.

## Overview

Rapid RI is an prototyping framework designed to streamline the deployment of AI-driven video analytics at the edge. By leveraging cutting-edge technologies and pre-trained deep learning models, Rapid RI enables real-time processing and analysis of video streams, making it an ideal solution for various applications such as security surveillance, traffic monitoring, and retail analytics. The framework's modular architecture and integration capabilities ensure that users can easily customize and extend its functionalities to meet their specific needs.

The tool is built to be user-friendly, allowing customization without the need for extensive coding knowledge. Validate your ideas by developing an end-to-end solution faster.

**Note:** This tool is not intended for production use.


### Key Features

- **EdgeVideoAnalyticsMicroservice (EVAM) Pipeline:** Detect and classify objects using pre-configured AI models. Customize parameters such as thresholds and object types without requiring additional coding.
- **Integration with MQTT, Node-RED, and Grafana:** Facilitates efficient message handling, real-time monitoring, and insightful data visualization.
- **User-Friendly:** Simplifies configuration and operation through prebuilt scripts and configuration files.

## How It Works

The architecture of Rapid RI is designed to facilitate seamless integration and operation of various components involved in AI-driven video analytics.

![Architecture Diagram](/tools/rapid_ri/docs/developer-guide/_static/Rapid_RI.png)

### Components

- **EVAM (VA Pipeline):** Processes video frames, extracts metadata, and integrates AI inference results.
- **Model Registry (DNN Models):** A repository that stores deep learning models used for inference in the EVAM pipeline.
- **Mosquitto MQTT Broker:** Facilitates message communication between components like Node-RED and EVAM using the MQTT protocol.
- **Node-RED:** A low-code platform for setting up application-specific rules and triggering MQTT-based events.
- **WebRTC Stream Viewer:** Displays real-time video streams processed by the pipeline for end-user visualization.
- **Grafana Dashboard:** A monitoring and visualization tool for analyzing pipeline metrics, logs, and other performance data.
- **Inputs (Video Files and Cameras):** Provide raw video streams or files as input data for processing in the pipeline.

The Edge Video Analytics Microservice (EVAM) is a core component of Rapid RI, designed to handle video analytics at the edge. It leverages pre-trained deep learning models to perform tasks such as object detection, classification, and tracking in real-time. EVAM is highly configurable, allowing users to adjust parameters like detection thresholds and object types to suit specific use cases. This flexibility ensures that users can deploy AI-driven video analytics solutions quickly and efficiently, without the need for extensive coding or deep learning expertise.

It integrates various components such as MQTT, Node-RED, and Grafana to provide a robust and flexible solution for real-time video inference pipelines. The tool is built to be user-friendly, allowing customization without the need for extensive coding knowledge. Validate your ideas by developing an end-to-end solution faster.

### **Hardware Requirements**
| Component  | Minimum Requirement                |
|------------|------------------------------------|
| CPU        | Intel® 11th Gen Core™ i5 or higher |
| GPU        | Intel® UHD Graphic                 |
| RAM        | 16 GB                               |
| Storage    | 50 GB free space                   |


### **Software Requirements**
| Requirement  | Details      |
|--------------|--------------|
| Supported OS | Ubuntu 24.04 |
| Dependencies | Docker 20.10 |



## Next Steps
- [Get Started](/tools/rapid_ri/docs/developer-guide/get-started.md)
- [System Requirements](/tools/rapid_ri/docs/developer-guide/system-requirements.md)
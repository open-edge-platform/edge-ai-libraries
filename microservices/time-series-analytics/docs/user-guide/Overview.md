# Time Series Analytics

The Time Series Analytics microservice provides the analytics capabilities for a time series use case.

## Overview

The **Time Series Analytics Microservice** is a powerful, flexible solution for real-time analysis of time series data. Built on top of **Kapacitor**, it enables both streaming and batch processing, seamlessly integrating with **InfluxDB** for efficient data storage and retrieval.

What sets this microservice apart is its support for advanced analytics through **User-Defined Functions (UDFs)** written in Python. By leveraging the Intel® Extension for Scikit-learn*, users can accelerate machine learning workloads within their UDFs, unlocking high-performance anomaly detection, predictive maintenance, and other sophisticated analytics.

Key features include:
- **Bring your own Data Sets and corresponding User Defined Functions(UDFs) for custom analytics**: Easily implement and deploy your own Python-based analytics logic, following Kapacitor’s UDF standards.
- **Seamless Integration**: Automatically stores processed results back into InfluxDB for unified data management and visualization.
- **Model Registry Support**: Dynamically fetch and deploy UDF scripts, machine learning models, and TICKscripts from the Model Registry microservice, enabling rapid customization and iteration.
- **Versatile Use Cases**: Ideal for anomaly detection, alerting, and advanced time series analytics in industrial, IoT, and enterprise environments.

For more information on creating custom UDFs, see the [Kapacitor Anomaly Detection Guide](https://docs.influxdata.com/kapacitor/v1/guides/anomaly_detection/)

---

## How it works

### High-Level Architecture

![Time Series Analytics Microservice High Level Architecture](_images/Time-Series-Analytics-Microservice-Architecture.png)

As seen in the architecture diagram, the `Time Series Analytics` microservice can take input data from various sources.
The input data that this microservice takes can be broadly divided into two:
1. **Input payload and configuration management via REST APIs**
   a. REST clients sending the data in JSON format
   b. Telegraf services sending the data in line protocol format
2. **UDF deployment package** (comprises of UDF, TICKScripts, models)
   a. Through Volume mounts OR docker cp OR kubectl cp command
   b. Pulling the UDF deployment package from the Model Registry microservice

As a default flow, we have sample temperature simulator to ingest data in JSON format and have pre-packaged simple process based User Defined Function (UDF) in `Time Series Analytics` microservice to flag the temperature
points if they don't fall under a range as anomalies. The output is seen in the logs of the microservice now.

For understanding the other ways of ingesting data, UDF deployment package configuration, publishing alerts and writing data back to InfluxDB via TICKScripts, please refer the following docs of Wind Turbine Sample app:
- [Overview.md](https://github.com/open-edge-platform/edge-ai-suites/tree/main/manufacturing-ai-suite/wind-turbine-anomaly-detection/docs/user-guide/Overview.md)
- [Getting Started](https://github.com/open-edge-platform/edge-ai-suites/tree/main/manufacturing-ai-suite/wind-turbine-anomaly-detection/docs/user-guide/get-started.md)
- [How to configure alerts](https://github.com/open-edge-platform/edge-ai-suites/tree/main/manufacturing-ai-suite/wind-turbine-anomaly-detection/docs/user-guide/how-to-configure-alerts.md)
- [How to configure custom UDF](https://github.com/open-edge-platform/edge-ai-suites/tree/main/manufacturing-ai-suite/wind-turbine-anomaly-detection/docs/user-guide/how-to-configure-custom-udf.md)

---

## Summary

This guide demonstrated how the overview and architecture of the Wind Turbine Anomaly Detection sample app. For more details to get started, refer to [Getting Started](./get-started.md).

# Configuring Time Series Analytics Microservice

## Configuration Overview

This document describes the configuration options available in `config.json` for the Time Series Analytics Microservice.

### Example Configuration

```json
{
    "udfs": {
        "name": "windturbine_anomaly_detector",
        "models": "windturbine_anomaly_detector.pkl",
        "device": "cpu"
    },
    "alerts": {
        "mqtt": {
            "mqtt_broker_host": "ia-mqtt-broker",
            "mqtt_broker_port": 1883,
            "name": "my_mqtt_broker"
        },
        "opcua": {
            "opcua_server": "opc.tcp://ia-opcua-server:4840/freeopcua/server/",
            "namespace": 1,
            "node_id": 2004
        }
    }
}
```

> **Note:** The maximum allowed size for `config.json` is 5 KB.

## Configuration Details

### **UDFs Configuration**

| Key      | Mandatory | Description                                                                                 | Example Value                          |
|----------|-----------|--------------------------------------------------------------------------------------------|----------------------------------------|
| `name`   | Yes       | The name of the UDF script.                                                                 | `"windturbine_anomaly_detector"`       |
| `models` | No       | The name of the model file used by the UDF.                                                 | `"windturbine_anomaly_detector.pkl"`   |
| `device` | No        | Specifies the hardware `cpu` or `gpu` for executing the UDF model inference. Default is `cpu` | `"cpu"`                                |


Please refer to [Running inferencing on GPU](https://github.com/open-edge-platform/edge-ai-suites/blob/release-2025.2.0/manufacturing-ai-suite/industrial-edge-insights-time-series/docs/user-guide/get-started.md#running-user-defined-functionudf-inference-on-gpu) for usage of GPU in Time Series - Wind Turbine Anomaly Detection Sample App

> **Note on GPU Support:**
> - GPU inferencing for machine learning models is supported via the Intel scikit-learn extension (scikit-learn-intelex)
> - Intel iGPU (Integrated Graphics Processing Unit) drivers are included within the Time Series Analytics Microservice to facilitate GPU usage.
> - The scikit-learn-intelex package comes pre-installed, delivering optimized performance and GPU-enabled model inferencing for Intel hardware.
> - Actual GPU utilization is determined by the model's compatibility with GPU execution and the available GPU hardware resources.


### **Alerts Configuration** (optional)

#### **MQTT Configuration** (optional)

| Key                 | Mandatory | Description                                                 | Example Value          |
|---------------------|-----------|-------------------------------------------------------------|------------------------|
| `mqtt_broker_host`  | Yes       | The hostname or IP address of the MQTT broker.              | `"ia-mqtt-broker"`     |
| `mqtt_broker_port`  | Yes       | The port number of the MQTT broker.                         | `1883`                 |
| `name`              | Yes       | The name of the MQTT broker configuration.                  | `"my_mqtt_broker"`     |


For more information on how to configure MQTT alerts, refer to [Publishing MQTT Alerts](https://github.com/open-edge-platform/edge-ai-suites/blob/release-2025.2.0/manufacturing-ai-suite/industrial-edge-insights-time-series/docs/user-guide/how-to-guides/how-to-configure-alerts.md#docker---publish-mqtt-alerts)

> **Note:**
>
> - MQTT Broker Availability: Ensure that the MQTT broker is accessible and available on the network before initializing this client. 
> - The broker must be reachable via the configured host and port. 

#### **OPC UA Configuration** (optional)

| Key            | Mandatory | Description                                                 | Example Value                                      |
|----------------|-----------|-------------------------------------------------------------|----------------------------------------------------|
| `opcua_server` | Yes       | The OPC UA server endpoint URL.                             | `"opc.tcp://ia-opcua-server:4840/freeopcua/server/"` |
| `namespace`    | Yes       | The namespace index for the OPC UA node.                    | `1`                                                |
| `node_id`      | Yes       | The node ID where alerts will be published.                 | `2004`                                             |

For more information on how to configure OPC-UA alerts, refer to [Publishing OPC-UA Alerts](https://github.com/open-edge-platform/edge-ai-suites/blob/release-2025.2.0/manufacturing-ai-suite/industrial-edge-insights-time-series/docs/user-guide/how-to-guides/how-to-configure-alerts.md#docker---publish-opc-ua-alerts)

> **Note:**
>
> - An OPC UA server must be available and running at the specified endpoint
>   for this code to function properly. 
> - Ensure the server is accessible and the connection parameters (endpoint URL, security settings, credentials)
> are correctly configured before attempting to connect.


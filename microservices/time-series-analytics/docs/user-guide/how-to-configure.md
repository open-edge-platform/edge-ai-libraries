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
| `device` | No        | Specifies the hardware `CPU` or `GPU` for executing the UDF model inference. Default is `cpu` | `"cpu"`                                |


> **Note on GPU Support:**
> - GPU acceleration is supported for compatible models that have GPU capabilities
> - Intel iGPU (Integrated Graphics Processing Unit) drivers are included as part of the `Time Series Analytics Microservice`
> - Intel scikit-learn extension package (scikit-learn-intelex) is pre-installed in the image
>   to provide optimized performance for Intel GPUs
> - The actual GPU utilization depends on the specific model's GPU support and available hardware


### **Alerts Configuration** (optional)

#### **MQTT Configuration** (optional)

| Key                 | Description                                                 | Example Value          |
|---------------------|-------------------------------------------------------------|------------------------|
| `mqtt_broker_host`  | The hostname or IP address of the MQTT broker.              | `"ia-mqtt-broker"`     |
| `mqtt_broker_port`  | The port number of the MQTT broker.                         | `1883`                 |
| `name`              | The name of the MQTT broker configuration.                  | `"my_mqtt_broker"`     |

> **Note:**
>
> - MQTT Broker Availability: Ensure that the MQTT broker is accessible and available on the network before initializing this client. 
> - The broker must be reachable via the configured host and port. 

#### **OPC UA Configuration** (optional)

| Key            | Description                                                 | Example Value                                      |
|----------------|-------------------------------------------------------------|----------------------------------------------------|
| `opcua_server` | The OPC UA server endpoint URL.                             | `"opc.tcp://ia-opcua-server:4840/freeopcua/server/"` |
| `namespace`    | The namespace index for the OPC UA node.                    | `1`                                                |
| `node_id`      | The node ID where alerts will be published.                 | `2004`                                             |

> **Note:**
>
> - An OPC UA server must be available and running at the specified endpoint
>   for this code to function properly. 
> - Ensure the server is accessible and the connection parameters (endpoint URL, security settings, credentials)
> are correctly configured before attempting to connect.


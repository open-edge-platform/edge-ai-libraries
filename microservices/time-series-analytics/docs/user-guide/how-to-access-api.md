# How to access Time Series Analytics Microservice API

The Time Series Analytics Microservice provides an interactive Swagger UI at `http://localhost:5000/docs`.

**Note:** Use the link `http://localhost:30002/docs` to access the Swagger UI if doing a Helm-based deployment on a Kubernetes cluster.

## Accessing the Swagger UI

### To view the current configuration:

1. Open the Swagger UI in your browser.
2. Locate the `GET /config` endpoint.
3. Expand the endpoint and click **Execute**.
4. The response will display the current configuration of the Time Series Analytics Microservice.

### To update the current configuration:

1. Open the Swagger UI in your browser.
2. Find the `POST /config` endpoint.
3. Expand the endpoint, enter the new configuration in the request body, and click **Execute**.
4. This enables dynamic configuration at runtime. The service will apply the updated configuration and start with the new configuration.

> **Note:** If you restart the Time Series Analytics Microservice, it will start with the default configuration present in the `config.json` file.

### To send input data to the Time Series Analytics Microservice

1. Open the Swagger UI in your browser.
2. Find the `POST /input` endpoint.
3. The input data consists of keys `topic`, `tags`(optional), `fields` and `timestamp`(optional).
4. Below is the example configuration for `temperature_classifier` UDF input:

    ```json
    {
    "topic": "point_data",
    "tags": {
        "additionalProp1": {}
    },
    "fields": {
        "temperature": 20
    },
    "timestamp": 0
    }
    ```
5. Expand the endpoint, enter the input data in the request body, and click **Execute**.
6. The service will use the input for processing data.

### To send OP CUA alerts

1. Open the Swagger UI in your browser.
2. Find the `POST /opcua_alerts` endpoint.
3. Below is the example configuration for alert input:

    ```json
    {
    "alert": "message"
    }
    ```
4. Expand the endpoint, enter the alert data in the request body, and click **Execute**.
5. The service will send alert to OP CUA server as configured in the config.

> **Note:** Before using the OPC UA alerts API, ensure that you have the OPC-UA server running and have added `opcua` to the `alerts` section in `config.json` file

### Check the status of the Time Series Analytics Microservice

1. Open the Swagger UI in your browser.
2. Locate the `GET /health` endpoint.
3. Expand the endpoint and click **Execute**.
4. The response will display the current status of Kapacitor daemon of the Time Series Analytics Microservice.
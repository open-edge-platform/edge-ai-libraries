# Deploy Time Series Analytics Microservice

This guide describes how to build, start, and stop the Time Series Analytics Microservice (TSAM)
as part of the ViPPET stack, and how to configure it with a sample Wind Turbine anomaly
detection UDF.

## Prerequisites

- Docker and Docker Compose installed
- `make` available on the host
- `wget` installed (required to download UDF packages)

## Configure Environment Variables - Build, Start, and Stop

### Build

Build all required Docker images:

```bash
make build-experimental
```

### Start

Start all services, including the Time Series Analytics Microservice:

```bash
make run-experimental
```

### Stop and Clean

Stop all running services and clean any artifacts:

```bash
make stop-experimental
make clean-experimental
```

---

## Deploy the Wind Turbine anomaly detection UDF

Once the services are running, follow the steps below to deploy the Wind Turbine anomaly detection UDF into the TSAM.

The TSAM Swagger UI is available at **[http://localhost:5000/docs](http://localhost:5000/docs)**.

### Step 1. Download the UDF package

Download the pre-built Wind Turbine UDF tar archive:

```bash
wget https://raw.githubusercontent.com/open-edge-platform/edge-ai-resources/main/timeseries-udf-deployment-packages/wind-turbine-anomaly-detection.tar
```

### Step 2. Upload the UDF package

1. Open **[http://localhost:5000/docs](http://localhost:5000/docs)** in a browser.
2. Navigate to **POST /udfs/package**.
3. Click **Try it out**.
4. Under **Choose File**, select the downloaded `wind-turbine-anomaly-detection.tar` file.
  ![UDF Upload Diagram](../../_assets/udf_upload.png)
5. Click **Execute**.

A successful response returns the message: `UDF deployment package 'wind-turbine-anomaly-detection.tar' uploaded successfully.`

### Step 3. Apply the configuration

1. Open **[http://localhost:5000/docs](http://localhost:5000/docs)** in a browser.
2. Navigate to **POST /config**.
3. Click **Try it out**.
4. In the **Request Body** field, paste the following configuration:

```json
{
    "udfs": {
        "name": "windturbine_anomaly_detector",
        "models": "windturbine_anomaly_detector.pkl",
        "device": "cpu"
    }
}
```

  ![UDF configuration Diagram](../../_assets/config_udf.png)

1. Click **Execute**.

A successful response returns the message: `Configuration updated successfully.`

---

### Step 4. Verify the Time Series Analytics Microservice logs

Check that processing is running correctly:

```bash
docker logs -f ia-time-series-analytics-microservice
```

You should see output similar to the following:

```text
2026-05-26 04:43:45,599 - classifier_startup - INFO - Connected to Kapacitor on port 9092
2026-05-26 04:43:45,621 - classifier_startup - INFO - Kapacitor initialized successfully
2026-05-26 04:43:46,201 - classifier_startup - INFO - HTTP service listening on [::]:9092
2026-05-26 04:43:46,201 - classifier_startup - INFO - Started task windturbine_anomaly_detector
INFO: 172.18.0.7:52784 - "POST /input HTTP/1.1" 200 OK
INFO: 172.18.0.7:52786 - "POST /input HTTP/1.1" 200 OK
```

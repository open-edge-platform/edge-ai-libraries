# Deploy Time Series Analytics Microservice

This guide describes how to build, start, and stop the Time Series Analytics Microservice (TSAM)
as part of the ViPPET stack, and how to configure it with a sample Wind Turbine anomaly
detection UDF.

## Prerequisites

- Docker and Docker Compose installed
- `make` available on the host
- `wget` installed (required to download UDF packages)

> Time Series Analytics can run on CPU or GPU, but NPU is not supported.

## Activate the Experimental Time Series stack

The Time Series Analytics Microservice is started from the experimental compose stack.
Use the project Makefile targets from the tool root directory:

```bash
cd tools/visual-pipeline-and-platform-evaluation-tool
```

Activation is performed with the
`build-experimental` and `run-experimental` targets.

### Build the experimental stack

Build all required Docker images:

```bash
make build-experimental
```

### Start the experimental stack

Start all services, including the Time Series Analytics Microservice:

```bash
make run-experimental
```

This command enables the Time Series flow by layering `compose.experimental.yml` on top of the standard
compose stack, including `ia-time-series-analytics-microservice` and `ia-timeseries-ingestion`.

### Verify that Time Series services are active

Check if both Time Series services are running:

```bash
docker ps --format '{{.Names}}' | grep -E 'ia-time-series-analytics-microservice|ia-timeseries-ingestion'
```

### Stop and Clean

Stop all running services and clean any artifacts:

```bash
make stop-experimental
make clean-experimental
```

---

## Deploy the Wind Turbine anomaly detection UDF

Once the services are running, deploy the Wind Turbine anomaly detection UDF through ViPPET.
This flow downloads the package through `model-download`, validates it, uploads it to
TSAM, and applies the UDF name and model file found in the package. The device
is selected by the active pipeline variant.

1. Open ViPPET and select the **Wind Turbine Anomaly Detection** pipeline.
2. Click **Deploy UDF** in the Pipeline Editor toolbar.
3. Leave **Package source** set to **Model download**. ViPPET downloads the
  `wind-turbine-anomaly-detection` package automatically.
4. Click **Deploy**.

For a custom package, select **Local tar package** and choose the `.tar` archive instead.
The archive must contain exactly one Python UDF file under `udfs/` and exactly one
model file under `models/`. ViPPET derives the UDF name and model file from these
entries. When an optional `config.json` is included, its UDF name and model file
must match the archive entries or deployment fails with a validation error.

After successful deployment, ViPPET applies the configuration automatically. You do
not need to upload the archive or call `POST /config` through TSAM Swagger UI.

### Verify Time Series logs

Check that processing is running correctly:

```bash
docker logs -f ia-time-series-analytics-microservice
```

In a separate terminal, you can also verify ingestion activity:

```bash
docker logs -f ia-timeseries-ingestion
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

---

## Verify the pipeline in the ViPPET UI

After TSAM services and UDF configuration are ready, verify the full flow in the UI.

### Confirm the new pipeline appears on Dashboard

Open ViPPET in the browser and go to **Dashboard**. In the **Pipelines** section,
you should see the new **Wind Turbine Anomaly Detection** pipeline card.

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="../../_assets/ViPPET-UI-Time-Series-Pipeline-dark.png">
  <img src="../../_assets/ViPPET-UI-Time-Series-Pipeline-light.png" alt="Wind Turbine pipeline card on Dashboard">
</picture>

### Open the Wind Turbine pipeline in Pipeline Editor

Click the **Wind Turbine Anomaly Detection** card to open Pipeline Editor.
You should see the flow:

- **Input**
- **Anomaly Detection**
- **Output**

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="../../_assets/ViPPET-UI-Wind-Turbine-Pipeline-Editor-dark.png">
  <img src="../../_assets/ViPPET-UI-Wind-Turbine-Pipeline-Editor-light.png" alt="Wind Turbine pipeline in Pipeline Editor">
</picture>

### Run pipeline and inspect runtime data

Click **Run pipeline** in the top-right corner.

In the right panel:

- In the **Performance** tab, verify charts are updating for, among others:
  - **Inference Time**
  - **End-to-End Time**
- In the **Metadata JSON** tab, verify ingestion payload includes values such as:
  - `grid_active_power`
  - `wind_speed`

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="../../_assets/ViPPET-UI-Wind-Turbine-Charts-dark.png">
  <img src="../../_assets/ViPPET-UI-Wind-Turbine-Charts-light.png" alt="Wind Turbine pipeline runtime data in Performance tab">
</picture>

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="../../_assets/ViPPET-UI-Wind-Turbine-metrics-dark.png">
  <img src="../../_assets/ViPPET-UI-Wind-Turbine-metrics-light.png" alt="Wind Turbine pipeline runtime data in Metadata JSON tab">
</picture>

# Get Started

- **Time to Complete:** 30 minutes
- **Programming Language:** Python 3

## Prerequisites

- [System Requirements](./get-started/system-requirements.md)
- Docker Compose and access to an InfluxDB 3 Core instance

## Build the Time Series Analytics API Image

Build from the original microservice directory. The published service image name remains `intel/ia-time-series-analytics-microservice`.

```bash
git clone https://github.com/open-edge-platform/edge-ai-libraries.git -b main
cd edge-ai-libraries/microservices/time-series-analytics/docker
docker compose build
```

To include copyleft sources during the build:

```bash
docker compose build --build-arg COPYLEFT_SOURCES=true
```

## Deploy the Wind Turbine Sample

The Wind Turbine deployment, InfluxDB 3 Core service, model, UDF plugin, and simulator configuration are maintained in the original [Industrial Edge Insights Time Series suite](https://github.com/open-edge-platform/edge-ai-suites/tree/main/manufacturing-ai-suite/industrial-edge-insights-time-series).

Build the Time Series Analytics API image from this repository first, using the same image name and tag configured by the suite `.env`. Then follow the suite's Docker [Get Started guide](https://github.com/open-edge-platform/edge-ai-suites/blob/main/manufacturing-ai-suite/industrial-edge-insights-time-series/docs/user-guide/get-started.md) and run either `make up_mqtt_ingestion` or `make up_opcua_ingestion` from the suite root.

The suite Makefile generates an offline Core admin token, deploys the services, packages the Core plugin and model without Python cache files, uploads the package to the API, and posts the UDF configuration. Stream mode uses a Core table trigger; batch mode uses a 20-minute scheduled trigger.

The plugin package contains:

```text
udfs/influx3_windturbine/__init__.py
udfs/influx3_windturbine/requirements.txt
models/<model-file>
```

There are no TICKscripts in the Core package.

## Query Processed Data

From the suite root, query Core with the generated local token:

```bash
docker exec ia-influxdb influxdb3 query \
  --token "$(jq -r '.token' .secrets/admin-token.json)" \
  --database datain \
  'SELECT * FROM "wind-turbine-anomaly-data" LIMIT 10'
```

The API configuration payload limit remains 5 KB. The UDF tar upload limit defaults to 100 MB.

## Access the API

The Time Series Analytics Microservice Swagger UI is available at `http://<host_ip>:5000/docs`.
See the [API documentation](./how-to-access-api.md).

## Troubleshooting

- Check the API logs with `docker logs -f ia-time-series-analytics-microservice`.
- Check Core Processing Engine and plugin logs with `docker logs ia-influxdb 2>&1 | grep -i error`.
- Confirm `/health` returns 200, the UDF package was uploaded, and the Core trigger was registered after `/config`.

## Other Deployment Options

- [How to Deploy with Helm](./get-started/deploy-with-helm.md): guide for Kubernetes deployments. Helm migration to Core is not part of this Docker migration.

## Supporting Resources

- [Overview](./index.md)
- [System Requirements](./get-started/system-requirements.md)

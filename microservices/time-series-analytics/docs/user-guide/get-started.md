# Get Started

- **Time to Complete:** 30 minutes
- **Programming Language:** Python 3

## Prerequisites

- [System Requirements](./get-started/system-requirements.md)
- Docker Compose
- For GPU inference, a supported Intel GPU and host GPU drivers

## Deploy Standalone

The image runs the Time Series Analytics API and InfluxDB 3 Core together. From the microservice's `docker/` directory, build and start it with the same Compose workflow used upstream:

```bash
docker compose build
docker compose up -d
```

The one-shot initializer creates an offline Core admin token in a private Docker volume and prepares the persistent data volume before the combined container starts. The API is available at `http://localhost:5000`; Core is bound to `127.0.0.1:8181`. Both volumes persist across `docker compose down`; `docker compose down -v` removes them.

GPU deployments use the host's `/dev/dri` devices, as in the original Compose setup.

### Run the Temperature Classifier

From the microservice root, package and upload the built-in Core plugin, then activate the existing `config.json`:

```bash
tar --exclude='__pycache__' --exclude='*.pyc' \
  -cf temperature_classifier.tar udfs/temperature_classifier
curl -X POST http://localhost:5000/udfs/package \
  -F "file=@temperature_classifier.tar"
curl -s -X POST http://localhost:5000/config \
  -H 'Content-Type: application/json' \
  -d @config.json
```

Generate sample data with the existing simulator:

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r simulator/requirements.txt
python simulator/temperature_input.py --port 5000
```

Core logs temperatures outside the inclusive 20–25 range:

```bash
docker logs -f ia-time-series-analytics-microservice | grep Temperature
```

To include copyleft sources during the image build:

```bash
docker compose build --build-arg COPYLEFT_SOURCES=true
```

## Deploy the Wind Turbine Sample

The Wind Turbine model, UDF plugin, and simulator configuration are maintained in the original [Industrial Edge Insights Time Series suite](https://github.com/open-edge-platform/edge-ai-suites/tree/main/manufacturing-ai-suite/industrial-edge-insights-time-series).

Build the combined Time Series Analytics/Core image from this repository first, using the same image name and tag configured by the suite `.env`. Then follow the suite's Docker [Get Started guide](https://github.com/open-edge-platform/edge-ai-suites/blob/main/manufacturing-ai-suite/industrial-edge-insights-time-series/docs/user-guide/get-started.md) and run either `make up_mqtt_ingestion` or `make up_opcua_ingestion` from the suite root.

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
docker exec ia-time-series-analytics-microservice influxdb3 query \
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
- Check Core Processing Engine and plugin logs with `docker logs ia-time-series-analytics-microservice 2>&1 | grep -i error`.
- Confirm `/health` returns 200, the UDF package was uploaded, and the Core trigger was registered after `/config`.

## Other Deployment Options

- [How to Deploy with Helm](./get-started/deploy-with-helm.md): guide for Kubernetes deployments. Helm migration to Core is not part of this Docker migration.

## Supporting Resources

- [Overview](./index.md)
- [System Requirements](./get-started/system-requirements.md)

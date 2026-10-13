# Get Started

- **Time to Complete:** 30 minutes
- **Programming Language:** Python 3

## Prerequisites

- [System Requirements](./get-started/system-requirements.md)

### Docker Configuration

1. **Run Docker as Non-Root**: Follow the steps in [Manage Docker as a non-root user](https://docs.docker.com/engine/install/linux-postinstall/#manage-docker-as-a-non-root-user).
2. **Configure Proxy (if required)**:
   - Set up proxy settings for Docker client and containers as described in [Docker Proxy Configuration](https://docs.docker.com/engine/cli/proxy/).
   - Example `~/.docker/config.json`:

     ```json
     {
       "proxies": {
         "default": {
           "httpProxy": "http://<proxy_server>:<proxy_port>",
           "httpsProxy": "http://<proxy_server>:<proxy_port>",
           "noProxy": "127.0.0.1,localhost"
         }
       }
     }
     ```

   - Configure the Docker daemon proxy as per [Systemd Unit File](https://docs.docker.com/engine/daemon/proxy/#systemd-unit-file).

3. **Enable Log Rotation**:
   - Add the following configuration to `/etc/docker/daemon.json`:

     ```json
     {
       "log-driver": "json-file",
       "log-opts": {
         "max-size": "10m",
         "max-file": "5"
       }
     }
     ```

   - Reload and restart Docker:

     ```bash
     sudo systemctl daemon-reload
     sudo systemctl restart docker
     ```

## Clone source code

```bash
git clone https://github.com/open-edge-platform/edge-ai-libraries.git -b main
cd edge-ai-libraries/microservices/time-series-analytics/docker
```

## Build Docker Image

Navigate to the application directory and build the Docker image:

```bash
docker compose build
```

> [!NOTE]
> To include copyleft licensed sources when building the Docker image, use the below command:
> 
> ```bash
> docker compose build --build-arg COPYLEFT_SOURCES=true
> ```

## Push Docker Images (Optional)

To push images to a Docker registry:

1. Update the following fields in `edge-ai-libraries/microservices/time-series-analytics/docker/.env`:
   - `DOCKER_REGISTRY`
   - `DOCKER_USERNAME`
   - `DOCKER_PASSWORD`

2. Push the images:

   ```bash
   docker login $DOCKER_REGISTRY
   docker compose push
   ```

## Standalone Docker Deployment

The Compose stack runs the FastAPI service and InfluxDB 3 Core together in one
container. The API is available on port `5000`; Core is internal to the
container on port `8181`. An initializer creates the Core admin token and
prepares persistent data and secret volumes.

The shipped `config.json` selects the built-in plugin in `plugin/__init__.py`.
It processes the `point_data` measurement and logs temperatures outside the
inclusive 20–25 range. No model or extra Python package is needed.

## Deploy with Docker Compose

From `microservices/time-series-analytics/docker/`, start the standalone stack:

```bash
docker compose up -d
docker compose ps
```

The API becomes available at `http://localhost:5000`. Core remains internal to
the container; the host maps `127.0.0.1:8181` for local CLI access.

## Upload the Temperature Plugin

From the `docker/` directory, move to the microservice root, package the built-in
plugin, and upload it:

```bash
cd ..
rm -f temperature_classifier.tar
tar --exclude='__pycache__' --exclude='*.pyc' -cf temperature_classifier.tar plugin/
curl -X POST http://localhost:5000/plugin/package \
  -F "file=@temperature_classifier.tar"
```

## Activate the Plugin

Post the shipped `config.json` to configure the Core trigger:

```bash
curl -s -X POST http://localhost:5000/config \
  -H 'accept: application/json' \
  -H 'Content-Type: application/json' \
  -d @config.json
```

## Ingest Temperature Data

The simulator sends points to `point_data`, which is the built-in plugin's
input measurement:

```bash
python3 -m venv venv
source venv/bin/activate
pip3 install -r simulator/requirements.txt
python3 simulator/temperature_input.py --port 5000
```

## Verify the Temperature Plugin

The plugin logs temperatures outside the configured range:

```bash
docker logs -f ia-time-series-analytics-microservice
```

## Accessing the Swagger UI

The Time Series Analytics Microservice provides an interactive Swagger UI at `http://<host_ip>:5000/docs`.
Please refer [API documentation](./how-to-access-api.md).

## Bring down the microservice

```sh
cd docker && docker compose down
```

This preserves the persistent Core data and token volumes. Add `-v` only when
you also intend to delete those volumes.

## Troubleshooting

- Check container logs to catch any failures:

  ```bash
  docker logs -f ia-time-series-analytics-microservice
  docker logs -f ia-time-series-analytics-microservice | grep -i error

  docker logs ia-time-series-analytics-microservice | grep -i error
  ```

## Supporting Resources

- [Overview](./index.md)
- [System Requirements](./get-started/system-requirements.md)

<!--hide_directive
:::{toctree}
:hidden:

./get-started/system-requirements

:::

hide_directive-->

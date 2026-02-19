# Get Started

- **Time to Complete:** 30 minutes
- **Programming Language:**  Python 3

## Prerequisites

- [System Requirements](./get-started/system-requirements.md)

### Docker Configuration

1. **Run Docker as Non-Root**: Follow the steps in [Manage Docker as a non-root user](https://docs.docker.com/engine/install/linux-postinstall/#manage-docker-as-a-non-root-user).
2. **Configure Proxy (if required)**:
   - Set up proxy settings for Docker client and containers as described in [Docker Proxy Configuration](https://docs.docker.com/network/proxy/).
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
git clone https://github.com/open-edge-platform/edge-ai-libraries.git
cd edge-ai-libraries/microservices/time-series-analytics/docker
```

## Build Docker Image

Navigate to the application directory and build the Docker image:

```bash
docker compose build
```

> **Note:**
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

## Configuration Details

> **Note:** For the default deployment, no need to change anything in the configuration.

**Time Series Analytics Microservice** uses the User Defined Function(UDF) deployment package(TICK Scripts, UDFs, Models) which is already built-in to the container image.
By default, we have a simple UDF python script at `edge-ai-libraries/microservices/time-series-analytics/udfs/temperature_classifier.py` which does not use any model file for
inferencing, it just does a simple check to filter the temperature points which are less than 20 OR greater than 25.
The corresponding tick script is available at `edge-ai-libraries/microservices/time-series-analytics/temperature_classifier.tick`.

Directory (`edge-ai-libraries/microservices/time-series-analytics/`) details is as below:

### `config.json`

| Key                     | Description                                                                                     | Example Value                          |
|-------------------------|-------------------------------------------------------------------------------------------------|----------------------------------------|
| `udfs`                  | Configuration for the User-Defined Functions (UDFs).                                            | See below for details.                 |

**UDFs Configuration**:

The `udfs` section specifies the details of the UDFs used in the task.

| Key     | Description                                                                 | Example Value                          |
|---------|-----------------------------------------------------------------------------|----------------------------------------|
| `name`  | The name of the UDF script.                                                 | `"temperature_classifier"`             |

> **Note:** The maximum allowed size for `config.json` is 5 KB.

**Alerts Configuration**: \<Optional>

The `alerts` section defines the settings for alerting mechanisms, such as MQTT protocol.
Please note the MQTT broker needs to be available.

**MQTT Configuration**:

The `mqtt` section specifies the MQTT broker details for sending alerts.

| Key                 | Description                                                                 | Example Value          |
|---------------------|-----------------------------------------------------------------------------|------------------------|
| `mqtt_broker_host`  | The hostname or IP address of the MQTT broker.                              | `"ia-mqtt-broker"`     |
| `mqtt_broker_port`  | The port number of the MQTT broker.                                         | `1883`                |
| `name`              | The name of the MQTT broker configuration.                                  | `"my_mqtt_broker"`     |

### `config/`

`kapacitor_devmode.conf` would be updated as per the above `config.json` at runtime for usage.

### `udfs/`

Contains the python script to process the incoming data.

### `tick_scripts/`

The TICKScript `temperature_classifier.tick` determines processing of the input data coming in.
Mainly, has the details on execution of the UDF file and publishing of alerts.

## Deploy with Docker Compose

Navigate to the application directory and run the Docker container:

```bash
docker compose up -d
```

## Ingesting Temperature Data into the Time Series Analytics Microservice

Run the following script to ingest temperature data into the Time Series Analytics Microservice:

```bash
pip3 install -r simulator/requirements.txt
python3 simulator/temperature_input.py --port 5000
```

## Verify the Temperature Classifier Results

Run below commands to see the filtered temperature results:

``` bash
docker logs -f ia-time-series-analytics-microservice
```

## Accessing the Swagger UI

The Time Series Analytics Microservice provides an interactive Swagger UI at `http://<host_ip>:5000/docs`.
Please refer [API documentation](./how-to-access-api.md).

## Bring down the microservice

```sh
docker compose down -v
```

## Troubleshooting

- Check container logs to catch any failures:

  ```bash
  docker logs -f ia-time-series-analytics-microservice
  docker logs -f ia-time-series-analytics-microservice | grep -i error

  # Debugging UDF errors if container is not restarting and providing expected results
  docker exec -it ia-time-series-analytics-microservice bash
  $ cat /tmp/log/kapacitor/kapacitor.log | grep -i error
  ```

## Other Deployment options

- [How to Deploy with Helm](./get-started/deploy-with-helm.md): Guide for deploying the application on a k8s cluster using Helm.

## Supporting Resources

- [Overview](./index.md)
- [System Requirements](./get-started/system-requirements.md)

<!--hide_directive
:::{toctree}
:hidden:

./get-started/system-requirements
./get-started/deploy-with-helm

:::

hide_directive-->

# Deploy Time Series Analytics Microservice

This guide describes how to build, start, and stop the Time Series Analytics Microservice (TSAM) as part of the ViPPET stack, and how to configure it with a sample Wind Turbine anomaly detection UDF.

## Prerequisites

- Docker and Docker Compose installed
- `make` available on the host
- `wget` installed (required to download UDF packages)

---

## Configure Environment Variables

Before building or starting the services, update the InfluxDB credentials `INFLUXDB_USERNAME` and `INFLUXDB_PASSWORD` in `setup_env.sh`.

---

## Build, Start, and Stop

### Build

Build all required Docker images:

```bash
make build
```

### Start

Start all services, including the Time Series Analytics Microservice:

```bash
make run
```

### Stop

Stop all running services:

```bash
make stop
```

---

## Configure the Wind Turbine Anomaly Detection UDF

Once the services are running, follow the steps below to deploy the Wind Turbine anomaly detection UDF into the TSAM.

The TSAM Swagger UI is available at **http://localhost:5000/docs**.

### Step 1. Download the UDF package

Download the pre-built Wind Turbine UDF tar archive:

```bash
wget https://raw.githubusercontent.com/open-edge-platform/edge-ai-resources/main/timeseries-udf-deployment-packages/wind-turbine-anomaly-detection.tar
```

### Step 2. Upload the UDF package

1. Open **http://localhost:5000/docs** in a browser.
2. Navigate to **POST /udfs/package**.
3. Click **Try it out**.
4. Under **Choose File**, select the downloaded `wind-turbine-anomaly-detection.tar` file.
  ![UDF Upload Diagram](../_assets/udf_upload.png)
5. Click **Execute**.

A successful response returns the message: `UDF deployment package 'wind-turbine-anomaly-detection.tar' uploaded successfully.`

### Step 3. Apply the configuration

1. Open **http://localhost:5000/docs** in a browser.
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
  ![UDF configuration Diagram](../_assets/config_udf.png)

5. Click **Execute**.

A successful response returns the message: `Configuration updated successfully.`

---

## Verify the Deployment

### Step 4. Verify the Time Series Analytics Microservice logs

Check that processing is running correctly:

```bash
docker logs -f ia-time-series-analytics-microservice
```

You should see output similar to the following:

```
2026-05-26 04:43:45,599 - classifier_startup - INFO - Successful in connecting to Kapacitor onport 9092
2026-05-26 04:43:45,599 - classifier_startup - INFO - Kapacitor Port is Open for Communication....
2026-05-26 04:43:45,621 - classifier_startup - INFO - Kapacitor Tasks Enabled Successfully
2026-05-26 04:43:45,621 - classifier_startup - INFO - Kapacitor Initialized Successfully. Ready to Receive the Data....
2026-05-26 04:43:46,201 - classifier_startup - INFO - b'ts=2026-05-26T04:43:41.770Z lvl=info msg="backup file created" service=alert bytes=32768\n'
2026-05-26 04:43:46,201 - classifier_startup - INFO - b'ts=2026-05-26T04:43:41.770Z lvl=info msg="Topic Store updated" service=alert version=2\n'
2026-05-26 04:43:46,201 - classifier_startup - INFO - b'ts=2026-05-26T04:43:41.770Z lvl=info msg="starting HTTP service" service=http\n'
2026-05-26 04:43:46,201 - classifier_startup - INFO - b'ts=2026-05-26T04:43:41.770Z lvl=info msg=authentication service=http enabled=false\n'
2026-05-26 04:43:46,201 - classifier_startup - INFO - b'ts=2026-05-26T04:43:41.770Z lvl=info msg="listening on" service=http addr=[::]:9092 protocol=http\n'
2026-05-26 04:43:46,201 - classifier_startup - INFO - b'ts=2026-05-26T04:43:41.770Z lvl=info msg="listening for signals" service=run\n'
2026-05-26 04:43:46,201 - classifier_startup - INFO - b'ts=2026-05-26T04:43:45.619Z lvl=info msg="started task" service=kapacitor task_master=main task=windturbine_anomaly_detector\n'
2026-05-26 04:43:47,203 - classifier_startup - INFO - b'ts=2026-05-26T04:43:46.698Z lvl=info msg="UDF log" service=kapacitor task_master=main task=windturbine_anomaly_detector node=windturbine_anomaly_detector2 text="Extension for Scikit-learn* enabled (https://github.com/uxlfoundation/scikit-learn-intelex)"\n'
INFO:     172.18.0.7:52784 - "POST /input HTTP/1.1" 200 OK
2026-05-26 04:43:51,208 - classifier_startup - INFO - b'ts=2026-05-26T04:43:50.495Z lvl=info msg="UDF log" service=kapacitor task_master=main task=windturbine_anomaly_detector node=windturbine_anomaly_detector2 text="INFO:sklearnex: sklearn.ensemble.RandomForestRegressor.predict: running accelerated version on CPU"\n'
INFO:     172.18.0.7:52786 - "POST /input HTTP/1.1" 200 OK
2026-05-26 04:43:56,215 - classifier_startup - INFO - b'ts=2026-05-26T04:43:50.495Z lvl=info msg="UDF log" service=kapacitor task_master=main task=windturbine_anomaly_detector node=windturbine_anomaly_detector2 text="2026-05-26 04:43:50,495 - sklearnex - INFO - sklearn.ensemble.RandomForestRegressor.predict: running accelerated version on CPU"\n'
2026-05-26 04:43:56,216 - classifier_startup - INFO - b'ts=2026-05-26T04:43:55.510Z lvl=info msg="UDF log" service=kapacitor task_master=main task=windturbine_anomaly_detector node=windturbine_anomaly_detector2 text="INFO:sklearnex: sklearn.ensemble.RandomForestRegressor.predict: running accelerated version on CPU"\n'

```

### Step 5. Check the InfluxDB database

1. Get into the InfluxDB container:

   ```bash
   docker exec -it ia-influxdb bash
   ```

2. Run the following commands to see the data in InfluxDB:

   > **NOTE:**
   > Please ignore the error message `There was an error writing history file: open /.influx_history: read-only file system` happening in the InfluxDB shell.
   > This does not affect any functionality while working with the InfluxDB commands.

   ```bash
   # INFLUXDB_USERNAME and INFLUXDB_PASSWORD can be fetched from the .env file
   influx -username <username> -password <passwd>
   use datain         # database access
   show measurements
   # Run the below query to check the output measurement processed
   # by the Time Series Analytics Microservice
   select * from "wind-turbine-anomaly-data"
   ```

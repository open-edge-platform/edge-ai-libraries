# Environment Variables
DL Streamer Pipeline Server microservice's configuration is defined via environment variables.

## Mandatory 
### Enable and specify port for REST server 
- **REST_SERVER_PORT (Integer)**  - Port on which REST Server is hosted
  - Example: `REST_SERVER_PORT=8080`

### RTSP related config
- **RTSP_CAMERA_IP (String)** - IP address of RTSP camera. 
  - Example: `RTSP_CAMERA_IP=<ip-addr>`

### Username and ID 
- **PIPELINE_SERVER_USER (String)** - Name of the user inside the dlstreamer pipeline server container
  - Example: `PIPELINE_SERVER_USER=intelmicroserviceuser`
- **UID (Integer)** - User ID permissions for the above defined user
  - Example: `UID=1999`

### proxy settings
- **http_proxy (String)** - IP address and port of `http_proxy` server.
  - Example: `http_proxy=http:<ip-addr>:<port>`
- **https_proxy (String)** - - IP address and port of `https_proxy` server.
  - Example: `https_proxy=http:<ip-addr>:<port>`
- **no_proxy (String)** - - IP address and port of `no_proxy` server.
  - Example: `no_proxy=http:<ip-addr>:<port>`

## Optional

### MQTT related configs 
- **MQTT_HOST (String)** - IP address of machine on which MQTT broker is hosted
  - Example: `MQTT_HOST=<ip-addr>`
- **MQTT_PORT (Integer)** - Port on which MQTT service is running
  - Example: `MQTT_PORT=1883`

### S3 related settings (Configure only if S3 integration is enabled)
- **S3_STORAGE_HOST (String)** - IP address of machine on which S3 storage service is hosted
  - Example: `S3_STORAGE_HOST=<ip-addr>`
- **S3_STORAGE_PORT (Integer)** - Port on which S3 stroage service is running
  - Example: `S3_STORAGE_PORT=9000`
- **S3_STORAGE_USER (String)** - Username to login into S3 storage service 
  - Example: `S3_STORAGE_USER=minioadmin`
- **S3_STORAGE_PASS (String)** - Password to login into S3 storage service
  - Example: `S3_STORAGE_PASS=minioadmin`

### OPCUA related configuration (Configure only if OPCUA is enabled)
- **OPCUA_SERVER_IP (String)** - IP address of the OPCUA server
  - Example: `OPCUA_SERVER_IP=<ip-addr>`
- **OPCUA_SERVER_PORT (Integer)** - Port on which OPCUA service is running
  - Example: `OPCUA_SERVER_PORT=48010`
- **OPCUA_SERVER_USERNAME (String)** - Username to login into OPCUA server
  - Example: `OPCUA_SERVER_USERNAME=root`
- **OPCUA_SERVER_PASSWORD (String)** - Password to login into OPCUA server
  - Example: `OPCUA_SERVER_PASSWORD=secret`

### Open Telemetry related config (Configure only if open telemetry is enabled)
- **ENABLE_OPEN_TELEMETRY (Boolean)** - Set to `true` to enable open telemetry. Set to `false` to disable open telemetry
  - Example: `ENABLE_OPEN_TELEMETRY=true`
  - Example: `ENABLE_OPEN_TELEMETRY=false`
- **OTEL_COLLECTOR_HOST (String)** - Name of open telemetry service or IP address of machine on which open telemetry service is hosted
  - Example: `OTEL_COLLECTOR_HOST=otel-collector`
  - Example: `OTEL_COLLECTOR_HOST=<ip-addr>`
- **OTEL_COLLECTOR_PORT (Integer)** - Port on which open telemetry service is running
  - Example: `OTEL_COLLECTOR_PORT=4318`
- **OTEL_EXPORT_INTERVAL_MILLIS (Integer)** - Time interval (in milliseconds) between each export of telemetry data
  - Example: `OTEL_EXPORT_INTERVAL_MILLIS=5000`
- **SERVICE_NAME (String)** - Name given to service or application producing telemetry data
  - Example: `SERVICE_NAME=my-service`
- **PROMETHEUS_PORT (Integer)** - Port on which Prometheus metrics are exposed
  - Example: `PROMETHEUS_PORT=9999`

### Webrtc related config (Configure only if WebRTC is enabled)
- **WHIP_SERVER_IP (String)** - IP address of machine on which open mediamtx container is running
  - Example: `WHIP_SERVER_IP=<ip-addr>`
- **WHIP_SERVER_PORT (Integer)** - Port on which mediamtx server is running
  - Example: `WHIP_SERVER_PORT=8889`

### Miscellaneous env variables 
- **GST_DEBUG (Integer)** - Enable GST debug logs
  - Example: `GST_DEBUG=1`
- **ADD_UTCTIME_TO_METADATA (Boolean)** - Add UTC timestamp in metadata by DL Streamer Pipeline Server publisher
  - Example: `ADD_UTCTIME_TO_METADATA=true`
  - Example: `ADD_UTCTIME_TO_METADATA=false`
- **HTTPS (Boolean)** - Make it `true` to enable SSL/TLS secure mode, mount the generated certificates
  - Example: `HTTPS=true`
  - Example: `HTTPS=false`
- **MTLS_VERIFICATION (Boolean)** - Enable/disable client certificate verification for mTLS Model Registry Microservice
  - Example: `MTLS_VERIFICATION=true`
  - Example: `MTLS_VERIFICATION=false`
- **MR_URL (String)** - Sets the URL where the model registry microservice is accessible
  - Example: MR_URL=`http://10.100.10.100:32002`
  - Example: MR_URL=`http://model-registry:32002`
  - In order to connect to the model registry using its hostname, the DL Streamer Pipeline Server and model registry has to belong to the same shared network.
  - If not set or left empty, the DL Streamer Pipeline Server will not be able to connect to the model registry successfully.
- **MR_SAVED_MODELS_DIR (String)** - Sets the directory path where the DL Streamer Pipeline Server stores models downloaded from the model registry microservice.
  - Example: `MR_SAVED_MODELS_DIR=./mr_models`
  - The `.` (dot) refers to the current working directory inside the DL Streamer Pipeline Server container.  
  - For example, if the container's working directory is `/home/pipeline-server`, then `./mr_models` means `/home/pipeline-server/mr_models`.  
  - You can configure the volume mount for this directory in your respective `docker-compose.yml` file.
  - If not set, it defaults to `./mr_models`.
- **MR_REQUEST_TIMEOUT (Integer)** - Sets the timeout for requests sent to the model registry microservice.
  - Example: `MR_REQUEST_TIMEOUT=300`
  - If not set, it defaults to `300`.
- **MR_VERIFY_CERT (String)** - Specifies how SSL certificate verification is handled when communicating with the model registry microservice.
  - Example: `MR_VERIFY_CERT=/run/secrets/ModelRegistry_Server/ca-bundle.crt`
  - Example: `MR_VERIFY_CERT=yes`
  - This variable is only used if `MR_URL` contains `https`
  - If not set, it defaults to `/run/secrets/ModelRegistry_Server/ca-bundle.crt`
  - To enable SSL certificate verification using the system's default CA bundle, set this variable to: `yes`, `y`, `true`, `t`, or `1`
  - To verify the certificates issued by CAs not included in the system's default bundle, set it to the file or directory path that contains the custom CA bundle
  - To disable verification, set it to: `no`, `n`, `false`, `f`, `0`, or leave it empty
- **LOG_LEVEL (String)** - Set the logging level for DL Streamer Pipeline Server
  - Example: `LOG_LEVEL=INFO`
  - Example: `LOG_LEVEL=DEBUG`
  - Example: `LOG_LEVEL=ERROR`
  - Example: `LOG_LEVEL=WARN`
- **BASE_IMAGE (String)** - Base image name to be used to build the DL Streamer Pipeline Server docker
  - Example: `BASE_IMAGE=<base-image-name>`
- **DLSTREAMER_PIPELINE_SERVER_IMAGE (String)** - Image name to build or run DL Streamer Pipeline Server
  - Example: `DLSTREAMER_PIPELINE_SERVER_IMAGE=intel/dlstreamer-pipeline-server:3.1.0-ubuntu22`
- **BUILD_TARGET (String)** - Option to select the target build for DL Streamer Pipeline Server. Use `dlstreamer-pipeline-server` for optimized image and `dlstreamer-pipeline-server-extended` for extended image
  - Example: `BUILD_TARGET=dlstreamer-pipeline-server`
  - Example: `BUILD_TARGET=dlstreamer-pipeline-server-extended`
- **DLSTREAMER_PIPELINE_SERVER_DOCKERFILE (String)** - Path to docker file during building of DL Streamer Pipeline Server
  - Example: `DLSTREAMER_PIPELINE_SERVER_DOCKERFILE=Dockerfile`
# Environment Variables
DL Streamer Pipeline Server microservice's configuration is defined via environment variables.

## Mandatory 
### Enable and specify port for REST server 
- **REST_SERVER_PORT** `(integer)`

### RTSP related config
- **ENABLE_RTSP** `(boolean)`
- **RTSP_PORT** `(integer)`
- **RTSP_CAMERA_IP** `(string)`

### Username and ID 
- **PIPELINE_SERVER_USER** `(string)`
- **UID** `(integer)`

### proxy settings
- **http_proxy** `(boolean)`
- **https_proxy** `(boolean)`
- **no_proxy** `(string)` 

## Optional

### MQTT related configs 
- **MQTT_HOST** `(string)`
- **MQTT_PORT** `(integer)`

### S3 related settings (Configure only if S3 integration is enabled)
- **S3_STORAGE_HOST** `(string)`
- **S3_STORAGE_PORT** `(integer)` 
- **S3_STORAGE_USER** `(string)` 
- **S3_STORAGE_PASS** `(string)`

### OPCUA related configuration (Configure only if OPCUA is enabled)
- **OPCUA_SERVER_IP** `(string)`
- **OPCUA_SERVER_PORT** `(integer)`
- **OPCUA_SERVER_USERNAME** `(string)`
- **OPCUA_SERVER_PASSWORD** `(string)`

### Open Telemetry related config (Configure only if open telemetry is enabled)
- **ENABLE_OPEN_TELEMETRY** `(boolean)`
- **OTEL_COLLECTOR_HOST** `(string)`
- **OTEL_COLLECTOR_PORT** `(integer)`
- **OTEL_EXPORT_INTERVAL_MILLIS** `(integer)`
- **SERVICE_NAME** `(string)`
- **PROMETHEUS_PORT** `(int)`

### Webrtc related config (Configure only if WebRTC is enabled)
- **ENABLE_WEBRTC** `(boolean)`
- **WHIP_SERVER_IP** `(string)`
- **WHIP_SERVER_PORT** `(integer)`

### Miscellaneous env variables 
- **GST_DEBUG**=1 : Enable GST debug logs
- **DETECTION_DEVICE**=CPU : Default Detection Device
- **CLASSIFICATION_DEVICE**=CPU : Default Classification Device
- **ADD_UTCTIME_TO_METADATA**=true : Add UTC timestamp in metadata by DL Streamer Pipeline Server publisher
- **HTTPS**=false : Make it `true` to enable SSL/TLS secure mode, mount the generated certificates
- **MTLS_VERIFICATION**=false : Enable/disable client certificate verification for mTLS Model Registry Microservice
- **MR_URL**= : Sets the URL where the model registry microservice is accessible (e.g., `http://10.100.10.100:32002` or `http://model-registry:32002`).
  - In order to connect to the model registry using its hostname, the DL Streamer Pipeline Server and model registry has to belong to the same shared network.
  - If not set or left empty, the DL Streamer Pipeline Server will not be able to connect to the model registry successfully.
- **MR_SAVED_MODELS_DIR**=./mr_models : Sets the directory path where the DL Streamer Pipeline Server stores models downloaded from the model registry microservice.
  - The `.` (dot) refers to the current working directory inside the DL Streamer Pipeline Server container.  
  - For example, if the container's working directory is `/home/pipeline-server`, then `./mr_models` means `/home/pipeline-server/mr_models`.  
  - You can configure the volume mount for this directory in your respective `docker-compose.yml` file.
  - If not set, it defaults to `./mr_models`.
- **MR_REQUEST_TIMEOUT**=300 : Sets the timeout for requests sent to the model registry microservice.
  - If not set, it defaults to `300`.
- **MR_VERIFY_CERT**=/run/secrets/ModelRegistry_Server/ca-bundle.crt : Specifies how SSL certificate verification is handled when communicating with the model registry microservice.  
  - This variable is only used if `MR_URL` contains `https`
  - If not set, it defaults to `/run/secrets/ModelRegistry_Server/ca-bundle.crt`
  - To enable SSL certificate verification using the system's default CA bundle, set this variable to: `yes`, `y`, `true`, `t`, or `1`
  - To verify the certificates issued by CAs not included in the system's default bundle, set it to the file or directory path that contains the custom CA bundle
  - To disable verification, set it to: `no`, `n`, `false`, `f`, `0`, or leave it empty
- **APPEND_PIPELINE_NAME_TO_PUBLISHER_TOPIC**=false: Add pipeline name to a published topic(optional)
- **LOG_LEVEL**=INFO : Set the logging level for DL Streamer Pipeline Server
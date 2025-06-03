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
- **MR_URL**= : URL where the model registry microservice is accessible (e.g., `http://10.100.10.100:32002`). If not set or left empty, the DL Streamer Pipeline Server will not be able to connect to the model registry successfully.
- **MR_SAVED_MODELS_DIR**=./mr_models : Default directory to store models downloaded from the model registry microservice
- **MR_REQUEST_TIMEOUT**=300 : Default timeout for requests sent to the model registry microservice
- **MR_VERIFY_CERT**=/run/secrets/ModelRegistry_Server/ca-bundle.crt : Default path to the certificate bundle associated with the model registry microservice
- **APPEND_PIPELINE_NAME_TO_PUBLISHER_TOPIC**=false: Add pipeline name to a published topic(optional)
- **LOG_LEVEL**=INFO : Set the logging level for DL Streamer Pipeline Server
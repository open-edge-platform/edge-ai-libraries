
# Enable HTTPS for DL Streamer Pipeline Server (Optional)

To enable HTTPS for DL Streamer Pipeline Server, you'll need to provide the necessary certificate and key.
1. Execute the `generate_tls_certs_keys.sh` script to create the relevant self-signed certificates and keys for the certificate authority (CA) and DL Streamer Pipeline Server's server.
    ```bash
    cd [WORKDIR]/edge-ai-libraries/microservices/dlstreamer-pipeline-server/
    cd utils

    sudo ./generate_tls_certs_keys.sh
    ```
    **Note**: When you execute `generate_tls_certs_keys.sh`, the `<WORKDIR>/Certificates/ssl_server` directory and files will be created in the parent directory. 

    To learn more about the supported arguments for the `generate_tls_certs_keys.sh` script, please refer `README.md` file present at `[WORKDIR]/edge-ai-libraries/microservices/dlstreamer-pipeline-server/utils/` detailing the shell scripts or execute `./generate_tls_certs_keys.sh --help` in the Terminal.

1. Set the `HTTPS` environment variable to `true` in the `docker-compose.yml` file.
    ```YAML
    version: "3"
      services:
        dlstreamer-pipeline-server:
          ...
          environment:
          ...
            - HTTPS=true 
    ```
    **Note**: When HTTPS is enabled, you will need to use the `-k` flag with `curl` which disables attempts to verify self-signed certificates against a certificate authority.
    
    Example `curl` command to view all pipelines:
    ```bash
    curl -k --location -X GET https://localhost:8080/pipelines
    ```

## (Optional) Enable mTLS Verification
1. Execute the `generate_tls_certs_keys.sh` script to create the relevant self-signed certificates and keys for the CA, DL Streamer Pipeline Server's REST API server, and a client.
    ```bash
    cd [WORKDIR]/edge-ai-libraries/microservices/dlstreamer-pipeline-server/
    cd utils

    sudo ./generate_tls_certs_keys.sh true [server_ip]
    ```
    **Note**: When you execute `generate_tls_certs_keys.sh`, the `<WORKDIR>/Certificates/ssl_server` directory and files will be created in the parent directory. 
    
    To learn more about the supported arguments for the `generate_tls_certs_keys.sh` script, please refer `README.md` file present at `[WORKDIR]/edge-ai-libraries/microservices/dlstreamer-pipeline-server/utils/` detailing the shell scripts or execute `./generate_tls_certs_keys.sh --help` in the Terminal.

1. Set the `MTLS_VERIFICATION` environment variable to `true` in the `docker-compose.yml` file.
    ```YAML
    version: "3"
      services:
        dlstreamer-pipeline-server:
          ...
          environment:
          ...
            - MTLS_VERIFICATION=true 
    ```
    * Note: If `HTTPS=true` and `MTLS_VERIFICATION=true`, DL Streamer Pipeline Server's REST API server will verify a client's certificate in accordance with mTLS. You will need to specify the CA's certificate, the client's certificate and key with the `curl` command.

    Example `curl` command to view all pipelines:
    ```bash
    cd <WORKDIR>/Certificates/ssl_server
    sudo curl --cacert ca.crt --key client.key --cert client.crt --location -X GET https://localhost:8080/pipelines
    ```

    Example `curl` command to start a pipeline:
    ```bash
    cd <WORKDIR>/Certificates/ssl_server
    sudo curl --cacert ca.crt --key client.key --cert client.crt https://localhost:8080/pipelines/user_defined_pipelines/pallet_defect_detection -X POST -H 'Content-Type: application/json' -d '{
      "source": {
        "uri": "file:///home/pipeline-server/resources/videos/warehouse.avi",
        "type": "uri"
      },
      "destination": {
        "metadata": {
            "type": "file",
            "path": "/tmp/results.jsonl",
            "format": "json-lines"
        },
        "frame": {
            "type": "rtsp",
            "path": "pallet-defect-detection"
        }
      },
      "parameters": {
        "detection-properties": {
          "model": "/home/pipeline-server/resources/models/geti/pallet_defect_detection/deployment/Detection/model/model.xml",
          "device": "CPU"
        }
      }
    }'
    ```

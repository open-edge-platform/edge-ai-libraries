# How to publish frames to S3

## Steps

DL Streamer Pipeline Server supports storing frames from media source into an S3 compatible storage. It supports industry standard S3 APIs, thus making it compatible with any S3 storage of your choice. 

First you must add server configuration details such as host, port, credentials, etc. as environment variables to DL Streamer Pipeline Server. 

If you are launching the service along with DL Streamer Pipeline Server, you should add the S3 storage server service details to DL Streamer Pipeline Server's docker-compose.yml file present at `[WORKDIR]/edge-ai-libraries/microservices/dlstreamer-pipeline-server/docker/docker-compose.yml`. For this tutorial we will be following this approach.

> **Note** In a production deployment, get the server details from your system admin and update the environment variables or compose file accordingly.

For demonstration, we will use SeaweedFS as the S3 storage for frames, launching it together with DL Streamer Pipeline Server. To get started, follow the steps below.

1. Modify environment variables in `[WORKDIR]/edge-ai-libraries/microservices/dlstreamer-pipeline-server/docker/.env` file.
    - Provide the S3 storage server details and credentials.

        ```sh
        S3_STORAGE_HOST=seaweedfs-s3
        S3_STORAGE_PORT=8333
        S3_STORAGE_USER=suser
        S3_STORAGE_PASS=spass
        ```
        **Note**: SeaweedFS S3 gateway API is mapped to port 8888 externally (internal port 8333) to avoid conflict with DL Streamer Pipeline Server (which uses port 8080).
    - For metadata publishing, we would be using MQTT. To enable it, we need to add the host and port details of MQTT broker in `.env` file mentioned above.
        ```sh
        MQTT_HOST=<MQTT_BROKER_IP_ADDRESS>
        MQTT_PORT=1883
        ```
        **Note** the default compose file from DL Streamer Pipeline Server provides an MQTT broker already. If you already have a broker running, only the host and port details are to be added to the environment variables.

2. Add SeaweedFS services to the docker compose yml.
    - Update the docker-compose.yml file by adding `seaweedfs-master`, `seaweedfs-volume`, `seaweedfs-filer` and `seaweedfs-s3` under `services` section. Adjust the values to suit your setup. Credentials are loaded from the `.env` file updated in the previous step.

        ```yaml
        services:
          seaweedfs-master:
            image: chrislusf/seaweedfs:latest
            hostname: seaweedfs-master
            container_name: seaweedfs-master
            ports:
              - "9333:9333"  # Master server port
              - "19333:19333"  # Master gRPC port
            networks:
              - app_network
            volumes:
              - seaweed_master_data:/data
            environment:
              - NO_PROXY=localhost,127.0.0.1,seaweedfs-master,seaweedfs-volume,seaweedfs-filer,seaweedfs-s3,172.18.0.0/16
              - no_proxy=localhost,127.0.0.1,seaweedfs-master,seaweedfs-volume,seaweedfs-filer,seaweedfs-s3,172.18.0.0/16
            command: master -ip=seaweedfs-master -ip.bind=0.0.0.0

          seaweedfs-volume:
            image: chrislusf/seaweedfs:latest
            hostname: seaweedfs-volume
            container_name: seaweedfs-volume
            ports:
              - "8081:8080"  # Volume server HTTP port
              - "18080:18080"  # Volume server gRPC port
            networks:
              - app_network
            volumes:
              - seaweed_volume_data:/data
            environment:
              - NO_PROXY=localhost,127.0.0.1,seaweedfs-master,seaweedfs-volume,seaweedfs-filer,seaweedfs-s3,172.18.0.0/16
              - no_proxy=localhost,127.0.0.1,seaweedfs-master,seaweedfs-volume,seaweedfs-filer,seaweedfs-s3,172.18.0.0/16
            command: volume -mserver=seaweedfs-master:9333 -ip.bind=0.0.0.0 -port=8080
            depends_on:
              - seaweedfs-master

          seaweedfs-filer:
            image: chrislusf/seaweedfs:latest
            hostname: seaweedfs-filer
            container_name: seaweedfs-filer
            ports:
              - "8889:8888"  # Filer HTTP port (mapped to 8889 to avoid conflict)
              - "18888:18888"  # Filer gRPC port
            networks:
              - app_network
            volumes:
              - seaweed_filer_data:/data
              - ./seaweedfs_s3_config.json:/etc/seaweedfs/s3_config.json:ro
            environment:
              - NO_PROXY=localhost,127.0.0.1,seaweedfs-master,seaweedfs-volume,seaweedfs-filer,seaweedfs-s3,172.18.0.0/16
              - no_proxy=localhost,127.0.0.1,seaweedfs-master,seaweedfs-volume,seaweedfs-filer,seaweedfs-s3,172.18.0.0/16
            command: filer -master=seaweedfs-master:9333 -ip.bind=0.0.0.0
            depends_on:
              - seaweedfs-master
              - seaweedfs-volume
            healthcheck:
              test: ["CMD", "curl", "-f", "http://localhost:8888/"]
              interval: 10s
              timeout: 5s
              retries: 5
              start_period: 30s

          seaweedfs-s3:
            image: chrislusf/seaweedfs:latest
            hostname: seaweedfs-s3
            container_name: seaweedfs-s3
            ports:
              - "8888:8333"  # S3 API port (mapped to 8888 on host)
            networks:
              - app_network
            environment:
              - NO_PROXY=localhost,127.0.0.1,seaweedfs-master,seaweedfs-volume,seaweedfs-filer,seaweedfs-s3,172.18.0.0/16
              - no_proxy=localhost,127.0.0.1,seaweedfs-master,seaweedfs-volume,seaweedfs-filer,seaweedfs-s3,172.18.0.0/16
            command: s3 -filer=seaweedfs-filer:8888 -ip.bind=0.0.0.0 -config=/etc/seaweedfs/s3_config.json
            depends_on:
              - seaweedfs-master
              - seaweedfs-volume
              - seaweedfs-filer
            volumes:
              - ./seaweedfs_s3_config.json:/etc/seaweedfs/s3_config.json:ro
        ```

        Also add the volumes to the `volumes` section at the end of the docker-compose.yml:

        ```yaml
        volumes:
          vol_pipeline_root:
            driver: local
            driver_opts:
              type: tmpfs
              device: tmpfs
          seaweed_master_data:
            driver: local
          seaweed_volume_data:
            driver: local
          seaweed_filer_data:
            driver: local
        ```

    **Important**: Create a SeaweedFS S3 IAM configuration file `seaweedfs_s3_config.json` in the docker directory with the following content to enable username/password authentication:

        ```json
        {
          "identities": [
            {
              "name": "suser",
              "credentials": [
                {
                  "accessKey": "suser",
                  "secretKey": "spass"
                }
              ],
              "actions": [
                "Admin",
                "Read",
                "Write",
                "List"
              ]
            }
          ]
        }
        ```

    Place this file in the `[WORKDIR]/edge-ai-libraries/microservices/dlstreamer-pipeline-server/docker/` directory so it can be volume-mounted by the docker-compose file.

3. A sample config has been provided for this demonstration at `[WORKDIR]/edge-ai-libraries/microservices/dlstreamer-pipeline-server/configs/sample_s3write/config.json`. We need to volume mount the sample config file in `docker-compose.yml` file. Refer below snippets:

    ```sh
    volumes:
      # Volume mount [WORKDIR]/edge-ai-libraries/microservices/dlstreamer-pipeline-server/configs/sample_s3write/config.json to config file that DL Streamer Pipeline Server container loads.
      - "../configs/sample_s3write/config.json:/home/pipeline-server/config.json"
    ```
       
    **Note** Please note that there is no `gvawatermark` element in the pipeline string, which means unannotated frames will be being published to S3 storage. If you wish to publish annotated frames, consider adding it to your pipeline. In that case, the `"pipeline"` string may look like this.

    ```sh
    "pipeline": "{auto_source} name=source  ! decodebin ! videoconvert ! gvadetect name=detection model-instance-id=inst0 ! queue ! gvafpscounter ! gvawatermark ! gvametaconvert add-empty-results=true name=metaconvert ! jpegenc ! appsink name=destination",
    ```

    - The configuration above will allow DL Streamer Pipeline Server to load a pipeline that would run an object detection using dlstreamer element `gvadetect`. Although, the MQTT details are provided in the config.json, the S3 configuration related to the bucket and object path will be sent as part of pipeline launch request mentioned few steps below. To know more about mqtt publishing, refer [here](../user-guide/advanced-guide/detailed_usage/publisher/eis_mqtt_publish_doc.md).

4. Start DL Streamer Pipeline Server and SeaweedFS.
    ```sh
    docker compose up -d
    ```
5. Create SeaweedFS bucket.
    - DL Streamer Pipeline Server expects a bucket to be created before launching the pipeline. 
    - Install the package `boto3` in your python environment if not installed.
        
        It is recommended to create a virtual environment and install it there. You can run the following commands to add the necessary dependencies as well as create and activate the environment.
            
        ```sh
        sudo apt update && \
        sudo apt install -y python3 python3-pip python3-venv
        ```
        ```sh 
        python3 -m venv venv && \
        source venv/bin/activate
        ```

        Once the environment is ready, install `boto3` with the following command
        ```sh
        pip3 install --upgrade pip && \
        pip3 install boto3==1.36.17
        ```

        Here is a sample python script that would connect to the SeaweedFS server running and create a bucket named `dlstreamer-pipeline-results`. This is the bucket we will be using to put frame objects to. Modify the parameters according to the SeaweedFS server configured.

        ```python
        import boto3
        url = "http://localhost:8888"
        bucket_name = "dlstreamer-pipeline-results"
        # SeaweedFS S3 API with IAM authentication enabled
        client = boto3.client(
            "s3",
            endpoint_url=url,
            aws_access_key_id="suser",
            aws_secret_access_key="spass"
        )
        client.create_bucket(Bucket=bucket_name)
        buckets = client.list_buckets()
        print("Buckets:", [b["Name"] for b in buckets.get("Buckets", [])])
        ```
    - Execute it in a python environment that has `boto3` package installed. Save the python script above as `create_bucket.py` in your current directory.
        ```sh
        python3 create_bucket.py
        ```
6. Launch pipeline by sending the following curl request.
    ``` sh
    curl http://localhost:8080/pipelines/user_defined_pipelines/pallet_defect_detection -X POST -H 'Content-Type: application/json' -d '{
    "source": {
        "uri": "file:///home/pipeline-server/resources/videos/warehouse.avi",
        "type": "uri"
    },
    "destination": {
        "frame": [
            {
                "type": "s3_write",
                "bucket": "dlstreamer-pipeline-results",
                "folder_prefix": "camera1",
                "block": false
            }
        ]
    },
    "parameters": {
        "detection-properties": {
            "model": "/home/pipeline-server/resources/models/geti/pallet_defect_detection/deployment/Detection/model/model.xml",
            "device": "CPU"
        }
    }
    }'
    ```
    
    The frame destination sub-config for `s3_write` indicates that the frame objects (referred by there respective image handles) will be stored in the bucket `dlstreamer-pipeline-results` at the object path prefixed as `camera1`. For example `camera1\<IMG_HANDLE>.jpg`. To learn more about the configuration details of S3 storage mentioned in `S3_write`, refer [here](./advanced-guide/detailed_usage/publisher/s3_frame_storage.md#s3_write-configuration)
    
    **Note**: DL Streamer pipeline server supports only writing of object data to S3 storage. It does not support creating, maintaining or deletion of buckets. It also does not support reading or deletion of objects from bucket. Also, as mentioned before DL Streamer pipeline server assumes that the user already has a S3 storage with buckets configured.
7. Once you start DL Streamer pipeline server with above changes, you should be able to see frames written to S3 storage and metadata over MQTT on topic `dlstreamer_pipeline_results`. Since we are using SeaweedFS storage for our demonstration, the frames are being written to the SeaweedFS server.
    
    You can verify frames are stored by listing objects in the bucket:
    
    ```python
    import boto3
    # SeaweedFS S3 API with IAM authentication
    client = boto3.client(
        "s3",
        endpoint_url="http://localhost:8888",
        aws_access_key_id="suser",
        aws_secret_access_key="spass"
    )
    response = client.list_objects_v2(Bucket="dlstreamer-pipeline-results")
    for obj in response.get("Contents", []):
        print(f"{obj['Key']} - {obj['Size']} bytes")
    ```

8. To stop DL Streamer pipeline server and other services, run the following. Since the data is stored inside the SeaweedFS container for this demonstration, the frames will not persist after the containers are brought down.
    ```sh
    docker compose down -v
    ```
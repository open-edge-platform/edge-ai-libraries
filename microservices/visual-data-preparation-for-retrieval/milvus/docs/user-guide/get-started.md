# Get Started Guide

-   **Time to Complete:** 10 mins
-   **Programming Language:** Python

## Get Started

### Prerequisites
-    Install Docker: [Installation Guide](https://docs.docker.com/get-docker/).
-    Install Docker Compose: [Installation Guide](https://docs.docker.com/compose/install/).
-    Install Intel Client GPU driver: [Installation Guide](https://dgpu-docs.intel.com/driver/client/overview.html).

### Step 1: Get the docker images

#### Option 1: build from source
Clone the source code repository if you don't have it

```bash
git clone https://github.com/open-edge-platform/edge-ai-libraries.git
cd edge-ai-libraries/microservices
```

Run the command to build images:

```bash
docker build -t dataprep-visualdata-milvus:latest --build-arg https_proxy=$https_proxy --build-arg http_proxy=$http_proxy --build-arg no_proxy=$no_proxy -f visual-data-preparation-for-retrieval/milvus/src/Dockerfile .

# build the dependency image
cd multimodal-embedding-serving
docker build -t multimodal-embedding-serving:latest --build-arg https_proxy=$https_proxy --build-arg http_proxy=$http_proxy --build-arg no_proxy=$no_proxy -f docker/Dockerfile .
```

#### Option 2: use remote prebuilt images
Set a remote registry by exporting environment variables:

```bash
export REGISTRY="intel/"  
export TAG="latest" 
```

**Note**: If you are using a release version package, you will have a pre-defined docker compose file where image registry and tag are already set to the release version. In such case, you do not need to set the environment variables above, simply move forward to the next step. You may refer to the release notes for details on the version number or check the docker compose file that is used in the steps below.

### Step 2: Prepare host directories for data

```
mkdir -p $HOME/data
```

Make sure to put all your data (images and video) in the created data directory (`$HOME/data` in the example commands) BEFORE deploying the service.

Also, make sure the created path matches with the `HOST_DATA_PATH` variable in `deployment/docker-compose/env.sh`.

Note: supported media types: jpg, png, mp4

### Step 3: Deploy

#### Deploy the application together with the Milvus Server

1. Go to the deployment files

    ``` bash
    cd deployment/docker-compose/
    ```

2.  Set up environment variables, note that you need to set an embedding model first

    ``` bash
    export EMBEDDING_MODEL_NAME="CLIP/clip-vit-h-14" # Replace with your preferred model
    source env.sh 
    ```

    **Important**: You must set `EMBEDDING_MODEL_NAME` before running `env.sh`. See [multimodal-embedding-serving's Supported Models](../../../../multimodal-embedding-serving/docs/user-guide/supported_models.md) for available options.
    
3.  Deploy with docker compose

    ``` bash
    docker compose -f compose_milvus.yaml up -d
    ```

It might take a while to start the services for the first time, as there are some models to be prepare.

Check if all microservices are up and runnning
    ```bash
    docker compose -f compose_milvus.yaml ps
    ```

Output 
```
NAME                         COMMAND                  SERVICE                                 STATUS              PORTS
dataprep-visualdata-milvus   "uvicorn dataprep_vi…"   dataprep-visualdata-milvus              running (healthy)   0.0.0.0:9990->9990/tcp, :::9990->9990/tcp
milvus-etcd                  "etcd -advertise-cli…"   milvus-etcd                             running (healthy)   2379-2380/tcp
milvus-minio                 "/usr/bin/docker-ent…"   milvus-minio                            running (healthy)   0.0.0.0:9000-9001->9000-9001/tcp, :::9000-9001->9000-9001/tcp
milvus-standalone            "/tini -- milvus run…"   milvus-standalone                       running (healthy)   0.0.0.0:9091->9091/tcp, 0.0.0.0:19530->19530/tcp, :::9091->9091/tcp, :::19530->19530/tcp
multimodal-embedding   gunicorn -b 0.0.0.0:8000 - ...   Up (health: starting)   0.0.0.0:9777->8000/tcp,:::9777->8000/tcp                                              
```

## Sample curl commands

### Info

```curl
curl -X GET http://localhost:$DATAPREP_SERVICE_PORT/v1/dataprep/info
```

### Ingest Files
**Note**: the file directory or single file sent in the request should be under the specific host directory created in Step 2.

-    For Directory:
        ```curl
        curl -X POST http://localhost:$DATAPREP_SERVICE_PORT/v1/dataprep/ingest \
        -H "Content-Type: application/json" \
        -d '{
            "file_dir": "/path/to/directory",
            "frame_extract_interval": 15,
            "do_detect_and_crop": true
        }'
        ```

-    For Single File:
        ```curl
        curl -X POST http://localhost:$DATAPREP_SERVICE_PORT/v1/dataprep/ingest \
        -H "Content-Type: application/json" \
        -d '{
            "file_path": "/path/to/file",
            "meta": {
                "key": "value"
            },
            "frame_extract_interval": 15,
            "do_detect_and_crop": true
        }'
        ```

### Get File Info

```curl
curl -X GET http://localhost:$DATAPREP_SERVICE_PORT/v1/dataprep/get?file_path=/path/to/file
```

### Delete File in Database

```curl
curl -X DELETE http://localhost:$DATAPREP_SERVICE_PORT/v1/dataprep/delete?file_path=/path/to/file
```

### Clear Database

```curl
curl -X DELETE http://localhost:$DATAPREP_SERVICE_PORT/v1/dataprep/delete_all
```

## Learn More

-    Check the [API reference](./api-reference.md)
-    The visual data preparation microservice usually pairs with a retriever microservice, check the retriever's [get-started-guide](../../../retriever/docs/user-guide/get-started.md)
-    This microservice depends on the [multimodal embedding service](https://github.com/open-edge-platform/edge-ai-libraries/blob/main/microservices/multimodal-embedding-serving/docs/user-guide/get-started.md) for embedding extraction.



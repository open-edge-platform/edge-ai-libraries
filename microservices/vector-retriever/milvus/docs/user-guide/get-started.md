# Get Started Guide

-   **Time to Complete:** 10 mins
-   **Programming Language:** Python

## Get Started

### Prerequisites
-    Install Docker: [Installation Guide](https://docs.docker.com/get-docker/).
-    Install Docker Compose: [Installation Guide](https://docs.docker.com/compose/install/).
-    Install Intel Client GPU driver: [Installation Guide](https://dgpu-docs.intel.com/driver/client/overview.html).

### Step 1: Build
Clone the source code repository if you don't have it

```bash
git clone https://github.com/open-edge-platform/edge-ai-libraries.git -b release-1.2.0
cd edge-ai-libraries/microservices
```

Run the command to build image:

```bash
docker build -t retriever-milvus:latest --build-arg https_proxy=$https_proxy --build-arg http_proxy=$http_proxy --build-arg no_proxy=$no_proxy -f vector-retriever/milvus/src/Dockerfile .
```

### Step 2: Prepare host directories for models

```
mkdir -p $HOME/.cache/huggingface
mkdir -p $HOME/models
```

### Step 3: Deploy

#### Option1 (**Recommended**): Deploy the application together with the Milvus Server

1. Go to the deployment files

    ``` bash
    cd deployment/docker-compose/
    ```

2.  Set up environment variables

    ``` bash
    source env.sh
    ```

When prompting `Please enter the LOCAL_EMBED_MODEL_ID`, choose one model name from table below and input

##### Supported Local Embedding Models

| Model Name                          | Search in English | Search in Chinese | Remarks|
|-------------------------------------|----------------------|---------------------|---------------|
| CLIP-ViT-H-14                        | Yes                  | No                 |            |
| CN-CLIP-ViT-H-14              | Yes                  | Yes                  | Supports search text query in Chinese       | 


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
milvus-etcd                  "etcd -advertise-cli…"   milvus-etcd                             running (healthy)   2379-2380/tcp
milvus-minio                 "/usr/bin/docker-ent…"   milvus-minio                            running (healthy)   0.0.0.0:9000-9001->9000-9001/tcp, :::9000-9001->9000-9001/tcp
milvus-standalone            "/tini -- milvus run…"   milvus-standalone                       running (healthy)   0.0.0.0:9091->9091/tcp, 0.0.0.0:19530->19530/tcp, :::9091->9091/tcp, :::19530->19530/tcp
retriever-milvus             "uvicorn retriever_s…"   retriever-milvus                        running (healthy)   0.0.0.0:7770->7770/tcp, :::7770->7770/tcp
```

#### Option2: Deploy the application with the Milvus Server deployed separately
If you have customized requirements for the Milvus Server, you may start the Milvus Server separately and run the commands for retriever service only

``` bash
cd deployment/docker-compose/

source env.sh # refer to Option 1 for model selection

docker compose -f compose.yaml up -d
```

## Sample curl commands

### Basic Query

```curl
curl -X POST http://<host>:$RETRIEVER_SERVICE_PORT/v1/retrieval \
-H "Content-Type: application/json" \
-d '{
    "query": "example query",
    "max_num_results": 5
}'
```

### Query with Filter

```curl
curl -X POST http://<host>:$RETRIEVER_SERVICE_PORT/v1/retrieval \
-H "Content-Type: application/json" \
-d '{
    "query": "example query",
    "filter": {
        "type": "example"
    },
    "max_num_results": 10
}'
```

## Learn More

-    Check the [API reference](./api-reference.md)



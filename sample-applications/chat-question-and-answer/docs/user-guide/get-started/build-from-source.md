# Build from Source

This guide provides step-by-step instructions for building the ChatQ&A Sample Application from source.

> **Note:**
>
> - The dependent microservices must be built separately from their respective microservice folders.
> - The build instruction is applicable only on an Ubuntu system. Build from source is not supported either for the sample application or the dependent microservices on [Edge Microvisor Toolkit](https://github.com/open-edge-platform/edge-microvisor-toolkit). It is recommended to use prebuilt images on Edge Microvisor Toolkit.

## Prerequisites

Before you begin, ensure that you have the following prerequisites:

- Docker installed on your system: [Installation Guide](https://docs.docker.com/get-docker/).
- Model download microservice is up and running. [Get Started Guide](https://github.com/open-edge-platform/edge-ai-libraries/blob/main/microservices/model-download/docs/user-guide/get-started.md).
- `jq` command-line JSON processor: [Installation Guide](https://jqlang.github.io/jq/download/)

## Steps to Build from Source

1. **Clone the Repository**:
    - Clone the ChatQ&A Sample Application repository:

      ```bash
      # Clone the latest on mainline
      git clone https://github.com/open-edge-platform/edge-ai-libraries.git edge-ai-libraries
      # Alternatively, Clone a specific release branch
      git clone https://github.com/open-edge-platform/edge-ai-libraries.git edge-ai-libraries -b <release-tag>
      ```

2. **Bring Up the Model Download Microservice**:
  Before proceeding, you must bring up the model-download microservice with `plugin=openvino`. This service is required for downloading and converting models. For instructions on how to deploy and configure the model-download microservice, refer to its [Get Started guide](https://github.com/open-edge-platform/edge-ai-libraries/blob/main/microservices/model-download/docs/user-guide/get-started.md).

3. **Navigate to the Directory**:
    - Go to the directory where the Dockerfile is located:

      ```bash
      cd edge-ai-libraries/sample-applications/chat-question-and-answer
      ```

      Adjust the repo link appropriately in case of forked repo.

4. **Set Up Environment Variables**:
    Set up the environment variables based on the inference method you plan to use:

    _Common configuration_

    ```bash
    export HUGGINGFACEHUB_API_TOKEN=<your-huggingface-token>
    export LLM_MODEL=Qwen/Qwen2.5-7B-Instruct
    export EMBEDDING_MODEL_NAME=Alibaba-NLP/gte-large-en-v1.5
    export RERANKER_MODEL=BAAI/bge-reranker-base
    export DEVICE="CPU" # Options: CPU for VLLM and TGI. GPU is only enabled for openvino model server(OVMS) .

    # Model-Download microservice configuration
    export MODEL_DOWNLOAD_HOST=<your-model-download-host>
    export MODEL_DOWNLOAD_PORT=<your-model-download-port>
    ```

    _Optional OTLP configuration_

    ```bash
    # Set only if there is an OTLP endpoint available
    export OTLP_ENDPOINT_TRACE=<otlp-endpoint-trace>
    export OTLP_ENDPOINT=<otlp-endpoint>
    ```

    _Document Ingestion Microservice configuration_

    ```bash
    # Mandatory for safe URL ingestion by Document Ingestion Microservice to mitigate SSRF attacks.
    export ALLOWED_HOSTS=<comma_separated_list_of_trusted_domains> # Ex: example.com,subdomain.example.com
    ```

    For detailed guidance on configuring __ALLOWED_HOSTS__ for different deployment scenarios, refer [ALLOWED_HOSTS Configuration](https://github.com/open-edge-platform/edge-ai-libraries/blob/main/microservices/document-ingestion/pgvector/docs/user-guide/get-started.md#allowed_hosts-configuration)

    __NOTE__: If the system has an integrated GPU, its id is always 0 (GPU.0). The GPU is an alias for GPU.0. If a system has multiple GPUs (for example, an integrated and a discrete Intel GPU) It is done by specifying GPU.1,GPU.0 as a __DEVICE__

    Refer to the supported model list in the [Get Started](../get-started.md) document.

    _Run the below script to set up the rest of the environment depending on the model server and embedding._

    ```bash
    export REGISTRY="intel/"
    export TAG=2.0.1
    source setup.sh llm=<model-server> embed=<embedding>
    # Below are the options
    # model-server: VLLM(deprecated) , OVMS, TGI(deprecated)
    # embedding: OVMS, TEI
    ```

5. **Build the Docker Image**:
    - Build the Docker image for the ChatQ&A Sample Application:

      ```bash
      docker compose build
      ```

    - The following services will be built as shown in the below screenshot.

         ![Chatqna Services build from Source](../_assets/Chatqna-service-build.png)

    - Refer to [Overview](../index.md#technical-architecture) for details on the built microservices.
    Note: `chatqna` and `ChatQnA backend` refer to the same microservice.

6. **Run the Docker Container**:
    - Run the Docker container using the built image:

      ```bash
      docker compose up
      ```
7. **Access the Application**:
    - Open a browser and go to `http://<host-ip>:8101` to access the application dashboard.

## Verification

- Ensure that the application is running by checking the Docker container status:

  ```bash
  docker ps
  ```

- Access the application dashboard and verify that it is functioning as expected.

## Troubleshooting

- If you encounter any issues during the build or run process, check the Docker logs for errors:

  ```bash
  docker logs <container-id>
  ```

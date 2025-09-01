# How to Build from Source

This guide provides step-by-step instructions for building the ChatQ&A Sample Application from source.

> **Note:** 
> - The dependent microservices must be built separately from their respective microservice folders.
> - The build instruction is applicable only on an Ubuntu system. Build from source is not supported either for the sample application or the dependent microservices on [Edge Microvisor Toolkit (EMT)](https://github.com/open-edge-platform/edge-microvisor-toolkit). The user is recommended to use prebuilt images on EMT. 

## Prerequisites

Before you begin, ensure that you have the following prerequisites:
- Docker installed on your system: [Installation Guide](https://docs.docker.com/get-docker/).

## Steps to Build from Source

1. **Clone the Repository**:
    - Clone the ChatQ&A Sample Application repository:
      ```bash
      git clone https://github.com/open-edge-platform/edge-ai-libraries.git edge-ai-libraries
      ```

2. **Navigate to the Directory**:
    - Go to the directory where the Dockerfile is located:
      ```bash
      cd edge-ai-libraries/sample-applications/chat-question-and-answer
      ```
      Adjust the repo link appropriately in case of forked repo.
   
3. **Set Up Environment Variables**:
    Set up the environment variables based on the inference method you plan to use:

    _Common configuration_
    ```bash
    export HUGGINGFACEHUB_API_TOKEN=<your-huggingface-token>
    export LLM_MODEL=Intel/neural-chat-7b-v3-3
    export EMBEDDING_MODEL_NAME=BAAI/bge-small-en-v1.5
    export RERANKER_MODEL=BAAI/bge-reranker-base
    export DEVICE="CPU" #Options: CPU for VLLM and TGI. GPU is only enabled for openvino model server(OVMS) .
    export OTLP_ENDPOINT_TRACE=<otlp-endpoint-trace> # Optional. Set only if there is an OTLP endpoint available
    export OTLP_ENDPOINT=<otlp-endpoint> # Optional. Set only if there is an OTLP endpoint available
    ```
    __NOTE__: If the system has an integrated GPU, its id is always 0 (GPU.0). The GPU is an alias for GPU.0. If a system has multiple GPUs (for example, an integrated and a discrete Intel GPU) It is done by specifying GPU.1,GPU.0 as a __DEVICE__

    Refer to the supported model list in the [Get Started](./get-started.md) document.

     _Environment variables for OVMS as inference_
    ```bash
    # Create a python virtual environment
    python3 -m venv .venv
    # Activate the virtual env
    source .venv/bin/activate
    # Install required Python packages for model preparation
    pip install -r ovms_config/requirements.txt
    ```

    To run a **GATED MODEL** like Llama models, the user will need to pass their [huggingface token](https://huggingface.co/docs/hub/security-tokens#user-access-tokens). The user will need to request access to specific model by going to the respective model page on HuggingFace.

    _Go to https://huggingface.co/settings/tokens to get your token._
    ```bash
    # Login using huggingface-cli
    huggingface-cli login
    # pass hugging face token
    ```

    _Run the below script to set up the rest of the environment depending on the model server and embedding._
    ```bash
    export REGISTRY="intel/"
    source setup.sh llm=<model-server> embed=<embedding>
    # Below are the options
    # model-server: VLLM , OVMS, TGI
    # embedding: OVMS, TEI
    ```

4. **Build the Docker Image**:
    - Build the Docker image for the ChatQ&A Sample Application:
      ```bash
      docker compose build
      ```
    - The following services will be built as shown in the below screenshot.

         ![Chatqna Services build from Source](./images/Chatqna-service-build.png)
      
    - Refer to [Overview](./overview.md#technical-architecture) for details on the built microservices. 
    Note: `chatqna` and `ChatQnA backend` refer to the same microservice.

5. **Run the Docker Container**:
    - Run the Docker container using the built image:
      ```bash
      docker compose up
      ```
6. **Access the Application**:
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

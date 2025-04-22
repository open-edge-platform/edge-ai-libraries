# How to Build from Source

This guide provides step-by-step instructions for building the ChatQ&A Sample Application from source.

## Prerequisites

Before you begin, ensure that you have the following prerequisites:
- Docker installed on your system: [Installation Guide](https://docs.docker.com/get-docker/).

## Steps to Build from Source

1. **Clone the Repository**:
    - Clone the ChatQ&A Sample Application repository:
      ```bash
      git clone https://github.com/open-edge-platform/edge-ai-libraries.git edge-ai-libraries
      cd edge-ai-libraries/sample-applications/chat-question-and-answer/chart/subchart/pgvector
      ```

2. **Navigate to the Directory**:
    - Go to the directory where the Dockerfile is located:
      ```bash
      cd <repository-url>/sample-applications/chat-question-and-answer
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
    export OTLP_ENDPOINT_TRACE=<otlp-endpoint-trace> # Optional. Set only if there is an OTLP endpoint available
    export OTLP_ENDPOINT=<otlp-endpoint> # Optional. Set only if there is an OTLP endpoint available
    ```
    Refer to the supported model list in the [Get Started](./get-started.md) document.
    
    _Environment variables for OVMS as inference_
    ```bash
    # Install required Python packages for model preparation
    export PIP_EXTRA_INDEX_URL="https://download.pytorch.org/whl/cpu"
    pip3 install optimum-intel@git+https://github.com/huggingface/optimum-intel.git openvino-tokenizers[transformers]==2024.4.* openvino==2024.4.* nncf==2.14.0 sentence_transformers==3.1.1 openai "transformers<4.45"
    ```

    To run a **GATED MODEL** like Llama models, the user will need to pass their [huggingface token](https://huggingface.co/docs/hub/security-tokens#user-access-tokens). The user will need to request access to specific model by going to the respective model page on HuggingFace.

    _Go to https://huggingface.co/settings/tokens to get your token._
    ```bash
    # Login using huggingface-cli
    pip install huggingface-hub
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

5. **Run the Docker Container**:
    - Run the Docker container using the built image:
      ```bash
      docker compose up
      ```

6. **Access the Application**:
    - Open a browser and go to `http://<host-ip>:5173` to access the application dashboard.

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

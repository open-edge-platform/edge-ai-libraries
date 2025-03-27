# Get Started

<!--
**Sample Description**: Provide a brief overview of the application and its purpose.
-->
The ChatQ&A Sample Application is a modular Retrieval Augmented Generation (RAG) pipeline designed to help developers create intelligent chatbots that can answer questions based on enterprise data. This guide will help you set up, run, and modify the ChatQ&A Sample Application on Intel Tiber<sup>TM</sup> AI systems for the edge.

<!--
**What You Can Do**: Highlight the developer workflows supported by the guide.
-->
By following this guide, you will learn how to:
- **Set up the sample application**: Use Docker Compose to quickly deploy the application in your environment.
- **Run the application**: Execute the application to see real-time question answering based on your data.
- **Modify application parameters**: Customize settings like inference models and deployment configurations to adapt the application to your specific requirements.

## Prerequisites

- Verify that your system meets the [minimum requirements](./system-requirements.md).
- Install Docker: [Installation Guide](https://docs.docker.com/get-docker/).
- Install Docker Compose: [Installation Guide](https://docs.docker.com/compose/install/).
- Install `Python 3.11` or higher.

<!--
**Setup and First Use**: Include installation instructions, basic operation, and initial validation.
-->
## Running the application using Docker Compose
<!--
**User Story 1**: Setting Up the Application
- **As a developer**, I want to set up the application in my environment, so that I can start exploring its functionality.

**Acceptance Criteria**:
1. Step-by-step instructions for downloading and installing the application.
2. Verification steps to ensure successful setup.
3. Troubleshooting tips for common installation issues.
-->

1. **Clone the Repository**:
    Clone the ChatQ&A sample application repository. Note: Documentation will be updated post migration to the public repo to point to the new repo that is accessible outside of Intel.
    ```bash
    git clone https://github.com/open-edge-platform/edge-ai-libraries.git
    ```

2. **Navigate to the Directory**:
    Go to the directory where the Docker Compose file is located:
    ```bash
    cd edge-ai-libraries/sample-applications/chat-question-and-answer
    ```
    ***Embedding Models Supported for each model server***
    | Model Server | Models Supported |
    |--------------|-------------------|
    | `TEI`        | `BAAI/bge-small-en-v1.5`, `BAAI/bge-base-en-v1.5`, `BAAI/bge-large-en-v1.5` |
    | `OVMS`       | `BAAI/bge-small-en-v1.5`, `BAAI/bge-large-en-v1.5`, `nomic-ai/nomic-embed-text-v1.5`, `Alibaba-NLP/gte-large-en-v1.5`, `thenlper/gte-small` |

3. **Set Up Environment Variables**:
    Set up the environment variables based on the inference method you plan to use:

    _Common configuration_
    ```bash
    export HUGGINGFACEHUB_API_TOKEN=<your huggingface token>
    export LLM_MODEL=Intel/neural-chat-7b-v3-3
    export EMBEDDING_MODEL_NAME=BAAI/bge-small-en-v1.5
    export RERANKER_MODEL=BAAI/bge-reranker-base
    export OTLP_ENDPOINT_TRACE=<OTLP_ENDPOINT_TRACE> # Optional. Set only if there is an OTLP endpoint available or can be ignored
    export OTLP_ENDPOINT=<OTLP Endpoint> # Optional. Set only if there is an OTLP endpoint available or can be ignored
    ```

    _Environment variables for OVMS as inference_
    ```bash
    # Install required Python packages for model preparation
    export PIP_EXTRA_INDEX_URL="https://download.pytorch.org/whl/cpu"
    pip3 install optimum-intel@git+https://github.com/huggingface/optimum-intel.git openvino-tokenizers[transformers]==2024.4.* openvino==2024.4.* nncf==2.14.0 sentence_transformers==3.1.1 openai "transformers<4.45"
    ```

    To run a **GATED MODEL** like llama models, the user will need to pass their [huggingface token](https://huggingface.co/docs/hub/security-tokens#user-access-tokens). The user will need to request access to specific model by going to the respective model page in HuggingFace.

    _Go to https://huggingface.co/settings/tokens to get your token._
    ```bash
    # Login using huggingface-cli
    pip install huggingface-hub
    huggingface-cli login
    # pass hf_token
    ```

    _Run the below script to set up the rest of the environment depending on the model server and embedding._
    ```bash
    export REGISTRY="intel/"
    export TAG=1.1.1
    source setup.sh llm=<ModelServer> embed=<Embedding>
    # Below are the options
    # ModelServer: VLLM , OVMS, TGI
    # Embedding: OVMS, TEI
    ```

4. **Start the Application**:
    Start the application using Docker Compose:
    ```bash
    docker compose up
    ```

5. **Verify the Application**:
    Check that the application is running:
    ```bash
    docker ps
    ```

6. **Access the Application**:
    Open a browser and go to `http://{host_ip}:5173` to access the application dashboard.

## Running in Kubernetes

Refer to [Deploy with Helm](./deploy-with-helm.md) for the details. Ensure the prerequisites mentioned on this page are addressed before proceeding to deploy with Helm.

## Running Tests

1. Ensure you have the necessary environment variables set up as mentioned in the setup section.

2. Run the tests using `pytest`:
   ```sh
   cd sample-applications/chat-question-and-answer/tests/unit_tests/
   poetry run pytest
   ```

## Advanced Setup Options

For alternative ways to set up the sample application, see:
- [How to Build from Source](./build-from-source.md)

## Related Links

- [How to Test Performance](./how-to-performance.md)

## Supporting Resources

- [Docker Compose Documentation](https://docs.docker.com/compose/)
- [API Reference](./chatqna-api.yml)

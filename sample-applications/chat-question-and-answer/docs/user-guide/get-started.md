# Get Started

<!--
**Sample Description**: Provide a brief overview of the application and its purpose.
-->

The ChatQ&A Sample Application is a modular Retrieval Augmented Generation (RAG) pipeline designed to help developers create intelligent chatbots that can answer questions based on enterprise data. This guide will help you set up, run, and modify the ChatQ&A Sample Application on Intel Edge AI systems.

<!--
**What You Can Do**: Highlight the developer workflows supported by the guide.
-->

By following this guide, you will learn how to:

- **Set up the sample application**: Use Docker Compose to quickly deploy the application in your environment.
- **Run the application**: Execute the application to see real-time question answering based on your data.
- **Modify application parameters**: Customize settings like inference models and deployment configurations to adapt the application to your specific requirements.

## Prerequisites

- Verify that your system meets the [minimum requirements](./get-started/system-requirements.md).
- Install Docker: [Installation Guide](https://docs.docker.com/get-docker/).
- Install Docker Compose : `Required v2.33.1` [Installation Guide](https://docs.docker.com/compose/install/).
- Install `Python 3.11`.
- Model download microservice is up and running. [Get Started Guide](../../../../microservices/model-download/docs/user-guide/get-started.md).
- `jq` command-line JSON processor: [Installation Guide](https://jqlang.github.io/jq/download/).

<!--
**Setup and First Use**: Include installation instructions, basic operation, and initial validation.
-->

## Supported Models
All models - embedding, reranker, and LLM - which are supported by the chosen model serving can be used with this sample application. The models can be downloaded from popular model hubs like Hugging Face. Refer to respective model hub documentation for details on how to access and download models.

The sample application has been validated with a few models just to validate the functionality. This list is only illustrative and the user is not limited to only these models.

### Embedding Models validated for each model server
   | Model Server | Models Validated |
   |--------------|-------------------|
   | `TEI` | `Alibaba-NLP/gte-large-en-v1.5`, `nomic-ai/nomic-embed-text-v1.5` |
   | `OVMS` | `Alibaba-NLP/gte-large-en-v1.5`, `nomic-ai/nomic-embed-text-v1.5` |

### LLM Models validated for each model server
| Model Server | Models Validated |
   |--------------|-------------------|
   | `vLLM` (deprecated) | `Intel/neural-chat-7b-v3-3`, `Qwen/Qwen2.5-7B-Instruct`, `microsoft/Phi-3.5-mini-instruct`, `meta-llama/Llama-3.1-8B-instruct`, `deepseek-ai/DeepSeek-R1-Distill-Qwen-7B` |
   | `OVMS` | `Intel/neural-chat-7b-v3-3`, `Qwen/Qwen2.5-7B-Instruct`, `microsoft/Phi-3.5-mini-instruct`, `meta-llama/Llama-3.1-8B-instruct`, `deepseek-ai/DeepSeek-R1-Distill-Qwen-7B` |
   | `TGI` (deprecated) | `Intel/neural-chat-7b-v3-3`, `Qwen/Qwen2.5-7B-Instruct`, `microsoft/Phi-3.5-mini-instruct`, `meta-llama/Llama-3.1-8B-instruct`, `deepseek-ai/DeepSeek-R1-Distill-Qwen-7B` |

**Note:**
1. Limited validation was done on DeepSeek model.
2. Effective 2025.2.0 release, support for vLLM and TGI is deprecated. The functionality is not guaranteed to work and the user is advised not to use them. Should there be a strong requirement for the same, please raise an issue in github.

### Reranker Models validated
   | Model Server | Models Validated |
   |--------------|-------------------|
   | `TEI` | `BAAI/bge-reranker-base` |

### Getting access to models

To run a **GATED MODEL** like llama models, the user will need to pass their [huggingface token](https://huggingface.co/docs/hub/security-tokens#user-access-tokens). The user will need to request access to specific model by going to the respective model page in HuggingFace.

Visit https://huggingface.co/settings/tokens to get your token.

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
   Clone the repository.

   ```bash
   # Clone the latest on mainline
   git clone https://github.com/open-edge-platform/edge-ai-libraries.git edge-ai-libraries
   # Alternatively, Clone a specific release branch
   git clone https://github.com/open-edge-platform/edge-ai-libraries.git edge-ai-libraries -b <release-tag>
   ```
   Note: Adjust the repo link appropriately in case of forked repo.

2. **Bring Up the Model Download Microservice**:
  Before proceeding, you must bring up the model-download microservice with `plugin=openvino`. This service is required for downloading and converting models. For instructions on how to deploy and configure the model-download microservice, refer to its [Get Started guide](../../../../microservices/model-download/docs/user-guide/get-started.md).

3. **Navigate to the Directory**:
   Go to the directory where the Docker Compose file is located:

   ```bash
   cd edge-ai-libraries/sample-applications/chat-question-and-answer
   ```

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
   # Mandatory for safe URL ingestion by Document Ingestion Microservice to mitigate SSRF attacks
    export ALLOWED_HOSTS=<comma_separated_list_of_trusted_domains> # Ex: example.com,subdomain.example.com
    ```

    For detailed guidance on configuring __ALLOWED_HOSTS__ for different deployment scenarios, refer [ALLOWED_HOSTS Configuration](../../../../microservices/document-ingestion/pgvector/docs/user-guide/get-started.md#allowed_hosts-configuration)

    __NOTE__: If the system has an integrated GPU, its id is always 0 (GPU.0). The GPU is an alias for GPU.0. If a system has multiple GPUs (for example, an integrated and a discrete Intel GPU) It is done by specifying GPU.1,GPU.0 as a __DEVICE__

    Refer to the supported model list in the [Get Started](./get-started.md) document.

    _Run the below script to set up the rest of the environment depending on the model server and embedding._
    ```bash
    export REGISTRY="intel/"
    export TAG=2.0.1
    source setup.sh llm=<model-server> embed=<embedding>
    # Below are the options
    # model-server: VLLM(deprecated) , OVMS, TGI(deprecated)
    # embedding: OVMS, TEI
    ```

5. **Start the Application**:
   Start the application using Docker Compose:

   ```bash
   docker compose up
   ```
   - Refer to [the application architecture diagram](./how-it-works.md#technical-architecture-diagram) .

6. **Verify the Application**:
   Check that the application is running:

   ```bash
   docker ps
   ```

7. **Access the Application**:
   Open a browser and go to `http://<host-ip>:8101` to access the application dashboard. The application dashboard allows the user to,
    - Create and manage context by adding documents (pdf, docx, etc.) and web links (only https).
    > **Note**:
    > - There are restrictions on the max size of the document allowed.
    > - Only HTTPS URLs are allowed for web links.
    - Start Q&A session with the created context.

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

<!--hide_directive
:::{toctree}
:hidden:

get-started/system-requirements

:::
hide_directive-->
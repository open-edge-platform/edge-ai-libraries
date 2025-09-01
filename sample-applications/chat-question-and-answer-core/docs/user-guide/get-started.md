# Get Started

<!--
**Sample Description**: Provide a brief overview of the application and its purpose.
-->
The ChatQ&A Sample Application is a Retrieval Augmented Generation (RAG) pipeline designed to be used in a single user non concurrent deployment primarily targeting  Intel® Core&trade; deployments.  The application is intended to help developers create personal intelligent chatbots that can answer questions based on their private data. This guide will help you set up, run, and modify the ChatQ&A Sample Application on Intel Edge AI systems.

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
    Clone the repository.
    ```bash
    git clone https://github.com/open-edge-platform/edge-ai-libraries.git edge-ai-libraries
    ```
    Note: Adjust the repo link appropriately in case of forked repo.

2. **Navigate to the Directory**:
    Go to the directory where the Docker Compose file is located:
    ```bash
    cd edge-ai-libraries/sample-applications/chat-question-and-answer-core
    ```

3. **Configure Image Pulling Registry and Tag Environment Variables**:
    To utilize the release images for the ChatQ&A sample application from the registry, set the following environment variables:
    ```bash
    export REGISTRY="intel/"
    export UI_TAG=core_1.2.2
    # If you prefer to use the default CPU device, set the following:
    export BACKEND_TAG=core_1.2.2
    # If you want to utilize GPU device for inferencing, set the following:
    # Note: This image also supports CPU devices.
    export BACKEND_TAG=core_gpu_1.2.2
    ```
    Skip this step if you prefer to build the sample application from source. For detailed instructions, refer to **[How to Build from Source](./build-from-source.md)** guide for details.

4. **Set Up Environment Variables**:
    - Set up the environment variables:
      ```bash
       export HUGGINGFACEHUB_API_TOKEN=<your-huggingface-token>

       # For default CPU setup
       source scripts/setup_env.sh

       # For GPU setup
       source scripts/setup_env.sh -d gpu
      ```

5. **Model Configuration Setup**:
    - Model settings can be specified using a YAML configuration file. A sample template is available at [template.yaml](../../model_config/sample/template.yaml) to help you get started. After creating and customizing your YAML file, set the `MODEL_CONFIG_PATH` environment variable to point to its location. You can specify the path to your YAML configuration file using either an absolute path or a relative path. If you are not familiar with Docker volume mount logic, it is recommended to use a full path to avoid any potential issues.
      ```bash
      # Recommended: Using a full path to your YAML file
      export MODEL_CONFIG_PATH=<path-to-your-yaml-file>
      ```

      If `MODEL_CONFIG_PATH` is not set, the application will automatically fall back to its built-in default configuration, which uses the same [template YAML](../../model_config/sample/template.yaml) file.

    - A collection of ready-to-use YAML configuration files featuring validated combinations of LLMs, Embedding models, and Rerankers is available in the [model_config folder](../../model_config/). Feel free to explore these examples and use them as a starting point.

    - If you wish to assign the inference workload to other dedicated device such as CPU/GPU device independently, you can assign each model's inference workload to a specific device(e.g., CPU or GPU) independently by configuring the `device_settings` section in the YAML as below:
      ```bash
      # EMBEDDING_DEVICE: Specifies the device for embedding model inference.
      # RERANKER_DEVICE: Specifies the device for reranker model inference.
      # LLM_DEVICE: Specifies the device for LLM model inference.
      # Make sure that you are using the correct backend image if you wish to use GPU inferencing.
      device_settings:
        EMBEDDING_DEVICE: "GPU"
        RERANKER_DEVICE: "GPU"
        LLM_DEVICE: "GPU"
      ```

    - __NOTE__: If the system has an integrated GPU, its id is always 0 (GPU.0). The GPU is an alias for GPU.0. If a system has multiple GPUs (for example, an integrated and a discrete Intel GPU) It is done by specifying GPU.0, GPU.1

      ```bash
        device_settings:
          EMBEDDING_DEVICE: "<GPU.0/GPU.1>"
          RERANKER_DEVICE: "<GPU.0/GPU.1>"
          LLM_DEVICE: "<GPU.0/GPU.1>"
      ```

    - Refer to and use the same list of models as documented in [Chat Question-and-Answer](../../../chat-question-and-answer/docs/user-guide/get-started.md#supported-models).

6. **Start the Application**:
    Start the application using docker compose:
    ```bash
    docker compose -f docker/compose.yaml up
    ```

7. **Verify the Application**:
    Following log should be printed on the console to confirm that the application is ready for use.
      ```bash
      # chatqna-core    | INFO:     Application startup complete.
      # chatqna-core    | INFO:     Uvicorn running on http://0.0.0.0:8888
      ```

8. **Access the Application**:
    Open a browser and go to `http://<host-ip>:8102` to access the application dashboard. The application dashboard allows the user to,
    - Create and manage context by adding documents (pdf, docx, etc. Note: Web links are not supported for the Core version of the sample application. Note: There are restrictions on the max size of the document allowed.)
    - Start Q&A session with the created context.


## Advanced Setup Options

For alternative ways to set up the sample application, see:

- [How to Build from Source](./build-from-source.md)

## Supporting Resources

- [Docker Compose Documentation](https://docs.docker.com/compose/)
- [API Reference](./api-docs/chatqna-api.yml)

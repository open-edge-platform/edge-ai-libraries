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
    Clone the ChatQ&A sample application repository. Note: Documentation will be updated post-migration to the public repo to point to the new repo that is accessible outside of Intel.
    ```bash
    git clone https://github.com/open-edge-platform/edge-ai-libraries.git
    ```

2. **Navigate to the Directory**:
    Go to the directory where the Docker Compose file is located:
    ```bash
    cd edge-ai-libraries/sample-applications/chat-question-and-answer-core
    ```

3. **Configure Image Pulling Registry and Tag Environment Variables**:
    To utilize the release images for the ChatQ&A sample application from the registry, set the following environment variables:
    ```bash
    export REGISTRY="intel/"
    export BACKEND_TAG=core_1.1.1
    export UI_TAG=core_1.1.1
    ```
    Skip this step if you prefer to build the sample application from source. For detailed instructions, refer to **[How to Build from Source](./build-from-source.md)** guide for details.

4. **Set Up Environment Variables**:
    Set up the environment variables:
    ```bash
    export HUGGINGFACEHUB_API_TOKEN=<your huggingface token>
    source scripts/setup_env.sh
    ```
    Configure the models to be used - LLM, Embeddings, Rerankers - in the `scripts/setup_env.sh` as needed.

5. **Start the Application**:
    Start the application using docker compose:
    ```bash
    docker compose -f docker/compose.yaml up
    ```

6. **Verify the Application**:
    Following log should be printed on the console to confirm that the application is ready for use.
      ```bash
      # chatqna-core    | INFO:     Application startup complete.
      # chatqna-core    | INFO:     Uvicorn running on http://0.0.0.0:8888
      ```

7. **Access the Application**:
    Open a browser and go to `http://$HOST_IP:5173` to access the application dashboard.

## Advanced Setup Options

For alternative ways to set up the sample application, see:

- [How to Build from Source](./build-from-source.md)

## Supporting Resources

- [Docker Compose Documentation](https://docs.docker.com/compose/)
- [API Reference](./chatqna-api.yml)

# How to Build from Source

This section shows how to build the Document Summarization Sample Application from the source.

## Prerequisites

Before you begin, ensure that you have the following prerequisites:

- Docker platform installed on your system: [Installation Guide](https://docs.docker.com/get-docker/).

## Steps to Build from Source

1. **Clone the Repository**:
    - Clone the Document Summarization Sample Application repository:
      ```bash
      git clone <repository-url>
      ```

2. **Navigate to the Directory**:
    - Go to the directory where the Dockerfile is located:
      ```bash
      cd <repository-url>/sample-applications/document-summarization
      ```
	  
3. **Set Up Environment Variables**:
    - Set up the following environment variables:

      ```bash
      # OVMS Configuration
      export VOLUME_OVMS=<model-export-path-for-OVMS>  # For example, use: export VOLUME_OVMS="$PWD"
      export LLM_MODEL=<llm-model>

      # Docker Image Registry Configuration
      export REGISTRY="intel/"
      export UI_TAG=1.0
      export BACKEND_TAG=1.0
      ```
        > **Note:**  
        > OpenTelemetry and OpenLit Configurations are optional. Set these only if there is an OTLP endpoint available.

        > ```bash
        >  export OTLP_ENDPOINT=<OTLP-endpoint>
        >  export no_proxy=${no_proxy},$OTLP_ENDPOINT,
        >   ```
      
    - Run the following script to set up the rest of the environment:

        ```bash
        source ./setup.sh
        ```

4. **Build the Docker Image**:
    - Build the Docker image for the Document Summarization Sample Application:
      ```bash
      docker compose build
      ```

5. **Run the Docker Container**:
    - Run the Docker container using the built image:
      ```bash
      docker compose up
      ```
      
    - This will start:
     
        - The OVMS service for model serving (gRPC: port 9300, REST: port 8300)
        
        - The FastAPI backend service (port 8090)
        
        - The Gradio UI service (port 9998)
        
        - The nginx (port 8101)

6. **Access the Application**:
    - Open a browser and go to `http://<host-ip>:8101` to access the application dashboard (Gradio UI at port 9998 and Gradio UI through NGINX web server at port 8101).
    - To access FastAPI documentation, go to `http://${host_ip}:8090/docs` in the browser.

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

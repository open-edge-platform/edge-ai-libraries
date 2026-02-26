# Build from Source

This section shows how to build the Model Download microservice from source.

## Prerequisites

- **Docker platform**: Install Docker platform from [Get Docker](https://docs.docker.com/get-docker/).

## Build Model Download Microservice

1. **Clone the repository**:

      ```bash
      # Clone the latest on the mainline
        git clone https://github.com/open-edge-platform/edge-ai-libraries.git edge-ai-libraries
      # Alternatively, clone a specific release branch
        git clone https://github.com/open-edge-platform/edge-ai-libraries.git edge-ai-libraries -b <release-tag>
      ```
2. **Navigate to the directory**:

    - Go to the model-download microservice directory
      ```bash
      cd microservices/model-download
      ```
3. **Configure the environment variables**

    - Set the following environment variable:
	
      ```bash
      export HUGGINGFACEHUB_API_TOKEN=<your huggingface token>
      ```
    - To use the Geti™ software, set the following environment variables:
	
      ```bash
      export GETI_HOST=<GETI_HOST_ADDRESS>
      export GETI_TOKEN=<GETI_ACCESS_TOKEN>
      export GETI_SERVER_API_VERSION=v1
      export GETI_SERVER_SSL_VERIFY=False  #DEFAULT is FALSE
      ```
4. **Build the Docker image**:

      ```bash
      source scripts/run_service.sh --build
      ``` 
      - When the image is complete as shown in the following figure,
    ![alt text](./images/image.png)
    
		you can do the following if needed:
      - Force rebuild from scratch (no cache): `source scripts/run_service.sh --rebuild`
	  
      - Display usage information: `source scripts/run_service.sh --help`
      
5. **Run the Docker container using the image**: 

      ```bash
        source scripts/run_service.sh up --plugins all --model-path tmp/models
      ```
> **Note:** Running the Docker container brings up the service and installs the dependencies for available plugins. See the [details of the available options](./get-started.md#options-available-with-the-script).

6.  **Access the application**:
    - Open a browser and go to `http://<host-ip>:8200/api/v1/docs` to access the OpenAPI specification documentation for the application.

## Verify the Application

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
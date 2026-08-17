# How to Build from Source

This section shows how to build the Video Search and Summary sample application from source.

> **Note:**
>
> - The dependent microservices can be built separately from their respective microservice folders which is recommended. There is an option provided to build dependencies along with sample application if required.
> - The build instruction is applicable only on an Ubuntu system. Build from source is not supported either for the sample application or the dependent microservices on [Edge Microvisor Toolkit](https://github.com/open-edge-platform/edge-microvisor-toolkit). It is recommended to use prebuilt images on Edge Microvisor Toolkit.

## Prerequisites

1. Address all [prerequisites](./get-started.md#prerequisites).
2. Configure the required [environment variables](./get-started.md#set-required-environment-variables).
3. If the setup is behind a proxy, ensure `http_proxy`, `https_proxy`, and `no_proxy` are properly set on the shell.
4. Ensure `make` is installed on the system.

## Steps to Build from Source

1. **Clone the Repository**:

   Clone the Video Summary Sample Application repository:

   ```bash
   # Clone the latest on mainline
   git clone https://github.com/open-edge-platform/edge-ai-libraries.git edge-ai-libraries
   # Alternatively, Clone a specific release branch
   git clone https://github.com/open-edge-platform/edge-ai-libraries.git edge-ai-libraries -b <release-tag>
   ```

2. **Navigate to the Directory**:

   Go to VSS sample application directory:

   ```bash
   cd edge-ai-libraries/sample-applications/video-search-and-summarization
   ```

3. **Build the Docker Images**:

   If you need to customize the application or build your own images, you can use the `make build` command in the repository.

   **3.1 Customizing Build Configuration**

   The Makefile constructs image names from registry URL, project name, and tag.

     ```bash
     export REGISTRY_URL=<your-container-registry-url>    # e.g. "docker.io/username/"
     export PROJECT_NAME=<your-project-name>              # e.g. "video-search-and-summarization"
     export TAG=<your-tag>                                # e.g. "rc4" or "latest"
     ```

   > **_IMPORTANT:_** Each image is named as **\<REGISTRY_URL>\<PROJECT_NAME>/\<microservice-name>:\<TAG>**. For example, with `REGISTRY_URL=docker.io/username/` and `PROJECT_NAME=video-search-and-summarization`, an image is built as **docker.io/username/video-search-and-summarization/\<microservice-name>:\<TAG>**. If `REGISTRY_URL` or `PROJECT_NAME` are unset, the corresponding part is omitted. If `TAG` is unset, **latest** is used.

   **3.2 Building Images**

   The Makefile provides targets to build and push images. Use make commands to build the dependent microservices and application microservices.

   The application microservices are: `pipeline-manager`, `vss-ui`, `video-search`, and `video-ingestion`. The dependent microservices are: [Multimodal Embedding Serving](https://github.com/open-edge-platform/edge-ai-libraries/tree/release-2026.2.0/microservices/multimodal-embedding-serving/), [Multimodal data preparation](https://github.com/open-edge-platform/edge-ai-libraries/tree/release-2026.2.0/microservices/visual-data-preparation-for-retrieval/multimodal-dataprep), and [Vector Retriever](https://github.com/open-edge-platform/edge-ai-libraries/tree/release-2026.2.0/microservices/vector-retriever/vector-retriever) (the search path delegates all vector similarity search to it). `make build-deps` builds the vector-retriever via its own `build.sh`, producing one image per backend flavor bundled into the search stack (`vector-retriever-vdms` and `vector-retriever-milvus`).

   ```bash

   # Build the sample applications services
   make build

   # Build the sample applications dependencies
   make build-deps

   # Push all built images to the configured registry
   make push
   ```

   After building, you can verify the created images with:

   ```bash
   docker images | grep <your-project-name>
   ```

4. **Run the Application**:

   Building from source only produces the images. To run and access the
   application, follow the deployment steps in the
   [Get Started](./get-started.md) guide.

## Building with Copyleft Sources

If you need to include copyleft sources in your build, you can set the following environment variable:

```bash
export ADD_COPYLEFT_SOURCES=true
```

When this environment variable is set to `true`, it allows the Dockerfiles to conditionally include copyleft sources when needed.

## Troubleshooting

- If you encounter any issues during the build or run process, check the Docker logs for errors:

  ```bash
  docker logs <container-id>
  ```

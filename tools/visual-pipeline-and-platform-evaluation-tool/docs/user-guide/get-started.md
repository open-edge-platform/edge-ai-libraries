# Get Started

The **Visual Pipeline and Platform Evaluation Tool** helps hardware decision-makers and software developers
select the optimal Intel® platform by adjusting workload parameters and analyzing the provided performance metrics.
Through its intuitive web-based interface, users can run the Smart NVR pipeline and evaluate key metrics such as
throughput, CPU and GPU metrics, enabling them to assess platform performance and determine the ideal sizing for
their needs.

By following this guide, you will learn how to:

- **Set up the sample application**: Use Docker Compose tool to quickly deploy the application in your environment.
- **Run a predefined pipeline**: Execute the Smart NVR pipeline and observe metrics.

## Prerequisites

- Verify that your system meets the [minimum requirements](./system-requirements.md).
- Install Docker platform: [Installation Guide](https://docs.docker.com/get-docker/).
- Latest NPU Linux drivers [Linux NPU Driver Releases](https://github.com/intel/linux-npu-driver/releases).

## Set up and First Use

1. **Set Up Environment Variables**:
    - Create and navigate to the directory:

      ```bash
      mkdir -p visual-pipeline-and-platform-evaluation-tool/models
      mkdir -p visual-pipeline-and-platform-evaluation-tool/shared/models
      mkdir -p visual-pipeline-and-platform-evaluation-tool/shared/videos
      cd visual-pipeline-and-platform-evaluation-tool
      ```

    - Download all required files:

      ```bash
      curl -LO "https://github.com/open-edge-platform/edge-ai-libraries/raw/refs/heads/release-2025.2.0/tools/visual-pipeline-and-platform-evaluation-tool/setup_env.sh"
      curl -LO "https://github.com/open-edge-platform/edge-ai-libraries/raw/refs/heads/release-2025.2.0/tools/visual-pipeline-and-platform-evaluation-tool/compose.yml"
      curl -LO "https://github.com/open-edge-platform/edge-ai-libraries/raw/refs/heads/release-2025.2.0/tools/visual-pipeline-and-platform-evaluation-tool/compose.cpu.yml"
      curl -LO "https://github.com/open-edge-platform/edge-ai-libraries/raw/refs/heads/release-2025.2.0/tools/visual-pipeline-and-platform-evaluation-tool/compose.gpu.yml"
      curl -LO "https://github.com/open-edge-platform/edge-ai-libraries/raw/refs/heads/release-2025.2.0/tools/visual-pipeline-and-platform-evaluation-tool/compose.npu.yml"
      curl -LO "https://github.com/open-edge-platform/edge-ai-libraries/raw/refs/heads/release-2025.2.0/tools/visual-pipeline-and-platform-evaluation-tool/Makefile"
      curl -Lo models/Dockerfile "https://github.com/open-edge-platform/edge-ai-libraries/raw/refs/heads/release-2025.2.0/tools/visual-pipeline-and-platform-evaluation-tool/models/Dockerfile"
      curl -Lo models/model_manager.sh "https://github.com/open-edge-platform/edge-ai-libraries/raw/refs/heads/release-2025.2.0/tools/visual-pipeline-and-platform-evaluation-tool/models/model_manager.sh"
      curl -Lo shared/videos/default_recordings.yaml "https://github.com/open-edge-platform/edge-ai-libraries/raw/refs/heads/release-2025.2.0/tools/visual-pipeline-and-platform-evaluation-tool/shared/videos/default_recordings.yaml"
      curl -Lo shared/models/supported_models.yaml "https://github.com/open-edge-platform/edge-ai-libraries/raw/refs/heads/release-2025.2.0/tools/visual-pipeline-and-platform-evaluation-tool/shared/models/supported_models.yaml"
      chmod +x models/model_manager.sh
      chmod +x setup_env.sh
      ```

2. **Start the Application**:
    - Run the following command:

      ```bash
      make build-models run
      ```

3. **Verify the Application**:
    - Check that the application is running:

      ```bash
      docker compose ps
      ```

4. **Access the Application Swagger UI**:
    - Open a browser and go to `http://localhost:7860/docs` to access the Swagger UI.

## Validation

1. **Verify Build Success**:
   - Check the logs. Look for confirmation messages indicating that the microservice has started successfully.

## Advanced Setup Options

For alternative ways to set up the sample application, see:

- [How to Build from Source](./how-to-build-source.md)

### Model Installation and Management

When you first launch the Visual Pipeline and Platform Evaluation Tool,
you will be prompted to select and install the models you wish to use.
This step allows you to choose only the models relevant to your intended pipelines.

If you want to manage your installed models again, run the following command:

```bash
make install-models-force
```

## Troubleshooting

1. **Containers Not Starting**:
   - Check the Docker logs for errors:

     ```bash
     docker compose logs
     ```

2. **Port Conflicts**:
   - Update the `ports` section in the Docker Compose file to resolve conflicts.

## Supporting Resources

- [Docker Compose Documentation](https://docs.docker.com/compose/)

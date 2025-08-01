# Get Started

The **Visual Pipeline and Platform Evaluation Tool (ViPPET)** helps hardware decision-makers and software developers select the optimal Intel platform by adjusting workload parameters and analyzing the provided performance metrics. Through its intuitive web-based interface, users can run the Smart NVR pipeline and evaluate key metrics such as throughput, CPU and GPU metrics, enabling them to assess platform performance and determine the ideal sizing for their needs.

By following this guide, you will learn how to:
- **Set up the sample application**: Use Docker Compose to quickly deploy the application in your environment.
- **Run a predefined pipeline**: Execute the Smart NVR pipeline and observe metrics.


## Prerequisites
- Verify that your system meets the [minimum requirements](./system-requirements.md).
- Install Docker: [Installation Guide](https://docs.docker.com/get-docker/).
- Latest NPU Linux Drivers [Linux NPU Driver Releases](https://github.com/intel/linux-npu-driver/releases).


## Set up and First Use

1. **Set Up Environment Variables**:
    - Download the setup script:
      ```bash
      curl -L -o setup_env.sh "https://raw.githubusercontent.com/open-edge-platform/edge-ai-libraries/refs/heads/main/tools/visual-pipeline-and-platform-evaluation-tool/setup_env.sh"
      ```
    - Execute the setup script with the desired device profile:
      ```bash
       # For default CPU setup
       source setup_env.sh

       # For GPU setup
       source setup_env.sh -d gpu
     
       # For NPU setup
       source setup_env.sh -d npu
      ```
      
2. **Download the Compose File**:
    - Create and navigate to directory:
      ```bash
        mkdir visual-pipeline-and-platform-evaluation-tool
        cd visual-pipeline-and-platform-evaluation-tool
      ```
    - Download the Docker Compose file:
      ```bash
        curl -L -o compose.yml "https://raw.githubusercontent.com/open-edge-platform/edge-ai-libraries/refs/heads/main/tools/visual-pipeline-and-platform-evaluation-tool/compose.yml"
      ```

3. **Download the Artifacts**:
    - Download the artifacts:
      ```bash
        mkdir -p video_generator
        curl -L -o video_generator/background.gif "https://raw.githubusercontent.com/open-edge-platform/edge-ai-libraries/refs/heads/main/tools/visual-pipeline-and-platform-evaluation-tool/video_generator/background.gif"
        curl -L -o video_generator/config.json "https://raw.githubusercontent.com/open-edge-platform/edge-ai-libraries/refs/heads/main/tools/visual-pipeline-and-platform-evaluation-tool/video_generator/config.json"
        mkdir -p video_generator/images/cars
        curl -L -o video_generator/images/cars/1.png "https://raw.githubusercontent.com/open-edge-platform/edge-ai-libraries/refs/heads/main/tools/visual-pipeline-and-platform-evaluation-tool/video_generator/images/cars/1.png"
        curl -L -o video_generator/images/cars/2.png "https://raw.githubusercontent.com/open-edge-platform/edge-ai-libraries/refs/heads/main/tools/visual-pipeline-and-platform-evaluation-tool/video_generator/images/cars/2.png"
        curl -L -o video_generator/images/cars/3.png "https://raw.githubusercontent.com/open-edge-platform/edge-ai-libraries/refs/heads/main/tools/visual-pipeline-and-platform-evaluation-tool/video_generator/images/cars/3.png"
        mkdir -p video_generator/images/persons
        curl -L -o video_generator/images/persons/1.png "https://raw.githubusercontent.com/open-edge-platform/edge-ai-libraries/refs/heads/main/tools/visual-pipeline-and-platform-evaluation-tool/video_generator/images/persons/1.png"
        curl -L -o video_generator/images/persons/2.png "https://raw.githubusercontent.com/open-edge-platform/edge-ai-libraries/refs/heads/main/tools/visual-pipeline-and-platform-evaluation-tool/video_generator/images/persons/2.png"
        curl -L -o video_generator/images/persons/3.png "https://raw.githubusercontent.com/open-edge-platform/edge-ai-libraries/refs/heads/main/tools/visual-pipeline-and-platform-evaluation-tool/video_generator/images/persons/3.png"
      ```

4. **Start the Application**:
    - Run the application using Docker Compose:
      ```bash
      docker compose up -d
      ```

5. **Verify the Application**:
    - Check that the application is running:
      ```bash
      docker compose ps
      ```

6. **Access the Application**:
    - Open a browser and go to `http://localhost:7860/?__theme=light` to access the application UI.

    - **Expected Results**:
      - The microservice’s UI loads successfully.
      - The Smart NVR pipeline is automatically executed when the "Run" button is clicked, and the output video is shown with device metrics.

## Make Changes

1. **Change GPU Selection Between Available Integrated and Discrete GPU**:

    - **List the Available Devices**:
      ```bash
      ls /dev/dri/
      ```

    - **Update the compose.yaml File**:
      Modify the `compose.yaml` file to specify the discrete GPU device by updating the `/dev/dri` path to the appropriate `renderXXXX` device as "/dev/dri/renderXXXX". Please note that usually the discrete GPU is mentioned as "renderD129". 

      Example:
      ```yaml
      vippet:
        ...
        ...
        devices:
          - "/dev/dri/renderD129:/dev/dri/renderD129"
        ...
      ```

## Validation

1. **Verify Build Success**:
   - Check the logs. Look for confirmation messages indicating the microservice started successfully.

## Advanced Setup Options

For alternative ways to set up the sample application, see:

- [How to Build from Source](./how-to-build-source.md)

### Known Issues

- **Issue 1**: The VIPPET container fails to start the analysis when the "Run" button is clicked in the UI, specifically for systems without GPU. This results in the analysis process either failing or becoming unresponsive for users without GPU hardware.
  - **Solution**: To avoid this issue, consider upgrading the hardware to meet the required specifications for optimal performance.

## Troubleshooting

1. **Containers Not Starting**:
   - Check the Docker logs for errors:
     ```bash
     docker compose logs
     ```
2. **Port Conflicts**:
   - Update the `ports` section in the Compose file to resolve conflicts.


## Supporting Resources
- [Docker Compose Documentation](https://docs.docker.com/compose/)


<!--
TODO: 
1. Update the git URL

-->


# Get Started

The Rapid RI Framework is a comprehensive toolset designed to accelerate the development of AI-driven applications. It provides a modular architecture that integrates seamlessly with various input sources and leverages AI models to deliver accurate and actionable insights.

By following this guide, you will learn how to:
- **Set up the sample application**: Use Docker Compose to quickly deploy the application in your environment.
- **Run a predefined pipeline**: Execute a sample pipeline to see object detection in action.
- **Modify application parameters**: Customize settings like input sources, and inference device to adapt the application to your specific requirements.


## Prerequisites
- Verify that your system meets the [minimum requirements](./system-requirements.md).
- Install Docker: [Installation Guide](https://docs.docker.com/get-docker/).
- Install Python pip and venv packages
```bash
  sudo apt update && sudo apt install -y python3-pip python3-venv
```

## Set up Device and UseCase

Modify the HOST_IP variable in the .env file to your actual host IP address.
Modify the "Case" variable in the '.env' file to the actual use case(eg. Smart_Parking/Smart_Tolling).
Execute the update_dashboard.sh script.
Execute the 'install.sh' script
These 4 steps need to be done for the first time setup and whenever a new commit is pulled.


## Set up and First Use

1. **Download the Compose File**:
    - Download the Docker Compose file and configuration:
      ```bash
        git clone https://github.com/intel-innersource/frameworks.ai.ai-suite-for-vision/tree/main/tools/rapid_ri
      ```

2. **Navigate to the Directory**:
    - Go to the directory where you saved the Compose file:
      ```bash
      cd frameworks.ai.ai-suite-for-vision/tools/rapid_ri/
      ```

3. **Update the Usecase and IP Address**:
      
      - Open the `.env` file:
        ```bash
        nano .env
        ```
      - Modify the HOST_IP variable in the .env file to your actual host IP address.
        ```bash
        HOST_IP=10.10.10.10
        ```
      - Choose the use case you want to deploy by editing the `.env` file. Available use cases are `Smart_Parking`, and `Loitering_Detection`.
        ```bash
        Case=Smart_Parking
        ```
      - Save and close the file.

4. **Update Dashboard with your Host IP Address and Use Case**
    ```bash
        ./update_dashboard
    ```

5. **Download the Model and Video files**
    ```bash
        ./install.sh
    ```

6. **Start the Application**:
    - Run the application using Docker Compose:
      ```bash
      docker compose up -d
      ```

7. **Verify the Application**:
    - Check that the application is running:
      ```bash
      docker ps
      ```

8. **Access the Application**:
    - Open a browser and go to `http://127.0.0.1:3000` to access the Grafana dashboard.
        - Change the IP address to your host IP if you are accessing it remotely.
    - Log in with the following credentials:
        - **Username:** `admin`
        - **Password:** `admin`
    - Check under the Dashboards section for the default dashboard named "Video Analytics Dashboard".
    

9. **Run a Predefined Pipeline**:
    - Run the following commands to start the pipeline
        ```bash
        ./run_sample.sh
        ```
    - **Expected Results**:
    - The dashboard displays detected objects (e.g., vehicles, pedestrians).
        - Metrics such as FPS (frames per second) are provided for detected objects.
    - ![Dashboard Example: Traffic Detection](/tools/rapid_ri/docs/developer-guide/_static/grafana_dashboard.png)
      *Figure 1: Example of a dashboard showing object detection.*

## Stop the Containers

1.  To stop the application, use the following commands:

    ```bash
    docker compose down
    ```

## Next Steps
- [How to Customize the Application](how-to-customize-application.md)

## Troubleshooting

1. **Containers Not Starting**:
   - Check the Docker logs for errors:
     ```bash
     docker compose logs
     ```

2. **No Video Streaming on Grafana Dashboard**
    - Go to the Grafana "Video Analytics Dashboard".
    - Click on the Edit option (located on the right side) under the WebRTC Stream panel. 
    - Update the URL from `http://localhost:8083` to `http://host-ip:8083`.

## Supporting Resources
- [Docker Compose Documentation](https://docs.docker.com/compose/)
- [Edge Video Analytics Microservice](https://docs.edgeplatform.intel.com/edge-video-analytics-microservice/2.3.0/user-guide/Overview.html)
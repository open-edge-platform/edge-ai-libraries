# Get Started

-   **Time to Complete:** 5 - 15 minutes
-   **Programming Language:** Python 3

## Prerequisites

* [System Requirements](./system-requirements.md)
  
## Quick try out
Follow the steps in this section to quickly pull the latest pre-built DL Streamer Pipeline Server docker image followed by running a sample usecase. 

### Pull the image and start container

- Pull the image with the latest tag from dockerhub registry

   For Ubuntu 22.04:
   ```sh
     docker pull intel/dlstreamer-pipeline-server:3.1.0-ubuntu22
   ```
   For Ubuntu 24.04:
   ```sh
     docker pull intel/dlstreamer-pipeline-server:3.1.0-ubuntu24
   ```

- Clone the Edge-AI-Libraries repository from open edge platform and change to the docker directory inside DL Streamer Pipeline Server project.

  ```sh
    cd [WORKDIR]
    git clone https://github.com/open-edge-platform/edge-ai-libraries.git
    cd edge-ai-libraries/microservices/dlstreamer-pipeline-server/docker
    ```

- Bring up the container

   ```sh
     docker compose up
   ```
   
### Run default sample

Once the container is up, we will send a pipeline request to DL Streamer pipeline server to run a detection model on a warehouse video. Both the model and video are provided as default sample in the docker image.

We will send the below curl request to run the inference.
It comprises of a source file path which is `warehouse.avi`, a destination, with metadata directed to a json fine in `/tmp/resuts.jsonl` and frames streamed over RTSP with id `pallet_defect_detection`. Additionally, we will also provide the GETi model path that would be used for detecting defective boxes on the video file.

Open another terminal and send the following curl request
``` sh
    curl http://localhost:8080/pipelines/user_defined_pipelines/pallet_defect_detection -X POST -H 'Content-Type: application/json' -d '{
    "source": {
        "uri": "file:///home/pipeline-server/resources/videos/warehouse.avi",
        "type": "uri"
    },
    "destination": {
        "metadata": {
            "type": "file",
            "path": "/tmp/results.jsonl",
            "format": "json-lines"
        },
        "frame": {
            "type": "rtsp",
            "path": "pallet_defect_detection"
        }
    },
    "parameters": {
        "detection-properties": {
            "model": "/home/pipeline-server/resources/models/geti/pallet_defect_detection/deployment/Detection/model/model.xml",
            "device": "CPU"
        }
    }
}'
```

The REST request will return a pipeline instance ID, which can be used as an identifier to query later the pipeline status or stop the pipeline instance. For example, a6d67224eacc11ec9f360242c0a86003.

- To view the metadata, open another terminal and run the following command,
  ```sh
    tail -f /tmp/results.jsonl
  ```

- RTSP Stream will be accessible at `rtsp://<SYSTEM_IP_ADDRESS>:8554/pallet_defect_detection`.  Users can view this on any media player e.g. vlc (as a network stream), ffplay etc 

  ![sample frame RTSP stream](./images/sample-pallet-defect-detection.png)

To check the pipeline status and stop the pipeline send the following requests,

 - view the pipeline status that you triggered in the above step.
   ```sh
    curl --location -X GET http://localhost:8080/pipelines/status
   ```

 - stop a running pipeline instance, 
   ```sh
    curl --location -X DELETE http://localhost:8080/pipelines/{instance_id}
   ```

Now you have successfully run the DL Streamer Pipeline Server container, sent a curl request to start a pipeline within the microservice which runs the Geti based pallet defect detection model on a sample warehouse video. Then, you have also looked into the status of the pipeline to see if everything worked as expected and eventually stopped the pipeline as well.


## Legal Information
Intel, the Intel logo, and Xeon are trademarks of Intel Corporation in the U.S. and/or other countries.

GStreamer is an open source framework licensed under LGPL. See [GStreamer licensing](https://gstreamer.freedesktop.org/documentation/frequently-asked-questions/licensing.html)⁠. You are solely responsible for determining if your use of GStreamer requires any additional licenses. Intel is not responsible for obtaining any such licenses, nor liable for any licensing fees due, in connection with your use of GStreamer.

*Other names and brands may be claimed as the property of others.

## Advanced Setup Options

For alternative ways to set up the microservice, see:

- [How to Deploy with Helm](./how-to-deploy-with-helm.md)

## Troubleshooting
- [Troubleshooting Guide](./troubleshooting-guide.md)

## Known Issues

- **Running DL Streamer Pipeline Server on Ubuntu 24.04**

    User has to install `docker compose v2` to run DL Streamer Pipeline Server on Ubuntu 24.04.


## Contact Us

Please contact us at dlsps_support[at]intel[dot]com for more details or any support.

## Supporting Resources

* [Overview](Overview.md)
* [API Reference](api-reference.md)
* [System Requirements](system-requirements.md)

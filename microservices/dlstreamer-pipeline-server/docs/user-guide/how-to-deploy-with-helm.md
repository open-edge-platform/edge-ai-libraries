# How to Deploy with Helm

-   **Time to Complete:** 5 - 15 minutes
-   **Programming Language:** Python 3

## Prerequisites

- [System Requirements](./system-requirements.md)
- K8s installation on single or multi node must be done as pre-requisite to continue the following deployment. Note: The kubernetes cluster is set up with `kubeadm`, `kubectl` and `kubelet` packages on single and multi nodes with `v1.30.2`.
  Refer to tutorials such as <https://adamtheautomator.com/install-kubernetes-ubuntu> and many other
  online tutorials to setup kubernetes cluster on the web with host OS as ubuntu 22.04.
- For helm installation, refer to [helm website](https://helm.sh/docs/intro/install/)
- Clone the Edge-AI-Libraries repository from open edge platform and change to the helm directory inside DL Streamer Pipeline Server project.

  ```sh
    cd [WORKDIR]
    git clone https://github.com/open-edge-platform/edge-ai-libraries.git
    cd edge-ai-libraries/microservices/dlstreamer-pipeline-server/helm
    ```

## Quick try out
Follow the steps in this section to quickly pull the latest pre-built DL Streamer Pipeline Server helm charts followed by running a sample usecase.

### Pull the helm chart (Optional)

- Note: The helm chart should be downloaded when you are not using the helm chart provided in `edge-ai-libraries/microservices/dlstreamer-pipeline-server/helm`

- Download helm chart with the following command

    `helm pull oci://registry-1.docker.io/intel/dlstreamer-pipeline-server --version 2025.2.0-rc1`
- unzip the package using the following command

    `tar -xvf dlstreamer-pipeline-server-2025.2.0-rc1.tgz`
- Get into the helm directory

    `cd dlstreamer-pipeline-server`

### Configure and update the environment variables

Update the below fields in `values.yaml` file in the helm chart

  ``` sh
  env:
    http_proxy: # example: http_proxy: http://proxy.example.com:891
    https_proxy: # example: http_proxy: http://proxy.example.com:891
  images:
    dlstreamer_pipeline_server: # example: dlstreamer_pipeline_server: intel/dlstreamer-pipeline-server:3.1.0-ubuntu22
  ```

### Install the helm chart

- Install the helm chart

    `helm install dlsps . -n apps --create-namespace`
- Check if DL Streamer Pipeline Server is running fine

    `kubectl get pods --namespace apps`and monitor its logs using `kubectl logs -f <pod_name> -n apps`

### Run default sample

Once the pods are up, we will send a pipeline request to DL Streamer Pipeline Server to run a detection model on a warehouse video.
The resources such as video and model are copied into `dlstreamer-pipeline-server` pod by `initContainers`.

We will send the below curl request to run the inference.
It comprises of a source file path which is `warehouse.avi`, a destination, with metadata directed to a json file in `/tmp/resuts.jsonl` and frames streamed over RTSP with id `pallet_defect_detection`. Additionally, we will also provide the GETi model path that would be used for detecting defective boxes on the video file.

Open another terminal and send the following curl request
```sh
  curl http://localhost:30007/pipelines/user_defined_pipelines/pallet_defect_detection -X POST -H 'Content-Type: application/json' -d '{
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

- RTSP Stream will be accessible at `rtsp://<SYSTEM_IP_ADDRESS>:30025/pallet_defect_detection`.  Users can view this on any media player e.g. vlc (as a network stream), ffplay etc

  ![sample frame RTSP stream](./images/sample-pallet-defect-detection.png)

To check the pipeline status and stop the pipeline send the following requests,

 - view the pipeline status that you triggered in the above step.
   ```sh
    curl --location -X GET http://localhost:30007/pipelines/status
   ```

 - stop a running pipeline instance,
   ```sh
    curl --location -X DELETE http://localhost:30007/pipelines/{instance_id}
   ```

 - Uninstall the helm chart,
   ```sh
    helm uninstall dlsps -n apps
   ```

Now you have successfully run the DL Streamer Pipeline Server container, sent a curl request to start a pipeline within the microservice which runs the Geti based pallet defect detection model on a sample warehouse video. Then, you have also looked into the status of the pipeline to see if everything worked as expected and eventually stopped the pipeline as well.

## Troubleshooting
- [Troubleshooting Guide](./troubleshooting-guide.md)

## Summary

In this get started guide, you learned how to start the DL Streamer Pipeline Server service and start default pipeline.

## Learn More

-   For getting started with the deployment using docker, please go [here](get-started.md)
-   Understand the components, services, architecture, and data flow, in
    the [Overview](Overview.md).
-   For more details on advanced configuration, usage of features refer to [Advanced user guide](./advanced-guide/Overview.md)
-   For more details on Deep Learning Streamer (DL Streamer) visit [this](https://github.com/open-edge-platform/dlstreamer/blob/master/docs/source/index.md) page.

## Legal Information
Intel, the Intel logo, and Xeon are trademarks of Intel Corporation in the U.S. and/or other countries.

GStreamer is an open source framework licensed under LGPL. See [GStreamer licensing](https://gstreamer.freedesktop.org/documentation/frequently-asked-questions/licensing.html)⁠. You are solely responsible for determining if your use of GStreamer requires any additional licenses. Intel is not responsible for obtaining any such licenses, nor liable for any licensing fees due, in connection with your use of GStreamer.

*Other names and brands may be claimed as the property of others.

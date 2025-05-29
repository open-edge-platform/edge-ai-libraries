 # OPCUA Publishing post pipeline execution

 **Contents**
  - [Overview](#overview)
  - [Prerequisites for OPCUA publishing](#prerequisites-for-opc-ua-publishing)
    - [Configure and start OPCUA Server](#configuring-and-starting-the-opc-ua-server)
  - [Configure DL Streamer Pipeline Server for OPCUA Publishing](#configure-dl-streamer-pipeline-server-for-opcua-publishing)
  - [Error Handling](#error-handling)


## Overview

Processed frames and metadata can be published to an OPC UA server. Before publishing, the OPC UA client must be properly configured and started. The flow is as follows:

1. Start the OPC UA server.
2. Configure the DL Streamer Pipeline Server to use OPC UA and start DL Streamer Pipeline Server.
3. Start the pipeline.
4. DL Streamer Pipeline Server writes the metadata to a variable on the OPC UA server.
5. Other clients interested in receiving metadata from DL Streamer Pipeline Server can connect to the server and read the variable.

## Prerequisites for OPC UA Publishing

Before DL Streamer Pipeline Server can publish data, the OPC UA server must be configured and started.

### Configuring and Starting the OPC UA Server

If you already have a functioning OPC UA server, you can skip this step. Otherwise, this section provides instructions for using the OPC UA server provided by [Unified Automation](https://www.unified-automation.com).

1. **Download and Install the OPC UA Server**
   Download the [OPC UA C++ Demo Server (Windows)](https://www.unified-automation.com/downloads/opc-ua-servers.html) and install it on your Windows machine. Please note that this server is available only for Windows.

2. **Starting the OPC UA Server**
    * Open the Start menu on your Windows machine and search for **UaCPPServer**.
    * Launch the application to start the server.

## Configure DL Streamer Pipeline Server for OPCUA Publishing
To publish the meta-data and frame over OPCUA, follow the steps below.

1. Modify environment variables
    - Provide the OPCUA server details and credentials in `[WORKDIR]/edge-ai-libraries/microservices/dlstreamer-pipeline-server/docker/.env` file.
        ```sh
        OPCUA_SERVER_IP=<IP-Address of the OPCUA server>
        OPCUA_SERVER_PORT=48010
        OPCUA_SERVER_USERNAME=<Username of OPCUA server> # example OPCUA_SERVER_USERNAME=root
        OPCUA_SERVER_PASSWORD=<Password of OPCUA server> # example OPCUA_SERVER_PASSWORD=secret
        ```
    The `OPCUA_SERVER_USERNAME` and `OPCUA_SERVER_PASSWORD` are optional. If these values are not set, DL Streamer Pipeline Server will attempt to connect to the OPCUA server anonymously.
2. Update the environment section for DL Streamer Pipeline Server service in docker-compose.yml with OPCUA environment variables.
    ```yaml
    services:
      dlstreamer-pipeline-server:
        environment:
          - OPCUA_SERVER_IP=$OPCUA_SERVER_IP
          - OPCUA_SERVER_PORT=$OPCUA_SERVER_PORT
          - OPCUA_SERVER_USERNAME=$OPCUA_SERVER_USERNAME
          - OPCUA_SERVER_PASSWORD=$OPCUA_SERVER_PASSWORD
    ```
3. A sample config has been provided for this demonstration at `[WORKDIR]/edge-ai-libraries/microservices/dlstreamer-pipeline-server/configs/sample_opcua/config.json`. We need to volume mount the sample config file in `docker-compose.yml` file. Refer below snippets:

```sh
    volumes:
      # Volume mount [WORKDIR]/edge-ai-libraries/microservices/dlstreamer-pipeline-server/configs/sample_opcua/config.json to config file that DL Streamer Pipeline Server container loads.
      - "../configs/sample_opcua/config.json:/home/pipeline-server/config.json"
```


        
        - `variable` OPCUA server variable to which the meta data will be written.
            `ns=3;s=Demo.Static.Scalar.String` is an example OPC UA server variable supported by `OPC UA C++ Demo Server`
        - `publish_frame` set this flag to '*true*' if you need frame blobs inside the metadata to be published. If it is set to '*false*' only metadata will be published.
    - The configuration above will allow DL Streamer Pipeline Server to load a pipeline that would run an object detection using dlstreamer element `gvadetect` and publish the meta-data along with the frame if `publish_frame` is set to `true` to OPC UA server variable.

4. Allow DL Streamer Pipeline Server to read the above modified configuration. 
    - We do this by volume mounting the modified default config.json in `docker-compose.yml` file. To learn more, refer [here](../../../how-to-change-dlstreamer-pipeline.md).
    
        ```yaml
        services:
          dlstreamer-pipeline-server:
            volumes:
              - "../configs/default/config.json:/home/pipeline-server/config.json"
        ```
5. Start DL Streamer Pipeline Server.
    ```sh
    docker compose up -d
    ```
6. Launch pipeline by sending the following curl request.
    ``` sh
    curl http://localhost:8080/pipelines/user_defined_pipelines/pallet_defect_detection -X POST -H 'Content-Type: application/json' -d '{
            "source": {
                "uri": "file:///home/pipeline-server/resources/videos/warehouse.avi",
                "type": "uri"
            },
            "parameters": {
                "detection-properties": {
                    "model": "/home/pipeline-server/resources/models/geti/pallet_defect_detection/deployment/Detection/model/model.xml",
                    "device": "CPU"
                }
            }
        }'
    ```

    Alternatively, we can launch pipeline by sending OPCUA through curl request.
    
    ``` sh
    curl http://localhost:8080/pipelines/user_defined_pipelines/pallet_defect_detection -X POST -H 'Content-Type: application/json' -d '{
        "source": {
            "uri": "file:///home/pipeline-server/resources/videos/warehouse.avi",
            "type": "uri"
        },
        "destination": {
            "metadata": [
                {
                    "type": "opcua",
                    "publish_frame": true,
                    "variable" : "<OPCUA-server-variable>"
                }
            ]
        },
        "parameters": {
            "detection-properties": {
                "model": "/home/pipeline-server/resources/models/geti/pallet_defect_detection/deployment/Detection/model/model.xml",
                "device": "CPU"
            }
        }
    }'
    ```

7. Run the following sample subscriber on the same/different machine by updating the `<IP-Address of OPCUA Server>` and `<OPCUA-server-variable>` to read the meta-data written to OPC UA server variable from DL Streamer Pipeline Server. Please update the below script with `ip`, `username` and `password` as mentioned in the step 1.

    ```python
    import asyncio
    from asyncua import Client, Node

    class SubscriptionHandler:
        def datachange_notification(self, node: Node, val, data):
            print(val)

    async def main():
        client = Client(url="opc.tcp://<IP-Address of OPCUA Server>:48010")
        client.set_user("<use the username provided in step 1>")
        client.set_password("<use the password provided in step 1>")
        async with client:
            handler = SubscriptionHandler()
            subscription = await client.create_subscription(50, handler)
            myvarnode = client.get_node("<OPCUA-server-variable>")
            await subscription.subscribe_data_change(myvarnode)
            await asyncio.sleep(100)
            await subscription.delete()
            await asyncio.sleep(1)

    if __name__ == "__main__":
        asyncio.run(main())
    ```

## Error Handling
**Connection Issues**: If there are any connection issues with the OPC UA server, messages will not be written to the server variable.

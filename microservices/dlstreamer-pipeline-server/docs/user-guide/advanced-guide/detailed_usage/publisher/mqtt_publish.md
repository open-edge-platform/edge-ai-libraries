 # MQTT Publishing

 **Contents**

- [Overview](#overview)
- [Prerequisites](#prerequisites-for-mqtt-publishing)
  - [Configure and start MQTT broker](#configure-and-start-mqtt-broker)
  - [Start MQTT Subscriber](#start-mqtt-subscriber)
- [Configure DL Streamer Pipeline Server for MQTT Publishing](#configure-dl-streamer-pipeline-server-for-mqtt-publishing)
  - [Configuration options](#configuration-options)
  - [Metadata filtering](#metadata-filtering)
- [Secure MQTT Publishing](#secure-publishing)
- [Error handling](#error-handling)


## Overview
The processed frames and metadata can be published over to a MQTT message broker. Prior to publishing, MQTT broker/subscriber needs to be configured and started. Here is an overview of the flow,
- DL Streamer Pipeline Server will be the MQTT publisher and publishes to MQTT broker.
- Broker receives messages from DL Streamer Pipeline Server and forwards the messages to MQTT subscribers.
- Subscriber receives messages from broker on the subscribed topic. <br>

## Prerequisites for MQTT publishing
*(Broker configuration, certificates generation are for development and testing purposes only)*

Prior to DL Streamer Pipeline Server publishing, MQTT broker and subscriber needs to be configured and started.

### Configure and start MQTT broker

MQTT broker should be configured to accept connections. Start the broker from [WORKDIR]/edge-ai-libraries/microservices/dlstreamer-pipeline-server/ directory.
For example, start [eclipse mosquitto](https://mosquitto.org/) MQTT broker using configuration in `[WORKDIR]/edge-ai-libraries/microservices/dlstreamer-pipeline-server/utils/mosquitto` as below. Make sure `echo $PWD` shows the root of DL Streamer Pipeline Server repository.

  ```sh
  docker run -d --name=mqtt_broker -p 1883:1883 -v $PWD/utils/mosquitto/mosquitto.conf:/mosquitto/config/mosquitto.conf eclipse-mosquitto
  ```

With the above configuration, the broker listens on port 1883.

### Start MQTT Subscriber
Once the mqtt broker is configured and up, connect to the mqtt broker and subscriber to topics in order to receive messages that will be published.

  - For example, run the below command to subscribe using [mosquitto_sub](https://mosquitto.org/man/mosquitto_sub-1.html) client,

    ```sh
    sudo apt install mosquitto-clients
    
    mosquitto_sub --topic <topic name> -p 1883 -h <mqtt broker address>
    ```

  - Alternatively, [Eclipse Paho MQTT Python Client](https://github.com/eclipse/paho.mqtt.python) can be used for subscribing to broker and receiving messages.

    Please make sure to update the `<topic_name>` and `<mqtt broker address>` in the script before running.

    Make sure to install the python packages:
    ```sh
    pip install paho-mqtt opencv-python numpy
    ```

    ```python
    import paho.mqtt.subscribe as subscribe

    def on_message(client, userdata, message):
        print("%s %s" % (message.topic, message.payload))

    subscribe.callback(on_message, "<topic name>", hostname="<mqtt broker address>")
    ```

    Here is a sample subscriber script for receiving both frame (JPEG encoded) and metadata, printing the metadata and saving the frame as jpg image.

    ```python
    import paho.mqtt.subscribe as subscribe
    import json
    import base64
    import numpy as np
    import cv2

    def on_message(client, userdata, message):
        print("Receiving frame and metadata")
        msg = json.loads(message.payload)

        metadata = msg[0]
        print("Metadata:", metadata)

        output_file_name = "output_" + str(metadata['frame_id']) + ".jpg"
        print("Saving frame to {}".format(output_file_name))
        img = base64.b64decode(msg[1].encode("utf-8"))
        img = np.frombuffer(img, dtype="uint8")
        img = cv2.imdecode(img, cv2.IMREAD_UNCHANGED)
        cv2.imwrite(output_file_name, img)

    subscribe.callback(on_message, "<topic_name>", hostname="<mqtt broker address>")
    ```

    More details on the subscribe helper functions can be found [here](https://github.com/eclipse/paho.mqtt.python)

## Configure DL Streamer Pipeline Server for MQTT Publishing
### Configuration options
Add values to following parameters present in `[WORKDIR]/edge-ai-libraries/microservices/dlstreamer-pipeline-server/docker/.env` file
```sh
MQTT_HOST=<mqtt broker address>
MQTT_PORT=1883
```
  - `host` mqtt broker hostname or IP address
  - `port` port to connect to the broker

Add below configuration in appropriate config.json file in in `[WORKDIR]/edge-ai-libraries/microservices/dlstreamer-pipeline-server/configs/default/` directory to enable publishing to the mqtt broker.
  ```json
    "mqtt_publisher": {
      "publish_frame": false
    }
   ```
  - `publish_frame` set this flag to '*true*' if you need frame blobs and metadata to be published. If it is set to '*false*' only metadata will be published.
    
      NOTE: When publish_frame is set to 'true', it is advised to use a pipeline element such as `jpegenc` to do the frame encoding to publish over MQTT. If not present, frame is encoded to jpeg but it is limited to frames with the following image orders - `RGB`, `GRAY8`, `NV12` and `I420`. This capability is however limited and not performance efficient.

Other parameters that can be part of `mqtt_publisher` config are mentioned below - 
  - `topic` topic to which message will be published. Defaults to `dlstreamer_pipeline_results` *(optional)*
  - `qos` quality of service level to use which defaults to 0. Values can be 0, 1, 2. *(optional)*
    More details on the QoS levels can be found [here](https://www.hivemq.com/blog/mqtt-essentials-part-6-mqtt-quality-of-service-levels)
  - `protocol` protocol version to use which defaults to 4 i.e. MQTTv311. Values can be 3, 4, 5 based on the versions MQTTv3, MQTTv311, MQTTv5 respectively *(optional)*

The configuration above can also be sent as part of REST request payload allowing users to launch new instances with different configurations such as `topic`, etc. Refer [here](../../../how-to-start-dlstreamer-pipeline-server-mqtt-publish.md) for an example.

### Metadata filtering
Below configuration can be used to optionally filter out messages sent to mqtt broker for classification and detection usecases.

- For detection:

  ```json
    "mqtt_publisher": {
      "filter": {
            "type": "detection",
            "label_score": {"shipping label": 0.4, "box": 0.4}
      }
    }
  ```

- For classification:
  ```json
  "mqtt_publisher": {
      "filter": {
          "type": "classification",
            "label_score": {
                "anomalous": 0.5
            }
      }
    }
  ```

  - `type` to specify type of filter config `classification` or `detection`
  - `label score` to specify key-value pair `class label`: `threshold`. Any detections < threshold will be skipped.

  - Note:
    - For detection, metadata is expected to have, for example,
      
      `'predictions': {'labels_to_revisit_full_scene': None, 'kind': 'prediction', 'id': None, 'maps': [], 'media_identifier': None, 'modified': None, 'annotations': [{'labels_to_revisit': None, 'shape': {'type': 'RECTANGLE', 'x': 333, 'height': 198, 'y': 127, 'width': 255}, 'id': None, 'labels': [{'id': None, 'probability': 0.9196773171424866, 'source': None, 'color': '#00f5d4', 'name': 'box'}], 'modified': None}, {'labels_to_revisit': None, 'shape': {'type': 'RECTANGLE', 'x': 494, 'height': 154, 'y': 143, 'width': 83}, 'id': None, 'labels': [{'id': None, 'probability': 0.7351013422012329, 'source': None, 'color': '#edb200', 'name': 'shipping label'}], 'modified': None}]...}`
    - For classification, metadata is expected to have, for example,
       `...{'label': 'Person', 'score': 0.5}...`

## Secure Publishing
MQTT publishing to broker could be over a secure communication channel providing encryption and authentication over TLS. More details on the broker configuration options can be found [here](https://mosquitto.org/man/mosquitto-conf-5.html) and the files required for SSL/TLS support are specified [here](https://mosquitto.org/man/mosquitto-tls-7.html).

Follow the below steps to establish a secure connection with MQTT broker,

1. Generate Certificates

   CA (Certificate Authority), client and server certificates need to be generated which will be used for configuring MQTT broker and DL Streamer Pipeline Server.

   Below script can be used for generating certificates using openssl. (Command reference: https://mosquitto.org/man/mosquitto-tls-7.html).

   - Make sure to edit the `<IP address of broker>` in the script. This will be the broker address.
   -  Executing the below script with ask for a password for ca.key and the same password to be used again when prompter during signing step.

    ```bash
      echo "Creating CA Key and Certificate"
      openssl req -new -x509 -days 365 -extensions v3_ca -keyout ca.key -out ca.crt -subj "/CN=example.com"

      echo "Creating Server key"
      openssl genrsa -out server.key 2048

      echo "Creating Server Certificate signing request"
      openssl req -subj "/CN=<IP address of broker>" -out server.csr -key server.key -new

      echo "Signing Server certificate"
      openssl x509 -req -in server.csr -extfile <(echo "subjectAltName=IP:<IP address of broker>") -CA ca.crt -CAkey ca.key -CAcreateserial -out server.crt -days 365

      echo "Creating Client key"
      openssl genrsa -out client.key 2048

      echo "Creating Client Certificate signing request"
      openssl req -subj "/" -out client.csr -key client.key -new

      echo "Signing Client certificate"
      openssl x509 -req -in client.csr -CA ca.crt -CAkey ca.key -CAcreateserial -out client.crt -days 365

      mkdir -p client
      mv client.* client/

      mkdir -p server
      mv server.* server/

    ```

    Once the certificates are generated, make sure to move the certificates to right location. Make sure `echo $PWD` shows the root of DL Streamer Pipeline Server repository.
    - Move ca.crt, server/server.crt, server/server.key to `$PWD/utils/mosquitto/certificates`
      ```sh
      mkdir $PWD/utils/mosquitto/certificates
      mkdir $PWD/utils/mosquitto/certificates/server
      cp <path to ca.crt> $PWD/utils/mosquitto/certificates
      cp <path to server/server.crt> $PWD/utils/mosquitto/certificates/server
      cp <path to server/server.key> $PWD/utils/mosquitto/certificates/server
      ```

    - Move ca.crt, client/client.crt, client/client.key to `$PWD/certificates`
      ```sh
      mkdir $PWD/certificates
      mkdir $PWD/certificates/client
      cp <path to ca.crt> $PWD/certificates
      cp <path to client/client.crt> $PWD/certificates/client
      cp <path to client/client.key> $PWD/certificates/client
      ```

    - Change permission for client.key in `$PWD/certificates/client`
      ```sh
        sudo chmod 644 $PWD/certificates/client/client.key
      ```

2. Configure and start MQTT broker

   - Modify the `[WORKDIR]/edge-ai-libraries/microservices/dlstreamer-pipeline-server/utils/mosquitto/mosquitto.conf` file as below.

    ```sh
      allow_anonymous true

      listener 8883

      cafile /mosquitto/config/certificates/ca.crt
      keyfile /mosquitto/config/certificates/server/server.key
      certfile /mosquitto/config/certificates/server/server.crt

      require_certificate true
    ```
    With the above configuration, the broker listens on port 8883 and is set up for mutual authentication.

    - Start MQTT broker

      ```sh
      docker run -d --name=mqtt_broker -p 8883:8883 -v $PWD/utils/mosquitto:/mosquitto/config eclipse-mosquitto
      ```

3. Configure and start MQTT subscriber

    As broker is configured for secure connection, CA certificate and client certificate/key needs to be provided when starting the subscriber.

    - For example, run the below command to subscribe using [mosquitto_sub](https://mosquitto.org/man/mosquitto_sub-1.html) client,

        ```sh
        sudo apt install mosquitto-clients

        mosquitto_sub --topic <topic name> -p 8883 -h <mqtt broker address> --cafile $PWD/certificates/ca.crt --cert $PWD/certificates/client/client.crt --key $PWD/certificates/client/client.key

        ```

    - Alternatively, [Eclipse Paho MQTT Python Client](https://github.com/eclipse/paho.mqtt.python) can be used for subscribing to broker and receiving messages.

      Please make sure to update the `<topic_name>`, `<mqtt broker address>`, `<path to ca.rt>`, `<path to client.crt>`, `<path to client.key`> in the script before running.

      Make sure to install the python packages:
      ```sh
      pip install paho-mqtt opencv-python numpy
      ```
      
      ```python
      import paho.mqtt.subscribe as subscribe

      def on_message(client, userdata, message):
          print("%s %s" % (message.topic, message.payload))

      subscribe.callback(on_message, "<topic name>", hostname="<mqtt broker address>", port=8883, tls={'ca_certs': "<path to ca.crt>", 'certfile': "<path to client.crt>", 'keyfile': "<path to client.key>"})
      ```

      Here is a sample subscriber script for receiving both frame (JPEG encoded) and metadata, printing the metadata and saving the frame as jpg image.

        ```python
        import paho.mqtt.subscribe as subscribe
        import json
        import base64
        import numpy as np
        import cv2

        def on_message(client, userdata, message):
            print("Receiving frame and metadata")
            msg = json.loads(message.payload)

            metadata = msg[0]
            print("Metadata:", metadata)

            output_file_name = "output_" + str(metadata['frame_id']) + ".jpg"
            print("Saving frame to {}".format(output_file_name))
            img = base64.b64decode(msg[1].encode("utf-8"))
            img = np.frombuffer(img, dtype="uint8")
            img = cv2.imdecode(img, cv2.IMREAD_UNCHANGED)
            cv2.imwrite(output_file_name, img)

        subscribe.callback(on_message, "<topic_name>", hostname="<mqtt broker address>", port=8883, tls={'ca_certs': "<path to ca.crt>", 'certfile': "<path to client.crt>", 'keyfile': "<path to client.key>"})
        ```

4. Configure DL Streamer Pipeline Server for establishing secure connection with MQTT broker

   Add values to following parameters present in `[WORKDIR]/edge-ai-libraries/microservices/dlstreamer-pipeline-server/docker/.env` file
    ```sh
    MQTT_HOST=<mqtt broker address>
    MQTT_PORT=1883
    ```

   Add below configuration in appropriate config.json file in in `[WORKDIR]/edge-ai-libraries/microservices/dlstreamer-pipeline-server/configs/default/` directory to enable publishing to the mqtt broker.

    ```json
      "mqtt_publisher": {
        "tls": {
            "ca_cert": "/MqttCerts/ca.crt",
            "client_key": "/MqttCerts/client/client.key",
            "client_cert": "/MqttCerts/client/client.crt"
        }
      }
    ```

## Error Handling
1. If connection to MQTT broker is successful, messages are published to the broker.
2. If there are connection issues with MQTT broker, messages will not be published to the broker.
3. Reconnection is automatically attempted when connection is lost. The time between successive reconnect attempts starts with 1s and doubles for every attempt until a max of 30s is reached after which it will always be 30s.
3. If connection is re-established, subsequent messages will be published to the broker.
4. Publishing to EIS Message bus remains unimpacted.

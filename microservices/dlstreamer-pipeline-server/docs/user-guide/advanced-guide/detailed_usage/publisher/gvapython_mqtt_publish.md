
```{eval-rst}
:orphan:
```

# MQTT Publishing via gvapython

- [Overview](#overview)
- [Prerequisites](#prerequisites)
  - [Verify MQTT broker has started](#verify-mqtt-broker-has-started)
  - [Start MQTT Subscriber](#start-mqtt-subscriber)
  - [Configure DL Streamer Pipeline Server for MQTT Publishing](#configure-dl-streamer-pipeline-server-for-mqtt-publishing)
  - [Configuration options](#configuration-options)
  - [Sample REST Request](#sample-rest-request)
- [Secure MQTT Publishing](#secure-publishing)
- [Error handling](#error-handling)

## Overview
The processed frames and metadata can be published over to a MQTT message broker. Prior to publishing, MQTT broker/subscriber needs to be configured and started. Here is an overview of the flow,
- DL Streamer Pipeline Server will be the MQTT publisher and publishes to MQTT broker.
- Broker receives messages from DL Streamer Pipeline Server and forwards the messages to MQTT subscribers.
- Subscriber receives messages from broker on the subscribed topic. <br>

The python script `[WORKDIR]/edge-ai-libraries/microservices/dlstreamer-pipeline-server/user_scripts/gvapython/mqtt_publisher.py` supports publishing frames and metadata to specified MQTT broker.

## Prerequisites
Prior to DL Streamer Pipeline Server publishing, MQTT broker and subscriber needs to be configured and started.

### Verify MQTT broker has started
When bringing up DL Streamer Pipeline Server containers in standalone mode using `docker compose up`, MQTT broker is also started listening on port `1883`. 
Verify MQTT broker is up and running using `docker ps`.

To configure and start MQTT broker refer [here](./eis_mqtt_publish_doc.md#configure-and-start-mqtt-broker)

### Start MQTT Subscriber
For starting MQTT subscriber, refer [here](./eis_mqtt_publish_doc.md#start-mqtt-subscriber)

## Configure DL Streamer Pipeline Server for MQTT Publishing

### Configuration options
Here is a sample configuration which performs Pallet Defect Detection and publishes the inference results to mqtt broker using gvapython script. 

```bash 
"pipeline": "{auto_source} name=source  ! decodebin ! videoconvert ! gvadetect name=detection ! queue ! gvawatermark ! gvametaconvert name=metaconvert ! gvapython class=MQTTPublisher function=process module=/home/pipeline-server/gvapython/mqtt_publisher/mqtt_publisher.py name=mqtt_publisher ! gvametapublish name=destination ! appsink name=appsink",
```

```bash
        "parameters": {
            "type": "object",
                "properties": {
                    "detection-properties": {
                        "element": {
                            "name": "detection",
                            "format": "element-properties"
                        }
                    },
                    "mqtt_publisher": {
                        "element": {
                            "name": "mqtt_publisher",
                            "property": "kwarg",
                            "format": "json"
                        },
                        "type": "object"
                    }
                }
        }
```

Modify the config to change the pipeline configuration as needed.

Add below configuration as part of REST request to enable publishing to the mqtt broker.

  - `topic` topic to which message will be published. Defaults to `dlstreamer_pipeline_results`. *(optional)*
  - `publish_frame` whether to publish only metadata or both frames and metadata can be published to the mqtt broker.
    Defaults to `false`. *(optional)*
      - When `publish_frame` is false, only metadata will be published.
      - When `publish_frame` is true, both metadata and frame will be published.
          |  Payload   |   Type         |
          |  :-------------------   |  :-------------------------                                  |
          |  Only metadata          |   JSON (metadata)
          |  Both frame and metadata|   JSON (metadata, frame) where frames are Base64 encoded UTF-8 string |

  - `qos` quality of service level to use which defaults to 0. Values can be 0, 1, 2. *(optional)*
    More details on the QoS levels can be found [here](https://www.hivemq.com/blog/mqtt-essentials-part-6-mqtt-quality-of-service-levels)
  - `protocol` protocol version to use which defaults to 4 i.e. MQTTv311. Values can be 3, 4, 5 based on the versions MQTTv3, MQTTv311, MQTTv5 respectively *(optional)*

- When publishing frames, the frames are always JPEG encoded.

### Sample REST request

```sh
curl localhost:8080/pipelines/user_defined_pipelines/pallet_defect_detection -X POST -H 'Content-Type: application/json' -d '{
                "source": {
                    "uri": "file:///home/pipeline-server/resources/videos/warehouse.avi",
                    "type": "uri"
                },
				"destination": {
				     "frame": {
						"type": "rtsp",
						"path": "pallet_defect_detection"
                    }
				},
                "parameters": {
                    "detection-properties": {
                        "model": "/home/pipeline-server/resources/models/geti/pallet_defect_detection/deployment/Detection/model/model.xml",
                        "device": "CPU"
                    },
					"mqtt_publisher": {
						"publish_frame": false
					}
                }
}'
```
`NOTE` `"host"` and `"port"` of mqtt publisher needs to be updated in `[WORKDIR]/edge-ai-libraries/microservices/dlstreamer-pipeline-server/docker/.env` file
```sh
MQTT_HOST=<mqtt broker address>
MQTT_PORT=1883
```

## Secure publishing 
Publishing to MQTT broker could be over a secure communication channel providing encryption and authentication over TLS.

Follow the steps 1, 2 and 3 from [here](./eis_mqtt_publish_doc.md#secure-publishing). 
- Generate certificates
- Configure and start MQTT broker
- Configure and start MQTT subscriber

Upon completing the broker and subscriber setup, refer to the below steps to configuring DL Streamer Pipeline Server for secure connection.

- Add values to following parameters present in `[WORKDIR]/edge-ai-libraries/microservices/dlstreamer-pipeline-server/docker/.env` file
    ```sh
    MQTT_HOST=<mqtt broker address>
    MQTT_PORT=8883
    ```

- Modify `docker-compose.yml`. The port number should match with the value specified in the `[WORKDIR]/edge-ai-libraries/microservices/dlstreamer-pipeline-server/docker/.env` file. In the above example we have used port `8883`, hence we need to add the ports with same value in `docker-compose.yml` file as shown below

    ```yaml
        ports:
        - "8883:8883"
    ```

- Sample REST request with configuration for secure connection

    ```sh
    curl localhost:8080/pipelines/user_defined_pipelines/pallet_defect_detection -X POST -H 'Content-Type: application/json' -d '{
                "source": {
                    "uri": "file:///home/pipeline-server/resources/videos/warehouse.avi",
                    "type": "uri"
                },
				"destination": {
				     "frame": {
						"type": "rtsp",
						"path": "pallet_defect_detection"
                    }
				},
                "parameters": {
                    "detection-properties": {
                        "model": "/home/pipeline-server/resources/models/geti/pallet_defect_detection/deployment/Detection/model/model.xml",
                        "device": "CPU"
                    },
					"mqtt_publisher": {
                        "tls": {
                            "ca_cert": "/MqttCerts/ca.crt",
                            "client_key": "/MqttCerts/client/client.key",
                            "client_cert": "/MqttCerts/client/client.crt"
					    }
                    }
                }
    }'
   
    ```

## Error Handling
Refer to the section [here](./eis_mqtt_publish_doc.md#error-handling) for error handling details. 

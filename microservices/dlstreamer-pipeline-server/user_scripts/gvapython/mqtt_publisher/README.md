### MQTT Publisher:

This python script supports publishing frames and metadata to specified MQTT broker.

#### Refer to the sample pipeline [Person Detection pipeline with MQTT Publishing](../../../pipelines/user_defined_pipelines/mqtt_publisher_sample/pipeline.json) which performs person detection and publishes the inference results to mqtt broker using this script.


Sample REST request:

```json
curl localhost:8080/pipelines/user_defined_pipelines/mqtt_publisher_sample -X POST -H 'Content-Type: application/json' -d '
{
    "source": {
        "uri": "file:///home/pipeline-server/resources/classroom.avi",
        "type": "uri"
    },
    "destination": {
        "metadata": {
            "type": "file",
            "path": "/tmp/results.jsonl",
            "format": "json-lines"
        }
    },
    "parameters": {
        "mqtt_publisher_config": {
            "host": "<mqtt broker address>",
            "port": 1883
        }
    }
}'

```


#### MQTT publishing to broker could be over a secure communication channel providing encryption and authentication over TLS.

Follow the below steps to securely connect to MQTT broker. 
-  [Generate certificates](../../../eii/docs//mqtt_publish_doc.md#secure-publishing#1)
- [Configure and start broker](../../../eii/docs//mqtt_publish_doc.md#secure-publishing#2)
- [Configure and start subscriber](../../../eii/docs//mqtt_publish_doc.md#secure-publishing#3) 
    
Upon completing the broker and subscriber setup, refer to the below steps to configuring secure connection. 

- Modify [docker-compose.yml](../../docker-compose.yml)

    ```yaml
        ports:
        - "8883:8883"
    ```

- Sample REST request with configuration for secure connection

    ```json
    curl localhost:8080/pipelines/user_defined_pipelines/mqtt_publisher_sample -X POST -H 'Content-Type: application/json' -d '
    {
        "source": {
            "uri": "file:///home/pipeline-server/resources/classroom.avi",
            "type": "uri"
        },
        "destination": {
            "metadata": {
                "type": "file",
                "path": "/tmp/results.jsonl",
                "format": "json-lines"
            }
        },
        "parameters": {
            "mqtt_publisher_config": {
                "host": "<mqtt broker address>",
                "port": 8883,
                "tls": {
                    "ca_cert": "/MqttCerts/ca.crt",
                    "client_key": "/MqttCerts/client/client.key",
                    "client_cert": "/MqttCerts/client/client.crt"
                }
            }
        }
    }'

    ```


### Note:
- Prerequisites for MQTT Publisher (setting up mqtt broker, subscriber) can be found [here](../../../eii/docs/mqtt_publish_doc.md#prerequisites-for-mqtt-publishing)

- Configuration

  - `host` mqtt broker hostname or IP address
  - `port` port to connect to the broker
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

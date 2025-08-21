### MQTT Publisher:

This python script supports publishing frames and metadata to specified MQTT broker.

We need to update the pipeline key in `[WORKDIR]/edge-ai-libraries/microservices/dlstreamer-pipeline-server/configs/default/config.json` as shown below:
```sh
"pipeline": "{auto_source} name=source  ! decodebin ! videoconvert ! gvadetect name=detection ! queue ! gvawatermark ! gvametaconvert name=metaconvert ! gvapython class=MQTTPublisher function=process module=/home/pipeline-server/gvapython/mqtt_publisher/mqtt_publisher.py name=mqtt_publisher ! gvafpscounter ! gvametapublish name=destination ! appsink name=appsink"
```
Add mqtt_publisher to the `properties` key in the `config.json` file as shown below:
```sh
  "mqtt_publisher": {
    "element": {
      "name": "mqtt_publisher",
      "property": "kwarg",
      "format": "json"
    },
    "type": "object"
  }

```


Sample REST request:

```json
curl localhost:8080/pipelines/user_defined_pipelines/pallet_defect_detection -X POST -H 'Content-Type: application/json' -d '
{
    "source": {
        "uri": "file:///home/pipeline-server/resources/videos/warehouse.avi",
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
	"detection-properties": {
            "model": "/home/pipeline-server/resources/models/geti/pallet_defect_detection/deployment/Detection/model/model.xml",
            "device": "CPU"
        },
        "mqtt_publisher": {
            "publish_frame": true
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

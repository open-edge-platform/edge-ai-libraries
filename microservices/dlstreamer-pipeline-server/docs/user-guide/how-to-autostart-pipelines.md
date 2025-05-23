# How to autostart pipelines

## Steps

DL Streamer Pipeline Server allows autostarting pipelines provided all the necessary payload information such as source, destination, model parameters etc are available in the configuration file.

There are 2 ways to enable autostarting the pipeline. First way is to provide all the necessary payload information while defining the pipeline itself. Second way is to provide the information under the `"pipelines"` config with `"payload"` as the keyword.

Autostart for a pipeline can be enabled by setting the flag `auto_start` to `true`. This would start an instance of pipeline immediately as soon as DL Streamer Pipeline Server container is up.

### Method 1 - Specifying all the information in the pipeline itself - 

Replace the following sections in `[WORKDIR]/edge-ai-libraries/microservices/dlstreamer-pipeline-server/configs/default/config.json` with the following

- replace `"pipeline"` section with  

    ```sh
    "pipeline": "multifilesrc location=/home/pipeline-server/resources/videos/warehouse.avi name=source  ! decodebin ! videoconvert ! gvadetect model=/home/pipeline-server/resources/models/geti/pallet_defect_detection/deployment/Detection/model/model.xml name=detection ! queue ! gvawatermark ! gvafpscounter ! gvametaconvert add-empty-results=true name=metaconvert ! gvametapublish file-format=json-lines file-path=/tmp/results.jsonl name=destination ! appsink name=appsink",
    ```
- set `"auto_start"`to `"true"`.

    Notice that we have inlined model xml path (in `gvadetect` element) and metadata publish file (in `gvametapublish` element) into the pipeline string.

- After making changes to config.json, make sure to save it and restart DL Streamer Pipeline Server. Ensure that the changes made to the config.json are reflected in the container by volume mounting (as mentioned [above](./how-to-change-dlstreamer-pipeline.md#how-to-change-deep-learning-streamer-pipeline)) it.

    ```sh
    cd [WORKDIR]/edge-ai-libraries/microservices/dlstreamer-pipeline-server/docker/    
    docker compose up
    ```
    We should see the metadata results in `/tmp/results.jsonl` file like the following snippet.

    ```sh
    {"objects":[{"detection":{"bounding_box":{"x_max":0.2760509825893678,"x_min":0.0009660996147431433,"y_max":0.5821986049413681,"y_min":0.23702500760555267},"confidence":0.8490034937858582,"label":"box","label_id":0},"h":166,"region_id":4602,"roi_type":"box","w":176,"x":1,"y":114},{"detection":{"bounding_box":{"x_max":0.18180961161851883,"x_min":0.051308222115039825,"y_max":0.4810962677001953,"y_min":0.3541457951068878},"confidence":0.7778390645980835,"label":"defect","label_id":2},"h":61,"region_id":4603,"roi_type":"defect","w":84,"x":33,"y":170}],"resolution":{"height":480,"width":640},"tags":{},"timestamp":96862470800}
    {"objects":[{"detection":{"bounding_box":{"x_max":0.2759847411653027,"x_min":0.0009118685266003013,"y_max":0.5828713774681091,"y_min":0.2364599108695984},"confidence":0.8393885493278503,"label":"box","label_id":0},"h":166,"region_id":4606,"roi_type":"box","w":176,"x":1,"y":114},{"detection":{"bounding_box":{"x_max":0.18369046971201897,"x_min":0.044871505349874496,"y_max":0.480486124753952,"y_min":0.34511199593544006},"confidence":0.7414445281028748,"label":"defect","label_id":2},"h":65,"region_id":4607,"roi_type":"defect","w":89,"x":29,"y":166}],"resolution":{"height":480,"width":640},"tags":{},"timestamp":96895871652}
    ```
    **Note** If `"auto_start"`to `"false"`, then you can start the pipeline manually by sending the curl request as shown below. In this case, curl request need not have any parameters as all the required parameters to start the pipeline is already mentioned in the pipeline config above.

    ```sh
    curl http://localhost:8080/pipelines/user_defined_pipelines/pallet_defect_detection -X POST -H 'Content-Type: application/json' -d '{}'
    ```


### Method 2 - Add REST payload under `"payload"` section of the pipeline config.

- In case you have provided placeholders in you pipeline configuration, we can also plug in the REST payload in the pipeline configuration and make use of the `auto_start` feature to start DL Streamer Pipeline Server with this pipeline with the payload provided. 

  The REST payload can be added inside a `payload` key section and the `autostart` key is then set `true`. 

  Following is a sample config with payload provided and `auto_start` set to `true`

    ```json
    {
        "config": {
            "pipelines": [
                {
                    "name": "pallet_defect_detection",
                    "source": "gstreamer",
                    "queue_maxsize": 50,
                    "pipeline": "{auto_source} name=source  ! decodebin ! videoconvert ! gvadetect name=detection ! queue ! gvawatermark ! gvafpscounter ! gvametaconvert add-empty-results=true name=metaconvert ! gvametapublish name=destination ! appsink name=appsink",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "detection-properties": {
                                    "element": {
                                    "name": "detection",
                                    "format": "element-properties"
                                    }
                            }
                        }
                    },
                    "auto_start": true,
                    "payload": {
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
                    }
                }
            ]
        }
    }
    ```

- Ensure that the changes made to the config.json are reflected in the container by volume mounting (as described [here](./how-to-change-dlstreamer-pipeline.md#how-to-change-deep-learning-streamer-pipeline)).

- Start DL Streamer Pipeline Server

    ```sh
        cd [WORKDIR]/edge-ai-libraries/microservices/dlstreamer-pipeline-server/docker/
        docker compose up
    ```
  The pipeline would start automatically as soon as DL Streamer Pipeline Server starts. 

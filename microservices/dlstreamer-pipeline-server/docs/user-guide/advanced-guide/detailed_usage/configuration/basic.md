# Basic Deep Learning Streamer Pipeline Server Configuration

DL Streamer Pipeline Server exposes multiple application related fields in the config file. The configuration file is expected to be created at **[WORKDIR]/configs/default/config.json** on your host machine.

Here is a sample of basic config file. 
    
```json
{
    "config": {
        "pipelines": [
            {
                "name": "pallet_defect_detection",
                "source": "gstreamer",
                "pipeline": "{auto_source} name=source  ! decodebin ! videoconvert ! gvadetect name=detection model-instance-id=inst0 ! queue ! gvawatermark ! gvafpscounter ! gvametaconvert add-empty-results=true name=metaconvert ! gvametapublish name=destination ! appsink name=appsink",
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
                "auto_start": false
            }
        ]
    }
}
```
The following table describes the essential attributes that are supported in the `config` section. 

|      Parameter      |                                                     Description                                                |
| :-----------------: | -------------------------------------------------------------------------------------------------------------- |
| `pipelines`         | List of DL Streamer pipelines.                                      |

The parameters applicable for each pipeline are described below.
|      Parameter      |                                                     Description                                                |
| :-----------------: | -------------------------------------------------------------------------------------------------------------- |
| `name`         | Name of the pipeline. This is used to differentiate pipeline URL in CURL command e.g. [SERVER-IP]/pipelines/user_defined_pipelines/[NAME]   |
| `pipeline`          | 	DL Streamer pipeline description. |
| `source`            | Source of the frames. This should be `"gstreamer"` or `"image-ingestor"`.                                              |
| `parameters`            | Optional JSON object specifying pipeline parameters that can be customized when the pipeline is launched |
| `auto_start`          | The Boolean flag for whether to start the pipeline on DL Streamer Pipeline Server start up. |
| `queue_maxsize`          | Optional queue size to limit the output buffer from appsink element. |
| `udfs` | UDF config parameters |

Refer [this](../../../how-to-change-dlstreamer-pipeline.md) tutorial to update config file and deploy DL Streamer Pipeline Server with updated configs. 

DL Streamer Pipeline Server pipelines are executed by GStreamer, hence to realize any usecase users will have to create their pipeline using GStreamer. Refer [GStreamer Documentation](https://gstreamer.freedesktop.org/documentation/) and [GStreamer Plugins](https://gstreamer.freedesktop.org/documentation/plugins_doc.html?gi-language=c) for detailed guidelines on constructing pipelines.


# Defining Media Analytics Pipelines
| [Pipeline Definition Files](#pipeline-definition-files) | [Pipeline Discovery](#how-pipeline-definition-files-are-discovered-and-loaded) | [Pipeline Definition](#pipeline-definition) | [Source Abstraction](#source-abstraction) | [Pipeline Parameters](#pipeline-parameters) | [Deep Learning Models](#deep-learning-models) |

Media analytics pipelines are directed graphs of audio/video
processing, computer vision, and deep learning inference
operations. The following sections explain how media analytics
pipelines are defined and loaded by Deep Learning Streamer Pipeline Server (DL Streamer Pipeline Server) .

# Pipeline Definition Files
DL Streamer Pipeline Server exposes multiple application related fields in the config file.
The default config is present at `[WORKDIR]/edge-ai-libraries/microservices/dlstreamer-pipeline-server/configs/default/config.json`.


The following table describes the essential attributes that are supported in the `config` section.

|      Parameter      |                                                     Description                                                |
| :-----------------: | -------------------------------------------------------------------------------------------------------------- |
| `pipelines`         | List of DL Streamer pipelines.                                      |

The parameters applicable for each pipeline are described below.
|      Parameter      |                                                     Description                                                |
| :-----------------: | -------------------------------------------------------------------------------------------------------------- |
| `name`         | Name of the pipeline.                                      |
| `pipeline`          | 	DL Streamer pipeline description. |
| `source`            | Source of the frames. This should be `"gstreamer"` or `"image-ingestor"`.                                              |
| `parameters`            | Optional JSON object specifying pipeline parameters that can be customized when the pipeline is launched |
| `auto_start`          | The Boolean flag for whether to start the pipeline on DL Streamer Pipeline Server start up. |
| `udfs` | UDF config parameters |


## How Pipeline Definition Files are Discovered and Loaded

Pipeline definition files are created from `config.json` and are stored in a hierarchical directory structure that determines their name and version. The `config.json` file is present inside the DL Streamer Pipeline Server container image. After startup, DL Streamer Pipeline Server searches the configured pipeline directory and loads all pipeline definitions that are found.

The hierarchical directory structure looks like the below inside the DL Streamer Pipeline Server container image:
`/var/cache/pipeline_root/user_defined_pipelines/<pipeline-name>/pipeline.json`

Here is a sample directory listing:
```
/var/cache/pipeline_root
                ├── user_defined_pipelines
                │   └── pallet_defect_detection
                │       └── pipeline.json
```

> **Note:** While not required, pipeline definition files are named
> `pipeline.json` by convention.


## Pipeline Definition
The pipeline property within a `config.json` file describes the order
and type of operations in the media analytics pipeline. The syntax of
the template property is specific to the underlying framework
i.e. `GStreamer`. Pipeline use the `source`,
`destination` and `parameters` sections of an incoming pipeline
`request` to customize the source, destination and behavior of a
pipeline implemented in an underlying framework.

### GStreamer Pipeline Definition

> **Note:** This section assumes an understanding of the GStreamer
> framework.


GStreamer templates use the [GStreamer Pipeline
Description](https://gstreamer.freedesktop.org/documentation/tools/gst-launch.html?gi-language=c#pipeline-description)
syntax to concatenate elements into a pipeline. The Pipeline Server `pipeline_manager` and `gstreamer_pipeline` modules
parse the template, configure the `source`, `destination`, and
`appsink` elements and then construct the pipeline based on incoming
requests.

The `source`, `destination` and `appsink` elements in a pipeline template
intentionally avoid assigning explicit media source and destination
properties. This enables the properties to be dynamically defined by
the calling application.

#### Object Detection
**Example:**
```
"pipeline": "uridecodebin name=source",
            " ! gvadetect model={models[person_vehicle_bike_detection][1][network]} name=detection",
            " ! gvametaconvert name=metaconvert ! gvametapublish name=destination",
            " ! appsink name=appsink"
```
Note: The model used in the above pipeline is an example of how it can be used from [here](https://github.com/open-edge-platform/dlstreamer/blob/master/docs/source/supported_models.md). Please refer to the documentation for DL Streamer on how to download any given model for your usage [here](https://github.com/open-edge-platform/dlstreamer/blob/master/docs/source/dev_guide/model_preparation.md).

#### Source Abstraction
`{auto_source}` is a virtual source that is updated with the appropriate GStreamer element and properties at request time.
The GStreamer element is chosen based on the `type` specified in the source section of the request (shown below), making pipelines flexible as they can be reused for source media of different types.

**Sample video pipeline**
```
"pipeline": "{auto_source}",
            " ! gvadetect model={models[person_vehicle_bike_detection][1][network]} name=detection",
            " ! gvametaconvert name=metaconvert ! gvametapublish name=destination",
            " ! appsink name=appsink"
```
Note: The model used in the above pipeline is an example of how it can be used from [here](https://github.com/open-edge-platform/dlstreamer/blob/master/docs/source/supported_models.md). Please refer the documentation from DL Streamer on how to download any given model for your usage [here](https://github.com/open-edge-platform/dlstreamer/blob/master/docs/source/dev_guide/model_preparation.md).

**Sample audio pipeline**
```
"pipeline": "{auto_source} ! audioresample ! audioconvert",
            " ! audio/x-raw, channels=1,format=S16LE,rate=16000 ! audiomixer name=audiomixer",
            " ! level name=level",
            " ! gvaaudiodetect model={models[audio_detection][environment][network]} name=detection",
            " ! gvametaconvert name=metaconvert ! gvametapublish name=destination",
            " ! appsink name=appsink"
```
Note: The model used in the above pipeline is an example of how it can be used from [here](https://github.com/open-edge-platform/dlstreamer/blob/master/docs/source/supported_models.md). Please refer the documentation from DL Streamer on how to download any given model for your usage [here](https://github.com/open-edge-platform/dlstreamer/blob/master/docs/source/dev_guide/model_preparation.md).


|    Source    |    GStreamer Element     |      Source section of curl request       |        Source pipeline snippet     | Remarks |
| :----------: |  :---------------------: | ----------------------------------------- | ---------------------------------- |---------|
| Application  | `appsrc`	                  | N/A	                                | N/A                           |         |
| File | `urisourcebin`	| <pre>"source": {<br>  "uri": "file://path",<br>  "type": "uri"<br>}<br></pre> | <pre>`urisourcebin` uri=file://path name=source</pre> |         |
| RTSP | `urisourcebin`	| <pre> "source": { <br>  "uri": "rtsp://url",<br>   "type": "uri"<br> }<br></pre> | <pre> `urisourcebin` uri=rtsp://url name=source</pre> |         |
| URL | `urisourcebin`	| <pre> "source": { <br>  "uri": "https://url",<br>   "type": "uri"<br> }<br></pre> | <pre> `urisourcebin` uri=https://url name=source </pre> | If you are behind proxy, make sure to set proxy as below in docker compose file for this URLs to work <pre> `http_proxy=http://proxy.example.com:123` <br> `https_proxy=http://proxy.example.com:123`  </pre>  |
| Web camera | `urisourcebin`	| <pre> "source": { <br>   `"device": "/dev/video0`",<br>   type": "webcam",<br> }<br></pre> | <pre> `v4l2src device=/dev/video0` name=source ! `video/x-raw,format=YUY2` </pre> |         |
| Custom GStreamer Element | `urisourcebin`	| <pre> "source": { <br>   "element": GStreamer Element name,<br>   "type": "gst"<br> }<br></pre> Example for microphone for an audio pipeline: <br> <pre> "source": { <br>   "element": `"alsasrc"`,<br>   "type": "gst",<br>   properties": { <br>        `"device": "hw:1,0"` <br>}<br></pre> | <pre> `alsasrc device=hw:1,0 name=source`</pre> |         |

> Note: For request of `type=gst`, the container must support the corresponding element.

Source request accepts the following optional fields set via the request:
- `capsfilter` if set is applied right after the source element as shown in example below.
  The default value of capsfilter for webcam is `image/jpeg` but it can be set via the request to another valid format.
  ```json
    "source": {
        "device": "/dev/video0",
        "type": "webcam",
        "capsfilter": "video/x-h264"
    }
  ```
  The source pipeline resolves to:
  ```
  v4l2src device=/dev/video0 name=source ! capsfilter caps=video/x-h264 ! ..
  ```
- `postproc` if set is applied _after_ the source and capsfilter element (if specified).
  Below is an example of the use of `capsfilter` and `postproc`
  ```json
    "source": {
        "element": "videotestsrc",
        "type": "gst",
        "capsfilter": "video/x-raw,format=GRAY8",
        "postproc": "rawvideoparse",
        "properties": {
            "pattern": "snow"
        }
    }
  ```
    The source pipeline resolves to:
  ```
  videotestsrc name=source ! capsfilter caps=video/x-raw,format=GRAY8 ! rawvideoparse ! ..
  ```

#### Element Names

Each element in a GStreamer pipeline has a name that is either
generated automatically or set by using the standard element property:
`name`. Using the `name` property in a template creates an explicit
alias for the element that can then be used in the `parameters`
section of a pipeline definition. More details on parameters can be
found in the [Pipeline Parameters](#pipeline-parameters) section.

Certain element names also trigger special default handling by the
Pipeline Server modules. For example in the `object_detection/person_vehicle_bike`
sample template the special element name `source` results in the
`urisourcebin`'s `uri` property getting automatically set to the
source uri of an incoming request.

#### Element Properties

Each element in a GStreamer pipeline can be configured through its
set of properties.

The `object_detection/person_vehicle_bike` template demonstrates how to set the
`gvadetect` element's properties to select the deep learning model
used to detect objects in a video frame.

```
gvadetect model={models[person_vehicle_bike_detection][1][network]} model-proc={models[person_vehicle_bike_detection][1][proc]} name=detection
```

The `model` and `model-proc` properties reference file paths to the
deep learning model as discovered and populated by the Pipeline Server `model_manager` module. The `model_manager` module provides a
python dictionary associating model names and versions to their
absolute paths enabling pipeline templates to reference them by
name. You can use the `model-proc` property to point to custom model-proc by specifying absolute path. More details are provided in the [Deep Learning Models](#deep-learning-models) section.

#### Model Persistance in OpenVINO<sup>&#8482;</sup> GStreamer Elements

`model-instance-id` is an optional property that will hold the model in memory instead
of releasing it when the pipeline completes. This improves load time and reduces memory
usage when launching the same pipeline multiple times. The model is associated
with the given ID to allow subsequent runs to use the same model instance.

It's important to be careful when using this property when running pipelines across
multiple hardware targets as models are loaded for a specific device. For
example, if a model is loaded on the CPU and is given an instance ID of 'inf0',
then that ID must not be used to run the model on the GPU. The same caveat applies to the video formats. The model will be set to the initial image format (e.g. RGBx) during the first pipeline run and any subsequent pipeline runs will error if the image formats differs (e.g a YV12).

When using a pipeline with elements that target different accelerators, the model-instance-id
property must be parameterized so that a unique id can be provided for each
accelerator. As an example if you have different detection and classification models,
they must have different parameter names so that the Pipeline Server can distinguish between them.
Here is a pipeline definition snippet showing `model-instance-id` properties of `gvadetect` and `gvaclassify` elements mapped to parameters `detection-model-instance-id` and `classification-model-instance-id` respectively.

```
    "detection-model-instance-id": {
        "element": {
            "name": "detection",
            "property": "model-instance-id"
        },
        "type": "string"
    },
    "classification-model-instance-id": {
        "element": {
            "name": "classification",
            "property": "model-instance-id"
        },
        "type": "string"
    }
```

Different pipelines may share the same value for `model-instance-id` as long as
the model is the same across all instances using the assigned id, and
targets the same hardware device and video format.

#### More Information

For more information and examples of media analytics pipelines created
with DL Streamer please see the [tutorial](https://github.com/open-edge-platform/dlstreamer/blob/master/docs/source/get_started/tutorial.md).

## Pipeline Parameters

Pipeline parameters enable developers to customize pipelines based on
incoming requests. Parameters are an optional section within a
pipeline definition and are used to specify which pipeline properties
are configurable and what values are valid. Developers can also
specify default values for each parameter or set to read from environment variable.

### Defining Parameters as JSON Schema

The `parameters` section in a pipeline definition provides the JSON
schema used to validate the `parameters` in a request. It can also
provide details on how those parameters are interpreted by the
`gstreamer_pipeline` or `ffmpeg_pipeline` modules.

The `parameters` section of a pipeline request is a JSON object. The
`parameters` section of a pipeline definition is the JSON schema for
that JSON object. For more details on JSON schemas please refer to JSON schema
[documentation](https://json-schema.org/understanding-json-schema/reference/object.html).


**Example:**

The following `parameters` section contains two parameters: `height`
and `width`:

```json
"parameters": {
    "type": "object",
    "properties": {
        "height": {
            "type": "integer",
            "minimum": 200,
            "maximum": 400,
            "default": 200
        },
        "width": {
            "type": "integer",
            "minimum": 400,
            "maximum": 600,
            "default": 400
        }
    }
}
```

Once defined these parameters can be used in a pipeline template by
direct substitution.

```json
"pipeline": " urisourcebin name=source ! concat name=c ! decodebin ! videoscale",
                " ! video/x-raw,height={parameters[height]},width={parameters[width]}",
                " ! appsink name=appsink"
```


### Special Handling for Media Frameworks

In addition to specifying the `type`, `default` and `allowed values`
in JSON schema notation, pipeline parameters can also include
properties that determine how they are interpreted by media analytics
frameworks.

#### Parameters and GStreamer Elements

Parameters in GStreamer pipeline definitions can include information
on how to associate a parameter with one or more GStreamer element
properties.

The JSON schema for a GStreamer pipeline parameter can include an
`element` section in one of the below forms.

1. **Simple String**. <br/> <br/>
   The string indicates the `name` of an element in
   the GStreamer pipeline. The property to be set is taken from the
   parameter name.

   **Example:**

   The following snippet defines the parameter `inference-interval`
   which sets the `inference-interval` property of the `detection`
   element.

   ```json
   "parameters": {
   "type": "object",
   "properties": {
        "inference-interval": {
            "element": "detection",
            "type": "integer",
            "minimum": 0,
            "maximum": 4294967295,
            "default": 1
            }
        }
    }
    ```

1. **Object**. <br/> <br/> The object indicates the element `name`,
   `property` and `format` for the parameter. The `format` is only
   required in special cases where the property value has to be
   formatted as a valid JSON document.

   **Example:**

   The following snippet defines the parameter `interval`
   which sets the `inference-interval` property of the `detection`
   element.

   ```json
   "parameters": {
   "type": "object",
   "properties": {
        "interval": {
            "element": {
                "name":"detection",
                "property":"inference-interval"
            },
            "type": "integer",
            "minimum": 0,
            "maximum": 4294967295,
            "default": 1
            }
        }
    }
    ```

1. **Array** of Objects or Strings. <br/> <br/> An array specifying
   multiple element properties to be set by the same pipeline
   parameter.

   **Example:**

   The following snippet defines the parameter `interval` which sets
   the `inference-interval` property of the `detection` element and
   the `inference-interval` property of the `classification` element.

   ```json
   "parameters": {
   "type": "object",
   "properties": {
        "interval": {
            "element":
                [ {"name":"detection",
                    "property":"inference-interval"},
                  {"name":"classification",
                   "property":"inference-interval"}
                ],
            "type": "integer",
            "minimum": 0,
            "maximum": 4294967295,
            "default": 1
            }
        }
    }
    ```

1. **Object** with dictionary of properties. <br/> <br/> A dictionary specifying properties that apply to a pipeline element by name.

    **Example:**

    The following snippet defines `detection-properties` which can be used to pass
    GStreamer element properties for the `detection` element without explicitly defining each one. This can be enabled by setting `format` as `element-properties` for the parameter.
    > **Note:** The property names are expected to match the GStreamer properties for the corresponding element.

    ```json
    "parameters": {
            "type": "object",
            "detection-properties" : {
                "element": {
                    "name": "detection",
                    "format": "element-properties"
                }
            }
    }
    ```

    Pipeline Request
    ```json
    "source": {
        "uri":"file:///temp.mp4",
        "type": "uri"
    },
    "parameters" : {
        "detection-properties": {
            "threshold": 0.1,
            "device": "CPU"
        }
    }
    ```

#### Parameters and default value

Parameters default value in pipeline definitions can be set in section in one of two forms(setting value or by environment variable) below.

1. **Set default value directly**

    A default value can be set for the element property using `default` key.

   **Example:**

   The following snippet defines the parameter `detection-device`
   which sets the `device` property of `detection` with default value `GPU`

   ```json
   "parameters": {
   "type": "object",
   "properties": {
        "detection-device": {
            "element": {
                "name":"detection",
                "property":"device"
            },
            "type": "string",
            "default": "GPU"
            }
        }
    }
    ```

2. **Read default value from environment variable**

    A default value can be set using environment variable for the element property using `default` key.

   **Example:**

   The following snippet defines the parameter `detection-device`
   which sets the `device` property of the `detection` with default value from environment variable `DETECTION_DEVICE`. If the environment variable is not set, pipeline server won't set a default and the element's built-in default will be used by the underlying framework.

   ```json
   "parameters": {
   "type": "object",
   "properties": {
        "detection-device": {
            "element": {
                "name":"detection",
                "property":"device"
            },
            "type": "string",
            "default": "{env[DETECTION_DEVICE]}"
            }
        }
    }
    ```


#### Parameters and FFmpeg Filters

Parameters in FFmpeg pipeline definitions can include information on
how to associate a parameter with one or more FFmpeg filters.

The JSON schema for a FFmpeg pipeline parameter can include a
`filter` section in one of two forms.

1. **Object**. <br/> <br/> The object indicates the filter `name`,
   `type`, `property`, `index` and `format` for the parameter. The
   `format` is only required in special cases where the property value
   has to be formatted as a valid JSON document.

   **Example:**

   The following snippet defines the parameter `inference-interval` which sets
   the `interval` property of the first `detect` filter.

   ```json
   "parameters": {
   "type": "object",
   "properties": {
        "inference-interval": {
            "filter": {"name":"detect",
                       "type":"video",
                       "index":0,
                       "property":"interval"},
            "type": "integer",
            "minimum": 0,
            "maximum": 4294967295,
            "default": 1
            }
        }
    }
    ```

1. **Array** of Objects. <br/> <br/> An array specifying
   multiple filter properties to be set by the same pipeline
   parameter.

   **Example:**

   The following snippet defines the parameter `interval` which sets
   the `interval` property of the `detect` filter and
   the `interval` property of the `classify` filter.

   ```json
   "parameters": {
   "type": "object",
   "properties": {
        "inference-interval": {
            "filter":[ {"name":"detect",
                        "type":"video",
                        "index":0,
                        "property":"interval"},
                       {"name":"classify",
                        "type":"video",
                        "index":0,
                        "property":"interval"}
                     ],
            "type": "integer",
            "minimum": 0,
            "maximum": 4294967295,
            "default": 1
            }
        }
    }
    ```

### Parameter Resolution in Pipeline Templates

Parameters passed in through a request are resolved in a pipeline
template either through direct substitution or through special media
framework handling.

#### Direct Substitution

Wherever a value in a pipeline template is referenced through a key in
the parameters object its value is taken from the incoming request. If not
supplied in the request it is set to the specified default value.

**Example:**

Pipeline Template:

```json
"pipeline": "urisourcebin name=source uri={source[uri]} ! concat name=c ! decodebin ! videoscale"
             " ! video/x-raw,height={parameters[height]},width={parameters[width]}"
             " ! appsink name=appsink"
```

Pipeline Parameters:
```json
"parameters": {
    "type": "object",
    "properties": {
        "height": {
            "type": "integer",
            "minimum": 200,
            "maximum": 400,
            "default": 200
        },
        "width": {
            "type": "integer",
            "minimum": 400,
            "maximum": 600,
            "default": 400
        }
     }
 }
```

Pipeline Request:
```json
{
  "source": {
   "type":"uri",
   "uri":"file:///temp.mp4"
  },
  "parameters": {
    "height":300,
    "width":300
  }
}
```

Parameter Resolution:

```
"urisourcebin name=source uri=file:///temp.mp4 ! concat name=c ! decodebin ! videoscale" \
" ! video/x-raw,height=300,width=300" \
" ! appsink name=appsink"
```


#### Media Framework Handling
When a parameter definition contains details on how to set GStreamer
`element` or FFmpeg `filter` properties, templates do not need to
explicitly reference the parameter.

**Example:**

Pipeline Template:

```json
"pipeline": "urisourcebin name=source ! concat name=c ! decodebin ! videoscale"
             " ! video/x-raw,height=300,width=300"
             " ! appsink name=appsink"
```

Pipeline Parameters:
```json
"parameters": {
    "type": "object",
    "properties": {
        "scale_method": {
            "type": "string",
            "element": {
                "name": "videoscale",
                "property": "method"
            },
            "enum": ["nearest-neighbour","bilinear"],
            "default": "bilinear"
        }
    }
}
```

Pipeline Request:
```json
{
 "source": {
  "type":"uri",
  "uri":"file:///temp.mp4"
 },
 "parameters": {
   "scale_method":"nearest-neighbour"
 }
}
```

Parameter Resolution:

> **Note:** Parameters defined this way are set via the GStreamer
> Python API. The following pipeline string is provided for
> illustrative purposes only.

```
"urisourcebin name=source uri=file:///temp.mp4 ! concat name=c ! decodebin ! videoscale method=nearest-neighbour" \
" ! video/x-raw,height=300,width=300" \
" ! appsink name=appsink"
```
### Reserved Parameters

The following parameters have built-in handling within the Pipeline Server modules and should only be included in pipeline
definitions wishing to trigger that handling.

#### bus-messages

A boolean parameter that can be included in GStreamer pipeline
definitions to trigger additional logging for GStreamer bus messages.

If included and set to true, GStreamer bus messages will be logged
with log-level `info`. This is useful for elements which post messages
to the bus such as
[level](https://gstreamer.freedesktop.org/documentation/level/index.html?gi-language=c).

**Example:**

```json
"parameters": {
      "type": "object",
      "properties": {
              "bus-messages": {
              "type": "boolean",
              "default": true
      }
    }
}
```


# Deep Learning Models

## OpenVINO<sup>&#8482;</sup> Toolkit's Intermediate Representation

The Pipeline Server applications and pipelines use deep learning
models in the OpenVINO<sup>&#8482;</sup> Toolkit's [Intermediate
Representation](https://docs.openvino.ai/2025/documentation/openvino-ir-format.html)
format (`IR`). A model in the `IR` format is represented by two files:

* `<model_name>.xml`. An XML file describing the model layers,
  precision and topology.

* `<model_name>.bin`. A binary file encoding a trained model's weights.

### Converting Models
For more information on converting models from popular frameworks into
`IR` format please see the OpenVINO<sup>&#8482;</sup> Toolkit
documentation for [model optimizer](https://docs.openvino.ai/2025/openvino-workflow/model-optimization.html).

### Ready To Use Models

For more information on ready to use deep learning models that have
been converted into the IR format (or include conversion instructions)
please see the the OpenVINO<sup>&#8482;</sup> Toolkit documentation
for
[model_downloader](https://docs.openvino.ai/2023.3/omz_tools_downloader.html)
and the OpenVINO<sup>&#8482;</sup> Toolkit [Open Model
Zoo](https://github.com/openvinotoolkit/open_model_zoo).

## Model-Proc Files

In addition to the `.xml` and `.bin` files that are part of a model's
`IR` format, `DL Streamer` elements and `FFmpeg Video Analytics`
filters make use of an additional JSON file specifying the input and
output processing instructions for a model. Processing instructions
include details such as the expected color format and resolution of
the input as well labels to associate with a models outputs.
The Pipeline Server automatically looks for this file in the path
`models/model-alias/model-version/*.json`. Note that the model manager will
fail to load if there are multiple ".json" model-proc files in this directory.

Some models might have a separate `.txt` file for `labels`, in addition to or instead of `model-proc`.
If such a file exists, the Pipeline Server automatically looks for this file in the path
`models/model-alias/model-version/*.txt`.

For more details on model proc and labels see [Model Proc File](https://github.com/open-edge-platform/dlstreamer/blob/master/docs/source/dev_guide/model_proc_file.md).

### Deep Learning Streamer (DL Streamer)
For more information on DL Streamer `model-proc` files and samples for
common models please see the DL Streamer
[documentation](https://github.com/open-edge-platform/dlstreamer/blob/master/docs/source/dev_guide/how_to_create_model_proc_file.md#how-to-create-model-proc-file).
and
[samples](https://github.com/dlstreamer/dlstreamer/tree/master/samples).

### FFmpeg Video Analytics
For `model-proc` files for use with `FFmpeg Video Analytics` please
see the following [samples](https://github.com/VCDP/FFmpeg-patch/tree/ffmpeg4.2_va/samples/model_proc)

## How Deep Learning Models are Discovered and Referenced

Model files are stored in a hierarchical directory structure that
determines their name, version and precision.

On startup, the Pipeline Server `model_manager` searches
the configured model directory and creates a dictionary storing the
location of each model and their associated collateral
(i.e. `<model-name>.bin`, `<model-name>.xml`, `<model-name>.json`, `<labels>.txt`)

The hierarchical directory structure is made up of four levels:

`<model-root-directory>/<model-name>/<version>/<precision>`

> Note: Not all models have a file for labels. In such cases, the labels could be listed in the `model-proc`file.

Here's a sample directory listing for the `yolo-v3-tf` model:
Note: The mentioned model is available [here](https://github.com/open-edge-platform/dlstreamer/blob/master/docs/source/supported_models.md).

```
models/
└── object_detection                // name
    ├── 1                           // version
    │   ├── yolo-v3-tf.json         // proc file
    │   ├── coco-80cl.txt           // labels file
    │   ├── FP16                    // precision
    │   │   ├── yolo-v3-tf.bin      // bin file
    │   │   ├── yolo-v3-tf.mapping
    │   │   └── yolo-v3-tf.xml      // network file
    │   ├── FP32
    │   │   ├── yolo-v3-tf.bin
    │   │   ├── yolo-v3-tf.mapping
    │   │   └── yolo-v3-tf.xml
```


## Referencing Models in Pipeline Definitions

Pipeline definitions reference models in their templates in a similar
way to how they reference parameters. Instead of being resolved by
values passed into the pipeline by a request, model paths are resolved
by passing in a dictionary containing information for all models that
have been discovered by the `model_manager` module.

Pipeline templates refer to specific model files using a nested
dictionary and standard Python dictionary indexing with the following
hierarchy: `models[model-name][version][precision][file-type]`.

The default precision for a given model and inference device
(`CPU`:`FP32`,`HDDL`:`FP16`,`GPU`:`FP16`,`VPU`:`FP16`,`MYRIAD`:`FP16`,
`MULTI`:`FP16`,`HETERO`:`FP16`,`AUTO`:`FP16`) can also be referenced
without specifying the precision:
`models[model-name][version][file-type]`.

**Examples:**

* `models[object_detection][1][proc]` expands to `models/object_detection/1/yolo-v3-tf.json`
* `models[object_detection][1][labels]` expands to `models/object_detection/1/coco-80cl.txt`
* If running on CPU `models[object_detection][1][network]` expands to `models/object_detection/1/FP32/yolo-v3-tf.xml`
* Running on GPU `models[object_detection][1][network]` expands to `models/object_detection/1/FP16/yolo-v3-tf.xml`
* `models[object_detection][1][FP16][network]` expands to `models/object_detection/1/FP16/yolo-v3-tf.xml`

---
\* Other names and brands may be claimed as the property of others.

# REST Endpoints Reference Guide

## RESTful Endpoints

The RESTful API has a default maximum body size of 10 KB, this can be changed by setting the environment variable MAX_BODY_SIZE in bytes.

| Path | Description |
|----|------|
| [`GET` /pipelines](#get-pipelines) | Return supported pipelines. |
| [`GET` /pipelines/status](#get-pipelinesstatus) | Return status of all pipeline instances. |
| [`GET` /pipelines/{instance_id}/status](#get-pipelinesinstance_idstatus) | Return status of a pipeline instance. |
| [`POST` /pipelines/{name}/{version}](#post-pipelinesnameversion) | Start new pipeline instance. |
| [`GET` /pipelines/{instance_id}](#get-pipelinesinstance_id) | Return pipeline instance summary. |
| [`POST` /pipelines/{name}/{version}/{instance_id}](#post-pipelinesnameversioninstance_id) | Send request to an already queued pipeline. Supported only for source of type "image_ingestor". |
| [`DELETE` /pipelines/{instance_id}](#delete-pipelinesinstance_id) | Stops a running pipeline or cancels a queued pipeline. |
| [`POST` /pipelines/{name}/{version}/{instance_id}/models](#post-pipelinesnameversioninstance_idmodels) | Download files from the model registry microservice associated with a specific model and deploy it in pipeline. |

### `GET` /pipelines

Return supported pipelines

#### Responses

#####   200 - Success
###### application/json
##### Example _(generated)_

```json
[
  {
    "description": "description",
    "type": "GStreamer",
    "parameters": {
      "key": {
        "default": ""
      }
    }
  }
]
```


### `GET` /pipelines/status

Return status of all pipeline instances.

#### Responses

#####   200 - Success
###### application/json
##### Example _(generated)_

```json
[
{
"id": 1,
"state": "COMPLETED",
"avg_fps": 8.932587737800183,
"start_time": 1638179813.2005367,
"elapsed_time": 72.43142008781433,
"message": "",
"avg_pipeline_latency": 0.4533823041311556
},
{
"id": 2,
"state": "RUNNING",
"avg_fps": 6.366260838099841,
"start_time": 1638179886.3203313,
"elapsed_time": 16.493194580078125,
"message": "",
"avg_pipeline_latency": 0.6517487730298723
},
{
"id": 3,
"state": "ERROR",
"avg_fps": 0,
"start_time": null,
"elapsed_time": null,
"message": "Not Found (404), URL: https://github.com/intel-iot-devkit/sample.mp4, Redirect to: (NULL)"
}
]
```

### `GET` /pipelines/{instance_id}/status
Returns status of a particular instance.

#### Responses

#####   200 - Success
###### application/json
##### Example _(generated)_

```json
{
"id": 1,
"state": "COMPLETED",
"avg_fps": 8.932587737800183,
"start_time": 1638179813.2005367,
"elapsed_time": 72.43142008781433,
"message": "",
"avg_pipeline_latency": 0.4533823041311556
}
```

### `POST` /pipelines/{name}/{version}

Start new pipeline instance. Four sections are supported by default: source, destination, parameters, and tags. These sections have special handling based the schema defined in the pipeline.json file for the requested pipeline.


#### Path parameters

##### name

Name: name(required)
Type: string
In: path
Accepted values: any

##### version

Name: version(required)
Type: string
In: path
Accepted values: any


#### Request body

##### Example


```json
{
  "sync": false,
  "source": {
    "type": "uri",
    "uri": "file:///root/video-examples/example.mp4"
  },
  "destination":{},
  "parameters": {},
  "tags": {}
}
```

#### Responses

#####   200 - Success


### `DELETE` /pipelines/{instance_id}

Stop pipeline instance.


#### Path parameters

##### instance_id

Name: instance_id(required)
Type: string
In: path
Accepted values: any

#### Responses

#####   200 - Success


### `POST` /pipelines/{name}/{version}/{instance_id}

Send request to an already queued pipeline. Supported only for pipelines with `source` - `image_ingestor`. 

The request can be synchronous or asynchronous depending upon whether the `sync` flag was set to `false`(default) or `true` when the pipeline was queued. See [here](#get-pipelinesinstance_id)

#### Synchronous behavior
By default, the pipeline is queued in asynchronous mode i.e. `sync`: `false`. For a queued pipeline operating in asynchronous mode, requests are processed in the background and an immediate response is sent indicating that the operation is underway. The pipeline stores the results in the destination defined via the `POST /pipelines/{name}/{version}/` endpoint. However, if `sync` is set to `true`, the REST request is blocked until the response comes back with the data or if a timeout occurs. The latter case will respond with an error message that the timeout has occurred. By default, the timeout is 2 seconds, but can be set to a different value as per your use case.


#### Path parameters

##### name

Name: name(required)
Type: string
In: path
Accepted values: any

##### version

Name: version(required)
Type: string
In: path
Accepted values: any

##### instance_id

Name: instance_id(required)
Type: string
In: path
Accepted values: any


#### Request body

- `source`: file or image source. 
  - `type`: `file` or `base64_image`. Must be an accessible file path or **base64** encoded image blob.
  - `path`: path for `file` source type.
  - `data`: base64 encoded image blob for `base64_image` source type.
- `publish_frame`: Optional, defaults to `false`, If set to true, it would send base64 encoded image frames.
- `timeout`: Optional, int. Applicable only in synchronous execution where the timeout value(in sec) decides until when the request is blocked if the data has not arrived already.
- `destination`: Optional
- `parameters`: Optional. Pipeline specific runtime parameters.
- `custom_meta_data`: Optional. custom meta data to be appended in metadata.

##### Example


```json
{
  "source": {
    "type": "file",
    "path": "file:///root/image-examples/example.png"
  },
  "destination":{},
  "parameters": {},
  "publish_frame": true
  "custom_meta_data": {"my_id":100, "series_name":"DLStreamerPipelineServer1"}
}
```
#### Responses

#####   200 - Success

###### application/json

##### Example
```text
{
  "metadata": {
    "height": 480,
    "width": 820,
    "channels": 4,
    "source_path": "file:///root/image-examples/example.png",
    "caps": "video/x-raw, width=(int)820, height=(int)468",
    ...
        
        <other pipeline metadata>
        
    ...
  },
  "blobs": "=8HJLhxhj77XHMHxilNKjbjhBbnkjkjBhbjLnjbKJ80n0090u9lmlnBJoiGjJKBK=76788GhjbhjK"
}
```

### `POST` /pipelines/{name}/{version}/{instance_id}/models

Download files from the model registry microservice associated with a specific model and deploy the newly downloaded model in the pipeline.
- Properties are supported: `name` (string), `project_name` (string), `version` (string), `category` (string), `architecture` (string), `precision` (string), `deploy` (boolean), and  `pipeline_element_name`(string). These properties allow DL Streamer Pipeline Server to query for a model stored in the model registry microservice. 
- If `deploy` is set to `true`, the specified pipeline instance will be stopped and a new instance will be started using the downloaded model. The default value for `deploy` is `false`. 
- When `deploy` is set to true, `pipeline_element_name` should be provided to update the newly downloaded model for this element in the pipeline. For example, if pipeline has `gvadetect name=detection`, `pipeline_element_name` would be `detection`.
- If a response from the model registry microservice is not received within 300 seconds by default, this request will time out and return a relevant response.  


#### Path parameters

##### name

Name: name(required)
Type: string
In: path
Accepted values: any

##### version

Name: version(required)
Type: string
In: path
Accepted values: any

##### instance_id

Name: instance_id(required)
Type: string
In: path
Accepted values: any

#### Request body

##### Example 1
Download model: 

If the user is aware that there is only one model in model registry with a given name then user can provide only `name` in the request body to retrieve the model from the registry.
```json
{
    "name": "PalletDetection_YOLO_v1",
}
```

Other model properties can be provided to retrieve a specific model the model registry.

```json
{
    "project_name": "pallet-detection",
    "version": "v1",
    "category": "Detection",
    "architecture": "YOLO",
    "precision": "FP16"
}
```
##### Example 2
Download/Update model: 

Along with model properties, `deploy` and `pipeline_element_name` should be provided to download the model and restart the pipeline with the newly download model set for the specific pipeline element.
```json
{
    "project_name": "pallet-detection",
    "version": "v2",
    "category": "Detection",
    "architecture": "YOLO",
    "precision": "FP16",
    "deploy": true,
    "pipeline_element_name": "detection"
}
```

#### Responses

#####   200 - Success

### `GET` /pipelines/{instance_id}

Return pipeline instance summary.


#### Path parameters

##### instance_id

Name: instance_id(required)
Type: string
In: path
Accepted values: any

#### Responses

#####   200 - Success

###### application/json

##### Example
```json
{
  "id": 0,
  "launch_command": "",
  "name": "",
  "request": {
    "destination": {},
    "source": {},
    "parameters": {},
    "tags": {}
  },
  "type": "type",
  "version": ""
}
```
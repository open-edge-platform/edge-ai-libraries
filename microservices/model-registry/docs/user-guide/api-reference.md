# API Reference
**Version: 1.0.2**

## Introduction
The Model Registry microservice offers a robust suite of endpoints designed to manage machine learning models within a locally deployed environment.

Additionally, this microservice allows users to access metadata for Intel® Geti hosted resources, such as projects and models.

It also facilitates the storage of models, making them readily available for downstream applications and services.

## Endpoints

### /health

#### GET

##### Description:

Get the health status of the service.

##### Responses

| Code | Description |
| ---- | ----------- |
| 200 | Successful Response |

**200 - Successful Response**
```json
{
    "status": "string"
}
```

### /models

#### GET

##### Description:

Get all registered model(s).

##### Request Parameters

| Name | Located in | Description | Required | Schema |
| ---- | ---------- | ----------- | -------- | ---- |
| name | query |  | No |  |
| project_name | query |  | No |  |
| category | query |  | No |  |
| version | query |  | No |  |
| architecture | query |  | No |  |
| precision | query |  | No |  |

##### Responses

| Code | Description |
| ---- | ----------- |
| 200 | Successful Response |
| 422 | Validation Error |

**200 - Successful Response**
```json
[
  {
    "id": "string",
    "name": "string",
    "target_device": "string",
    "created_date": "string",
    "last_updated_date": "string",
    "precision": [
      "string"
    ],
    "size": 0,
    "version": "string",
    "format": "string",
    "origin": "string",
    "file_url": "string",
    "project_id": "string",
    "project_name": "string",
    "category": "string",
    "target_device_type": "string",
    "score": 0,
    "overview": "string",
    "optimization_capabilities": "string",
    "labels": [
      "string"
    ],
    "architecture": "string"
  }
]
```

**422 - Validation Error**
```json
{
  "detail": [
    {
      "loc": [
        "string",
        0
      ],
      "msg": "string",
      "type": "string"
    }
  ]
}
```

#### POST

##### Description:

Store the metadata and artifacts for a model.

##### Request Body
| Name | Type | Located in | Description | Required | Schema |
|---|---|---|---|---|---|
| file | string($binary) | Body | The ZIP file containing model files and related artifacts. | Yes |  |
| name | string | Body | The human-readable name of the model. | Yes |  |
| version | string | Body | The version of the model (e.g., 1.0, 1A, v2). | Yes |  |
| target_device | string | Body | The hardware platform the model is designed to run on (e.g., CPU, GPU, FPGA). | No |  |
| precision | string | Body | The precision of the model (e.g., FP32, FP16, INT8, INT4). Defaults to FP32. | No |  |
| format | string | Body | The format of the model (e.g. openvino, pytorch). | No |  |
| score | number | Body | A metric that represents the model's performance. | No |  |
| id | string | Body | A unique identifier for the model. | No |  |
| created_date | string | Body | The date and time the model was first created or trained. If empty, this will be the date and time the model was registered.(e.g. 2024-02-28 15:39:07.054000) | No |  |
| size | integer | Body | The storage space occupied by the model files (e.g., in bytes). | No |  |
| origin | string | Body | The source of the model (e.g., geti), or where it was obtained from. | No |  |
| project_id | string | Body | The unique identifier of the project the model belongs to, if applicable. | No |  |
| project_name | string | Body | The human-readable name of the project the model belongs to, if applicable. | No |  |
| category | string | Body | The category associated to the labels used by the model (e.g. Detection, Classification, etc.). | No |  |
| target_device_type | string | Body | A more specific categorization of the target device (e.g., client, edge, cloud). | No |  |
| overview | string | Body | A general description of the model's purpose, function, and intended use cases. (e.g. {"description":"The description of the model"}) | No |  |
| optimization_capabilities | string | Body | If applicable, information about any specific optimizations made to the model, such as for speed, accuracy, or size reduction. | No |  |
| labels | string | Body | A list of categories or classes the model can predict, if applicable. | No |  |
| architecture | string | Body | The type of machine learning architecture used. | No |  |


##### Responses

| Code | Description | Example |
| ---- | ----------- | ------- |
| 201 | Created | model_id |
| 409 | Conflict | Model ID {id} is already in use. |
| 422 | Validation Error | {"detail": [{"loc": ["string", 0],"msg": "string","type": "string"}]} |
| 500 | Internal Server Error | |



### /models/{model_id}

#### GET

##### Description:

Get a registered model by ID.

##### Request Parameters

| Name | Located in | Description | Required | Schema |
| ---- | ---------- | ----------- | -------- | ---- |
| model_id | path |  | Yes |  |

##### Responses

| Code | Description |
| ---- | ----------- |
| 200 | Successful Response |
| 404 | Not Found |
| 422 | Validation Error |

**200 - Successful Response**
```json
{
  "id": "string",
  "name": "string",
  "target_device": "string",
  "created_date": "string",
  "last_updated_date": "string",
  "precision": [
    "string"
  ],
  "size": 0,
  "version": "string",
  "format": "string",
  "origin": "string",
  "file_url": "string",
  "project_id": "string",
  "project_name": "string",
  "category": "string",
  "target_device_type": "string",
  "score": 0,
  "overview": "string",
  "optimization_capabilities": "string",
  "labels": [
    "string"
  ],
  "architecture": "string"
}
```

**404 - Not Found**
```
Model not found.
```

**422 - Validation Error**
```json
{
  "detail": [
    {
      "loc": [
        "string",
        0
      ],
      "msg": "string",
      "type": "string"
    }
  ]
}
```


#### PUT

##### Description:

Update the specified properties of a registered model.

The ability to update a model's stored compressed `file`, and `id` is not supported. 

If you would like to update any of these properties, you will need to delete the existing model (`DELETE /models`) and submit a `POST /models` request to store a model with the desired properties.

##### Request Parameters

| Name | Located in | Description | Required | Schema |
| ---- | ---------- | ----------- | -------- | ---- |
| model_id | path |  | Yes |  |


##### Request Body
| Name | Type | Located in | Description | Required | Schema |
|---|---|---|---|---|---|
| file | string($binary) | Body | The ZIP file containing model files and related artifacts. | Yes |  |
| name | string | Body | The human-readable name of the model. | Yes |  |
| version | string | Body | The version of the model (e.g., 1.0, 1A, v2). | Yes |  |
| target_device | string | Body | The hardware platform the model is designed to run on (e.g., CPU, GPU, FPGA). | No |  |
| precision | string | Body | The precision of the model (e.g., FP32, FP16, INT8, INT4). Defaults to FP32. | No |  |
| format | string | Body | The format of the model (e.g. openvino, pytorch). | No |  |
| score | number | Body | A metric that represents the model's performance. | No |  |
| id | string | Body | A unique identifier for the model. | No |  |
| created_date | string | Body | The date and time the model was first created or trained. If empty, this will be the date and time the model was registered.(e.g. 2024-02-28 15:39:07.054000) | No |  |
| size | integer | Body | The storage space occupied by the model files (e.g., in bytes). | No |  |
| origin | string | Body | The source of the model (e.g., geti), or where it was obtained from. | No |  |
| project_id | string | Body | The unique identifier of the project the model belongs to, if applicable. | No |  |
| project_name | string | Body | The human-readable name of the project the model belongs to, if applicable. | No |  |
| category | string | Body | The category associated to the labels used by the model (e.g. Detection, Classification, etc.). | No |  |
| target_device_type | string | Body | A more specific categorization of the target device (e.g., client, edge, cloud). | No |  |
| overview | string | Body | A general description of the model's purpose, function, and intended use cases. (e.g. {"description":"The description of the model"}) | No |  |
| optimization_capabilities | string | Body | If applicable, information about any specific optimizations made to the model, such as for speed, accuracy, or size reduction. | No |  |
| labels | string | Body | A list of categories or classes the model can predict, if applicable. | No |  |
| architecture | string | Body | The type of machine learning architecture used. | No |  |


##### Responses

| Code | Description |
| ---- | ----------- |
| 200 | OK |
| 400 | Bad Request |
| 404 | Not Found |
| 422 | Validation Error |
| 500 | Internal Server Error |

**200 - OK**
```json
{
  "status": "string"
}
```

**400 - Bad Request**
```json
{
  "status": "error",
  "message": "Invalid request. Check the request body and ensure at least 1 supported field is provided."
}
```

**404 - Not Found**
```json
{
  "status": "error",
  "message": "Model not found."
}
```

**422 - Validation Error**
```json
{
  "detail": [
    {
      "loc": [
        "string",
        0
      ],
      "msg": "string",
      "type": "string"
    }
  ]
}
```

**500 - Internal Server Error**
```json
{
  "status": "error",
  "message": "string"
}
```



#### DELETE

##### Description:

Delete a registered model by ID.

##### Request Parameters

| Name | Located in | Description | Required | Schema |
| ---- | ---------- | ----------- | -------- | ---- |
| model_id | path |  | Yes |  |

##### Responses

| Code | Description | Example |
| ---- | ----------- | ------- |
| 204 | No Content | |
| 404 | Not Found | Model not found. |
| 422 | Validation Error | {"detail": [{"loc": ["string", 0],"msg": "string","type": "string"}]} |



### /models/{model_id}/files

#### GET

##### Description:

Get a ZIP file containing the artifacts (files) for a registered model.

##### Request Parameters

| Name | Located in | Description | Required | Schema |
| ---- | ---------- | ----------- | -------- | ---- |
| model_id | path |  | Yes |  |

##### Responses

| Code | Description | Example |
| ---- | ----------- | ------- |
| 200 | OK | binary file data |
| 404 | Not Found | Model not found. |
| 422 | Validation Error | {"detail": [{"loc": ["string", 0],"msg": "string","type": "string"}]} |
| 500 | Internal Server Error | |

### /projects

#### GET

##### Description:

Get projects in a remote Intel® Geti workspace.


In order to execute successful requests to this endpoint, the following environment variables are required to be set before starting the model registry microservice: `GETI_HOST`, `GETI_TOKEN`, `GETI_SERVER_API_VERSION`, `GETI_ORGANIZATION_ID`, and `GETI_WORKSPACE_ID`.

##### Responses

| Code | Description |
| ---- | ----------- |
| 200 | Successful Response |

**200 - Successful Response**
```json
[
  {
    "id": "string",
    "name": "string",
    "creation_time": "string",
    "model_groups": []
  }
]
```


### /projects/{project_id}

#### GET

##### Description:

Get a project by ID in a remote Intel® Geti workspace.


In order to execute successful requests to this endpoint, the following environment variables are required to be set before starting the model registry microservice: `GETI_HOST`, `GETI_TOKEN`, `GETI_SERVER_API_VERSION`, `GETI_ORGANIZATION_ID`, and `GETI_WORKSPACE_ID`.

##### Request Parameters

| Name | Located in | Description | Required | Schema |
| ---- | ---------- | ----------- | -------- | ---- |
| project_id | path |  | Yes |  |

##### Responses

| Code | Description |
| ---- | ----------- |
| 200 | Successful Response |
| 404 | Not Found |
| 422 | Validation Error |

**200 - Successful Response**
```json
{
  "id": "string",
  "name": "string",
  "creation_time": "string",
  "model_groups": []
}
```

**404 - Not Found**
```
Project not found
```

**422 - Validation Error**
```json
{
  "detail": [
    {
      "loc": [
        "string",
        0
      ],
      "msg": "string",
      "type": "string"
    }
  ]
}
```


### /projects/{project_id}/geti-models/download

#### POST

##### Description:

Store the metadata and artifacts for 1 or more OpenVINO optimized model(s) from a remote Intel® Geti workspace into the registry. 



In order to execute successful requests to this endpoint, the following environment variables are required to be set before starting the model registry microservice: `GETI_HOST`, `GETI_TOKEN`, `GETI_SERVER_API_VERSION`, `GETI_ORGANIZATION_ID`, and `GETI_WORKSPACE_ID`.

If the `models` object contains a list of contains 1 or more `{"id":"<model_identifier>", "group_id": "model_group_identifier"}`, 1 or more models
  will be downloaded and registered.

##### Request Parameters

| Name | Located in | Description | Required | Schema |
| ---- | ---------- | ----------- | -------- | ---- |
| project_id | path |  | Yes |  |

##### Request Body
```json
{
  "models": [
    {
      "id": "string",
      "group_id": "string"
    }
  ]
}
```

##### Responses

| Code | Description |
| ---- | ----------- |
| 201 | Created |
| 403 | Forbidden |
| 404 | Not Found |
| 409 | Conflict |
| 422 | Validation Error |
| 500 | Internal Server Error |


**201 - Created**
```
Model(s): {string} registered.
```

**403 - Forbidden**
```
Model(s): {string} can not be registered.
```

**404 - Not Found**
```
Project or model id not found. No model(s) registered.
```

**409 - Conflict**
```
Model(s): {string} is already registered. No model(s) registered.
Tip: Delete the previously mentioned model(s) or remove the id(s) from the request body then try again.
```

**422 - Validation Error**
```json
{
  "detail": [
    {
      "loc": [
        "string",
        0
      ],
      "msg": "string",
      "type": "string"
    }
  ]
}
```

**500 - Internal Server Error**
```json
```

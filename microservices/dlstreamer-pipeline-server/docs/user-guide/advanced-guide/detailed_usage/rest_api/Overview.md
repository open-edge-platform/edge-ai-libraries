# REST API guide


* [REST API Guide](#rest-api-guide)
    - [RESTful Interface](../../../api-reference.md)
    - [Defining Pipelines](./defining_pipelines.md)
    - [Customizing Pipeline Requests](./customizing_pipeline_requests.md)

The REST Server harnesses the capabilities of the DL Streamer Pipeline Server, offering a easy to use solution for constructing and managing video analytics pipelines. With the help of JSON files, users can effortlessly define and adapt their pipelines as required. Additionally, it provides a streamlined set of RESTful endpoints for seamless pipeline control.

The following REST API endpoints are currently supported.

|      Path           |                                 Description                     |
| :-----------------: | ----------------------------------------------------------------|
| `GET /pipelines`                            | Return supported pipelines.             |
| `GET /pipelines/status`                     | Return status of all pipeline instances.|
| `POST /pipelines/{name}/{version}`          | Start a new pipeline instance.          |
| `GET /pipelines/{instance_id}`              | Return pipeline instance summary.       |
| `POST /pipelines/{name}/{version}/{instance_id}`  | Send request to an already queued pipeline. Supported only for source of type `"image-ingestor"`       |
| `DELETE /pipelines/{instance_id}`           | Stops a running pipeline.               |
| `POST /pipelines/{name}/{version}/{instance_id}/models`     | Download files from the model registry microservice associated with a specific model.               |

Learn how to access and utilize the RESTful endpoints provided by the Pipeline Server for efficient pipeline management [here](../../../api-reference.md).

Learn how to structure and set parameters for your pipelines using JSON files [here](./defining_pipelines.md).

Learn how to tailor your pipeline requests to meet specific requirements [here](./customizing_pipeline_requests.md).

<!--hide_directive
```{toctree}
:maxdepth: 5
:hidden:
restapi_reference_guide.md
defining_pipelines.md
customizing_pipeline_requests.md
```
hide_directive-->

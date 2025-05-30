# Working with other services 
DL Streamer Pipeline Server can work with following microservices for visualization and model management.
- [Model Registry (MRaaS)](#model-registry-mraas)  Hosts models to be deployed on the edge node. Users can provide required configurations to DL Streamer Pipeline Server to pull models from Model Registry and deploy downloaded model.

## Model Registry (MRaaS)
This microservice hosts models to be deployed on the edge node. Users can provide required configurations to DL Streamer Pipeline Server to pull models from Model Registry and deploy downloaded model.
This document provides instructions on how to get started with the model registry microservice, utilize its REST API, and configure DL Streamer Pipeline Server to interact with it.

The model registry microservice provides a centralized repository that can be accessed by different applications, services, or developers to store, and access models. It is an essential tool for deploying machine learning models, as it streamlines model management, fosters collaboration, and ultimately, aids in improving model deployments.

In the current release of DL Streamer Pipeline Server, the following two workflows are supported. 
1. [Init Model download/deployment](#init-model-downloaddeployment): Model download and deployment during initialization phase of DL Streamer Pipeline Server from the model registry microservice. Based on user inputs in configuration file of DL Streamer Pipeline Server, model is downloaded and the model path is dynamically updated in the pipeline configuration. 
2. [Runtime Model download/deployment](#runtime-model-downloaddeployment): Model download and deployment through REST API during DL Streamer Pipeline Server's runtime. Based on user inputs, model is downloaded and once the model download is completed, current pipeline is stopped and a new pipeline is launched with newly downloaded model.

### Get Started Guide
**Note**: This guide assumes you have completed [DL Streamer Pipeline Server's Get Started Guide](../../../get-started.md)

1. Pull the `intel/model-registry:1.0.3` Docker* image available on [Docker Hub](https://hub.docker.com/r/intel/model-registry)
    ```sh
    docker pull intel/model-registry:1.0.3
    ```

2.  Follow the instructions in the Model Registry's Get Started Guide: https://docs.edgeplatform.intel.com/model-registry-as-a-service/1.0.3/user-guide/get-started.html to run the microservice.
3. Send a POST request to store a model.
   * Use the following `curl` command to send a POST request with FormData fields corresponding to the model's properties. 

    ```bash
    curl -X POST 'PROTOCOL://HOSTNAME:32002/models' \
    --header 'Content-Type: multipart/form-data' \
    --form 'name="MODEL_NAME"' \
    --form 'file=@MODEL_ARTIFACTS_ZIP_FILE_PATH;type=application/zip' \
    --form 'version="MODEL_VERSION"' \
    --form 'project_name="Pallet Defect Detection"' \
    --form 'category="Detection"' \
    --form 'precision="FP32"' \
    --form 'architecture="YOLOX-TINY"'
    ```

   * Replace `PROTOCOL` with `https` if **HTTPS** mode is enabled. Otherwise, use `http`.
     * If **HTTPS** mode is enabled, and you are using self-signed certificates, add the `-k` option to your `curl` command to ignore SSL certificate verification.
   * Replace `HOSTNAME` with the actual host name or IP address of the host system where the service is running.
   * Replace `MODEL_NAME` with the name of the model to be stored.
   * Replace `MODEL_ARTIFACTS_ZIP_FILE_PATH` with the file path to the zip file containing the model's artifacts.
   * Replace `MODEL_VERSION` with the version of the model to be stored.
    > Note: For any manual upload of Intel Geti models on model registry, please make sure to provide `origin` as `Geti`.
4. Send a GET request to retrieve a list of models and verify the successful storage of the model in Step 3.
   * Use the following `curl` command to send a GET request to the `/models` endpoint. 
   ```bash
   curl -X GET 'PROTOCOL://HOSTNAME:32002/models'
   ```
   * Replace `PROTOCOL` with `https` if **HTTPS** mode is enabled. Otherwise, use `http`.
     * If **HTTPS** mode is enabled, and you are using self-signed certificates, add the `-k` option to your `curl` command to ignore SSL certificate verification.
   * Replace `HOSTNAME` with the actual host name or IP address of the host system where the service is running.
### DL Streamer Pipeline Server Integration
#### Pre-requisites
In order to successfully, store models received from the model registry microservice within the context of DL Streamer Pipeline Server, the following steps are required before starting the Docker* container for DL Streamer Pipeline Server:
1. Create the `mr_models` directory in the same directory as your `docker-compose.yml` as referenced [here](../../../get-started.md) in the `volumes` section. 
   * This directory will contain the models downloaded from the model registry using DL Streamer Pipeline Server's REST API.
   * The ownership of this directory is required to be the same user of the container (`intelmicroserviceuser`) to enable models to be stored successfully.
    ```sh
    mkdir -p mr_models
    
    sudo useradd -u 1999 intelmicroserviceuser
    # Verify that the user exists
    getent passwd intelmicroserviceuser
    sudo chown intelmicroserviceuser:intelmicroserviceuser mr_models
    ```

#### Configuration (.env)

##### HTTPS and HTTP mode

Model registry microservice supports both HTTPS and HTTP protocols. HTTP mode is enabled by default.
When enabled in HTTPS MODE, DL Streamer Pipeline Server will attempt to verify its SSL certificate using the file(s) in the `/run/secrets/ModelRegistry_Server` directory within the Docker container by default.


*Note: If you would prefer to run the model registry in HTTP mode, set the `ENABLE_HTTPS_MODE` environment variable to `false` before starting the containers. The remainder of this section can be skipped if you are using HTTP mode.*

1. Create the `Certificates/model_registry/` directory in the same directory as your `docker-compose.yml`.
    * This directory should contain the `ca-bundle.crt` file associated to the model registry.  
    ```sh
    mkdir -p Certificates/model_registry
    ```
    * Note: The `/run/secrets/ModelRegistry_Server` directory in the container is mounted to the local `Certificates/model_registry` directory on the host system as defined in the example `docker-compose.yml` file.

2. Navigate to the model registry's `Certificates/ssl` directory used with the model registry Docker container
    ```shell
    cd <path/to>/Certificates/ssl
    ```
3. Create a **CA BUNDLE** file from the model registry's `server-ca.crt` and `server.crt` files in its `Certificates/ssl` directory
    ```shell
    sudo cat server-ca.crt server.crt > ca-bundle.crt
    ```

4. Move (**DO NOT Copy**) the newly created `ca-bundle.crt` file from the model registry's `Certificates/ssl` directory to DL Streamer Pipeline Server's `Certificates/model_registry/` directory.
    * **Note**: By default, DL Streamer Pipeline Server requires the `ca-bundle.crt` file when sending requests to the model registry to verify its SSL certificate. 
    * The `ca-bundle.crt` file is required for DL Streamer Pipeline Server and should not be kept in the model registry's `Certificates/ssl` directory when its containers are started. It will lead to SSL certificate verification issues between the model registry and its dependent containers.
    ```shell
    sudo mv ca-bundle.crt <path/to>/Certificates/model_registry/
    ```
**Note**: The following environment variable is used when HTTPS Mode is enabled:
* **MR_VERIFY_CERT (String)**: Controls whether SSL certificate verification is performed during HTTPS requests to the model registry microservice.
    * Valid options are `True`, `False`, and `</path/to/CA_Bundle_file>`.
        * `True` causes DL Streamer Pipeline Server to validate the model registry's certificate's chain of trust, checks its expiration date and verify its hostname.
        * `False` causes DL Streamer Pipeline Server to ignore verifying the SSL certificate. This may be useful during testing, but not advised for production.
        * `</path/to/CA_Bundle_file>` specifies the path to a **CA_BUNDLE** file.
    * Example: `MR_VERIFY_CERT=False`
    * Default Value: `/run/secrets/ModelRegistry_Server/ca-bundle.crt`
#### Init model download/deployment

##### Configuration (config.json)

DL Streamer Pipeline Server requires the following configuration properties to search, retrieve and store a model locally from the model registry microservice:
A sample config has been provided for this demonstration at `[WORKDIR]/edge-ai-libraries/microservices/dlstreamer-pipeline-server/configs/model_registry/config.json`. We need to volume mount the sample config file in `docker-compose.yml` file. `WORKDIR` is your host machine workspace. Refer below snippets:

```sh
    volumes:
      # Volume mount [WORKDIR]/edge-ai-libraries/microservices/dlstreamer-pipeline-server/configs/model_registry/config.json to config file that DL Streamer Pipeline Server container loads.
      - "../configs/model_registry/config.json:/home/pipeline-server/config.json"
```
The following configuration applies to both the supported protocols HTTPS(default) and HTTP. 
Replace `<PROTOCOL>` in the following steps with `https` or `http` according to the mode the model registry microservice is in when started based on the value of `ENABLE_HTTPS_MODE` and the corresponding steps completed in the previous section.
* **model_registry** (Object): The properties used to connect to the model registry microservice and the directory to save models locally within the context of DL Streamer Pipeline Server.
  * Location: Within the `config` object.
  * Supported sub-properties:
    * **url** (String): The service's IP address or hostname and port of the running model registry microservice.
        * Example: `"url": "<PROTOCOL>://10.101.10.101:32002"`
    * **request_timeout** (Number, Optional): The maximum amount of time in seconds that requests involving the model registry microservice are allowed to take.
        * More details: If not provided, a default value of 300 seconds will be applied.
    * **saved_models_dir** (String): The directory where models are saved when retrieved from the model registry microservice.
        * More details: If this directory does not exist, it will be created when a model is being saved for the first time.
        * Example: `"saved_models_dir": "./mr_models"`

* **model_params** (List): The properties used to retrieve a model stored in the model registry microservice provided as list of properties for each model to be downloaded. 
    * Location: Within an object in the `"config.pipelines"` list.
    * Supported sub-properties:
        * **name** (String, Optional): The name associated to a model.
        	* Example: `"name": "pallet-detection-FP32-YOLO"`
        * **project_name** (String, Optional): The name of the project associated to a model.
        	* Example: `"project_name": "Pallet Defect Detection"`
        * **version** (String, Optional): The version of a model.
        	* Example: `"version": "1"`
        * **category** (String, Optional): The category of a model.
        	* Example: `"category": "Detection"`
        * **architecture** (String, Optional): The architecture of a model.
        	* Example: `"architecture": "YOLOX-TINY"`
        * **precision** (String, Optional): The precision of a model.
        	* Example: `"precision": "FP32"`
    * **Note**: The query performed is an `AND` search if more than 1 sub-property is provided. Despite all the sub-properties being optional, DL Streamer Pipeline Server requires at least 1 sub-property to execute a query. 
    
    In addition to the properties mentioned above, the following properties would be used to dynamically update the model path in the pipeline configuration for the model retrieved from the model registry microservice.
    * **deploy** (String): The category of a model.
        * Example: `"deploy": true`
    * **pipeline_element_name** (String): The name of the inference element in the pipeline to which the model is associated.
        * Example: `"pipeline_element_name": "detection"`
    * **origin** (String, Optional): The origin of a model to differentiate geti vs non-geti models. When not provided the model is considered a non-geti (omz) model.
        * Example: `"origin": "Geti"`
    
    The model path is constructed based on the `model query params`.
    * Geti model:
        * Deployment directory path: `{config.model_registry.saved_models_dir}`/`{model_params.name}`\_m-`{model_params.version}`_`{model_params.precision}`/deployment
            * Location: Within an object in the `"config.pipelines[...].udfs.udfloader[...]"` list.
            * Example: `"deployment": "./mr_models/pallet_detection_m-v1_fp32/deployment"`
        * Model path: `{config.model_registry.saved_models_dir}`/`{model_params.name}`\_m-`{model_params.version}`_`{model_params.precision}`/deployment/`{model_params.category}/model/model.xml`
            * Location: model property for inferencing element within pipeline definition `"config.pipelines[...]"` list.
            * Example: `"pipeline": "....gvadetect model=./mr_models/pallet_detection_m-v1_fp32/deployment/model/model.xml name=detection...."`
    * Non-Geti OMZ model:
        * Model path: `{config.model_registry.saved_models_dir}`/`{model_params.name}`\_m-`{model_params.version}`_`{model_params.precision}`/`{model_params.precision}`/`{model_params.name}.xml`
            * Location: model property for inferencing element within pipeline definition `"config.pipelines[...]"` list.
            * Example: `"pipeline": "....gvadetect model=./mr_models/yolo11s_m-v1_fp32/FP32/yolo11s.xml name=detection...."`

Replace the `<PROTOCOL>` and `<IP_ADDRESS_OR_SERVICE_HOSTNAME>` accordingly.

The `config.json` file must be volume mounted inside the `[WORKDIR]/edge-ai-libraries/microservices/dlstreamer-pipeline-server/docker/docker-compose.yml` to reflect the configuration changes when DL Streamer Pipeline Server is brought up.

```sh
volumes:
      # Volume mount [WORKDIR]/edge-ai-libraries/microservices/dlstreamer-pipeline-server/configs/config.json to config file that DL Streamer Pipeline Server container loads."
      - "../configs/config.json:/home/pipeline-server/config.json"
```

Next bring up the containers
```sh
cd [WORKDIR]/edge-ai-libraries/microservices/dlstreamer-pipeline-server/docker
docker compose up
```

Open another terminal and send the following curl request

**Example request**
```sh
curl http://localhost:8080/pipelines/user_defined_pipelines/pallet_defect_detection -X POST -H 'Content-Type: application/json' -d '{
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
                        "model": "mr_models/pdd_m-v1_fp32/deployment/Detection/model/model.xml"
                    }
               }
}'
```
> Note: When deploy=true, `parameters` might not be required as the model path will be dynamically added to the pipeline configuration. 

#### Runtime model download/deployment
Refer to the [documentation](../../detailed_usage/rest_api/restapi_reference_guide.md#post-pipelinesnameversioninstance_idmodels) for more details on downloading/deploying model from model registry during runtime.

For more details on `model query params` to be provided as part of REST request, refer to the above [section](#configuration-configjson)

##### Example
Download/Update model: 

Along with model properties, `deploy`, `origin` and `pipeline_element_name` should be provided to download the model and restart the pipeline with the newly download model set for the specific pipeline element.
```json
{
    "name": "pallet-detection-FP32-YOLO",
    "project_name": "pallet-detection",
    "version": "v2",
    "category": "Detection",
    "architecture": "YOLO",
    "precision": "FP32",
    "deploy": true,
    "pipeline_element_name": "detection"
}
```

#### Supported Models for Model Update/Deployment
- Geti models (retrieved and stored from Geti server) which is expected to have `origin` ('Geti'). For any manual upload of Geti models on model registry, please make sure to provide `origin`. 
- OMZ models having directory structure, for example, `yolo11s-m_v1_FP32/FP32/yolo11s.xml`.

#### Recommendations
Usage of `model-instance-id` property for inferencing elements in pipeline is not recommended for runtime model updates as using this property would persist the same original model across pipeline instances. 
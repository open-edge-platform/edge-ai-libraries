# How to Interface with Intel® Geti™ Software

These steps demonstrate how to interact with a remote Intel Geti server such as accessing projects and storing OpenVINO optimized models in the Model Registry microservice using `curl` commands on a Linux system.

In order to execute successful requests to the endpoints below, the following environment variables are required to be set before starting the model registry microservice: `GETI_HOST`, `GETI_TOKEN`, `GETI_SERVER_API_VERSION`, `GETI_ORGANIZATION_ID`, and `GETI_WORKSPACE_ID`.

## Fetching a List of Projects and their OpenVINO optimized models hosted on a remote Intel Geti server

1. **Send a GET request to retrieve a list of projects.**
    * Use the following `curl` command to send a GET request to the `/projects` endpoint. 

    ```bash
    curl -X GET 'PROTOCOL://HOSTNAME:32002/projects'
    ```

    * Replace `PROTOCOL` with `https` if **HTTPS** mode is enabled. Otherwise, use `http`.
      * If **HTTPS** mode is enabled, and you are using self-signed certificates, add the `-k` option to your `curl` command to ignore SSL certificate verification.
    * Replace `HOSTNAME` with the actual host name or IP address of the host system where the service is running.

1. **Parse the response.**
    * The response will be a list containing the metadata of projects hosted on a remote Intel Geti server.

## Getting a specific project hosted on a remote Intel Geti server

1. **Send a GET request to get a project.**
    * Use the following `curl` command to send a GET request to the `/projects/PROJECT_ID` endpoint.

    ```bash
    curl -L -X GET 'PROTOCOL://HOSTNAME:32002/projects/PROJECT_ID'
    ```

    * Replace `PROTOCOL` with `https` if **HTTPS** mode is enabled. Otherwise, use `http`.
      * If **HTTPS** mode is enabled, and you are using self-signed certificates, add the `-k` option to your `curl` command to ignore SSL certificate verification.
    * Replace `HOSTNAME` with the actual host name or IP address of the host system where the service is running.
    * Replace `PROJECT_ID` with the `id` of the desired project.

1. **Parse the response.**
    * The response will have a `200 OK` status code and the metadata for a project.


## Storing a model from a remote Intel Geti server into the Registry

1. **Send a POST request to store a model from a remote Intel Geti server into the registry.**
    * Use the following `curl` command to send a POST request: 

    ```bash
    curl -X POST 'PROTOCOL://HOSTNAME:32002/projects/PROJECT_ID/geti-models/download' \
    --header 'Content-Type: application/json' \
    --data '{
      "models": [
        {
            "id": MODEL_ID,
            "group_id": MODEL_GROUP_ID
        }
      ]
    }'
    ```


    * Replace `PROTOCOL` with `https` if **HTTPS** mode is enabled. Otherwise, use `http`.
      * If **HTTPS** mode is enabled, and you are using self-signed certificates, add the `-k` option to your `curl` command to ignore SSL certificate verification.
    * Replace `HOSTNAME` with the actual host name or IP address of the host system where the service is running.
    * Replace `MODEL_ID` with the ID of the OpenVINO optimized model to be stored.
    * Replace `MODEL_GROUP_ID` with the ID of the group the model belongs to.

1. **Parse the response.**
    * The response will include the ID of the newly stored model.

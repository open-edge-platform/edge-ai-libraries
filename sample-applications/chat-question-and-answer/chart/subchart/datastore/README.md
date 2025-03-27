# DataStore Helm Chart

This Helm chart deploys the `dataStore` service. The `dataStore` service requires a Minio server to be running.

## Prerequisites

- Kubernetes cluster
- Helm installed
- MinIo server [Minio server deployment steps](../minioserver/README.md)

## Deployment Steps

1. **Clone the repository:**

    ```sh
    git clone <repository-url>
    cd <repository-directory>/chart/subchart/datastore
    ```

2. **Update the `values.yaml` file:**

    Ensure that the `MINIO_HOST`, `MINIO_ACCESS_KEY`, and `MINIO_SECRET_KEY` are set correctly in the `values.yaml` file. Default values are already added in `values.yaml`.

    | Parameter          | Description                                      | Default Value                          |
    |--------------------|--------------------------------------------------|----------------------------------------|
    | `dataStore.image.repository`  | Docker image repository for datastore        | `intel/object-store` |
    | `dataStore.image.tag`         | Docker image tag                             | `1.1.1`                                   |
    | `dataStore.env.MINIO_HOST`    | Minio server host                            | `minio-server`                         |
    | `dataStore.env.MINIO_API_PORT`| Minio API port                               | `9000`                                 |
    | `dataStore.env.MINIO_ACCESS_KEY` | Minio access key                          | ``                           |
    | `dataStore.env.MINIO_SECRET_KEY` | Minio secret key                          | ``                            |

3. **Deploy the Helm chart:**

    Specify each parameter using the --set key=value[,key=value] argument to helm install. For example:
    ```sh
    helm install datastore . --set dataStore.env.MINIO_HOST=9000
    ```

    Alternatively, a YAML file that specifies the values for the parameters can be provided while installing the chart. For example:
    ```sh
    helm install datastore . \
    --set global.proxy.http_proxy=<your proxy> \
    --set global.proxy.https_proxy=<your proxy> \
    --set global.proxy.no_proxy=<your no_proxy> \
    --namespace <YOUR_NAMESPACE>
    ```

4. **Verify the deployment:**

    ```sh
    kubectl get pods
    kubectl get services
    ```

    Ensure that the `datastore` pod is running and the service is available.

5. **Accessing the Service locally**

    Once deployed, the DataStore service will be available within the Kubernetes cluster. You can access it using the service name and port specified in the `values.yaml` file.

    To access the service from your local machine, you can use `kubectl port-forward`:

    ```sh
    kubectl port-forward svc/<service-name> <local-port>:<service-port>
    ```
    Replace `<service-name>`, `<local-port>`, and `<service-port>` with the appropriate values from your deployment.

## Uninstalling the Chart

To uninstall/delete the `datastore` deployment:

```sh
helm uninstall datastore
```
The command removes all the Kubernetes components associated with the chart and deletes the release.

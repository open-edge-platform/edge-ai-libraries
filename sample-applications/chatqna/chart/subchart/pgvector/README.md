# PGVector Helm Chart

This Helm chart deploys pgVector, a PostgreSQL extension for vector similarity search.

## Prerequisites

- Kubernetes cluster
- Helm installed

## Installation

1. **Clone the repository**
    Clone the repository containing the Helm chart to your local machine.
    
    ```sh
    git clone <repository-url>
    cd <repository-directory>/chart/subchart/pgvector
    ```

2. **Install the Helm chart**

    ```sh
    helm install pgvector . \
    --set global.proxy.http_proxy=<your proxy> \
    --set global.proxy.https_proxy=<your proxy> \
    --set global.proxy.no_proxy=<your no_proxy> \
    --namespace <YOUR_NAMESPACE>
    ```

**Configuration**

    The following table lists the configurable parameters of the pgVector chart and their default values.

    | Parameter                         | Description                    | Default            |
    | --- | ----------- | ------------- |
    | `pgvectorContainer.image.repository`| Image repository for pgVector    | `pgvector/pgvector` |
    | `pgvectorContainer.image.tag`      | Image tag for pgVector  | `pg16`                   |
    | `pgvectorContainer.env.POSTGRES_USER`| PostgreSQL user  | `langchain`                   |
    | `pgvectorContainer.env.POSTGRES_PASSWORD`| PostgreSQL password    | `langchain`         |
    | `pgvectorContainer.env.POSTGRES_DB`| PostgreSQL database    | `langchain`                | 

3. **Install the Helm chart**

    ```sh
    helm install pgvector .  \
    --namespace <YOUR_NAMESPACE>
    ``` 
4. **Accessing the Service locally**

    Once deployed, the PGVector service will be available within the Kubernetes cluster. You can access it using the service name and port specified in the `values.yaml` file.

    To access the service from your local machine, you can use `kubectl port-forward`:

    ```sh
    kubectl port-forward svc/<service-name> <local-port>:<service-port>
    ```
    Replace `<service-name>`, `<local-port>`, and `<service-port>` with the appropriate values from your deployment.

**Cleanup**

To uninstall the Helm chart:
```sh
helm uninstall pgvector
```
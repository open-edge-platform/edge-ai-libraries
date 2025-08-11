# Dataprep microservice with pgVector

This Helm chart is used to deploy the `dataprep` service with pgVector.

data-prep will use pgVector, tei and MINIO service, please specify the endpoints.

## Prerequisites

Before deploying the `dataprep` service, ensure the following services are up and running:

1. **pgVector**: A PostgreSQL extension for vector similarity search. [PgVector deployment steps](../pgvector/README.md)
2. **TEI (Text Embedding Inference)**: A service for generating text embeddings. [TEI deployment steps](../tei/README.MD)
3. **MinIO** : An object storage service to store the documents [MinIO deployment steps](../minioserver/README.md)

## Deployment Steps

1. **Clone the Repository**

   ```sh
   git clone https://github.com/open-edge-platform/edge-ai-libraries.git edge-ai-libraries -b release-1.2.0
   cd edge-ai-libraries/sample-applications/chat-question-and-answer/chart/subchart/dataprep
   ```
   Adjust the repo link appropriately in case of forked repo.

2. **Update Values**
    Edit the values.yaml file to set the appropriate values for your environment, especially the
    ```sh
     HUGGINGFACEHUB_API_TOKEN
     PG_CONNECTION_STRING
     TEI_ENDPOINT_URL
     MINIO_ACCESS_KEY
     MINIO_SECRET_KEY
    ```
    The values can also be set while running the deploy command with helm.

3. **Deploy Using Helm**

    ```sh
    helm install dataprep . --set global.huggingface.apiToken=<your-huggingface-token> \
    --set dataprepPgvector.env.PG_CONNECTION_STRING=<your-pg-connection-string> \
    --set dataprepPgvector.env.TEI_ENDPOINT_URL=<your-tei-endpoint-url> \
    --set dataprepPgvector.env.MINIO_ACCESS_KEY=<your-minio-access-key> \
    --set dataprepPgvector.env.MINIO_SECRET_KEY=<yout-minio-secret-key> \
    --namespace <your-namespace>
    ```
4. **Verify Deployment**
    Check the status of the deployment to ensure all pods are running correctly.
    ```sh
    kubectl get pods
    ```
5. **Accessing the Service locally**

    Once deployed, the dataprep service will be available within the Kubernetes cluster. You can access it using the service name and port specified in the `values.yaml` file.

    To access the service from your local machine, you can use `kubectl port-forward`:

    ```sh
    kubectl port-forward svc/<service-name> <local-port>:<service-port>
    ```
    Replace `<service-name>`, `<local-port>`, and `<service-port>` with the appropriate values from your deployment.

## Uninstall ##
    To uninstall the dataprep service, run the following command:
    ```sh
    helm uninstall dataprep
    ```
    This will remove all resources associated with the dataprep service.
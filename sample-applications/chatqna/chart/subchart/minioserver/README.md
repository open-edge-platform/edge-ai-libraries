# Minio Server Deployment using Helm Chart

This guide provides the steps to deploy the MinIO server using the provided Helm chart.

## Prerequisites

- Helm installed
- Kubernetes cluster up and running
- Access to the Minio Helm chart

## Steps to Deploy

1. **Clone the Repository**

   Clone the repository containing the Helm chart to your local machine.

   ```sh
   git clone <repository-url>
   cd <repository-directory>/chart/subchart/minioserver
   ```
2. **Update Values**
    
    Update the values.yaml file with the necessary configurations. Ensure you set the MINIO_ROOT_USER and MINIO_ROOT_PASSWORD environment The following table lists the configurable parameters of the Minio server Helm chart and their default values.

    | Parameter                        | Description                                    | Default                                  |
    | --- | ----------- | ------------- |
    | `minioServer.name`               | Name of the MinIO server                       | `minio-server`                           |
    | `minioServer.image.repository`   | MinIO server image repository                  | `minio/minio:RELEASE.2025-02-07T23-21-09Z-cpuv1`                    |
    | `minioServer.volumes`            | Volumes to mount                               | `/mnt/miniodata:/data`                   |
    | `minioServer.env.MINIO_ROOT_USER`| MinIO root user                                | ``                             |
    | `minioServer.env.MINIO_ROOT_PASSWORD`| MinIO root password                        | ``                              |

    Specify each parameter using the `--set key=value[,key=value]` argument to `helm install`. For example:

    ```sh
    helm install minio-server . --set minioServer.env.MINIO_ROOT_USER=myuser,minioServer.env.MINIO_ROOT_PASSWORD=mypassword \
    --namespace <YOUR_NAMESPACE>
    ```

3. **Deploy the Helm Chart**
    
    Use the following command to deploy the Helm chart:
    ```sh
    helm install minio-server . \
    --namespace <YOUR_NAMESPACE>
    ```

5. **Accessing the Service locally**

    Once deployed, the Minio server service will be available within the Kubernetes cluster. You can access it using the service name and port specified in the `values.yaml` file.

    To access the service from your local machine, you can use `kubectl port-forward`:

    ```sh
    kubectl port-forward svc/<service-name> <local-port>:<service-port>
    ```
    Replace `<service-name>`, `<local-port>`, and `<service-port>` with the appropriate values from your deployment.

5. **Cleanup**
    
    To delete the MinIO server deployment, use the following command:
    ```sh
    helm uninstall minio-server
    ```




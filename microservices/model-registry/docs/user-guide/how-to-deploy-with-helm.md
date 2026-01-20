# How to Deploy with Helm

Use Helm to deploy Model Registry to a Kubernetes cluster. This guide will help you to:

- Add the Helm chart repository.
- Configure the Helm chart to match your deployment needs.
- Deploy and verify the microservice.

Helm simplifies Kubernetes deployments by streamlining configurations and enabling easy scaling
and updates. For more details, see [Helm Documentation](https://helm.sh/docs/).

## Prerequisites

Before You Begin, ensure the following:

- **System Requirements**: Verify that your system meets the [minimum requirements](./get-started/system-requirements.md).
- **Tools Installed**: Install the required tools:
    - Kubernetes CLI (kubectl)
    - Helm 3 or later
- **Cluster Access**: Confirm that you have access to a running Kubernetes cluster with
appropriate permissions.

This guide assumes basic familiarity with Kubernetes concepts, kubectl commands, and Helm
charts. If you are new to these concepts, see:

- [Kubernetes Documentation](https://kubernetes.io/docs/home/)
- [Helm Documentation](https://helm.sh/docs/)

## Steps to Deploy

1. **Create directories to be used for persistent storage by the Postgres* and MinIO* Docker containers**
    ```sh
    mkdir -p /opt/intel/mr/data/mr_postgres

    mkdir -p /opt/intel/mr/data/mr_minio

    useradd -u 2025 mruser

    chown -R mruser:mruser /opt/intel/mr/data/mr_postgres /opt/intel/mr/data/mr_minio
    ```
    > **Note**: The data in these directories will persist after the containers are removed.
    If you would like to subsequently start the containers with no pre-existing data, delete
    the contents in the directories before starting the containers.

2. **Pull the Helm chart from Docker Hub**
    ```sh
    helm pull oci://registry-1.docker.io/intel/model-registry --version 1.0.3-helm
    ```

3. **Unzip the file**
    ```sh
    tar xvf model-registry-1.0.3-helm.tgz
    ```

4. **Navigate into the directory**
    ```sh
    cd model-registry
    ```

5. **Open the `values.yaml` file and enter values for the following variables:**
    - `MINIO_SECRET_KEY`
    - `POSTGRES_PASSWORD`

    For more information about the supported environment variables, refer to the [Environment Variables](./environment-variables.md) documentation.

6. **Install the helm chart**
    ```sh
    helm install modelregistry . -n apps --create-namespace
    ```

7. **Check the status of the pods and verify the microservice is running**
    ```sh
    kubectl get pods --namespace apps
    ```

8. **Monitor the logs for the pod associated to the `model-registry` to identify any issues and verify that it is operating successfully**
    ```sh
    kubectl logs -f {{pod_name}} -n apps
    ```

## Troubleshooting

1. **Helm Chart Not Found**:

   - Check if the Helm repository was added:

     ```bash
     helm repo list
     ```

2. **Pods Not Running**:

   - Review pod logs:

     ```bash
     kubectl logs {{pod-name}} -n {{namespace}}
     ```

3. **Service Unreachable**:

   - Confirm the service configuration:

     ```bash
     kubectl get svc -n {{namespace}}
     ```

## Supporting Resources

- [Kubernetes Documentation](https://kubernetes.io/docs/home/)
- [Helm Documentation](https://helm.sh/docs/)
- [API Reference](./api-reference.md)

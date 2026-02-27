# Deploy with Helm Chart

This section shows how to deploy Model Download using Helm chart.

## Prerequisites

Before you begin, ensure that you have the following prerequisites:
- Kubernetes cluster set up and running.
- The cluster must support **dynamic provisioning of Persistent Volumes (PV)**. See [Kubernetes Documentation on Dynamic Volume Provisioning](https://kubernetes.io/docs/concepts/storage/dynamic-provisioning/) for details.
- Install `kubectl` on your system. See [Kubernetes Documentation on Tool Installation](https://kubernetes.io/docs/tasks/tools/install-kubectl/). Ensure access to the Kubernetes cluster.
- Helm chart installed on your system: See [Installing Helm](https://helm.sh/docs/intro/install/).

## Install Helm Chart from Docker Hub or from Source

To deploy with Helm chart, you can either install the chart from Docker hub or from source.

### Option 1: Install from Docker Hub

1. Pull the specific chart

   Use the following command to pull the Helm chart from [Docker Hub](https://hub.docker.com/r/intel/model-download-chart):

   ```bash
   helm pull oci://registry-1.docker.io/intel/model-download-chart --version <version-no>
   ```

   See the [Docker hub's tags page](https://hub.docker.com/r/intel/model-download-chart/tags) for details on the latest version number to use for the application.

2. Extract the `.tgz` file

   Extract the `.tgz` file:
   ```bash
   tar -xvf model-download-chart-<version-no>.tgz
   ```

3. This will create a directory named `model-download-chart`, containing the chart files. Navigate to the extracted directory:
   
   ```bash
   cd model-download-chart
   ```

### Option 2: Install from Source

1. Clone the repository containing the Helm chart:

   ```bash
   # Clone the latest on the mainline
     git clone https://github.com/open-edge-platform/edge-ai-libraries.git edge-ai-libraries
   # Alternatively, clone a specific release branch
     git clone https://github.com/open-edge-platform/edge-ai-libraries.git edge-ai-libraries -b <release-tag>
   ```

2. Navigate to the chart directory:

   ```bash
   cd edge-ai-libraries/microservices/model-download/chart
   ```

## Configure the `values.yaml` File

Edit the `values.yaml` file located in the chart directory to set the necessary environment variables. Set your proxy settings as required.

The following is a summary of key configuration options available in the `values.yaml` file:

| Parameter           | Description                                 | Example Value            | Required |
|---------------------|---------------------------------------------|--------------------------|----------|
| `env.HUGGINGFACEHUB_API_TOKEN`      | Hugging Face access token                   | `hf_xxx`                 | Yes      |
| `env.GETI_WORKSPACE_ID` | GETI workspace ID |  | Yes, For GETI connection |
| `env.GETI_HOST` | GETI connection host address |  | Yes, For GETI connection |
| `env.GETI_TOKEN` | GETI Personal Access token |  | Yes, For GETI connection |
| `env.GETI_SERVER_API_VERSION` | GETI API version | `v1` | Yes, For GETI connection |
| `env.GETI_SERVER_SSL_VERIFY` | Enables SSL certificate validation for HTTPS/HTTP GETI hosts | `False` | Yes, For GETI connection |
| `service.nodePort`  | Sets the static port (in the 30000–32767 range) | 32000                | Yes      |
| `env.ENABLED_PLUGINS`| Comma-separated list of plugins to enable (e.g., `huggingface,ollama,ultralytics, openvino and geti`) or `all` to enable all available plugins | `all` | Yes |
| `image.repository`	| image repository url	| intel/model-download | Yes |
| `image.tag`	        | latest image tag	    | latest            | Yes |


> **Note:** See the chart's `values.yaml` file for a full list of configurable parameters.

## Deploy the Helm Chart

```bash
helm install model-download . -n <your-namespace>
```

> **Note:** `model-download` creates and manages a shared PVC that can be used by dependent applications such as ChatQnA.

## Verify the Deployment

Check the status of the deployed resources to ensure everything is running correctly:

```bash
kubectl get pods -n <your-namespace>
kubectl get services -n <your-namespace>
```

## Access the Application

Open the application's Swagger documentation in a browser through `http://<node-ip>:<node-port>/api/v1/docs`.

## Uninstall Helm chart

```bash
helm uninstall <name> -n <your-namespace>
```

## Verify the Application

1. Ensure that all pods are running and the services are accessible.

2. Access the application dashboard and verify that it is functioning as expected.

## Troubleshooting

- If you encounter any issues during the deployment process, check the Kubernetes logs for errors:

  ```bash
  kubectl logs <pod-name>
  ```
- If the PVC created during a Helm chart deployment is not removed or auto-deleted due to a deployment failure or being stuck, delete it manually:

  ```bash
  # List the PVCs present in the given namespace
  kubectl get pvc -n <namespace>

  # Delete the required PVC from the namespace
  kubectl delete pvc <pvc-name> -n <namespace>
  ```
**Note:**
  Delete the shared PVC only after confirming no other workload or application (for example, ChatQnA) depends on it. In such cases, uninstall the dependent application first, then clean up `model-download` resources, and finally delete the shared PVC if required.

## Learn More

- [Build from Source](./build-from-source.md)

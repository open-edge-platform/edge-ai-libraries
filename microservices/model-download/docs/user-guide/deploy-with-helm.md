# How to deploy with Helm

This guide provides step-by-step instructions for deploying the Model-Download Microservice using Helm.

## Prerequisites

Before you begin, ensure that you have the following prerequisites:
- Kubernetes cluster set up and running.
- The cluster must support **dynamic provisioning of Persistent Volumes (PV)**. Refer to the [Kubernetes Dynamic Provisioning Guide](https://kubernetes.io/docs/concepts/storage/dynamic-provisioning/) for more details.
- Install `kubectl` on your system. Refer to [Installation Guide](https://kubernetes.io/docs/tasks/tools/install-kubectl/). Ensure access to the Kubernetes cluster.
- Helm installed on your system: [Installation Guide](https://helm.sh/docs/intro/install/).

## Steps to deploy with Helm

Following steps should be followed to deploy Model-Download using Helm. You can install from source code or pull the chart from Docker hub.

**_Steps 1 to 2 varies depending on if the user prefers to build or pull the Helm details._**

### Option 1: Install from Docker Hub

#### Step 1: Pull the Specific Chart

Use the following command to pull the Helm chart from [Docker Hub](https://hub.docker.com/r/intel/model-download):

```bash
helm pull oci://registry-1.docker.io/intel/model-download --version <version-no>
```

🔍 Refer to the [Docker Hub tags page](https://hub.docker.com/r/intel/model-download/tags) for details on the latest version number to use for the application.

#### Step 2: Extract the `.tgz` File

After pulling the chart, extract the `.tgz` file:
```bash
tar -xvf model-download-<version-no>.tgz
```

This will create a directory named `model-download` containing the chart files. Navigate to the extracted directory.
```bash
cd model-download
```

### Option 2: Install from Source

#### Step 1: Clone the Repository

*Clone the repository containing the Helm chart*:
```bash
# Clone the latest on mainline
  git clone https://github.com/open-edge-platform/edge-ai-libraries.git edge-ai-libraries
# Alternatively, Clone a specific release branch
  git clone https://github.com/open-edge-platform/edge-ai-libraries.git edge-ai-libraries -b <release-tag>
```

#### Step 2: Change to the Chart Directory

Navigate to the chart directory:
```bash
cd edge-ai-libraries/microservices/model-download/chart
```

## Common Steps

#### Step 3: Configure the `values.yaml` File

Edit the `values.yaml` file located in the chart directory to set the necessary environment variables. Ensure you set the `env.HUGGINGFACEHUB_API_TOKEN` and proxy settings as required

Below is a summary of key configuration options available in the `values.yaml` file:

| Parameter           | Description                                 | Example Value            | Required |
|---------------------|---------------------------------------------|--------------------------|----------|
| `env.HUGGINGFACEHUB_API_TOKEN`      | Hugging Face access token                   | `hf_xxx`                 | Yes      |
| `service.nodePort`  | Sets the static port (in the 30000–32767 range) | 32000                | Yes      |
| `env.ENABLED_PLUGINS`| Comma-separated list of plugins to enable (e.g., `huggingface,ollama,ultralytics`) or `all` to enable all available plugins | `all` | Yes |
| `image.repository`	| image repository url	| intel/model-download | Yes |
| `image.tag`	        | latest image tag	    | 1.0.0                | Yes |


> **Note:** Refer to the chart's `values.yaml` for a full list of configurable parameters.

### Step 4: Deploy the Helm Chart

Deploy the Model-Download Helm chart:

```bash
helm install model-download . -n <your-namespace>
```

### Step 5: Verify the Deployment

Check the status of the deployed resources to ensure everything is running correctly

```bash
kubectl get pods -n <your-namespace>
kubectl get services -n <your-namespace>
```

### Step 6: Access the Application

Open the application swagger documentation in a browser at `http://<node-ip>:<node-port>/api/v1/docs`

### Step 7: Uninstall Helm chart

To uninstall helm charts deployed, use the following command:

```bash
helm uninstall <name> -n <your-namespace>
```

## Verification

- Ensure that all pods are running and the services are accessible.
- Access the application dashboard and verify that it is functioning as expected.

## Troubleshooting

- If you encounter any issues during the deployment process, check the Kubernetes logs for errors:
  ```bash
  kubectl logs <pod-name>
  ```
- If the PVC created during a Helm chart deployment is not removed or auto-deleted due to a deployment failure or being stuck, it must be deleted manually using the following commands:
  ```bash
  # List the PVCs present in the given namespace
  kubectl get pvc -n <namespace>

  # Delete the required PVC from the namespace
  kubectl delete pvc <pvc-name> -n <namespace>
  ```

## Related links

- [How to Build from Source](./build-from-source.md)
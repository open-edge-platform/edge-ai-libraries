# How to deploy with Helm

This guide provides step-by-step instructions for deploying the Chat Question-and-Answer Core Sample Application using Helm.

## Prerequisites

Before you begin, ensure that you have the following prerequisites:
- Kubernetes cluster set up and running.
- The cluster must support **dynamic provisioning of Persistent Volumes (PV)**. Refer to the [Kubernetes Dynamic Provisioning Guide](https://kubernetes.io/docs/concepts/storage/dynamic-provisioning/) for more details.
- Install `kubectl` on your system. Refer to [Installation Guide](https://kubernetes.io/docs/tasks/tools/install-kubectl/). Ensure access to the Kubernetes cluster.
- Helm installed on your system: [Installation Guide](https://helm.sh/docs/intro/install/).

## Steps to deploy with Helm

Following steps should be followed to deploy ChatQ&A using Helm. You can install from source code or pull the chart from Docker Hub.

**_Steps 1 to 3 vary depending on whether the user prefers to build or pull the Helm details._**

### Option 1: Pull from Docker Hub

#### Step 1: Pull the specific Chart
```bash
helm pull oci://registry-1.docker.io/intel/chat-question-and-answer-core --version <version-no>
```
Refer to the release notes for details on the latest version number to use for the sample application.

#### Step 2: Extract the `.tgz` File

After pulling the chart, extract the `.tgz` file:
```bash
tar -xvf chat-question-and-answer-core-<version-no>.tgz
```

This will create a directory named `chat-question-and-answer-core` containing the chart files. Navigate to the extracted directory:
```bash
cd chat-question-and-answer-core
```
#### Step 3: Configure the `values.yaml` File

Edit the `values.yaml` file to set the necessary environment variables. Ensure you set the `huggingface.apiToken` and proxy settings as required.

To enable GPU support, set the configuration parameter `gpu.enabled` to `True` and provide the corresponding `gpu.key` that assigned in your cluster node in the `values.yaml` file.

For detailed information on supported and validated hardware platforms and configurations, please refer to the [Validated Hardware Platform](./system-requirements.md) section.


| Key | Description | Example Value |
| --- | ----------- | ------------- |
| `global.huggingface.apiToken` | Your Hugging Face API token      | `<your-huggingface-token>` |
| `global.EMBEDDING_MODEL`|   embedding model name      | BAAI/bge-small-en-v1.5|
| `global.RERANKER_MODEL`  | reranker model name   | BAAI/bge-reranker-base   |
| `global.LLM_MODEL` |  model to be used with ovms     | microsoft/Phi-3.5-mini-instruct|
| `global.UI_NODEPORT` | Sets the static port (in the 30000–32767 range) | |
| `global.keeppvc` | Set true to persists the storage. Default is false | false |
| `global.EMBEDDING_DEVICE`| set either CPU or GPU | CPU |
| `global.RERANKER_DEVICE`| set either CPU or GPU | CPU |
| `global.LLM_DEVICE`| set either CPU or GPU | CPU |
| `gpu.enabled` | Set is true for deploying on GPU  | false |
| `gpu.key` | Label assigned to the GPU node on kubernetes cluster by the device plugin example- gpu.intel.com/i915, gpu.intel.com/xe. Identify by running kubectl describe node| `<your-node-key-on-cluster>` |

**NOTE**:

- If `gpu.enabled` is set to False, the parameters `global.EMBEDDING_DEVICE`, `global.RERANKER_DEVICE`, and `global.LLM_DEVICE` must not be set to `GPU`.
A validation check is included and will throw an error if any of these parameters are incorrectly set to `GPU` while `GPU support is disabled`.

- When GPU support is enabled, the default value for these device parameters is GPU. On systems with an integrated GPU, the device ID is always 0 (i.e., GPU.0), and GPU is treated as an alias for GPU.0.
For systems with multiple GPUs (e.g., both integrated and discrete Intel GPUs), you can specify the desired devices using comma-separated IDs such as GPU.0, GPU.1 and etc.

### Option 2: Install from Source

#### Step 1: Clone the Repository

Clone the repository containing the Helm chart:

```bash
git clone https://github.com/open-edge-platform/edge-ai-libraries.git edge-ai-libraries
```

#### Step 2: Change to the Chart Directory

Navigate to the chart directory:

```bash
cd edge-ai-libraries/sample-applications/chat-question-and-answer-core/chart
```

#### Step 3: Configure the `values.yaml` File

Edit the `values.yaml` file located in the chart directory to set the necessary environment variables. Refer to the table in **Option 1, Step 3** for the list of keys and example values.

#### Step 4: Build Helm Dependencies

Navigate to the chart directory and build the Helm dependencies using the following command:

```bash
helm dependency build
```

## Common Steps after configuration

### Step 5: Deploy the Helm Chart

Deploy the Chat Question-and-Answer Core Helm chart:

```bash
helm install chatqna-core . --namespace <your-namespace>
```

### Step 6: Verify the Deployment

Check the status of the deployed resources to ensure everything is running correctly

```bash
kubectl get pods -n <your-namespace>
kubectl get services -n <your-namespace>
```

### Step 7: Retrieving the Service Endpoint (NodePort and NodeIP)

Open the UI in a browser at http://\<node-ip\>:\<ui-node-port\>

### Step 8: Update Helm Dependencies

If any changes are made to the subcharts, update the Helm dependencies using the following command:

```bash
helm dependency update
```
### Step 9: Uninstall Helm chart

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
  kubectl logs <pod_name>
  ```
- The _PVC_ created during helm chart deployment will remain present until explicitly deleted, use the below command to delete:
  ```bash
  kubectl delete pvc <pvc-name> -n <namespace>
  ```
## Related links

- [How to Build from Source](./build-from-source.md)
- [How to Benchmark](./benchmarks.md)

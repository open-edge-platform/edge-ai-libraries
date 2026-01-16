# How to deploy with Helm

This guide provides step-by-step instructions for deploying the Chat Question-and-Answer Core Sample Application using Helm.

## Prerequisites

Before you begin, ensure that you have the following prerequisites:
- Kubernetes cluster set up and running.
- The cluster must support **dynamic provisioning of Persistent Volumes (PV)**. Refer to the [Kubernetes Dynamic Provisioning Guide](https://kubernetes.io/docs/concepts/storage/dynamic-provisioning/) for more details.
- Install `kubectl` on your system. Refer to [Installation Guide](https://kubernetes.io/docs/tasks/tools/install-kubectl/). Ensure access to the Kubernetes cluster.
- Install `helm` on your system. Refer to [Installation Guide](https://helm.sh/docs/intro/install/).

## Steps to deploy with Helm

You can deploy the ChatQ&A Core application using `Helm` in **two ways**: by pulling the Helm chart from Docker Hub or by building it from the source code. Follow the steps below based on your preferred method.

**_⚠️ Note: Steps 1–3 differ depending on whether you choose to pull the chart or build it from source._**

### Option 1: Pull the Helm Chart from Docker Hub

#### Step 1: Pull the Helm Chart

Use the following command to pull the Helm chart from [Docker Hub](https://hub.docker.com/r/intel/chat-question-and-answer-core):

```bash
helm pull oci://registry-1.docker.io/intel/chat-question-and-answer-core --version <version-no>
```

🔍 Refer to the [Docker Hub tags page](https://hub.docker.com/r/intel/chat-question-and-answer-core/tags) for details on the latest version number to use for the sample application.


#### Step 2: Extract the Chart

Unpack the downloaded .tgz file:

```bash
tar -xvf chat-question-and-answer-core-<version-no>.tgz
cd chat-question-and-answer-core
```

#### Step 3: Configure the `values.yaml` files

Edit the `values.yaml` file to set the necessary environment variables. Ensure you set the `huggingface.apiToken` and `proxy settings` as required.

Next, choose the appropriate `values*.yaml` file based on the model framework you want to use:

**Note:** Do not use special characters in configuration values.

- OpenVINO toolkit: Use `values-openvino.yaml`

- Ollama: Use `values-ollama.yaml`

For OpenVINO toolkit framework, models (embedding, reranker and LLM) are downloaded from [HuggingFace Hub](https://huggingface.co/). For Ollama framework, models (embdding and LLM) are pulled from the [Ollama model registry](https://ollama.com/library).

To enable GPU support, set the configuration parameter `gpu.enabled` to `true` and provide the corresponding `gpu.key` that assigned in your cluster node in the `values.yaml` file.

GPU support only enabled for OpenVINO toolkit framework.

For detailed information on supported and validated hardware platforms and configurations, please refer to the [Validated Hardware Platform](./system-requirements.md) section.


| Key | Description | Example Value | Required When | Supported Framework (OpenVINO/Ollama) |
| --- | ----------- | ------------- | ------------- | ------------------- |
| `configmap.enabled` | Enable use of ConfigMap for model configuration. Set to true to use ConfigMap; otherwise, defaults in the application are used. (true/false) | true | Always. Default to `true` in `values.yaml` | Both |
| `global.huggingface.apiToken` | Hugging Face API token | `<your-huggingface-token>` | Always | OpenVINO |
| `global.EMBEDDING_MODEL` | Embedding Model Name | OpenVINO:<br> - BAAI/bge-small-en-v1.5<br> <br> Ollama:<br> - bge-large | If `configmap.enabled = true` | Both |
| `global.LLM_MODEL	` | LLM model for OVMS | OpenVINO:<br> - microsoft/Phi-3.5-mini-instruct<br> <br> Ollama:<br> - phi3 | If `configmap.enabled = true` | Both |
| `global.RERANKER_MODEL` | Reranker model name	| BAAI/bge-reranker-base | If `configmap.enabled = true` | OpenVINO |
| `global.PROMPT_TEMPLATE` | RAG template for formatting input to the LLM. Supports {context} and {question}. Leave empty to use default. | See `values.yaml` for example | Optional | Both |
| `global.UI_NODEPORT` | Static port for UI service (30000–32767). Leave empty for automatic assignment. |  | Optional | Both |
| `global.keeppvc` | Persist storage (true/false) | false | Optional. Default to `false` in `values.yaml` | Both |
| `global.EMBEDDING_DEVICE` | Device for embedding (CPU/GPU) | CPU | Always. Default to `CPU` in `values.yaml` | OpenVINO |
| `global.RERANKER_DEVICE` | Device for reranker (CPU/GPU) | CPU | Always. Default to `CPU` in `values.yaml` | OpenVINO |
| `global.LLM_DEVICE` | Device for LLM (CPU/GPU) | CPU | Always. Default to `CPU` in `values.yaml` | OpenVINO |
| `global.MAX_TOKENS` | Number of output tokens | 1024 | Optional. Default to `1024`. Not more than 1024. | Both |
| `global.keep_alive` | Controls how long a loaded model remains in memory after it has been used. | Example:<br> - "1h" (str) - 1 hour<br> - "30m" (str) - 30 minutes<br> - 1800 (int) - 1800 seconds/30 minutes<br> - 0 (int) - unload immediately after use<br> - -1 (int) - forever | Optional. Default to `-1` in `values-ollama.yaml` | Ollama |
| `gpu.enabled` | Deploy on GPU (true/false) | false | Optional | OpenVINO |
| `gpu.key` | Label assigned to the GPU node on kubernetes cluster by the device plugin. Example - `gpu.intel.com/i915`, `gpu.intel.com/xe`. Identify by running `kubectl describe node` | `<your-node-key-on-cluster>` | If `gpu.enabled = true` | OpenVINO |

**🔍NOTE**:

- If `configmap.enabled` is set to false, the application will use its default internal configuration. You can view the default configuration template [here](../../model_config/sample/).

- If `gpu.enabled` is set to `false`, the parameters `global.EMBEDDING_DEVICE`, `global.RERANKER_DEVICE`, and `global.LLM_DEVICE` must not be set to `GPU`.
A validation check is included and will throw an error if any of these parameters are incorrectly set to `GPU` while `GPU support is disabled`.

- When `gpu.enabled` is set to `true`, the default value for these device parameters is GPU. On systems with an integrated GPU, the device ID is always 0 (i.e., GPU.0), and GPU is treated as an alias for GPU.0.
For systems with multiple GPUs (e.g., both integrated and discrete Intel GPUs), you can specify the desired devices using comma-separated IDs such as GPU.0, GPU.1 and etc.


### Option 2: Install from Source

#### Step 1: Clone the Repository

Clone the repository containing the Helm chart:

```bash
# Clone the release branch
git clone https://github.com/open-edge-platform/edge-ai-libraries.git -b release-2025.2.0
```

#### Step 2: Change to the Chart Directory

Navigate to the chart directory:

```bash
cd edge-ai-libraries/sample-applications/chat-question-and-answer-core/chart
```

#### Step 3: Configure the `values.yaml` File

Edit the `values.yaml` file located in the chart directory to set the necessary environment variables. Refer to the table in **Option 1, Step 3** for the list of keys and example values.

**Note:** Do not use special characters in configuration values.

#### Step 4: Build Helm Dependencies

Navigate to the chart directory and build the Helm dependencies using the following command:

```bash
helm dependency build
```

## Common Steps after configuration

### Step 5: Deploy the Helm Chart

Deploy the Chat Question-and-Answer Core Helm chart:

- Deploy with OpenVINO toolkit:

   ```bash
   helm install chatqna-core -f values.yaml -f values-openvino.yaml . --namespace <your-namespace>
   ```

- Deploy with Ollama:

   ```bash
   helm install chatqna-core -f values.yaml -f values-ollama.yaml . --namespace <your-namespace>
   ```

### Step 6: Verify the Deployment

Check the status of the deployed resources to ensure everything is running correctly

```bash
kubectl get pods -n <your-namespace>
kubectl get services -n <your-namespace>
```

### Step 7: Access the Application

Nginx service running as a reverse proxy in one of the pods, helps us to access the application. We need to get Host IP and Port on the node where the nginx service is running.

Run the following command and replace <$my_namespace> with your own namespace to get the host IP of the node and port exposed by Nginx service:

```bash
chatqna_hostip=$(kubectl get pods -l app=chatqna-core-nginx -n $my_namespace -o jsonpath='{.items[0].status.hostIP}')
chatqna_port=$(kubectl get service chatqna-core-nginx -n $my_namespace -o jsonpath='{.spec.ports[0].nodePort}')
echo "http://${chatqna_hostip}:${chatqna_port}"
```

Copy the output of the above bash snippet and paste it into your browser to access the application UI.

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
- If the PVC created during a Helm chart deployment is not removed or auto-deleted due to a deployment failure or being stuck, it must be deleted manually using the following commands:
  ```bash
  # List the PVCs present in the given namespace
  kubectl get pvc -n <namespace>

  # Delete the required PVC from the namespace
  kubectl delete pvc <pvc-name> -n <namespace>
  ```
## Related links

- [How to Build from Source](./build-from-source.md)
- [How to Benchmark](./benchmarks.md)
# Deploy with Helm

This guide provides step-by-step instructions for deploying the ChatQ&A Sample Application using Helm.

## Prerequisites

Before you begin, ensure that you have the following prerequisites:
- Kubernetes cluster set up and running.
- The cluster must support **dynamic provisioning of Persistent Volumes (PV)**. Refer to the [Kubernetes Dynamic Provisioning Guide](https://kubernetes.io/docs/concepts/storage/dynamic-provisioning/) for more details.
- Install `kubectl` on your system. Refer to [Installation Guide](https://kubernetes.io/docs/tasks/tools/install-kubectl/). Ensure access to the Kubernetes cluster.
- Helm installed on your system: [Installation Guide](https://helm.sh/docs/intro/install/).

## Steps to deploy with Helm

Following steps should be followed to deploy ChatQ&A using Helm. You can install from source code or pull the chart from Docker hub.

**_Steps 1 to 3 varies depending on if the user prefers to build or pull the Helm details._**

### Option 1: Install from Docker Hub

#### Step 1: Pull the Specific Chart

Use the following command to pull the Helm chart from [Docker Hub](https://hub.docker.com/r/intel/chat-question-and-answer):

```bash
helm pull oci://registry-1.docker.io/intel/chat-question-and-answer --version <version-no>
```

🔍 Refer to the [Docker Hub tags page](https://hub.docker.com/r/intel/chat-question-and-answer/tags) for details on the latest version number to use for the sample application.

#### Step 2: Extract the `.tgz` File

After pulling the chart, extract the `.tgz` file:

```bash
tar -xvf chat-question-and-answer-<version-no>.tgz
```

This will create a directory named `chat-question-and-answer` containing the chart files. Navigate to the extracted directory.

```bash
cd chat-question-and-answer
```

#### Step 3: Configure the right `values*.yaml` file

Choose the appropriate `values*.yaml` file based on the model server you want to use and set the necessary environment variables:

- **For OVMS**: Use `values_ovms.yaml`.
- **For vLLM**: Use `values_vllm.yaml`.
- **For TGI**: Use `values_tgi.yaml`.

Note: If deploying from a cloned repo, the user can choose to edit only the `values.yaml` file which is symlinked to `values_ovms.yaml` as default option. When the chart is downloaded from registry, the symlink gets removed and the user should use the preferred `values*.yaml` file.

Ensure you set the `huggingface.apiToken` and proxy settings as required.

| Key | Description | Example Value |
| --- | ----------- | ------------- |
| `global.huggingface.apiToken` | Your Hugging Face API token                      | `<your-huggingface-token>` |
| `global.POSTGRES_USER`  | Give User name for PG Vector DB | `<your-postgres-user-id>` |
| `global.POSTGRES_PASSWORD`  | Give pwd for PG Vector DB | `<your-postgres-password>` |
| `global.MINIO_ROOT_USER`   | A Minio server user name | `<your-minio-user-id>` (user length should be at least 3) |
| `global.MINIO_ROOT_PASSWORD`| A password to connect to minio server | `<your-minio-password>` (password length should be at least 8 characters) |
| `global.OTLP_ENDPOINT` | OTLP endpoint | |
| `global.OTLP_ENDPOINT_TRACE` | OTLP endpoint for trace | |
| `global.teiEmbeddingService.enabled` | Flag to enable TEI embedding model server | `false` |
| `global.ovmsEmbeddingService.enabled` | Flag to enable OVMS embedding model server | `true` |
| `global.UI_NODEPORT` | Sets the static port (in the 30000–32767 range) | |
| `global.keeppvc` | Set true to persists the storage. Default is false | false |
| `global.ovmsEmbeddinggpuService.enabled` | To Enable OVMS Embedding on GPU | false |
| `global.GPU.enabled` | For model server deployed on GPU | false |
| `global.GPU.key` | Label assigned to the GPU node on kubernetes cluster by the device plugin example- gpu.intel.com/i915, gpu.intel.com/xe. Identify by running kubectl describe node <gpu-node> | `<your-node-key-on-cluster>` |
| `global.GPU.device` | Default is GPU, If the system has an integrated GPU, its id is always 0 (GPU.0). The GPU is an alias for GPU.0. If a system has multiple GPUs (for example, an integrated and a discrete Intel GPU) It is done by specifying GPU.1,GPU.0 | GPU |
| `Chatqna.name` | Name of the ChatQnA application                        | `chatqna` |
| `Chatqna.image.repository` | image repository url                | `intel/chatqna` |
| `Chatqna.image.tag` | latest image tag                                  | `2.0.1`   |
| `Chatqna.env.ENDPOINT_URL` | connection endpoint to model server |              |
| `Chatqna.env.INDEX_NAME` | index name for pgVector                      | `intel-rag` |
| `Chatqna.env.FETCH_K` |  Number of top K results to fetch               | `10` |
| `Chatqna.global.EMBEDDING_MODEL_NAME`|   embedding model name                        | `Alibaba-NLP/gte-large-en-v1.5`|
| `Chatqna.env.PG_CONNECTION_STRING` |    pgvector connection string      | `postgresql+psycopg://`|
| `Chatqna.env.LLM_MODEL` |  model to be used with tgi/vllm/ovms               | `Qwen/Qwen2.5-7B-Instruct`|
| `Chatqna.env.RERANKER_MODEL` |  model to be used with tei               | `BAAI/bge-reranker-base`|

NOTE: GPU is only enabled for openvino model server (OVMS)

### Option 2: Install from Source

#### Step 1: Clone the Repository

Clone the repository containing the Helm chart:

```bash
# Clone the latest on mainline
git clone https://github.com/open-edge-platform/edge-ai-libraries.git edge-ai-libraries
# Alternatively, Clone a specific release branch
git clone https://github.com/open-edge-platform/edge-ai-libraries.git edge-ai-libraries -b <release-tag>
```

#### Step 2: Change to the Chart Directory

Navigate to the chart directory:

```bash
cd edge-ai-libraries/sample-applications/chat-question-and-answer/chart
```

#### Step 3: Configure the `values*.yaml` File

Edit the `values*.yaml` file located in the chart directory to set the necessary environment variables. Refer to the table in **Option 1, Step 3** for the list of keys and example values.

#### Step 4: Build Helm Dependencies

Navigate to the chart directory and build the Helm dependencies using the following command:

```bash
helm dependency build
```

## Common Steps after configuration

### Step 5: Deploy the Helm Chart

Deploy the OVMS Helm chart:

```bash
helm install chatqna . -f values_ovms.yaml -n <your-namespace>
```

**Note:** (1) If deploying from cloned repo, using `values.yaml` also works as it points to `values_ovms.yaml` file as default option. (2) When deploying OVMS, the OVMS service is observed to take more time than other model serving due to model conversion time.

Deploy the vLLM Helm chart:

```bash
helm install chatqna . -f values_vllm.yaml -n <your-namespace>
```

Deploy the TGI Helm chart:

```bash
helm install chatqna . -f values_tgi.yaml -n <your-namespace>
```

### Step 6: Verify the Deployment

Check the status of the deployed resources to ensure everything is running correctly

```bash
kubectl get pods -n <your-namespace>
kubectl get services -n <your-namespace>
```

### Step 7: Access the Application

Open the UI in a browser at `http://<node-ip>:<ui-node-port>`

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
- [How to Test Performance](../how-to-performance.md)
- [How to Benchmark](../benchmarks.md)

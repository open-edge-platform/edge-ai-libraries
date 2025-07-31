# How to deploy with Helm\* Chart

This section shows how to deploy the Video Search and Summary Sample Application using Helm chart.

## Prerequisites
Before you begin, ensure that you have the following:
- Kubernetes\* cluster set up and running.
- The cluster must support **dynamic provisioning of Persistent Volumes (PV)**. Refer to the [Kubernetes Dynamic Provisioning Guide](https://kubernetes.io/docs/concepts/storage/dynamic-provisioning/) for more details.
- Install `kubectl` on your system. See the [Installation Guide](https://kubernetes.io/docs/tasks/tools/install-kubectl/). Ensure access to the Kubernetes cluster. 
- Helm chart installed on your system. See the [Installation Guide](https://helm.sh/docs/intro/install/).

## Steps to deploy with Helm
Do the following to deploy VSS using Helm chart. 

**_Steps 1 to 3 varies depending on if the user prefers to build or pull the Helm details._**

### Option 1: Install from Docker Hub

#### Step 1: Pull the Specific Chart

Use the following command to pull the Helm chart from Docker Hub:
```bash
helm pull oci://registry-1.docker.io/intel/video-search-and-summarization --version <version-no>
```

Refer to the release notes for details on the latest version number to use for the sample application.

#### Step 2: Extract the `.tgz` File

After pulling the chart, extract the `.tgz` file:
```bash
tar -xvf video-search-and-summarization-<version-no>.tgz
```

This will create a directory named `video-search-and-summarization` containing the chart files. Navigate to the extracted directory. 
```bash
cd video-search-and-summarization
```

#### Step 3: Configure the `values.yaml` File

Edit the `values.yaml` file to set the necessary environment variables. At minimum, ensure you set the services credentials and proxy settings as required.

| Key | Description | Example Value |
| --- | ----------- | ------------- |
| `global.huggingface.apiToken` | Your Hugging Face API token | `<your-huggingface-token>` |
| `global.proxy.http_proxy` | HTTP proxy if required | `http://proxy-example.com:000` |
| `global.proxy.https_proxy` | HTTPS proxy if required | `http://proxy-example.com:000` |
| `global.env.UI_NODEPORT` | UI service NodePort | `31998` |
| `global.env.POSTGRES_USER` | PostgreSQL user | `<your-postgres-user>` |
| `global.env.POSTGRES_PASSWORD` | PostgreSQL password | `<your-postgres-password>` |
| `global.env.POSTGRES_DB` | PostgreSQL database name | `video_summary_db` |
| `global.env.MINIO_ROOT_USER` | MinIO server user name | `<your-minio-user>` (at least 3 characters) |
| `global.env.MINIO_ROOT_PASSWORD` | MinIO server password | `<your-minio-password>` (at least 8 characters) |
| `global.env.MINIO_PROTOCOL` | MinIO protocol | `http:` |
| `global.env.MINIO_BUCKET` | MinIO bucket name | `video-search-summary` |
| `global.env.RABBITMQ_DEFAULT_USER` | RabbitMQ username | `<your-rabbitmq-username>` |
| `global.env.RABBITMQ_DEFAULT_PASS` | RabbitMQ password | `<your-rabbitmq-password>` |
| `global.env.VLM_MODEL_NAME` | VLM model to use | `Qwen/Qwen2.5-VL-7B-Instruct` |
| `global.env.OVMS_LLM_MODEL_NAME` | OVMS LLM model (when using OVMS) | `Intel/neural-chat-7b-v3-3` |
| `global.env.OTLP_ENDPOINT` | OTLP endpoint | Leave empty if not using telemetry |
| `global.env.OTLP_ENDPOINT_TRACE` | OTLP trace endpoint | Leave empty if not using telemetry |
| `global.env.keeppvc` | Set true to persists the storage. Default is false | false |

### Option 2: Install from Source

#### Step 1: Clone the Repository

Clone the repository containing the Helm chart:
```bash
git clone <repo>
```

#### Step 2: Change to the Chart Directory

Navigate to the chart directory:
```bash
cd <repo>/sample-applications/video-search-and-summarization/chart
```

#### Step 3: Configure the `values.yaml` File

Edit the `values.yaml` file located in the chart directory to set the necessary environment variables. Refer to the table in **Option 1, Step 3** for the list of keys and example values.
Choose the appropriate `*.yaml` file based on the model server/usecase you want to use:


### Step 4: Build Helm Dependencies

Navigate to the chart directory and build the Helm dependencies using the following command:

```bash
helm dependency build
```

### Step 5: Deploy the Helm Chart

Depending on your use case, deploy the Helm chart using the appropriate command.

> NOTE: Before switching to a different mode always stop the current application stack by running:

```bash
helm uninstall vss -n <your-namespace>
```

#### **Use Case 1: Video Summary Only**

Deploy the Video Summary application:

```bash
helm install vss . -f summary_override.yaml -n <your-namespace>
```

> Note delete the chart for installing the chart in other modes `helm uninstall vss -n <your-namespace>`

Replace `<your-namespace>` with your desired Kubernetes namespace.

> Note: If your namespace doesn't exist yet, create it with `kubectl create namespace <your-namespace>` before running the helm install command.

##### **Sub Use Case 1: Video Summary with OVMS**

If you want to use OVMS for LLM Summarization, deploy with the OVMS override values:

```bash
helm install vss . -f summary_override.yaml -f ovms_override.yaml -n <your-namespace>
```
**Note:** When deploying OVMS, the OVMS service may take more time to start due to model conversion.

#### **Use Case 2: Video Search Only**

To deploy only the Video Search functionality, use the search override values:

```bash
helm install vss . -f search_override.yaml -n <your-namespace>
```

### Step 6: Verify the Deployment

Check the status of the deployed resources to ensure everything is running correctly:

```bash
kubectl get pods -n <your-namespace>
kubectl get services -n <your-namespace>
```

Ensure all pods are in the "Running" state before proceeding.

### Step 7: Retrieving the Service Endpoint (NodePort and NodeIP)

To access the vss-nginx service running in your Kubernetes cluster using NodePort, you need to retrieve:

- NodeIP – The internal IP of a worker node.
- NodePort – The port exposed by the service (default is 31998 as specified in values.yaml).

Run the following command to get the service URL:
```bash
echo "http://$(kubectl get pods -l app=vss-nginx -n <your-namespace> -o jsonpath='{.items[0].status.hostIP}')":<ui-nodeport>
```

Simply copy and paste the output into your browser to access the Video Summary application UI.

### Step 8: Update Helm Dependencies

If any changes are made to the subcharts, update the Helm dependencies using the following command:

```bash
helm dependency update
```

### Step 9: Uninstall Helm chart

To uninstall the Video Summary Helm chart, use the following command:

```bash
helm uninstall vss -n <your-namespace>
```

## Verification

- Ensure that all pods are running and the services are accessible.
- Access the Video Summary application dashboard and verify that it is functioning as expected.
- Upload a test video to verify that the ingestion, processing, and summary pipeline works correctly.
- Check that all components (MinIO, PostgreSQL, RabbitMQ, video ingestion, VLM inference, audio analyzer) are functioning properly.

## Troubleshooting

- If you encounter any issues during the deployment process, check the Kubernetes logs for errors:
  ```bash
  kubectl logs <pod-name> -n <your-namespace>
  ```

- For component-specific issues:
  - Video ingestion problems: Check the logs of the videoingestion pod
  - VLM inference issues: Check the logs of the vlm-inference-microservice pod
  - Database connection problems: Verify the PostgreSQL pod is running correctly
  - Storage issues: Check the MinIO server status and connectivity

- If you're experiencing issues with the Hugging Face API, ensure your API token is valid and properly set in the values.yaml file.

## Related links
- [How to Build from Source](./build-from-source.md)
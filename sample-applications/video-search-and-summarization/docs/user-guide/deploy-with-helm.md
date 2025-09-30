# How to deploy with Helm\* Chart

This section shows how to deploy the Video Search and Summary Sample Application using Helm chart.

## Prerequisites
Before you begin, ensure that you have the following:
- Kubernetes\* cluster set up and running.
- The cluster must support **dynamic provisioning of Persistent Volumes (PV)**. Refer to the [Kubernetes Dynamic Provisioning Guide](https://kubernetes.io/docs/concepts/storage/dynamic-provisioning/) for more details.
- Install `kubectl` on your system. See the [Installation Guide](https://kubernetes.io/docs/tasks/tools/install-kubectl/). Ensure access to the Kubernetes cluster. 
- Helm chart installed on your system. See the [Installation Guide](https://helm.sh/docs/intro/install/).
- **Storage Requirement :** Application requests for **50GiB** of storage in its default configuration. (This should change with choice of models and needs to be properly configured). Please make sure that required storage is available in you cluster.
- Video Search and Summary requires PVC storage class to support `RWMany` mode. In case the default storage class used does not support it, consider using storage solution like [LongHorn](https://longhorn.io/docs/) that provides this support. Video Search and Summary intends to remove this prerequisite in future release and use only `RWOnce` mode. 

## Helm Chart Installation

In order to setup the end-to-end application, we need to acquire the charts and install it with optimal values and configurations. Subsequent sections will provide step by step details for the same.

### 1. Acquire the helm chart

There are 2 options to get the charts in your workspace:

#### Option 1: Get the charts from Docker Hub

##### Step 1: Pull the Specific Chart

Use the following command to pull the Helm chart from Docker Hub:
```bash
helm pull oci://registry-1.docker.io/intel/video-search-and-summarization --version <version-no>
```

Refer to the release notes for details on the latest version number to use for the sample application.

##### Step 2: Extract the `.tgz` File

After pulling the chart, extract the `.tgz` file:
```bash
tar -xvf video-search-and-summarization-<version-no>.tgz
```

This will create a directory named `video-search-and-summarization` containing the chart files. Navigate to the extracted directory to access the charts.

```bash
cd video-search-and-summarization
```

#### Option 2: Install from Source

##### Step 1: Clone the Repository

Clone the repository containing the Helm chart:
```bash
git clone https://github.com/open-edge-platform/edge-ai-libraries.git
```

##### Step 2: Change to the Chart Directory

Navigate to the chart directory:

```bash
cd edge-ai-libraries/sample-applications/video-search-and-summarization/chart
```


### 2. Configure Required Values

The application requires several values to be set by user in order to work. To make it easier, we have included a `user_values_override.yaml` file, which contains only the values that user needs to tweak. Open the file in your favorite editor or use nano:

```bash
nano user_values_override.yaml
```

Update or edit the values in YAML file as follows:

| Key | Description | Example Value |
| --- | ----------- | ------------- |
| `global.pvcName` | Name for PVC to be used for storage by all components of application | `vss-shared-pvc` |
| `global.keepPvc` | PVC gets deleted by default once helm is uninstalled. Set this to true to persist PVC (helps avoid delay due to model re-downloads when re-installing chart). | `true` or `false` |
| `global.huggingfaceToken` | Your Hugging Face API token | `<your-huggingface-token>` |
| `global.proxy.http_proxy` | HTTP proxy if required | `http://proxy-example.com:000` |
| `global.proxy.https_proxy` | HTTPS proxy if required | `http://proxy-example.com:000` |
| `global.vlmName` | VLM model to be used by VLM Inference Microservice | `Qwen/Qwen2.5-VL-7B-Instruct` |
| `global.llmName` | LLM model to be used by OVMS (used only when OVMS is enabled)| `Intel/neural-chat-7b-v3-3` |
| `global.env.POSTGRES_USER` | PostgreSQL user | `<your-postgres-user>` |
| `global.env.POSTGRES_PASSWORD` | PostgreSQL password | `<your-postgres-password>` |
| `global.env.MINIO_ROOT_USER` | MinIO server user name | `<your-minio-user>` (at least 3 characters) |
| `global.env.MINIO_ROOT_PASSWORD` | MinIO server password | `<your-minio-password>` (at least 8 characters) |
| `global.env.RABBITMQ_DEFAULT_USER` | RabbitMQ username | `<your-rabbitmq-username>` |
| `global.env.RABBITMQ_DEFAULT_PASS` | RabbitMQ password | `<your-rabbitmq-password>` |
| `global.env.OTLP_ENDPOINT` | OTLP endpoint | Leave empty if not using telemetry |
| `global.env.OTLP_ENDPOINT_TRACE` | OTLP trace endpoint | Leave empty if not using telemetry |
| `videoingestion.odModelName` | Name of object detection model used during video ingestion | `yolov8l-worldv2` |
| `videoingestion.odModelType` | Type/Category of the object detection Model | `yolo_v8` |
| `multimodalembeddingms.textEmbeddingModel` | Embedding model name used in unified video search and summary | `Qwen/Qwen3-Embedding-0.6B` |
| `multimodalembeddingms.imageEmbeddingModel` | Embedding model name used in standalone video search application | `openai/clip-vit-base-patch32` |


### 3. Build Helm Dependencies

Navigate to the chart directory and build the Helm dependencies using the following command:

```bash
helm dependency update
```

### 4. Set and Create a Namespace

We will install the helm chart in a new namespace. Create a shell variable to refer a new namespace and create it.

1. Refer a new namespace using shell variable `my_namespace`. Set any desired unique value.

    ```bash
    my_namespace=foobar
    ```

2. Create the Kubernetes namespace. If it is already created, creation will fail. You can update the namespace in previous step and try again.

    ```bash
    kubectl create namespace $my_namespace
    ```

> **_NOTE :_** All subsequent steps assume that you have `my_namespace` variable set and accessible on your shell with the desired namespace as its value.


### 5. Deploy the Helm Chart

At present, there are 4 use-cases for **Video Search and Summarization Application**. We will learn how to deploy each use-case using the helm chart.

> **_NOTE :_** Before switching to a different use-case always stop the current running use-case's application stack (if any) by uninstalling the chart : `helm uninstall vss -n $my_namespace`. This is not required if you are installing the helm chart for the first time.

#### **Use Case 1: Video Summarization Only (Using VLM Microservice)**

Deploy the Video Summarization application:

```bash
helm install vss . -f summary_override.yaml -f user_values_override.yaml -n $my_namespace
```

> **_NOTE :_** Delete the chart for installing the chart in other modes `helm uninstall vss -n $my_namespace`

#### **Use Case 2: Video Summarization with OVMS Microservice (OpenVINO Model Serving)**

If you want to use OVMS for LLM Summarization, deploy with the OVMS override values:

```bash
helm install vss . -f summary_override.yaml -f ovms_override.yaml -f user_values_override.yaml -n $my_namespace
```
**Note:** When deploying OVMS, the OVMS service may take more time to start due to model conversion.

#### **Use Case 3: Video Search Only**

To deploy only the Video Search functionality, use the search override values:

```bash
helm install vss . -f search_override.yaml -f user_values_override.yaml -n $my_namespace
```

#### **Use Case 4: Unified Video Search and Summarization**

To deploy only the Video Search functionality, use the search override values:

```bash
helm install vss . -f unified_summary_search.yaml -f user_values_override.yaml -n $my_namespace
```

### Step 6: Verify the Deployment

Check the status of the deployed resources to ensure everything is running correctly:

```bash
kubectl get pods -n $my_namespace
```

**Before proceeding to access the application we must ensure the following status of output of the above command:**

1. Ensure all pods are in the "Running" state. This is denoted by **Running** state mentioned in the **STATUS** column.

2. Ensure all containers in each pod are _Ready_. As all pods are running single container only, this is typically denoted by mentioning **1/1** in the **READY** column.

> **_IMPORTANT NOTE :_** When deployed for first time, it may take up-to around 50 Mins to bring all the pods/containers in running and ready state, as several containers try to download models which can take a while. The time to bring up all the pods depends on several factors including but not limited to node availability, node load average, network speed, compute availability etc.

> **_IMPORTANT NOTE :_** If you want to persist the downloaded models and avoid delays pertaining to model downloads when re-installing the charts, please set the `global.keepPvc` value to `true` in `user_values_override.yaml` file before installing the chart.

### Step 7: Accessing the application

Nginx service running as a reverse proxy in one of the pods, helps us to access the application. We need to get Host IP and Port on the node where the nginx service is running. 

Run the following command to get the host IP of the node and port exposed by Nginx service:

```bash
vss_hostip=$(kubectl get pods -l app=vss-nginx -n $my_namespace -o jsonpath='{.items[0].status.hostIP}')
vss_port=$(kubectl get service vss-nginx -n $my_namespace -o jsonpath='{.spec.ports[0].nodePort}')
echo "http://${vss_hostip}:${vss_port}"
```

Copy the output of above bash snippet and paste it into your browser to access the **Video Search and Summarization Application**.

### Step 8: Update Helm Dependencies

If any changes are made to the sub-charts, always remember to update the Helm dependencies using the following command before re-installing or upgrading your helm installation:

```bash
helm dependency update
```

### Step 9: Uninstall Helm chart

To uninstall the Video Summary Helm chart, use the following command:

```bash
helm uninstall vss -n $my_namespace
```

## Updating PVC Storage Size

If any of the microservice requires more or less storage than the default allotted storage in values file, this can be overridden for one or more services.

### Updating storage for VDMS-Dataprep and MultiModal Embedding Service

Set the required `sharedClaimSize` value while installing the helm chart. 

For example, if installing chart in search only mode :

```bash
helm install vss . -f search_override.yaml -f user_values_override.yaml --set sharedClaimSize=10Gi -n $my_namespace
```

If installing the chart in combined search and summary mode :

```bash
helm install vss . -f unified_summary_search.yaml -f user_values_override.yaml --set sharedClaimSize=10Gi -n $my_namespace
```

### Updating storage for other microservices

To update storage for other microservices we can, override the corresponding `claimSize` value in the main chart values file, while installing the chart.

For example, for updating storage for VLM-Inference Microservice in summary mode :

```bash
helm install vss . -f summary_override.yaml -f user_values_override.yaml --set vlminference.claimSize=50Gi -n $my_namespace
```

Similarly, for updating storage for OVMS in summary mode, we can install the chart in following ways :

```bash
helm install vss . -f summary_override.yaml -f user_values_override.yaml -f ovms_override.yaml --set ovms.claimSize=10Gi -n $my_namespace
```

Let's look at one more example, for updating storage for Minio Server in combined search and summary mode :

```bash
helm install vss . -f unified_summary_search.yaml -f user_values_override.yaml --set minioserver.claimSize=10Gi -n $my_namespace
```

If not set while installing the chart, all services will claim a default amount of storage set in the values file.

## Verification

- Ensure that all pods are running and the services are accessible.
- Access the Video Summary application dashboard and verify that it is functioning as expected.
- Upload a test video to verify that the ingestion, processing, and summary pipeline works correctly.
- Check that all components (MinIO, PostgreSQL, RabbitMQ, video ingestion, VLM inference, audio analyzer) are functioning properly.

## Troubleshooting

- **Pods not coming in Ready or Running state for a long time.**

  There could be several possible reasons for this. Most likely reasons are storage unavailability, node unavailability, network slow-down or faulty network etc. Please check with your cluster admin or try fresh installation of charts, **after deleting the PVC _(see next issue)_ and un-installing the current chart**.

- **All containers Ready, all Pods in Running state, application UI is accessible but search or summary is failing.**

  If PVC has been configured to be retained, most common reason for application to fail to work is a stale PVC. This problem most likely occurs when helm charts are re-installed after some updates to helm chart or the application image. To fix this, delete the PVC before re-installing the helm chart by following command:

    ```bash
    kubectl delete pvc vss-shared-pvc -n <your_namespace>
    ```

  If you have updated the `global.pvcName` in the values file, use the updated name instead of default PVC name `vss-shared-pvc` in above command.

- If you encounter any issues during the deployment process, check the Kubernetes logs for errors:

    ```bash
    kubectl logs <pod-name> -n $my_namespace
    ```

- For component-specific issues:
  - Video ingestion problems: Check the logs of the videoingestion pod
  - VLM inference issues: Check the logs of the vlm-inference-microservice pod
  - Database connection problems: Verify the PostgreSQL pod is running correctly
  - Storage issues: Check the MinIO server status and connectivity

- Some issues might be fixed by freshly setting up storage. This is helpful in cases where deletion of PVC is prohibited by configuration on charts un-installation (when `global.keepPvc` is set to true):

    ```bash
    kubectl delete pvc <pvc-name> -n $my_namespace
    ```

- If you're experiencing issues with the Hugging Face API, ensure your API token `global.huggingfaceToken` is valid and properly set in the `user_values_override.yaml` file.

## Related links
- [How to Build from Source](./build-from-source.md)

# How to deploy with Helm

This guide provides step-by-step instructions for deploying the Document Summarization Sample Application using Helm.

## Prerequisites

Before you begin, ensure that you have the following prerequisites:
- Kubernetes cluster set up and running.
- The cluster must support **dynamic provisioning of Persistent Volumes (PV)**. Refer to the [Kubernetes Dynamic Provisioning Guide](https://kubernetes.io/docs/concepts/storage/dynamic-provisioning/) for more details.
- Install `kubectl` on your system. Refer to [Installation Guide](https://kubernetes.io/docs/tasks/tools/install-kubectl/). Ensure access to the Kubernetes cluster.
- Helm installed on your system: [Installation Guide](https://helm.sh/docs/intro/install/).

## Steps to deploy with Helm

Following steps should be followed to deploy Document Summarization application using Helm. You can install from source code or pull the chart from Docker hub.

**_Steps 1 to 3 varies depending on if the user prefers to build or pull the Helm details._**

### Option 1: Install from Docker Hub

#### Step 1: Pull the Specific Chart

Use the following command to pull the Helm chart from [Docker Hub](https://hub.docker.com/r/intel/document-summarization):
```bash
helm pull oci://registry-1.docker.io/intel/document-summarization --version <version-no>
```

🔍 Refer to the [Docker Hub tags page](https://hub.docker.com/r/intel/document-summarization/tags) for details on the latest version number to use for the sample application.

Refer to the release notes for details on the latest version number to use for the sample application.

#### Step 2: Extract the `.tgz` File

After pulling the chart, extract the `.tgz` file:
```bash
tar -xvf document-summarization-<version-no>.tgz
```

This will create a directory named `document-summarization` containing the chart files. Navigate to the extracted directory. 
```bash
cd document-summarization
```

#### Step 3: Configure the `values.yaml` File

Edit the `values.yaml` file to set the necessary environment variables. Ensure you set the proxy settings as required.

| Key | Description | Example Value |
| --- | ----------- | ------------- |
| `global.proxy.noProxy` | NOPROXY | `<your-no-proxy>` |
| `global.proxy.httpProxy` | HTTP PROXY | `<your-http-proxy>` |
| `global.proxy.httpsProxy` | HTTPS PROXY | `<your-https-proxy>` |
| `global.huggingface.token` | Your Hugging Face API token | `<your-huggingface-token` |
| `global.ui.nodePort` | Sets the static port (in the 30000–32767 range) | |
| `global.otlp` | OTLP Endpoint | `<your-otlp-endpoint>` |
| `global.llm.llmModelId` | Model to be used with ovms | Intel/neural-chat-7b-v3-3 or microsoft/Phi-3.5-mini-instruct |


### Option 2: Install from Source

#### Step 1: Clone the Repository

Clone the repository containing the Helm chart:
```bash
git clone <repository-url>
```

#### Step 2: Change to the Chart Directory

Navigate to the chart directory:
```bash
cd <repository-url>/sample-applications/document-summarization/chart
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

Deploy the Document Summarization Helm chart:

```bash
helm install document-summarization . -n <your-namespace>
```
**Note:** When deploying OVMS, the OVMS service is observed to take more time than other model serving due to model conversion time.

### Step 6: Verify the Deployment

Check the status of the deployed resources to ensure everything is running correctly

```bash
kubectl get pods -n <your-namespace>
kubectl get services -n <your-namespace>
```

### Step 7: Retrieving the Service Endpoint (NodePort and NodeIP)

To access a docsum-nginx service running in your Kubernetes cluster using NodePort, you need to retrieve:

- NodeIP – The internal IP of a worker node.
- NodePort – The port exposed by the service.

Run the following command after replacing \<ui-node-port\> with your actual values:
```bash
  kubectl get nodes -o wide | awk '$2 == "Ready" {print $6 ":<ui-node-port>"; exit}'
```
Simply copy and paste the output into your browser.

### Step 8: Update Helm Dependencies

If any changes are made to the subcharts, update the Helm dependencies using the following command:

```bash
helm dependency update
```
### Step 9: Uninstall Helm chart

To uninstall helm charts deployed, use the following command:

```bash
helm uninstall document-summarization -n <your-namespace>
```

## Verification

- Ensure that all pods are running and the services are accessible.
- Access the application dashboard and verify that it is functioning as expected.

## Troubleshooting

- If you encounter any issues during the deployment process, check the Kubernetes logs for errors:
  ```bash
  kubectl logs <pod-name>
  ```
- The _PVC_ created during helm chart deployment will remain present until explicitly deleted, use the below command to delete:
  ```bash
  kubectl delete pvc <pvc-name> -n <namespace>
  ```
## Related links

- [How to Build from Source](./build-from-source.md)
- [How to Test Performance](./how-to-performance.md)

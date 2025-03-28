# How to deploy with Helm

This guide provides step-by-step instructions for deploying the Chat Question-and-Answer Core Sample Application using Helm.

## Prerequisites

Before you begin, ensure that you have the following prerequisites:
- Kubernetes cluster set up and running.
- Install `kubectl` on your system. Refer to [Installation Guide](https://kubernetes.io/docs/tasks/tools/install-kubectl/). Ensure access to the Kubernetes cluster.
- Helm installed on your system: [Installation Guide](https://helm.sh/docs/intro/install/).

## Steps to deploy with Helm

Following steps should be followed to deploy ChatQ&A using Helm.

### Step 1: Change to chart directory

```bash
cd chart
```

### Step 2: Configure the values.yaml file

Edit the `values.yaml` file located in the chart directory to set the necessary environment variables. Ensure you set the `huggingface.apiToken` and proxy settings as required.

| Key | Description | Example Value |
| --- | ----------- | ------------- |
| `global.huggingface.apiToken` | Your Hugging Face API token      | `<your-huggingface-token>` |
| `global.EMBEDDING_MODEL_NAME`|   embedding model name      | BAAI/bge-small-en-v1.5|
| `global.RERANKER_MODEL`  | reranker model name   | BAAI/bge-reranker-base   |
| `global.LLM_MODEL` |  model to be used with ovms     | Intel/neural-chat-7b-v3-3|

### Step 3: Build Helm Dependencies

Navigate to the chart directory and build the Helm dependencies using the following command:

```bash
helm dependency build
```

### Step 4: Deploy the Helm Chart

Deploy the Chat Question-and-Answer Core Helm chart:

```bash
helm install chatqna-core .  \
  --set global.huggingface.apiToken=<your-huggingface-token> \
  --set global.http_proxy=<your proxy>  \
  --set global.https_proxy=<your proxy>\
  --set global.no_proxy=<your proxy> \
  --set global.LLM_MODEL=<LLM model>  \
  --set global.EMBEDDING_MODEL_NAME=<embedding_model> \
  --set global.RERANKER_MODEL=<reranker model>  \
  --namespace <YOUR_NAMESPACE>
```

### Step 5: Verify the Deployment

Check the status of the deployed resources to ensure everything is running correctly

```bash
kubectl get pods -n <YOUR_NAMESPACE>
kubectl get services -n <YOUR_NAMESPACE>
```

### Step 6: Retrieving the Service Endpoint (NodePort and NodeIP)

To access a chatqna-core-nginx service running in your Kubernetes cluster using NodePort, you need to retrieve:

- NodeIP – The internal IP of a worker node.
- NodePort – The port exposed by the service.

Run the following command after replacing \<NAMESPACE\> with your actual values:

```bash
echo "http://$(kubectl get nodes -o jsonpath='{.items[0].status.addresses[?(@.type=="InternalIP")].address}'):$(kubectl get svc chatqna-core-nginx -n <YOUR_NAMESPACE> -o jsonpath='{.spec.ports[0].nodePort}')"
```
Simply copy and paste the output into your browser.

### Step 7: Update Helm Dependencies

If any changes are made to the subcharts, update the Helm dependencies using the following command:

```bash
helm dependency update
```
### Step 8: Uninstall Helm chart

To uninstall helm charts deployed, use the following command:

```bash
helm uninstall <name> -n <YOUR_NAMESPACE>
```

## Verification

- Ensure that all pods are running and the services are accessible.
- Access the application dashboard and verify that it is functioning as expected.

## Troubleshooting

- If you encounter any issues during the deployment process, check the Kubernetes logs for errors:
  ```bash
  kubectl logs <pod_name>
  ```

## Related links

- [How to Build from Source](./build-from-source.md)
- [How to Benchmark](./benchmarks.md)

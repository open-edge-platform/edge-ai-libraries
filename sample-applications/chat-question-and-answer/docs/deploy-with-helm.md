# How to deploy with Helm

This guide provides step-by-step instructions for deploying the ChatQ&A Sample Application using Helm.

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
| `global.huggingface.apiToken` | Your Hugging Face API token                      | `<your-huggingface-token>` |
| `global.POSTGRES_USER`  | Give User name for PG Vector DB | `<your-postgres-user-id>` |
| `global.POSTGRES_PASSWORD`  | Give pwd for PG Vector DB | `<your-postgres-password>` |
| `global.MINIO_ROOT_USER`   | A Minio server user name | `<your-minio-user-id> (MINIO_ROOT_USER length should be at least 3)` |
| `global.MINIO_ROOT_PASSWORD`| A password to connect to minio server | `<your-minio-password>` (MINIO_ROOT_PASSWORD length at least 8 characters) |
| `global.OTLP.endpoint` | OTLP Endpoint | |
| `global.OTLP.trace_endpoint` | OTLP Endpoint for Trace | |
| `Chatqna.name` | Name of the ChatQnA application                        | `chatqna` |
| `Chatqna.image.repository` | image repository url                | `intel/chatqna` |
| `Chatqna.image.tag` | latest image tag                                  | `1.1.1`   |
| `Chatqna.env.ENDPOINT_URL` | connection endpoint to model server |              |
| `Chatqna.env.INDEX_NAME` | index name for pgVector                      | intel-rag |
| `Chatqna.env.FETCH_K` |  Number of top K results to fetch               | 10 |
| `Chatqna.global.EMBEDDING_MODEL_NAME`|   embedding model name                        | BAAI/bge-small-en-v1.5|
| `Chatqna.env.PG_CONNECTION_STRING` |    pgvector connection string      | `postgresql+psycopg://`|
| `Chatqna.env.LLM_MODEL` |  model to be used with tgi/vllm/ovms               | Intel/neural-chat-7b-v3-3|

### Step 3: Build Helm Dependencies

Navigate to the chart directory and build the Helm dependencies using the following command:

```bash
helm dependency build
```

### Step 4: Deploy the Helm Chart

Deploy the OVMS Helm chart:

```bash
helm install chatqna . \
  --set global.huggingface.apiToken=<your-huggingface-token> \
  --set global.proxy.http_proxy=<your-proxy> \
  --set global.proxy.https_proxy=<your-proxy> \
  --set global.proxy.no_proxy=<your-no-proxy> \
  --set global.POSTGRES_USER=<postgres-user> \
  --set global.POSTGRES_PASSWORD=<postgres-password> \
  --set global.MINIO_ROOT_USER=<minio-root-user> \
  --set global.MINIO_ROOT_PASSWORD=<minio-root-password> \
  --set global.LLM_MODEL=<llm-model> \
  --set global.EMBEDDING_MODEL_NAME=<embedding-model> \
  --set global.RERANKER_MODEL=<reranker-model> \
  --set global.ovmsEmbeddingService.enabled=true \
  --namespace <your-namespace>
```
**Note:** When deploying OVMS, the OVMS service is observed to take more time than other model serving due to model conversion time.

Deploy the vLLM Helm chart:

```bash
helm install chatqna . \
  --set global.huggingface.apiToken=<your-huggingface-token> \
  --set global.proxy.http_proxy=<your-proxy> \
  --set global.proxy.https_proxy=<your-proxy> \
  --set global.proxy.no_proxy=<your-no-proxy> \
  --set global.POSTGRES_USER=<postgres-user> \
  --set global.POSTGRES_PASSWORD=<postgres-password> \
  --set global.MINIO_ROOT_USER=<minio-root-user> \
  --set global.MINIO_ROOT_PASSWORD=<minio-root-password> \
  -f values_vllm.yaml \
  --set global.LLM_MODEL=<llm-model> \
  --set global.EMBEDDING_MODEL_NAME=<embedding-model> \
  --set global.RERANKER_MODEL=<reranker-model> \
  --set global.teiEmbeddingService.enabled=true \
  --set global.OTLP.endpoint=<OTLP-endpoint> \
  --set global.OTLP.trace_endpoint=<OTLP-endpoint-trace> \
  --namespace <your-namespace>
```

Deploy the TGI Helm chart:

```bash
helm install chatqna . \
  --set global.huggingface.apiToken=<your-huggingface-token> \
  --set global.proxy.http_proxy=<your-proxy> \
  --set global.proxy.https_proxy=<your-proxy> \
  --set global.proxy.no_proxy=<your-no-proxy> \
  --set global.POSTGRES_USER=<postgres-user> \
  --set global.POSTGRES_PASSWORD=<postgres-password> \
  --set global.MINIO_ROOT_USER=<minio-root-user> \
  --set global.MINIO_ROOT_PASSWORD=<minio-root-password> \
  -f values_tgi.yaml \
  --set global.LLM_MODEL=<llm-model> \
  --set global.EMBEDDING_MODEL_NAME=<embedding-model> \
  --set global.RERANKER_MODEL=<reranker-model> \
  --set global.teiEmbeddingService.enabled=true \
  --namespace <your-namespace>
```

### Step 5: Verify the Deployment

Check the status of the deployed resources to ensure everything is running correctly

```bash
kubectl get pods -n <your-namespace>
kubectl get services -n <your-namespace>
```

### Step 6: Retrieving the Service Endpoint (NodePort and NodeIP)

To access a chatqna-nginx service running in your Kubernetes cluster using NodePort, you need to retrieve:

- NodeIP – The internal IP of a worker node.
- NodePort – The port exposed by the service.

Run the following command after replacing \<your-namespace\> with your actual values:
```bash
  echo "http://$(kubectl get nodes -o jsonpath='{.items[0].status.addresses[?(@.type=="InternalIP")].address}'):$(kubectl get svc chatqna-nginx -n <your-namespace> -o jsonpath='{.spec.ports[0].nodePort}')"
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

## Related links

- [How to Build from Source](./build-from-source.md)
- [How to Test Performance](./how-to-performance.md)
- [How to Benchmark](./benchmarks.md)
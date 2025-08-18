# Text Generation Inference Service Deployment

This guide provides instructions for deploying the Text Generation Inference (TGI) service using Helm.

## Prerequisites

- Kubernetes cluster
- Helm installed
- Access to the Hugging Face API token

## Installation

1. Clone the repository:

  ```sh
  git clone https://github.com/open-edge-platform/edge-ai-libraries.git edge-ai-libraries -b release-1.2.0
  cd edge-ai-libraries/sample-applications/chat-question-and-answer/chart/subchart/llm/tgi
  ```
  Adjust the repo link appropriately in case of forked repo.

2. Update the `values.yaml` file with your Hugging Face API token and other necessary configurations:

  | Key                          | Value                                                                 |
  |------------------------------|-----------------------------------------------------------------------|
  | `global.huggingface.apiToken`| `<your-huggingface-api-token>`                                         |
  | `tgiService.name`            | `text-generation-service`                                                         |
  | `tgiService.image.repository`| `ghcr.io/huggingface/text-generation-inference`                       |
  | `tgiService.image.tag`       | `3.0.1-intel-xpu`                                                                 |
  | `tgiService.volumes`         | `$PWD/data_tgi:/data`                                                 |
  | `tgiService.shm_size`        | `1g`                                                                  |
  | `tgiService.env.model_id`    | `Intel/neural-chat-7b-v3-3`                                           |

3. Deploy the Helm chart:

  ```sh
  helm install tgi-service . \
    --set global.huggingface.apiToken=<your-huggingface-token> \
    --set global.proxy.http_proxy=<your-http-proxy> \
    --set global.proxy.https_proxy=<your-https-proxy> \
    --set global.proxy.no_proxy=<your-no-proxy>  \
    --namespace <your-namespace>
  ```

4. Verify the deployment:

  ```sh
  kubectl get pods
  kubectl get services
  ```

## Accessing the Service locally

Once deployed, the TGI service will be available within the Kubernetes cluster. You can access it using the service name and port specified in the `values.yaml` file.

To access the service from your local machine, you can use `kubectl port-forward`:

```sh
kubectl port-forward svc/<service-name> <local-port>:<service-port>
```
Replace `<service-name>`, `<local-port>`, and `<service-port>` with the appropriate values from your deployment.

## Uninstallation

To uninstall the TGI service, run:

```sh
helm uninstall tgi-service
```

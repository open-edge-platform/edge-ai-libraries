# vLLM Deployment using Helm

This guide provides instructions for deploying the vLLM Inference Server using Helm.

## Prerequisites

- Kubernetes cluster
- Helm installed guide is here - [Helm](https://helm.sh/docs/intro/install/)
- Access to the Docker repository containing the vLLM image

## Installation

1. **Clone the repository:**

   ```sh
   git clone https://github.com/open-edge-platform/edge-ai-libraries.git edge-ai-libraries -b release-1.2.0
   cd edge-ai-libraries/sample-applications/chat-question-and-answer/chart/subchart/llm/vllm
   ```
   Adjust the repo link appropriately in case of forked repo.

2. **Update the `values.yaml` file:**

    Edit the `values.yaml` file to set the appropriate values for your environment, such as `huggingface.apiToken`, `proxy`, and `image` repository and tag.

3. **Deploy the Helm chart:**

    ```sh
    helm install vllm-service . \
    --set global.huggingface.apiToken=<your-huggingface-token> \
    --set global.proxy.http_proxy=<your-http-proxy> \
    --set global.proxy.https_proxy=<your-https-proxy> \
    --set global.proxy.no_proxy=<your-no-proxy>  \
    --namespace <your-namspace>
    ```

    This command will deploy the vLLM Inference Server with the specified configuration.

## Configuration

The `values.yaml` file contains the configuration options for the deployment. Key configurations include:

- `global.huggingface.apiToken`: Set your Hugging Face API token.
- `global.proxy`: Configure proxy settings.
- `vllmService.image`: Specify the Docker image repository and tag.
- `vllmService.env`: Environment variables for the vLLM service.

## Accessing the Service locally

Once deployed, the vLLM service will be available within the Kubernetes cluster. You can access it using the service name and port specified in the `values.yaml` file.

To access the service from your local machine, you can use `kubectl port-forward`:

```sh
kubectl port-forward svc/<service-name> <local-port>:<service-port>
```

Replace `<service-name>`, `<local-port>`, and `<service-port>` with the appropriate values from your deployment.

## Uninstallation

To uninstall the vLLM service, run:

```sh
helm uninstall vllm-service
```

# How to Deploy with Helm

Use Helm to deploy Model Registry to a Kubernetes cluster. This guide will help you:
- Add the Helm chart repository.
- Configure the Helm chart to match your deployment needs.
- Deploy and verify the microservice.

Helm simplifies Kubernetes deployments by streamlining configurations and enabling easy scaling and updates. For more details, see [Helm Documentation](https://helm.sh/docs/).


## Prerequisites

Before You Begin, ensure the following:

- **System Requirements**: Verify that your system meets the [minimum requirements](./system-requirements.md).
- **Tools Installed**: Install the required tools:
    - Kubernetes CLI (kubectl)
    - Helm 3 
- **Cluster Access**: Confirm that you have access to a running Kubernetes cluster with appropriate permissions.

This guide assumes basic familiarity with Kubernetes concepts, kubectl commands, and Helm charts. If you are new to these concepts, see:
- [Kubernetes Documentation](https://kubernetes.io/docs/home/)
- [Helm Documentation](https://helm.sh/docs/)


## Steps to Deploy

**Check the status of the pods and verify the microservice is running**
    ```sh
    kubectl get pods --namespace apps
    ```

## Troubleshooting

1. **Helm Chart Not Found**:

   - Check if the Helm repository was added:

     ```bash
     helm repo list
     ```

2. **Pods Not Running**:

   - Review pod logs:

     ```bash
     kubectl logs {{pod-name}} -n {{namespace}}
     ```

3. **Service Unreachable**:

   - Confirm the service configuration:

     ```bash
     kubectl get svc -n {{namespace}}
     ```


## Supporting Resources

- [Kubernetes Documentation](https://kubernetes.io/docs/home/)
- [Helm Documentation](https://helm.sh/docs/)
- [API Reference](./api-reference.md)

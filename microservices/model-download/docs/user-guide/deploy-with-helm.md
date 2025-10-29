# How to deploy with Helm

This guide provides step-by-step instructions for deploying the Model-Download Microservice using Helm.

## Prerequisites

Before you begin, ensure that you have the following prerequisites:
- Kubernetes cluster set up and running.
- The cluster must support **dynamic provisioning of Persistent Volumes (PV)**. Refer to the [Kubernetes Dynamic Provisioning Guide](https://kubernetes.io/docs/concepts/storage/dynamic-provisioning/) for more details.
- Install `kubectl` on your system. Refer to [Installation Guide](https://kubernetes.io/docs/tasks/tools/install-kubectl/). Ensure access to the Kubernetes cluster.
- Helm installed on your system: [Installation Guide](https://helm.sh/docs/intro/install/).

## Steps to deploy with Helm

Following steps should be followed to deploy Model-Download using Helm. You can install from source code or pull the chart from Docker hub.

**_Steps 1 to 3 varies depending on if the user prefers to build or pull the Helm details._**

### Option 1: Install from Docker Hub

#### Step 1: Pull the Specific Chart

Use the following command to pull the Helm chart from [Docker Hub](https://hub.docker.com/r/intel/model-download):

```bash
helm pull oci://registry-1.docker.io/intel/model-download --version <version-no>
```

🔍 Refer to the [Docker Hub tags page](https://hub.docker.com/r/intel/model-download/tags) for details on the latest version number to use for the application.

#### Step 2: Extract the `.tgz` File

After pulling the chart, extract the `.tgz` file:
```bash
tar -xvf model-download-<version-no>.tgz
```

This will create a directory named `model-download` containing the chart files. Navigate to the extracted directory.
```bash
cd model-download
```

#### Step 3: Configure the `values.yaml` File

Edit only the `values.yaml` file to set the necessary environment variables. Ensure you set the `env.HF_TOKEN` and proxy settings as required.

### Option 2: Install from Source

#### Step 1: Clone the Repository

Clone the repository containing the Helm chart:
```bash
git clone <repository-url>
```

#### Step 2: Change to the Chart Directory

Navigate to the chart directory:
```bash
cd <repository-url>/microservices/model-download/chart
```

#### Step 3: Configure the `values.yaml` File

Edit the `values.yaml` file located in the chart directory to set the necessary environment variables.


#### Step 4: Build Helm Dependencies

Navigate to the chart directory and build the Helm dependencies using the following command:

```bash
helm dependency build
```
## Common Steps after configuration

### Step 5: Deploy the Helm Chart

Deploy the Model-Download Helm chart:

```bash
helm install model-download . -n <your-namespace>
```

### Step 6: Verify the Deployment

Check the status of the deployed resources to ensure everything is running correctly

```bash
kubectl get pods -n <your-namespace>
kubectl get services -n <your-namespace>
```

### Step 7: Access the Application

Open the application swagger documentation in a browser at `http://\<node-ip\>:\<node-port\>/api/v1/docs`

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
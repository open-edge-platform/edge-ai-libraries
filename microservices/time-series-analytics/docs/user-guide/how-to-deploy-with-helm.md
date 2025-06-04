# How to Deploy with Helm

## Prerequisites

- [System Requirements](system-requirements.md)
-  K8s installation on single or multi node must be done as pre-requisite to continue the following deployment. Note: The kubernetes cluster is set up with `kubeadm`, `kubectl` and `kubelet` packages on single and multi nodes with `v1.30.2`.
  Refer to tutorials such as <https://adamtheautomator.com/installing-kubernetes-on-ubuntu> and many other
  online tutorials to setup kubernetes cluster on the web with host OS as ubuntu 22.04.
- For helm installation, refer to [helm website](https://helm.sh/docs/intro/install/)

> **Note**
> If Ubuntu Desktop is not installed on the target system, follow the instructions from Ubuntu to [install Ubuntu desktop](https://ubuntu.com/tutorials/install-ubuntu-desktop).

## Access to the helm charts - use one of the below options

- Use helm charts available at `<path-to-edge-ai-libaries-repo>/edge-ai-libraries/microservices/time-series-analytics/helm`

- Using pre-built helm charts:

    Follow this procedure on the target system to install the package.

    1. Download helm chart with the following command

        `helm pull oci://<path-to-internal-harbor-registry-OR-intel-docker-hub-registry-path>/time-series-analytics-microservice --version 1.0.0`

    2. unzip the package using the following command

        `tar -xvzf time-series-analytics-microservice-1.0.0.tgz`

    - Get into the helm directory

        `cd time-series-analytics-microservice-1.0.0`

## Install helm charts - use only one of the options below:

> **Note:**
> 1. Please uninstall the helm charts if already installed.
> 2. If the worker nodes are running behind proxy server, then please additionally set env.HTTP_PROXY and env.HTTPS_PROXY env like the way env.TELEGRAF_INPUT_PLUGIN is being set below with helm install command

    ```bash
    cd <helm-directory>
    helm install time-series-analytics-microservice . -n apps --create-namespace
    ```

Use the following command to verify if all the application resources got installed w/ their status:

```bash
   kubectl get all -n apps
```

## Verify the Temperature Classifier Results

Run below commands to see the filtered temperature results:


``` bash
kubectl logs -f deployment-time-series-analytics-microservice -n apps
```

## Uninstall helm charts

```bash
helm uninstall time-series-analytics-microservice -n apps
kubectl get all -n apps # it takes few mins to have all application resources cleaned up
```

## Troubleshooting

- Check pod details or container logs to catch any failures:
 
  ```bash
  kubectl describe pod deployment-time-series-analytics-microservice -n apps # shows details of the pod
  kubectl logs -f deployment-time-series-analytics-microservice -n apps | grep -i error


  # Debugging UDF errors if container is not restarting and providing expected results
  kubectl exec -it deployment-time-series-analytics-microservice bash
  $ cat /tmp/log/kapacitor/kapacitor.log | grep -i error
  ```
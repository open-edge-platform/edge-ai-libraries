# Deploy with Helm

## Prerequisites

- [System Requirements](../get-started/system-requirements.md)
- K8s installation on single or multi node must be done as pre-requisite to continue
  the following deployment. Note: The kubernetes cluster is set up with `kubeadm`,
  `kubectl` and `kubelet` packages on single and multi nodes with `v1.30.2`.
  Refer to tutorials such as <https://adamtheautomator.com/installing-kubernetes-on-ubuntu> and many other
  online tutorials to setup kubernetes cluster on the web with host OS as ubuntu 22.04.
- For helm installation, refer to [helm website](https://helm.sh/docs/intro/install/)

> **Note**
> If Ubuntu Desktop is not installed on the target system, follow the instructions from Ubuntu to [install Ubuntu desktop](https://ubuntu.com/tutorials/install-ubuntu-desktop).

## Access to the helm charts - use one of the below options

- Use helm charts available at `edge-ai-libraries/microservices/time-series-analytics/helm`

- Using pre-built helm charts:

    Follow this procedure on the target system to install the package.

    1. Download helm chart with the following command

        `helm pull oci://registry-1.docker.io/intel/time-series-analytics-microservice --version 2026.0.0-<date>-weekly-helm`

        Replace `<date>` with the actual patch version date (e.g., `20260120` for January 20th, 2026).
        `helm pull oci://registry-1.docker.io/intel/time-series-analytics-microservice --version 2026.0.0-20260120-weekly-helm`

    2. unzip the package using the following command

        `tar -xvzf time-series-analytics-microservice-2026.0.0-<date>-weekly-helm.tgz`

    - Get into the helm directory

        `cd time-series-analytics-microservice`

## Install helm charts

> **Note:**
>
> - Uninstall the helm charts if already installed.
> - If the worker nodes are running behind proxy server, then please additionally
>   set `env.HTTP_PROXY` and `env.HTTPS_PROXY` env like the way `env.TELEGRAF_INPUT_PLUGIN`
>   is being set as follows with helm install command

```bash
cd edge-ai-libraries/microservices/time-series-analytics/helm # path relative to git clone folder
# Copy the config.json file to helm directory
cp ../config.json .
# Install helm charts
helm install time-series-analytics-microservice . -n apps --create-namespace
```

Use the following command to verify if all the application resources got installed w/ their status:

```bash
   kubectl get all -n apps
```

## Ingesting Temperature Data into the Time Series Analytics Microservice

Run the following script to ingest temperature data into the Time Series Analytics Microservice:

```sh
cd edge-ai-libraries/microservices/time-series-analytics # path relative to git clone folder
pip3 install -r simulator/requirements.txt
python3 simulator/temperature_input.py --port 30002
```

## Verify the Temperature Classifier Results

Run following commands to see the filtered temperature results:


``` bash
POD_NAME=$(kubectl get pods -n apps -o jsonpath='{.items[*].metadata.name}' | tr ' ' '\n' | grep deployment-time-series-analytics-microservice | head -n 1)
kubectl logs -f $POD_NAME -n apps
```

## Uninstall helm charts

```bash
helm uninstall time-series-analytics-microservice -n apps
kubectl get all -n apps # it takes few mins to have all application resources cleaned up
```

## Troubleshooting

- Check pod details or container logs to catch any failures:

  ```bash
  POD_NAME=$(kubectl get pods -n apps -o jsonpath='{.items[*].metadata.name}' | tr ' ' '\n' | grep deployment-time-series-analytics-microservice | head -n 1)
  kubectl describe pod $POD_NAME $ -n apps # shows details of the pod
  kubectl logs -f $POD_NAME -n apps | grep -i error


  # Debugging UDF errors if container is not restarting and providing expected results
  kubectl exec -it $POD_NAME -n apps -- /bin/bash
  $ cat /tmp/log/kapacitor/kapacitor.log | grep -i error
  ```

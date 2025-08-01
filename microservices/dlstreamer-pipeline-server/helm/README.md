# Helm chart for Deep Learning Streamer Pipeline Server

## Steps to deploy the helm chart:

- Note: Incase you do not have a k8s cluster, then please follow the steps mentioned in 'Setup k8s cluster' below before deploying the helm chart.
- Get into the helm directory (where this README.md exists)
    `cd helm`
- Update the below fields in `values.yaml` file in the helm chart
    ``` sh
    env:
        http_proxy: # example: http_proxy: http://proxy.example.com:891
        https_proxy: # example: http_proxy: http://proxy.example.com:891
    images:
        dlstreamer_pipeline_server: # example: dlstreamer_pipeline_server: intel/dlstreamer-pipeline-server:3.1.0-ubuntu22
    ```
- Install the helm chart
    `helm install dlsps . -n apps --create-namespace`
- Check if Deep Learning Streamer Pipeline Server is running fine
    `kubectl get pods --namespace apps`and monitor its logs using `kubectl logs -f <pod_name> -n apps`
- The resources such as video and model are copied into `dlstreamer-pipeline-server` pod by `initContainers`.
- Send the curl command to start the pallet defect detection pipeline
    ``` sh
        curl http://localhost:30007/pipelines/user_defined_pipelines/pallet_defect_detection -X POST -H 'Content-Type: application/json' -d '{
            "source": {
                "uri": "file:///home/pipeline-server/resources/videos/warehouse.avi",
                "type": "uri"
            },
            "destination": {
                "metadata": {
                    "type": "file",
                    "path": "/tmp/results.jsonl",
                    "format": "json-lines"
                },
                "frame": {
                    "type": "rtsp",
                    "path": "pallet-defect-detection"
                }
            },
            "parameters": {
                "detection-properties": {
                    "model": "/home/pipeline-server/resources/models/geti/pallet_defect_detection/deployment/Detection/model/model.xml",
                    "device": "CPU"
                }
            }
        }'
    ```
- Open VLC media player on your windows system. Cick on Media -> Open Network Stream -> Enter `rtsp://<Host_IP_where_Deep_Learning_Streamer_Pipeline_Server_is_running>:30025/pallet-defect-detection` in network URL tab and hit Play to see the visualization.

## Troubleshooting
- [Troubleshooting Guide](../docs/user-guide/troubleshooting-guide.md)

## Setup k8s cluster

- [System Requirements](../docs/user-guide/system-requirements.md)

- Install Helm Charts: 
    - `curl -fsSL -o get_helm.sh https://raw.githubusercontent.com/helm/helm/main/scripts/get-helm-3`
    - `chmod 700 get_helm.sh`
    - `./get_helm.sh`

- Install kubeadm, kubectl, kubelet
    - Note: These instructions are for Kubernetes v1.30.
    - Update the apt package index and install packages needed to use the Kubernetes apt repository:
        - `sudo apt-get update`
    - apt-transport-https may be a dummy package. If so, you can skip that package.
        - `sudo apt-get install -y apt-transport-https ca-certificates curl gpg`
    - Download the public signing key for the Kubernetes package repositories. The same signing key is used for all repositories so you can disregard the version in the URL:
        - Note: If the directory `/etc/apt/keyrings` does not exist, it should be created before the curl command: `sudo mkdir -p -m 755 /etc/apt/keyrings`. In releases older than Debian 12 and Ubuntu 22.04, directory /etc/apt/keyrings does not exist by default, and it should be created.
        - `curl -fsSL https://pkgs.k8s.io/core:/stable:/v1.30/deb/Release.key | sudo gpg --dearmor -o /etc/apt/keyrings/kubernetes-apt-keyring.gpg`
    - Add the appropriate Kubernetes apt repository. Please note that this repository has packages only for Kubernetes 1.30. For other Kubernetes minor versions, you need to change the Kubernetes minor version in the URL to match your desired minor version (you should also check that you are reading the documentation for the version of Kubernetes that you plan to install). Note that this overwrites any existing configuration in /etc/apt/sources.list.d/kubernetes.list
        - `echo 'deb [signed-by=/etc/apt/keyrings/kubernetes-apt-keyring.gpg] https://pkgs.k8s.io/core:/stable:/v1.30/deb/ /' | sudo tee /etc/apt/sources.list.d/kubernetes.list`
    - Update the apt package index, install kubelet, kubeadm and kubectl, and pin their version:
        - `sudo apt-get update`
        - `sudo apt-get install -y kubelet kubeadm kubectl`
        - `sudo apt-mark hold kubelet kubeadm kubectl`
    - (Optional) Enable the kubelet service before running kubeadm:
        - `sudo systemctl enable --now kubelet`

- Install cri-docker-socker 
    - `wget https://github.com/Mirantis/cri-dockerd/releases/download/v0.3.13/cri-dockerd_0.3.13.3-0.ubuntu-jammy_amd64.deb`
    - `sudo dpkg -i cri-dockerd_0.3.13.3-0.ubuntu-jammy_amd64.deb`

- Initialize k8s environment
    - Add `"exec-opts": ["native.cgroupdriver=systemd"]` to `/etc/docker/daemon.json`
    - Add Pod IP and k8s IP to no_proxy in `/etc/environment`, `.docker/config.json`, `/etc/systemd/system/docker.service.d/<http> and <https>` proxy files. Pod IP is system IP address, k8s IP is `10.244.0.0/16`
    - Execute below commands
        - `sudo kubeadm reset  --cri-socket=unix:///var/run/cri-dockerd.sock`
        - `sudo swapoff -a`
        - `sudo systemctl stop kubelet`
        - `sudo systemctl stop docker`
        - `sudo rm -rf /var/lib/cni/*`
        - `sudo rm -rf /var/lib/kubelet/*`
        - `sudo rm -rf /etc/cni/*`
        - `sudo ifconfig cni0 down && sudo ip link delete cni0`
        - `sudo ifconfig flannel.1 down && sudo ip link delete flannel.1`
        - `sudo ifconfig docker0 down`
        - `sudo systemctl daemon-reload`
        - `sudo systemctl restart docker`
        - `sudo systemctl stop apparmor`
        - `sudo systemctl disable apparmor`
        - `sudo systemctl restart containerd.service`
        - `sudo kubeadm init --pod-network-cidr=10.244.0.0/16 --cri-socket=unix:///var/run/cri-dockerd.sock`

- Tainting the node: 
    - kubectl get nodes
    - Note: If you face issues with `kubectl get nodes` where it tries to connect to other clusters and not your local host machine cluster, then copy the kubeconfig file `/etc/kubernetes/admin.conf` to `~/.kube/config`. Do not forget to make a backup of  `~/.kube/config` file incase you need it later.
    - `kubectl describe node <node_name> | grep Taints`
    - `kubectl taint nodes --all <taints_details_from_above_command>-`

- Apply weave network.
    - `kubectl apply -f https://github.com/weaveworks/weave/releases/download/v2.8.1/weave-daemonset-k8s.yaml`

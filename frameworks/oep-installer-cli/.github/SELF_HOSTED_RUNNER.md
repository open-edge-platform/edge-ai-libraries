
### Setup Self-hosted Runner

```
sudo apt install -y virtinst cloud-image-utils

cd /var/lib/libvirt/images
sudo wget https://cloud-images.ubuntu.com/noble/current/noble-server-cloudimg-amd64.img
sudo qemu-img convert -O qcow2 noble-server-cloudimg-amd64.img runner.qcow2
sudo qemu-img resize runner.qcow2 60G
```

```
cat > user-data <<EOF
#cloud-config
users:
  - name: runner
    sudo: ALL=(ALL) NOPASSWD:ALL
    shell: /bin/bash
    ssh_authorized_keys:
      - $(cat ~/.ssh/id_rsa.pub)
package_update: true
packages: [curl, git, jq, shellcheck]
EOF

echo "instance-id: runner; local-hostname: runner" > meta-data
sudo cloud-localds /var/lib/libvirt/images/runner-seed.iso user-data meta-data
```

```
sudo virt-install \
  --name gh-runner \
  --memory 4096 --vcpus 2 \
  --disk /var/lib/libvirt/images/runner.qcow2,format=qcow2 \
  --disk /var/lib/libvirt/images/runner-seed.iso,device=cdrom \
  --os-variant ubuntu24.04 \
  --network network=default \
  --graphics none --import --noautoconsole
sudo virsh domifaddr gh-runner
ssh runner@<ip>
```

```
mkdir ~/actions-runner && cd ~/actions-runner
curl -o runner.tar.gz -L https://github.com/actions/runner/releases/latest/download/actions-runner-linux-x64-2.328.0.tar.gz
tar xzf runner.tar.gz

./config.sh --url https://github.com/intel-sandbox/oep-installer-cli \
  --token <YOUR_TOKEN> \
  --labels self-hosted,linux,oep-lab \
  --unattended

vi ~/actions-runner/.env /etc/environment # proxies

# gh CLI — required by create-component-issue.sh
sudo mkdir -p -m 755 /etc/apt/keyrings
wget -qO- https://cli.github.com/packages/githubcli-archive-keyring.gpg \
  | sudo tee /etc/apt/keyrings/githubcli-archive-keyring.gpg > /dev/null
sudo chmod go+r /etc/apt/keyrings/githubcli-archive-keyring.gpg
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main" \
  | sudo tee /etc/apt/sources.list.d/github-cli.list > /dev/null
sudo apt update && sudo apt install -y gh git curl jq shellcheck

sudo hostnamectl set-hostname oep-lab-runner-01
sudo ./svc.sh install runner
sudo ./svc.sh start
```

```
sudo virsh snapshot-create-as gh-runner clean-base --disk-only --atomic
```

### Create PAT

Create a fine-grained PAT on an account with write access to the repo:

Settings → Developer settings → Personal access tokens → Fine-grained tokens
Resource owner: intel-sandbox, repository: oep-installer-cli
Permissions: Issues: Read and write, Contents: Read-only, Pull requests: Read and write
Fine-grained tokens in an org often need admin approval, so a classic PAT with repo scope may be the quicker path if you're blocked.


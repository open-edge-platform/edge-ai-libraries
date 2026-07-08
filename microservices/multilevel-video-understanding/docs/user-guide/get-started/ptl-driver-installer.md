# PTL Driver Installation Guide

This guide covers building and installing the Intel Linux kernel overlay and iGPU platform software packages needed to enable the integrated GPU on a target machine with an Intel® Core™ Ultra (Panther Lake, PTL) processor — the same host used to run the on-device VLM/LLM model serving for this microservice.

> **Note:** This document is a point-in-time reference (including the pinned `mainline-tracking-overlay-v6.17.11-ubuntu-260128T080735Z` tag below). If the upstream [linux-kernel-overlay](https://github.com/intel/linux-kernel-overlay) repo has since been updated, check its latest tags/instructions and update the steps here accordingly as needed.

## Prerequisites

- Ubuntu Noble (24.04)
- Root/sudo access

## Install Dependencies

```bash
sudo apt install quilt libssl-dev kernel-wedge liblz4-tool libelf-dev flex bison git libdw-dev
```

## Build Kernel Debian Packages

### Step 1: Clone the kernel source code and check out the stated tag

```bash
git clone https://github.com/intel/linux-kernel-overlay.git
cd linux-kernel-overlay
git checkout mainline-tracking-overlay-v6.17.11-ubuntu-260128T080735Z
```

### Step 2: Trigger the kernel build

```bash
sudo -E ./build.sh -r no -t mainline-tracking-overlay-v6.17.11-ubuntu-260128T080735Z -b 1000 -c mainline-tracking
```

The following Debian packages will be generated under the `linux-kernel-overlay` directory:

- `linux-headers-<version>*_amd64.deb`
- `linux-image-<version>*_amd64.deb`
- `linux-image-<version>*_dbg_amd64.deb`
- `linux-libc-dev_<version>*_amd64.deb`

## Install Userspace and Kernel with a Script

```bash
sudo -E ../../../scripts/ptl_driver/install_ubuntu_gpu_drivers.sh UBUNTU_NOBLE PTL mainline-tracking-overlay-v6.17.11-ubuntu-260128T080735Z default
```

Once the installation is successful, the system will reboot automatically and you are ready to validate the platform.
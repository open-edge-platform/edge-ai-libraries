# Get Started

This document is a quick start guide to configure and deploy nodes using the Edge Device
Enablement Framework on Intel® Core™ and Intel® Xeon® Scalable processors with Intel® Iris® Xe
Integrated Graphics for Core platform.

A shell script installs the Edge Device Enablement Framework software from the Open Edge
Platform (OEP)'s `edge-ai-libraries/frameworks` folder. Users can download the installer script
and deploy it to the Edge Node.

## Installation Flow for EEF

![Installation flow](_images/installation_flow.png)
*Figure 1: Flow for Edge Device Enablement Framework*

## Step 1: Prerequisites and System Setup

Before starting the Edge Node deployment, ensure you meet the following prerequisites:

- The system is bootable to a fresh Ubuntu OS 24.04 Long Term Support (LTS) version.
- Internet connectivity is available on the node.
- The hostname of the target node(s) uses only lowercase letters, numerals, and hyphens.
  - For example: "wrk-8" is acceptable; "wrk_8", "WRK8", and "Wrk^8" are not accepted as hostnames.
- The required proxy settings are added to the /etc/environment file.
- Secure boot uses the following BIOS settings:

   <!--hide_directive
   <details>
   <summary><code><b>hide_directive-->Click to expand — BIOS Settings
   <!--hide_directive</b></code></summary>hide_directive-->

   <!--hide_directive ::::{tab-set} hide_directive-->
   <!--hide_directive :::{tab-item} hide_directive--> **Dell R760**
   <!--hide_directive :sync: dell-r760 hide_directive-->

   - BIOS Settings → System BIOS → System Security → Secure Boot → Enabled

   <!--hide_directive ::: hide_directive-->
   <!--hide_directive :::{tab-item} hide_directive--> **ASRock iEP-7020E or ASUS PE3000G**
   <!--hide_directive :sync: asrock-asus hide_directive-->

   - Press F2 → Go to UEFI Firmware Settings → Security Section → Secure Boot Section → Set Secure Boot Mode to Custom → Select Secure Boot → Enabled → Save Changes → Boot to setup.

   <!--hide_directive
   :::
   ::::
   </details>
   hide_directive-->

## Step 2: Download the Script

1. [Download](https://raw.githubusercontent.com/open-edge-platform/edge-ai-libraries/release-2026.2.0/frameworks/edgedevice-enablement-framework/base/va_enablement_node_profile/va_enablement_node_profile.sh) the Edge Device Enablement Framework script.

2. Download the file using wget:

   ```
   wget https://raw.githubusercontent.com/open-edge-platform/edge-ai-libraries/release-2026.2.0/frameworks/edgedevice-enablement-framework/base/va_enablement_node_profile/va_enablement_node_profile.sh
   ```

## Step 3: Run the Script and Configure Command-line Options

- Modify the permissions of the installer file to make it executable:

  ```bash
  chmod +x va_enablement_node_profile.sh
  ```

- Use one of the following commands based on your use case. The available use cases are: Intel®
  Edge System Qualification (Intel® ESQ) and Metro, Transportation Fusion Compute Controller
  (TFCC) and Intel® Video Processing Platform Reference Implementation (VPP), Intel vPro® Platform,
  Edge Workloads and Benchmarks, and DevKit Component Set. See the details below:

  <!--hide_directive ::::{tab-set} hide_directive-->
  <!--hide_directive :::{tab-item} hide_directive--> **Intel® ESQ and Metro**
  <!--hide_directive :sync: esq-metro hide_directive-->

  ```bash
  ./va_enablement_node_profile.sh
  ```

  <!--hide_directive ::: hide_directive-->
  <!--hide_directive :::{tab-item} hide_directive--> **TFCC and VPP RI**
  <!--hide_directive :sync: tfcc-vpp-ri hide_directive-->

  ```bash
  ./va_enablement_node_profile.sh tfcc
  ./va_enablement_node_profile.sh vpp
  ```

  <!--hide_directive ::: hide_directive-->
  <!--hide_directive :::{tab-item} hide_directive--> **Intel vPro® Platform**
  <!--hide_directive :sync: vpro-platform hide_directive-->

  ```bash
  ./va_enablement_node_profile.sh vpro
  ```

  <!--hide_directive ::: hide_directive-->
  <!--hide_directive :::{tab-item} hide_directive--> **Edge Workloads and Benchmarks**
  <!--hide_directive :sync: edge-workloads-benchmarks hide_directive-->

  ```bash
  ./va_enablement_node_profile.sh magic9
  ```

  <!--hide_directive ::: hide_directive-->
  <!--hide_directive :::{tab-item} hide_directive--> **DevKit Component Set**
  <!--hide_directive :sync: devkit-component-set hide_directive-->

  ```bash
  ./va_enablement_node_profile.sh devkit
  ```

  <!--hide_directive
  :::
  ::::
  hide_directive-->

- Execute the script with `--help` or `-h` to check the availability of any additional use
  case support:

  ```bash
  ./va_enablement_node_profile.sh -h
  ```

> **Note:** For Prometheus secure configuration details, see [Prometheus configuration](https://prometheus.io/docs/prometheus/latest/configuration/configuration/).

### User Inputs Required for Installer Execution

<!--hide_directive
<details>
<summary><code>hide_directive-->Click to expand — User Input
<!--hide_directive</code><code><b>hide_directive-->VA Enablement Node
<!--hide_directive</b></code></summary>hide_directive-->

| Prompt       | User Input                                                                                            |
| ------------ | ----------------------------------------------------------------------------------------------------- |
| Docker Group | For Metro/ESQ team enter 'yes', other users enter 'no'                                                |
| DL Streamer  | Do you want to install DL Streamer? (y/n) <br> (Comes up only for the DevKit command-line argument)   |
| XPU-SMI      | Do you want to install Intel XPU-SMI? (y/n) <br> (Comes up only for the DevKit command-line argument) |

<!--hide_directive
</details>hide_directive-->

## Step 4: Enable Time of Day (TOD) Provisioning

After the installer script finishes executing, follow these steps to deploy Time of Day (TOD) Provisioning:

<!--hide_directive
<details>
<summary><code><b>hide_directive-->Click to expand — Time of Day (TOD) Provisioning
<!--hide_directive</b></code></summary>hide_directive-->

TOD enables power management provisioning to save power at a specific time of day, delivering power
savings during non-peak hours on the edge device by using the Intel® Infrastructure Power Manager
(IPM).
Download the [Time of Day Provisioning software package](https://www.intel.com/content/www/us/en/secure/content-details/828016/time-of-day-provisioning-with-intel-tiber-edge-platform.html?DocID=828016)
and the technology guide, available through the same link, as shown in Figure 2. To deploy this
feature, follow the instructions in Chapter 9 of the TOD technology guide.

![TOD](_images/tod.png)
*Figure 2: Time of Day Home Page*

<!--hide_directive
</details>
hide_directive-->

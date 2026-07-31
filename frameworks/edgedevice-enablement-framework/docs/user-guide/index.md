# Edge Device Enablement Framework

<!--hide_directive
<div class="component_card_widget">
  <a class="icon_github" href="https://github.com/open-edge-platform/edge-ai-libraries/tree/main/frameworks/edgedevice-enablement-framework">
     GitHub
  </a>
  <a class="icon_document" href="https://github.com/open-edge-platform/edge-ai-libraries/blob/main/frameworks/edgedevice-enablement-framework/README.md">
     Readme
  </a>
</div>
hide_directive-->

The Edge Device Enablement Framework (EEF) delivers a set of curated, validated infrastructure
stacks (also known as profiles), providing a runtime for edge applications. It is built on a
modular framework where each node is based on a common foundation of hardware, OS, and container
runtime.

This document is a quick start guide to configure and deploy nodes using the Edge Device Enablement
Framework on Intel® Core™ and Intel® Xeon® Scalable processors with Intel® Iris® Xe Integrated
Graphics for Core platform.

## How It Works

This release of the Edge Device Enablement Framework currently contains the Video Analytics (VA)
Enablement Node profile, with components curated mainly for the needs of VA workloads. Command-line
options support the Metro, VPP, TFCC, vPRO, and Edge Workloads and Benchmarks enablement needs
on the edge nodes and a new 'DevKit' option with a very minimal set of components and GPU/NPU
driver installation.

## Main Supported Features

|**Category**                  |**Feature**               |
|------------------------------|--------------------------|
|**Hardware**                  | - Support for 4th and 5th Gen Intel® Xeon® Scalable processor <br> - Support for Intel® Core™ Ultra processor and 12th and 13th Gen Intel® Core™ industrial processors <br> - Support for Intel® Iris® Xe Integrated Graphics for Core platform - Intel® Atom® Processor |
|**OS**                        | - Ubuntu 24.04.4 (Or the latest LTS version from Canonical) |
|**CAAS**                      | - Model: Bare Metal <br> - ContainerD; Docker CE; Docker Compose |
|**Observability / Telemetry** | - Aggregate/query telemetry (e.g. Prometheus) <br> - GPU, CPU/Memory Telemetry <br> - Visualization / Logs analysis |
|**Security**                  | - Secure Boot (documentation) (Enabled for SPR, RPL. Not supported on MTL internal SKUs) <br> - A hardware RoT-based foundation (TPM chip SW) <br> - Secure network and communication (IPSEC, OpenSSL) |
|**Framework**                 | - OVPL; OpenVINO LTS; DLStreamer; GStreamer; Graph Compute Runtime; OpenCV with Ffmpeg |

## Key Hardware Elements Supported

|**Hardware Element**                                | **Description**   |
|----------------------------------------------------|---------------------------------------------------------------------------------------------------|
|**Processor**                                       | - 4th and 5th Gen Intel® Xeon® Scalable processors <br> - Intel® Core™ Ultra processors <br> - 12th and 13th Gen Intel® Core™ mobile processor-based server                                                                                                                                                  |
|**Supported Reference Platforms and Commercial HW** | - 4th and 5th Gen Intel® Xeon® Scalable processors on [Dell PowerEdge R760](https://www.dell.com/en-us/shop/servers-storage-and-networking/poweredge-r760-rack-server/spd/poweredge-r760/pe_r760_tm_vi_vp_sb) server <br> - Intel® Core™ Ultra processors on Intel reference platform <br> - 12th Gen Intel® Core™ desktop processors on [ASUS PE3000G](https://www.asus.com/networking-iot-servers/aiot-industrial-solutions/embedded-computers-edge-ai-systems/pe3000g/) <br> - 13th Gen Intel® Core™ desktop processors on ASRock [iEP-7020E Series](https://www.asrockind.com/en-gb/iEP-7020E) <br> - Intel® Atom® Processor [iEP-5020G Series](https://www.asrockind.com/en-gb/iEP-5020G%20Series)                                         |
|**Network**                                         | - Intel Integrated i229 <br> - Intel integrated i226 <br> - Intel® X710 Ethernet Network Adapter <br> - Intel® E810 Ethernet Network Adapter |
|**GPU**                                             | - Intel® Iris® Xe Graphics (integrated with 13th Gen Intel® Core™ mobile processor)               |

## Key Software Capabilities Updates

| **Capability**                      | **Software Packages**        |
|-------------------------------------|------------------------------|
| **Latest Software Support Summary** | - Prometheus 3.11.2 <br> - Grafana 2.6.0 <br> - cAdvisor v0.49.1 <br> - Intel® XPU SMI v1.3.5 <br> - OpenVINO 2025.4.0 <br> - OpenCV 4.12.0 <br> - FFmpeg 2025Q1 <br> - oneVPL 25.4.5 <br> - Intel® Media Driver 24.1.0 <br> - Libva 2.22.0 <br> - Mesa Driver 25.2 <br> - Intel Level Zero for GPU 1.3.29735.27-914~22.04 <br> - DiscreteTPM ubuntu-22.04 <br> - OpenSSL 3.1.4 <br> - Intel® LTS Kernel 6.6-intel <br> - Docker Compose 2.29 <br> - DockerCE 27.2 <br> - ContainerD 1.7.22 <br> - GPU driver i915 v0.28.0 |

## Edge Device Enablement Framework Profile Architecture

![Architecture](_images/Profile2.png)
*Figure 1: Architecture of the Video Analytics (VA) Enablement Node Profile Edge Device Enablement
Framework*

## Hardware Bill of Materials (HBOM)

| Feature                        | Specification |
|--------------------------------|---------------|
| **Supported Target Platforms** | - 4th and 5th Gen Intel® Xeon® Scalable Processor-based server (Dell PowerEdge R760 BIOS version) <br> - 12th and 13th Gen Intel® Core™ mobile processor-based server (ASRock on iEP-7020E Series BIOS version) <br> - Intel® Core™ Ultra processors |
| **GPU**                        | - Intel® Iris® Xe Graphics (integrated with 13th Gen Intel® Core™ mobile processor) |
| **Storage**                    | - Minimum: 128 GB <br> - Recommended: 256 GB |
| **Memory**                     | - Core: 64 GB <br> - Xeon: 128 |
| **Ethernet Adapter**           | - Xeon: <br> o Intel® X710 Ethernet Network Adapter <br> o Intel® E810 Ethernet Network Adapter <br> - Core: <br> o Intel integrated i226 |

## Software Bill of Materials (SBOM)

| Feature                         | Component |
|---------------------------------|-----------|
| **Observability and Telemetry** | - Platform-Observability<br>- Prometheus<br>- Grafana<br>- cAdvisor<br>- Intel® XPU Manager            |
| **Frameworks / Test Suite**     | - OpenVINO™ Toolkit<br>- DLStreamer<br>- OpenCV |
| **Power Management**            | - Intel Power Management |
| **Libraries**                   | - FFmpeg<br>- Intel® OneVPL<br>- Intel® Media Driver<br>- Libva<br>- Lib Mesa Driver<br>- Intel® Level Zero for GPU<br>- GPU A780<br>- Intel® Media Transport Library (iMTL)<br>- Media Communication Mesh (MCM) |
| **Security**                    | - TPM<br>- OpenSSL |
| **Container Runtime**           | Container-D |
| **Virtualization**              | QEMU-KVM |

## Enable Time of Day (TOD) Provisioning

The Edge Device Enablement Framework enables TOD provisioning through the Intel® Infrastructure
Power Manager (IPM) technology. This software allows power management provisioning to save power at
a specific time of day when Edge Nodes may be unused or underutilized. This feature delivers power
savings during non-peak hours for Edge services. You can install the feature on bare metal after
you deploy the Edge Node. To install the feature, follow the steps in
[Step 4](./get-started.md#step-4-enable-time-of-day-tod-provisioning) of the Get Started guide.

<!--hide_directive
:::{toctree}
:hidden:

Get Started <./get-started.md>
Release Notes <./release-notes.md>
Acronyms <./acronyms.md>

:::
hide_directive-->

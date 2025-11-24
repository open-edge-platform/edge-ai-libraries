# Welcome to Intel® Edge Device Enablement Framework (EEF)

The Intel® Edge Device Enablement Framework (EEF) delivers a set of curated, validated infrastructure stacks (aka profiles), providing a runtime for edge applications. It is built on a modular framework where each node is based on a common foundation of hardware, OS, and container runtime.


## Overview
This release of the Edge Device Enablement Framework currently supports three curated profiles tailoring mainly the needs of Video Analytics (VA) and industrial controller workloads.
|Profile Name             |Description      |
|-------------------------|-----------------|
|**Profile 1**: Video Analytics (VA) Enablement Node K8s Profile | - This profile has Video Analytics and Observability components along with the RKE2 K8s Cluster in a multi node <br> - Typical use case for this profile is Media and Video Analytics |
|**Profile 2**: Video Analytics (VA) Enablement Node Profile  | - This profile has Video Analytics and Observability components installed on Bare metal for Intel® Core and Intel® Xeon® systems.|
|**Profile 3**: Real Time (RT) Enablement Node Profile  | - This profile has RT kernel related components such as Real-Time Performance Measurements and Intel® Edge Controls for Industrial (ECI) customization with Ubuntu RT <br> - Typical use case for this profile is to provide real-time analytics for Industrial Controller and for Real-Time Performance Measurement (RTPM) |


## Get Started

Edge Software Hub is primarily intended for Public / External users.

EEF Profile scripts are available in the below path:
[Edge-device Enablement Framework](https://github.com/open-edge-platform/edge-ai-libraries/tree/main/frameworks/edgedevice-enablement-framework)

### Usage:

- Go to the required profile folder. Example:
```bash
cd base/va_enablement_node_profile
```
- Set executable permissions to the profile.sh script. Example: 
```bash
chmod +x "va_enablement_node_profile.sh"
```
- Execute it. Example:
```bash
"./va_enablement_node_profile.sh"
```
- Input parameters for TFCC and VPP RI use cases
```bash
"./va_enablement_node_profile.sh tfcc"
"./va_enablement_node_profile.sh vpp"
```
- Execute it with --help/-h for checking the availability of any additional use case support
```bash
"./va_enablement_node_profile.sh -h"
```
# Release Notes

## Revision History - 24.06

|       **Profile**                          |      **Summary**                 |
|--------------------------------------------|----------------------------------|
|Profile 1 : VA Enablement Node K8s Profile  | 1. Installed RKE2 agent |
|Profile 2 : VA Enablement Node Profile      | 1. Installed Media Tools - Opencv, FFMPEG, MTL, Mesa Driver, oneVPL, MCM, Intel XPU Manager, Intel Media Driver <br> 2. Installer Observability Stack for Baremetal OS - Platform-Observability-agent, Prometheus, Grafana, cAdvisor <br> 3. KVM and QEMU: Supported for bare-metal virtualization. <br> 4. Installed AI BOX Components - VA Base, VA Base-Dev, VA DLStreamer, VA OpenCV FFMPEG <br> 5. Inband Management: Support for Turtle Creek has been added. <br> 6. iGPU support enabled for core platforms. |
|Profile 3 : RT Enablement Node Profile      | 1. Installed RT kernel <br> 2. Installed Real-Time Performance Measurement (RTPM) <br> 3. Installed ECI Packages|


## Revision History - 24.08

|       **Profile**                          |      **Summary**                 |
|--------------------------------------------|----------------------------------|
|Profile 1 : VA Enablement Node K8s Profile  | 1. Inband Management: Support for Turtle Creek has been added. <br> 2. Observability Stack for Kubernetes Cluster: <br> &nbsp;&nbsp;&nbsp;&nbsp;- Platform-Observability Agent Installed directly on the OS, covering OpenTelemetry (Otel), FluentBit, and Telegraf. <br> &nbsp;&nbsp;&nbsp;&nbsp;- cAdvisor: Installed for monitoring container resource usage. <br> &nbsp;&nbsp;&nbsp;&nbsp;- Prometheus: Installed using the `prometheus-community/prometheus` Helm chart. <br> &nbsp;&nbsp;&nbsp;&nbsp;- Grafana: Installed using the `grafana/grafana` Helm chart. <br> 3. Network SRIOV Plugins: Added for enhanced networking capabilities. <br> 4. Network Feature Discovery: Implemented using Docker. <br> 5. Akri: Deployed with Docker for edge device discovery. <br> 6. IPSec Stack: Introduced for enhanced network security. <br> 7. GPU Plugins: Available through Helm charts for improved GPU management. <br> 8. KVM and QEMU: Supported for bare-metal virtualization. <br> 9. Istio Operator: Installed to manage service mesh architecture. <br> 10. OpenVINO Runtime and OpenCV: Added for AI inference and computer vision tasks. <br> 11. GPU Drivers: Integrated to enhance GPU support. <br> 12. Kubernetes Virtualization: Improved virtualization capabilities within the Kubernetes environment. <br> |
|Profile 2 : VA Enablement Node Profile      | 1. Enabled GPU drivers for Xeon platforms <br> 2. Introduced separate sets of AI Box Docker files and Docker validators for each supported platform, incorporating the necessary GPU/CPU enablement in the Release service.  <br> Included support for the Alder lake platform in AI Box Docker image build and validation. <br> 3. Enhanced the installer to set "6.6-intel" as the default kernel, which remains the default even after a reboot. <br> 4. Resolved DL-Streamer Docker build failures by generating separate installation scripts for each platform, addressing the required GPU/CPU enablement. <br> 5. Implemented functionality to handle the expiration of the External Release service token and automatically re-authenticate using a refresh token. <br> 6. Added dynamic geo-location detection and automatic GitHub mirror updates specifically for the PRC region.   |
|Profile 3 : RT Enablement Node Profile      | 1. Enabled Observability Stack: Integrated the Observability Stack along with the ECI packages. <br> 2. Installed the observability components (Platform-Observability-agent (covers, Otel, fluentbit, telegraf) Prometheus, Grafana, cAdvisor).  <br> 3. Installed Docker Images: Installed Docker images for Grafana, Loki, and Promtail.  <br>     |


## Revision History - 24.11

### Feature :-

- Added Uninstallation feature for all the profiles

### SBOM :-

|       **Profile**                          |      **Summary**                 |
|--------------------------------------------|----------------------------------|
|Profile 1 : VA Enablement Node K8s Profile  | 1. Upgraded to Ubuntu 24.04 <br> 2. enabled multi-node configuration <br> 3. Integrated Media Tools and DPDK <br> 4. Removed the helm chart installation steps from profile 1 script <br> 5. Created a new script for helm chart installation to support the multi-edge worker nodes <br> 6. Removed platform observability , fluent bit, telegraf, from baremetal <br> 7. Enabled SRIOV plugin support |
|Profile 2: VA Enablement Node Profile       | 1. Removed Release service token dependency <br> 2. Enabled NPU Support <br> 3. Added NTP Server prompt. User can directly enter their preferred NTP server |
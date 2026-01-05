# Troubleshooting


## Using REST API in Image Ingestor mode has low first inference latency

This is an expected behavior observed only for the first inference. Subsequent inferences would be considerably faster.
For inference on GPU, the first inference might be even slower. Latency for up to 15 seconds have been observed for image requests inference on GPU.
When in `sync` mode, we suggest users to provide a `timeout` with a value to accommodate for the first inference latency to avoid request time out.
Read [here](./advanced-guide/detailed_usage/rest_api/restapi_reference_guide.md#post-pipelinesnameversioninstance_id) to learn more about the API.

---

## Axis RTSP camera freezes or pipeline stops

Restart the DL Streamer pipeline server container with the pipeline that has this rtsp source.

---

## Deploying with Intel GPU K8S Extension

If you're deploying a GPU based pipeline (example: with VA-API elements like `vapostproc`, `vah264dec` etc., and/or with `device=GPU` in `gvadetect` in `dlstreamer_pipeline_server_config.json`) with Intel GPU k8s Extension, ensure to set the below details in the file `helm/values.yaml` appropriately in order to utilize the underlying GPU.
```sh
gpu:
   enabled: true
   type: "gpu.intel.com/i915"
   count: 1
```

---

## Deploying without Intel GPU K8S Extension

If you're deploying a GPU based pipeline (example: with VA-API elements like `vapostproc`, `vah264dec` etc., and/or with `device=GPU` in `gvadetect` in `dlstreamer_pipeline_server_config.json`) without Intel GPU k8s Extension, ensure to set the below details in the file `helm/values.yaml` appropriately in order to utilize the underlying GPU.
```sh
privileged_access_required: true
```

---

## Using RTSP/WebRTC streaming, S3_write or MQTT fails with GPU elements in pipeline

If you are using GPU elements in the pipeline, RTSP/WebRTC streaming, S3_write and MQTT will not work because these are expects CPU buffer. \
Add `vapostproc ! video/x-raw` before appsink element or `jpegenc` element(in case you are using S3_write) in the GPU pipeline.
```sh
# Sample pipeline

"pipeline": "{auto_source} name=source ! parsebin ! vah264dec ! vapostproc ! video/x-raw(memory:VAMemory) ! gvadetect name=detection model-instance-id=inst0 ! queue ! gvafpscounter ! gvametaconvert add-empty-results=true name=metaconvert ! gvametapublish name=destination ! vapostproc ! video/x-raw ! appsink name=appsink"
```

---

## RTSP streaming fails if you are using udfloader

If you are using udfloader<link> pipeline RTSP streaming will not work because RTSP pipeline does not support RGB, BGR or Mono format.
If you are using `udfloader pipeline` or `RGB, BGR or GRAY8` format in the pipeline, add  `videoconvert ! video/x-raw, format=(string)NV12` before `appsink` element in pipeline.
```sh
# Sample pipeline

"pipeline": "{auto_source} name=source  ! decodebin ! videoconvert ! video/x-raw,format=RGB ! udfloader name=udfloader ! gvametaconvert add-empty-results=true name=metaconvert ! gvametapublish name=destination ! videoconvert ! video/x-raw, format=(string)NV12 ! appsink name=appsink"
```

---

## Resolving Time Sync Issues in Prometheus

If you see the following warning in Prometheus, it indicates a time sync issue.

**Warning: Error fetching server time: Detected xxx.xxx seconds time difference between your browser and the server.**

You can following the below steps to synchronize system time using NTP.
1. **Install systemd-timesyncd** if not already installed:
   ```bash
   sudo apt install systemd-timesyncd
   ```

2. **Check service status**:
   ```bash
   systemctl status systemd-timesyncd
   ```

3. **Configure an NTP server** (if behind a corporate proxy):
   ```bash
   sudo nano /etc/systemd/timesyncd.conf
   ```
   Add:
   ```ini
   [Time]
   NTP=corp.intel.com
   ```
   Replace `corp.intel.com` with a different ntp server that is supported on your network.

4. **Restart the service**:
   ```bash
   sudo systemctl restart systemd-timesyncd
   ```

5. **Verify the status**:
   ```bash
   systemctl status systemd-timesyncd
   ```

This should resolve the time discrepancy in Prometheus.

---

## WebRTC Stream on web browser
The firewall may prevent you from viewing the video stream on web browser. Please disable the firewall using this command.
```sh
sudo ufw disable
```

---

## Inferencing on NPU

To perform inferencing on an NPU device (for platforms with NPU accelerators such as Ultra Core processors), ensure you have completed the required pre-requisites. Refer to the instructions [here](https://github.com/open-edge-platform/dlstreamer/blob/master/docs/source/dev_guide/advanced_install/advanced_install_guide_prerequisites.md#prerequisite-2---install-intel-npu-drivers) to install Intel NPU drivers.

---

## Unable to run GPU inference on some Arrow Lake machines with `resource allocation failed` errors

For example:

`ERROR vafilter gstvafilter.c:390:gst_va_filter_open:<vafilter0> vaCreateContext: resource allocation failed`

This issue has been observed on systems with the Ultra Core 7 265K processor running Ubuntu 22.04.
There are few options to fix this.

One is updating the kernel to `6.11.11-061111-generic` in the host system.

Alternately, install OpenCL runtime packages in the host system. Refer to the instructions from OpenVINO documentation [here](https://docs.openvino.ai/2025/get-started/install-openvino/configurations/configurations-intel-gpu.html#linux) to install GPU drivers.

---

## Error Logs

View the container logs using this command.
```sh
docker logs -f <CONTAINER_NAME>
```
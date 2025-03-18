# Contents
- [Contents](#contents)
- [User Defined Functions (UDF) Overview ](#User-Defined-Functions-(UDF)-Overview)
  - [UDF Config](#UDF-Config)
  - [Gstreamer `udfloader` Plug-in](#Gstreamer-udfloader-plug-in)
  - [Run Sample UDFs](#Run-Sample-UDFs)
    - [Python UDFs Run with Single Config](#Python-UDFs-run-with-single-config)
    - [Python UDF to Resize Frame](#Python-UDF-to-resize-frame)

# User Defined Functions (UDF) Overview
For more information about User Defined Functions (UDFs), refer to this [link.](../../common/video/udfs/README.md)
- Sample Python UDFs here [udfs/python](../user_scripts/udfs/python)

## UDF Config
For more information about UDF configuration, refer to this [link](../../common/video/udfs/README.md).
* [Click](../user_scripts/udfs/configs) for some example configurations

Examples of UDF config with native and python udfs together
```json
{
    "udfs":
    [
        {
            "name": "python.dummy",
            "type": "python"
        },
        {
            "name": "dummy",
            "type": "native"
        }
    ]
}
```

##  Gstreamer `udfloader` Plug-in 

Gstreamer `udfloader` plug-in supports loading and executing of python [UDFs](../user_scripts/udfs).

* Property: `config` - must be set with UDF configuration json file path.
* Attaches metadata from UDF to buffer as GVAJSONMeta.

## Run Sample UDFs

[PCB Demo](../../common/video/udfs/python/pcb/README.md)

- Config path [udfs/configs/python_pcb.json](../user_scripts/udfs/configs/python_pcb.json)
- Code [udfs/python/pcb](../user_scripts/udfs/python/pcb)
- RUN PCB Demo using gst-launch

```sh
gst-launch-1.0 uridecodebin uri=<path_to_pcb_d2000.avi_file_in_EII> ! videoconvert ! video/x-raw,format=BGR ! udfloader config="/home/pipeline-server/udfs/configs/python_pcb.json" ! gvametapublish file-format=json-lines ! fakesink

```
- RUN the PCB Demo using gstreamer [python appsink](tests/gst_appsink.py)

```sh
cd tests/
python3 gst_appsink.py

```

### Python UDFs Run with Single Config

- Config path [udfs/configs/dummy.json](../user_scripts/udfs/configs/dummy.json)
- Python code [udfs/python/dummy.py](../user_scripts/udfs/python/dummy.py)
- **RUN Python UDFs**

```sh
gst-launch-1.0 uridecodebin uri=<path_to_pcb_d2000.avi_file_in_EII> ! videoconvert ! video/x-raw,format=BGR ! udfloader config="/home/pipeline-server/udfs/configs/dummy.json" ! gvametapublish file-format=json-lines ! fakesink
```

### Python UDF to Resize Frame
- Config path [udfs/configs/python_resize.json](../user_scripts/udfs/configs/python_resize.json)
- Code [udfs/python/resize.py](../user_scripts/udfs/python/resize.py)
- This gstreamer pipeline saves resized video into `/tmp/python_resize.avi`.

```sh
gst-launch-1.0 uridecodebin uri=<path_to_pcb_d2000.avi_file_in_EII> ! videoconvert ! video/x-raw,format=BGR ! udfloader config="/home/pipeline-server/udfs/configs/python_resize.json" ! gvametapublish file-format=json-lines ! jpegenc ! avimux ! filesink location=/tmp/python_resize.avi
```

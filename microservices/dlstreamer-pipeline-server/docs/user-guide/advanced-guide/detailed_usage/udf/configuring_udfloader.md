#  Configuring udfloader element
The `udfloader` element has a single configurable property with the name `config`. This field expects a JSON string as an input. They key/value pairs in the JSON string should correspond to the constructor arguments of the UDFs class. Currently only atomic data types are supported.

**Sample UDF config**</br>

The UDF config should be passed to the `udfs` key in the EIS config file. The below example configures the `udfloader` element to load and execute a single UDF, which in this case happens to be the `geti_udf`.

  ```json
  {
        "udfs": [
            {
                "name": "python.geti_udf.geti_udf",
                "type": "python",
                "device": "CPU",
                "visualize": "false",
                "deployment": "./resources/geti/pallet_defect_detection/deployment",
                "metadata_converter": "null",
            }
        ]
  }
  ```
  In order to chain multiple UDFs, simply provide the configs for UDFs as additional entries in the `udfs` array in the EIS config file as shown below
  ``` json
    {
        "udfs": [
            {
                "name": "udf1",
                "type": "python",
                "arg1": "value1",
                "arg2": "value2"
            },
            {
                "name": "udf2",
                "type": "python",
                "arg1": "value1",
                "arg2": "value2"
            }
        ]
    }
  ```

<!-- ## Anomalib

Refer to the [doc](./anomalib_doc.md) for more details on Anomalib.

When trained/exported model is available, anomalib udf can be used for running inference.
As an example, a custom STFPM model trained on [Amazon’s Visual Anomaly (Visa) dataset](https://registry.opendata.aws/visa/) is included to detect anomalies in PCB.

Inferencing could be configured to be based on
- `openvino` - default openvino inferencer provided by Anomalib or
- `openvino_nomask` - custom openvino no mask inferencer derived from openvino inferencer which allows for image resolution to not have an impact on inference time.

Refer the below sample configuration to run the Anomalib UDF.

```json
  "udfs": [
            {
                "device": "CPU",
                "task": "classification",
                "inferencer": "openvino_nomask",
                "model_metadata": "/home/pipeline-server/udfs/python/anomalib_udf/stfpm/metadata.json",
                "name": "python.anomalib_udf.inference",
                "type": "python",
                "visualize": "true",
                "weights": "/home/pipeline-server/udfs/python/anomalib_udf/stfpm/model.onnx"
            }
        ]

```

**Note**: `inferencer` config parameter can be used to change b/w the default openvino inferencer provided by anomalib and the openvino_nomask inferencer which inherits from openvino inferencer. -->


## Pallet Defect Detection

This Geti udf supports deploying a project for local inference with OpenVINO using Intel® Geti™ SDK python package. It uses a Geti based Pallet Defect Detection model.


Refer the below config for the default config used for this Geti udf:

```json
 "udfs": [
            {
                "name": "python.geti_udf.geti_udf",
                "type": "python",
                "device": "CPU",
                "deployment": "./resources/geti/pallet_defect_detection/deployment",
                "visualize": "false",
                "metadata_converter": "null"
            }
        ]

```

## Add Label

This is a dummy udf for providing sample classification (anomalib usecase) data.

Add Label UDF is developed to facilitate anomalib training data collection where one is pointing camera on anomalous or non-anomalous product. While you point a camera to a given category of scene, default label value which is a configurable field (`"anomalous": "true" or "anomalous": "false"`) in this UDF is applied to every frame. This process needs to be repeated to every type of class (`"anomalous": "true" or "anomalous": "false"`) that you want to capture from the scene for training.

The following example shows the configuration for add label UDF. Either set `"anomalous": "true"` or `"anomalous": "false"`

```json
    "udfs": [
        {
            "type": "python",
            "name": "python.add_label",
            "anomalous": "true"
        }
    ]
```

There is no AI model involved. It is a simple UDF script that labels the data with default label values and saves in DataStore which is further expected to be consumed by Visualizer microservice and Intel® Edge Data Collection microservice.
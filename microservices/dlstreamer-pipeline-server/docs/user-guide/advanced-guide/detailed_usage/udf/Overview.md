# User Defined Functions (UDF)

* [UDF Writing Guide](#udf-writing-guide)
    - [How-To Guide for Writing UDF](#how-to-guide-for-writing-udf)
    - [Configuring UDFLoader element](#configuring-udfloader-element)
      - [Pallet Defect Detection](#pallet-defect-detection)
      - [Add Label](#add-label)

## UDF Writing Guide
An User Defined Function (UDF) is a chunk of user code that can transform video frames and/or manipulate metadata. For example, a UDF can act as filter, preprocessor, classifier or a detector. These User Defined Functions can be developed in Python. DL Streamer Pipeline Server provides a GStreamer plugin - `udfloader` using which users can configure and load arbitrary UDFs. These UDFs are then called once for each video frame.

## How-To Guide for Writing UDF
A detailed guide for developing UDFs is available [here](./UDF_writing_guide).

##  Configuring udfloader element
The `udfloader` element has a single configurable property with the name `config`. This field expects a JSON string as an input. They key/value pairs in the JSON string should correspond to the constructor arguments of the UDFs class. Currently only atomic data types are supported.

**Sample UDF config**</br>

The UDF config should be passed to the `udfs` key in the config file. The below example configures the `udfloader` element to load and execute a single UDF, which in this case happens to be the `geti_udf`.

  ```json
  {
        "udfs": [
            {
                "name": "python.geti_udf.geti_udf",
                "type": "python",
                "device": "CPU",
                "visualize": "false",
                "deployment": "./resources/geti/person_detection/deployment",
                "metadata_converter": null,
            }
        ]
  }
  ```
  In order to chain multiple UDFs, simply provide the configs for UDFs as additional entries in the `udfs` array in the config file as shown below
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

<!-- ### Anomalib
To learn about Anomalib and how to configure Anomalib UDF, refer to this [section](./configuring_udfloader.md#anomalib). -->

### Pallet Defect Detection
To learn how to configure Geti Pallet Defect Detection UDF, refer to this [section](./configuring_udfloader.md#pallet-defect-detection).

### Add Label
To learn how to configure Add Label UDF, refer to this [section](./configuring_udfloader.md#add-label).

<!--hide_directive
```{toctree}
:maxdepth: 5
:hidden:
UDF_writing_guide.md
configuring_udfloader.md
```
hide_directive-->

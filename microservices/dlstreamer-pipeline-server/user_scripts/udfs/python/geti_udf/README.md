# Geti UDF:

This Geti UDF supports functionality for deploying a project for local inference with OpenVINO using Intel® Geti™ SDK python package.

> **Status:** The upstream Geti SDK repository is archived and deprecated, is no longer
> maintained, supports Geti v2.x but not v3.0+, and reports known security issues. The SDK
> is not included in DLSPS images starting with the 2026.3 release. Use this UDF only if you
> have reviewed and accept these limitations and installed a compatible SDK separately.

As a pre-requisite for running this Geti UDF, first populate the deployment directory generated from Geti to the Geti UDF directory at `[WORKDIR]/dlstreamer-pipeline-server/user-scripts/udfs/geti_udf` before running DL Streamer Pipeline Server service.

Refer to the config below for the default config used for this Geti UDF:

```json
 "udfs": [
            {
                "name": "python.geti_udf.geti_udf",
                "type": "python",
                "device": "CPU",
                "deployment": "./resources/models/geti/person_detection/deployment",
                "visualize": "false",
                "metadata_converter": "geti_to_dcaas"
            }
        ]

```

As seen in the above snippet, the path to the deployment directory is fixed to the mentioned path. In case the UDF is not able to find the deployment directory in the mentioned path directory (i.e. inside the geti_udf), it will fail.

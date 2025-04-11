### Geti UDF:

This geti udf supports functionality for deploying a project for local inference with OpenVINO using Intel® Geti™ SDK python package.

As a pre-requisite for running this geti udf, one would need to populate the deployment directory generated from Geti to the [geti udf directory]([WORKDIR]/dlstreamer-pipeline-server/user-scripts/udfs/geti_udf) before running DL Streamer Pipeline Server service.

Refer the below config for the default config used for this geti udf:

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

As seen in the above snip the path to the deployment directory is fixed to the mentioned path. In case the UDF is not able to find the deployment directory in the mentioned path (i.e. inside the geti_udf) directory it will fail.

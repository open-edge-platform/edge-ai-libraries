# Anomalib

 **Contents**

<!-- - [Anomalib](#about-anomalib) -->
- [Supported Version](#supported-version-in-evam)
- [Training](#training)
- [Supported Models in EVAM](#supported-models-in-evam)
- [Inference using Anomalib UDF](#inference-using-anomalib-udf)


<!-- ## About Anomalib 
Anomalib is a deep learning library that aims to collect state-of-the-art anomaly detection algorithms for benchmarking on both public and private datasets. Anomalib provides several ready-to-use implementations of anomaly detection algorithms described in the recent literature, as well as a set of tools that facilitate the development and implementation of custom models. The library has a strong focus on visual anomaly detection, where the goal of the algorithm is to detect and/or localize anomalies within images or videos in a dataset. 

For more information on Anomalib refer to [Anomalib documentation](https://anomalib.readthedocs.io/en/latest/) & [Github reference](https://github.com/openvinotoolkit/anomalib/tree/v0.7.0) -->

## Supported version in EVAM
- v0.7.0

## Training

Anomalib includes ready to use anomaly detection models. A model can be trained based on default config provided for the model or can be customized for a particular dataset and category.

More details on Training and exporting a trained model can be found [here](https://github.com/openvinotoolkit/anomalib/tree/v0.7.0?tab=readme-ov-file).


## Supported models in EVAM

Currently a subset of available anomaly detection models in anomalib are supported in EVAM:
- [STFPM](https://github.com/openvinotoolkit/anomalib/blob/v0.7.0/src/anomalib/models/stfpm)
- [PADIM](https://github.com/openvinotoolkit/anomalib/blob/v0.7.0/src/anomalib/models/padim)
- [DFM](https://github.com/openvinotoolkit/anomalib/blob/v0.7.0/src/anomalib/models/dfm)


## Inference using Anomalib UDF

When trained/exported model is available, `[EVAM_WORKDIR]/user_scripts/udfs/python/anomalib_udf/` can be used for running inference.
As an example, a custom STFPM model trained on [Amazon’s Visual Anomaly (Visa) dataset](https://registry.opendata.aws/visa/) is included to detect anomalies in PCB.

Inferencing could be configured to be based on 
- `openvino` - default openvino inferencer provided by Anomalib or
- `openvino_nomask` - custom openvino no mask inferencer derived from openvino inferencer which allows for image resolution to not have an impact on inference time.

For more details on the configuration of the UDF, refer to this `[EVAM_WORKDIR]//user_scripts/udfs/python/anomalib_udf/README.md`. 
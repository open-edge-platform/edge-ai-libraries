# Time Series Analytics Microservice

It is a powerful, flexible solution for real-time analysis of time series data. Built on top of Kapacitor, it enables both streaming and batch processing, seamlessly integrating with InfluxDB for efficient data storage and retrieval.

> **Note**:
As this docker image is using ubuntu packages coming from Kapacitor base docker image, please note that the usage
of this docker image is intended for demo purposes only and not intended for production use. To receive expanded 
security maintenance from Canonical on the Ubuntu base layer, you may follow the [how-to guide to enable Ubuntu Pro
in a Dockerfile](https://documentation.ubuntu.com/pro-client/en/docs/howtoguides/enable_in_dockerfile/) which require the image to be rebuilt

## Supported versions
---

### [1.1.0-weekly](https://docs.openedgeplatform.intel.com/dev/edge-ai-libraries/time-series-analytics/release_notes/dec-2025.html#v1-1-0)

This is a weekly development build, may not be stable. 

#### Artifacts

1. [Docker image](https://hub.docker.com/layers/intel/ia-time-series-analytics-microservice/1.1.0-weekly/images/sha256-0bfc9a88234a0146e16947b3154854ad8242084cafc91b8b6ab2ca6a615f2f06)
2. [Helm charts](https://hub.docker.com/layers/intel/time-series-analytics-microservice/1.1.0-weekly/images/sha256-005a7965350a11dbdcab1d15807e57c52562adbc60d0c53ad1345f1bd9f0de04)

#### Deploy using Docker Compose
---
For more details on deployment, refer to the [documentation](https://docs.openedgeplatform.intel.com/dev/edge-ai-libraries/time-series-analytics/get-started.html).

#### Deploy on Kubernetes cluster using Helm Charts
---
For more details on deployment, refer to the [documentation](https://docs.openedgeplatform.intel.com/dev/edge-ai-libraries/time-series-analytics/how-to-deploy-with-helm.html).


### [1.0.0](https://docs.openedgeplatform.intel.com/2025.1/edge-ai-libraries/time-series-analytics/release_notes/aug-2025.html#v1-0-0)

This is a stable release.

#### Artifacts

1. [Docker image](https://hub.docker.com/layers/intel/ia-time-series-analytics-microservice/1.0.0/images/sha256-cfdc35ff984203fb33dcbb8ae746e38f303c5b460684727244e4ad0210236ed1)
2. [Helm charts](https://hub.docker.com/layers/intel/time-series-analytics-microservice/1.0.0/images/sha256-6930b6cbd378d1a94c53b89a34fb567f61a5979e38928939445f8d21dac27cb0)

#### Deploy using Docker Compose
---
For more details on deployment, refer to the [documentation](https://docs.openedgeplatform.intel.com/2025.1/edge-ai-libraries/time-series-analytics/get-started.html).

#### Deploy on Kubernetes cluster using Helm Charts
---
For more details on deployment, refer to the [documentation](https://docs.openedgeplatform.intel.com/2025.1/edge-ai-libraries/time-series-analytics/how-to-deploy-with-helm.html).


## License Agreement
Copyright (C) 2024 Intel Corporation.

Licensed under the Apache License, Version 2.0 (the "License"); you may not use this file except in compliance with the License. You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0⁠

## Legal Information
Intel, the Intel logo, and Xeon are trademarks of Intel Corporation in the U.S. and/or other countries.

*Other names and brands may be claimed as the property of others.
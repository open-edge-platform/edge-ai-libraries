[![License](https://img.shields.io/badge/License-Apache%202.0-blue)]()
[![#Libraries](https://img.shields.io/badge/%23Libraries-6-green)]()
[![#Microservices](https://img.shields.io/badge/%23Microservices-4-green)]()
[![#Tools](https://img.shields.io/badge/%23Tools-1-green)]()
[![#Samples](https://img.shields.io/badge/%23Samples-2-green)]()

# Edge-AI-Libraries

## Overview

The **Edge AI Libraries** project hosts a collection of libraries, microservices, and tools for Edge application development. This project also includes sample applications to showcase the generic AI use cases.

Key components of the **Edge AI Libraries**:

| Component | Category | Get Started | Developers Docs |
|:----------|:---------|:------------|:-----------------|
| [Anomalib](https://github.com/open-edge-platform/anomalib) | Library | [Link](https://github.com/open-edge-platform/anomalib?tab=readme-ov-file#-introduction) | [API Reference](https://github.com/open-edge-platform/anomalib?tab=readme-ov-file#-training) |
| [Dataset Management Framework (Datumaro)](https://github.com/open-edge-platform/datumaro)[`*`](#license) | Library | [Link](https://github.com/open-edge-platform/datumaro?tab=readme-ov-file#features) | [API Reference](https://open-edge-platform.github.io/datumaro/latest/docs/reference/datumaro_module.html) |
| [Deep Learning Streamer](libraries/dl-streamer) | Library | [Link](https://dlstreamer.github.io/get_started/get_started_index.html) | [API Reference](https://dlstreamer.github.io/elements/elements.html) |
| [Intel&reg; Geti&trade; SDK](https://github.com/open-edge-platform/geti-sdk) | Library | [Link](https://github.com/open-edge-platform/geti-sdk?tab=readme-ov-file#getting-started) | [API Reference](https://github.com/open-edge-platform/geti-sdk?tab=readme-ov-file#high-level-api-reference) |
| [OpenVINO&trade; toolkit](https://github.com/openvinotoolkit/openvino) | Library | [Link](https://docs.openvino.ai/2025/index.html) | [API Reference](https://docs.openvino.ai/2025/api/api_reference.html) |
| [OpenVINO&trade; Training Extensions](https://github.com/open-edge-platform/training_extensions) | Library | [Link](https://github.com/open-edge-platform/training_extensions?tab=readme-ov-file#introduction) | [API Reference](https://github.com/open-edge-platform/training_extensions?tab=readme-ov-file#quick-start) |
| [OpenVINO&trade; Model API](https://github.com/open-edge-platform/model_api) | Library | [Link](https://github.com/open-edge-platform/model_api?tab=readme-ov-file#installation) | [API Reference](https://github.com/open-edge-platform/model_api?tab=readme-ov-file#usage) |
| [Deep Learning Streamer Pipeline Server](microservices/dlstreamer-pipeline-server) | Microservice | [Link](microservices/dlstreamer-pipeline-server#quick-try-out) | [API Reference](microservices/dlstreamer-pipeline-server/docs/user-guide/api-docs/pipeline-server.yaml) |
| [Document Ingestion](microservices/document-ingestion) | Microservice | [Link](microservices/document-ingestion/pgvector/docs/get-started.md) | [API Reference](microservices/document-ingestion/pgvector/docs/dataprep-api.yml) |
| [Model Registry](microservices/model-registry) | Microservice | [Link](microservices/model-registry/docs/user-guide/get-started.md) | [API Reference](microservices/model-registry/docs/user-guide/api-docs/openapi.yaml) |
| [Object Store](microservices/object-store) | Microservice |  [Link](microservices/object-store/minio-store#configuration) | [Usage](microservices/object-store/minio-store#usage) |
| [Intel® Geti™](https://github.com/open-edge-platform/geti)[`*`](#license) | Tool | [Link](https://geti.intel.com/) | [Docs](https://docs.geti.intel.com) |
| [Intel® SceneScape](https://github.com/open-edge-platform/scenescape)[`*`](#license) | Tool | [Link](https://docs.openedgeplatform.intel.com/scenescape/main/user-guide/Getting-Started-Guide.html) | [Docs](https://docs.openedgeplatform.intel.com/scenescape/main/toc.html) |
| [Visual Pipeline and Platform Evaluation Tool](tools/visual-pipeline-and-platform-evaluation-tool) | Tool | [Link](tools/visual-pipeline-and-platform-evaluation-tool/docs/user-guide/get-started.md) | [Build](tools/visual-pipeline-and-platform-evaluation-tool/docs/user-guide/how-to-build-source.md) instructions |
| [Chat Question and Answer](sample-applications/chat-question-and-answer) | Sample Application |  [Link](sample-applications/chat-question-and-answer/docs/user-guide/get-started.md) | [Build](sample-applications/chat-question-and-answer/docs/user-guide/build-from-source.md) instructions |
| [Chat Question and Answer Core](sample-applications/chat-question-and-answer-core) | Sample Application | [Link](sample-applications/chat-question-and-answer-core/docs/user-guide/get-started.md) | [Build](sample-applications/chat-question-and-answer-core/docs/user-guide/build-from-source.md) instructions |


> Intel, the Intel logo, OpenVINO, and the OpenVINO logo are trademarks of Intel Corporation or its subsidiaries.

Please visit each library/microservice/tool/sample sub-directory for respective **Getting Started**, **Build** instructions and **Development** guides.

## More Sample Applications

Please visit the [**Edge AI Suites**](https://github.com/open-edge-platform/edge-ai-suites) project for a broader set of sample applications targeted at specific industry segments.

## Contribute

To learn how to contribute to the project, see [CONTRIBUTING.md](CONTRIBUTING.md).

## Community and Support

For support, please submit your bug report and feature request to [Github Issues](https://github.com/open-edge-platform/edge-ai-libraries/issues).

## License

The **Edge AI Libraries** project is licensed under the [APACHE 2.0](LICENSE) license, except for the following components:

| Component | License |
|:----------|:--------|
| Dataset Management Framework (Datumaro) | [MIT License](https://github.com/open-edge-platform/datumaro/blob/develop/LICENSE) |
| Intel® Geti™ | [Limited Edge Software Distribution License](https://github.com/open-edge-platform/geti/blob/main/LICENSE) |
| Intel® SceneScape | [Limited Edge Software Distribution License](https://github.com/open-edge-platform/scenescape/blob/main/LICENSE) |



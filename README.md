[![License](https://img.shields.io/badge/License-Apache%202.0-blue)]()
[![#Libraries](https://img.shields.io/badge/%23Libraries-6-green)]()
[![#Microservices](https://img.shields.io/badge/%23Microservices-4-green)]()
[![#Tools](https://img.shields.io/badge/%23Tools-1-green)]()
[![#Samples](https://img.shields.io/badge/%23Samples-2-green)]()

# Edge-AI-Libraries

## Overview

The **Edge AI Libraries** project hosts a collection of libraries, microservices, and tools for Edge application development. This project also includes sample applications to showcase the generic AI use cases.

Some of these components are available as git submodules, and can be fetched with `git submodule update --init --recursive`

Key components of the **Edge AI Libraries**:

| Component | Category | More Information |
|:----------|:---------|:-----------------|
| [Anomalib](https://github.com/open-edge-platform/anomalib)                                                                          | Library            | [Documentation](https://github.com/open-edge-platform/anomalib?tab=readme-ov-file#-introduction), [API Reference](https://github.com/open-edge-platform/anomalib?tab=readme-ov-file#-training) |
| [Dataset Management Framework (Datumaro)](https://github.com/open-edge-platform/datumaro)[`*`](#license)                            | Library            | [Documentation](https://github.com/open-edge-platform/datumaro?tab=readme-ov-file#features), [API Reference](https://open-edge-platform.github.io/datumaro/latest/docs/reference/datumaro_module.html) |
| [Deep Learning Streamer](libraries/dl-streamer)                                                                                     | Library            | [Documentation](https://docs.openedgeplatform.intel.com/dev/edge-ai-libraries/dl-streamer/get_started/get_started_index.html), [API Reference](./libraries/dl-streamer/docs/source/elements/elements.md) |
| [ECAT EnableKit](libraries/edge-control-libraries/fieldbus/ecat-enablekit)                                                          | Library            | [Documentation](./libraries/edge-control-libraries/fieldbus/ecat-enablekit/README.md), [API Reference](./libraries/edge-control-libraries/fieldbus/ecat-enablekit/docs/ecat_intro.md) |
| [EtherCAT Masterstack w/Intel silicon support](libraries/edge-control-libraries/fieldbus/ethercat-masterstack)                      | Library            | [Documentation](./libraries/edge-control-libraries/fieldbus/ethercat-masterstack/README.md), [API Reference](https://docs.etherlab.org/ethercat/1.6/pdf/ethercat_doc.pdf) |
| [FLANN optimized with oneAPI DPC++](libraries/robotics-ai-libraries/flann)                                                          | Library            | [Documentation](./libraries/robotics-ai-libraries/flann/README.md), [API Reference](https://www.cs.ubc.ca/research/flann/uploads/FLANN/flann_manual-1.8.4.pdf) |
| [Intel&reg; Geti&trade; SDK](https://github.com/open-edge-platform/geti-sdk)                                                        | Library            | [Documentation](https://open-edge-platform.github.io/geti-sdk/index.html), [API Reference](https://open-edge-platform.github.io/geti-sdk/api_reference.html) |
| [OpenVINO&trade; toolkit](https://github.com/openvinotoolkit/openvino)                                                              | Library            | [Documentation](https://docs.openvino.ai/2025/index.html), [API Reference](https://docs.openvino.ai/2025/api/api_reference.html) |
| [OpenVINO&trade; Training Extensions](https://github.com/open-edge-platform/training_extensions)                                    | Library            | [Documentation](https://github.com/open-edge-platform/training_extensions?tab=readme-ov-file#introduction), [API Reference](https://github.com/open-edge-platform/training_extensions?tab=readme-ov-file#quick-start) |
| [OpenVINO&trade; Model API](https://github.com/open-edge-platform/model_api)                                                        | Library            | [Documentation](https://github.com/open-edge-platform/model_api?tab=readme-ov-file#installation), [API Reference](https://github.com/open-edge-platform/model_api?tab=readme-ov-file#usage) |
| [Audio Analyzer](microservices/audio-analyzer)                                                                                      | Microservice       | [Documentation](https://docs.openedgeplatform.intel.com/dev/edge-ai-libraries/audio-analyzer/index.html), [API Reference](https://docs.openedgeplatform.intel.com/dev/edge-ai-libraries/audio-analyzer/api-reference.html) |
| [ORB Extractor](libraries/robotics-ai-libraries/orb-extractor)                                                                      | Library            | [Documentation](./libraries/robotics-ai-libraries/orb-extractor/README.md), [API Reference](./libraries/robotics-ai-libraries/orb-extractor/include/orb_extractor.h) |
| [PCL optimized with oneAPI DPC++](libraries/robotics-ai-libraries/pcl)                                                              | Library            | [Documentation](https://github.com/open-edge-platform/edge-ai-libraries/blob/main/libraries/robotics-ai-libraries/pcl/README.md#pcl-optimized-with-intel-oneapi-dpc) | [API Reference](https://pointclouds.org/documentation/annotated.html) |
| [PLCopen Servo](libraries/edge-control-libraries/plcopen-motion-control/plcopen-servo)                                              | Library            | [Documentation](https://github.com/open-edge-platform/edge-ai-libraries/tree/main/libraries/edge-control-libraries/plcopen-motion-control/plcopen-servo) | [API Reference](https://docs.openedgeplatform.intel.com/edge-ai-libraries/plcopen-motion-control/main/rt-motion/rt-motion.html#run-rtmotion-with-ethercat-servo) |
| [Real-time Data Agent](libraries/edge-control-libraries/rt-data-agent)                                                              | Library            | [Documentation](./libraries/edge-control-libraries/rt-data-agent/README.md), [API Reference](./libraries/edge-control-libraries/rt-data-agent/README.md) |
| [RTmotion](libraries/edge-control-libraries/plcopen-motion-control/plcopen-motion)                                                  | Library            | [Documentation](https://docs.openedgeplatform.intel.com/edge-ai-libraries/plcopen-motion-control/main/rt-motion/rt-motion.html), [API Reference](https://docs.openedgeplatform.intel.com/edge-ai-libraries/plcopen-motion-control/main/rt-motion/rt-motion.html#rtmotion-function-blocks) |
| [Deep Learning Streamer Pipeline Server](microservices/dlstreamer-pipeline-server)                                                  | Microservice       | [Documentation](https://docs.openedgeplatform.intel.com/dev/edge-ai-libraries/dlstreamer-pipeline-server/index.html), [API Reference](https://docs.openedgeplatform.intel.com/dev/edge-ai-libraries/dlstreamer-pipeline-server/api-reference.html) |
| [Document Ingestion](microservices/document-ingestion/pgvector)                                                                     | Microservice       | [Documentation](./microservices/document-ingestion/pgvector/docs/get-started.md), [API Reference](microservices/document-ingestion/pgvector/docs/dataprep-api.yml) |
| [Model Registry](microservices/model-registry)                                                                                      | Microservice       | [Documentation](https://docs.openedgeplatform.intel.com/2025.1/edge-ai-libraries/model-registry/index.html), [API Reference](https://docs.openedgeplatform.intel.com/dev/edge-ai-libraries/model-registry/api-reference.html) |
| [Multimodal Embedding Serving](microservices/multimodal-embedding-serving)                                                          | Microservice       | [Documentation](./microservices/multimodal-embedding-serving/docs/user-guide/get-started.md), [API Reference](microservices/multimodal-embedding-serving/docs/user-guide/api-docs/openapi.yaml) |
| [Time Series Analytics Microservice](microservices/time-series-analytics)                                                           | Microservice       | [Documentation](https://docs.openedgeplatform.intel.com/edge-ai-libraries/time-series-analytics/main/user-guide/Overview.html), [API Reference](https://docs.openedgeplatform.intel.com/edge-ai-libraries/time-series-analytics/main/user-guide/api-reference.html) |
| [Vector Retriever (with Milvus)](microservices/vector-retriever/milvus/)                                                            | Microservice       | [Documentation](https://docs.openedgeplatform.intel.com/dev/edge-ai-libraries/vector-retriever/index.html), [API Reference](https://docs.openedgeplatform.intel.com/dev/edge-ai-libraries/vector-retriever/api-reference.html) |
| [Visual-Data Preparation for Retrieval (with Milvus)](microservices/visual-data-preparation-for-retrieval/milvus/)                  | Microservice       | [Documentation](./microservices/visual-data-preparation-for-retrieval/milvus/docs/user-guide/get-started.md), [API Reference](./microservices/visual-data-preparation-for-retrieval/milvus/docs/user-guide/api-reference.md) |
| [Visual-Data Preparation for Retrieval (with VDMS)](microservices/visual-data-preparation-for-retrieval/vdms/)                      | Microservice       | [Documentation](./microservices/visual-data-preparation-for-retrieval/vdms/docs/user-guide/get-started.md), [API Reference](microservices/visual-data-preparation-for-retrieval/vdms/docs/user-guide/api-reference.md) |
| [VLM Inference Serving](microservices/vlm-openvino-serving)                                                                         | Microservice       | [Documentation](./microservices/vlm-openvino-serving/README.md) |
| [Intel® Geti™](https://github.com/open-edge-platform/geti)[`*`](#license)                                                           | Tool               | [Documentation](https://docs.geti.intel.com), [Product Page](https://geti.intel.com/) |
| [Intel® SceneScape](https://github.com/open-edge-platform/scenescape)[`*`](#license)                                                | Tool               | [Documentation](https://docs.openedgeplatform.intel.com/scenescape/main/user-guide/Getting-Started-Guide.html), [Docs](https://docs.openedgeplatform.intel.com/scenescape/dev/user-guide/api-reference.html) |
| [Visual Pipeline and Platform Evaluation Tool](tools/visual-pipeline-and-platform-evaluation-tool)                                  | Tool               | [Documentation](https://docs.openedgeplatform.intel.com/dev/edge-ai-libraries/visual-pipeline-and-platform-evaluation-tool/index.html), [Build instructions](https://docs.openedgeplatform.intel.com/dev/edge-ai-libraries/visual-pipeline-and-platform-evaluation-tool/how-to-build-source.html) |
| [Chat Question and Answer](sample-applications/chat-question-and-answer)                                                            | Sample Application | [Documentation](https://docs.openedgeplatform.intel.com/dev/edge-ai-libraries/chat-question-and-answer/index.html), [Build instructions](https://docs.openedgeplatform.intel.com/dev/edge-ai-libraries/chat-question-and-answer/build-from-source.html) |
| [Chat Question and Answer Core](sample-applications/chat-question-and-answer-core)                                                  | Sample Application | [Documentation](https://docs.openedgeplatform.intel.com/edge-ai-libraries/chat-question-and-answer-core/main/user-guide/overview.html), [Build instructions](https://docs.openedgeplatform.intel.com/edge-ai-libraries/chat-question-and-answer-core/main/user-guide/build-from-source.html) |
| [Document Summarization](sample-applications/document-summarization)                                                                | Sample Application | [Documentation](https://docs.openedgeplatform.intel.com/dev/edge-ai-libraries/document-summarization/index.html), [Build instructions](https://docs.openedgeplatform.intel.com/dev/edge-ai-libraries/document-summarization/build-from-source.html) |
| [PLCopen Benchmark](sample-applications/plcopen-benchmark)                                                                          | Sample Application | [README](./sample-applications/plcopen-benchmark/README.md) |
| [PLCopen Databus](sample-applications/plcopen-databus)                                                                              | Sample Application | [README](./sample-applications/plcopen-databus/README.md) |
| [Video Search and Summarization](sample-applications/video-search-and-summarization)                                                | Sample Application | [Documentation](https://docs.openedgeplatform.intel.com/dev/edge-ai-libraries/video-search-and-summarization/index.html), [Build instructions](https://docs.openedgeplatform.intel.com/dev/edge-ai-libraries/video-search-and-summarization/build-from-source.html) |
| [Optimized Isolation Forest Classifier Training and Inference Microservice](https://github.com/intel/isolation-forest-microservice) | Microservice       | [Documentation](https://github.com/intel/isolation-forest-microservice/blob/main/README.md) |
| [Optimizied Random Forest Training and Inference Microservice](https://github.com/intel/random-forest-microservice)                 | Microservice       | [Documentation](https://github.com/intel/random-forest-microservice/blob/main/README.md) |
| [Video Chunking Utils](https://github.com/open-edge-platform/edge-ai-libraries/tree/main/libraries/video-chunking-utils)            | Library            | [Documentation](https://github.com/open-edge-platform/edge-ai-libraries/tree/main/libraries/video-chunking-utils/README.md) |

> Intel, the Intel logo, OpenVINO, and the OpenVINO logo are trademarks of Intel Corporation or its subsidiaries.

Visit each library, microservice, tool, or sample sub-directory for the respective **Getting Started**, **Build** instructions and **Development** guides.

## More Sample Applications

Visit the [**Edge AI Suites**](https://github.com/open-edge-platform/edge-ai-suites) project for a broader set of sample applications targeted at specific industry segments.

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
| Intel® SceneScape | [Limited Edge Software Distribution License](https://github.com/open-edge-platform/scenescape?tab=readme-ov-file#license) |

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

| Component | Category | Get Started | Developers Docs |
|:----------|:---------|:------------|:-----------------|
| [Anomalib](https://github.com/open-edge-platform/anomalib) | Library | [Link](https://github.com/open-edge-platform/anomalib?tab=readme-ov-file#-introduction) | [API Reference](https://github.com/open-edge-platform/anomalib?tab=readme-ov-file#-training) |
| [Dataset Management Framework (Datumaro)](https://github.com/open-edge-platform/datumaro)[`*`](#license) | Library | [Link](https://github.com/open-edge-platform/datumaro?tab=readme-ov-file#features) | [API Reference](https://open-edge-platform.github.io/datumaro/latest/docs/reference/datumaro_module.html) |
| [Deep Learning Streamer](libraries/dl-streamer) | Library | [Link](./libraries/dl-streamer/docs/source/get_started/get_started_index.md) | [API Reference](./libraries/dl-streamer/docs/source/elements/elements.md) |
| [ECAT EnableKit](libraries/edge-control-libraries/fieldbus/ecat-enablekit) | Library | [Link](libraries/edge-control-libraries/fieldbus/ecat-enablekit/README.md) | [API Reference](libraries/edge-control-libraries/fieldbus/ecat-enablekit/docs/ecat_intro.md) |
| [EtherCAT Masterstack w/Intel silicon support](libraries/edge-control-libraries/fieldbus/ethercat-masterstack) | Library | [Link](libraries/edge-control-libraries/fieldbus/ethercat-masterstack/README.md) | [API Reference](https://docs.etherlab.org/ethercat/1.6/pdf/ethercat_doc.pdf) |
| [FLANN optimized with oneAPI DPC++](libraries/robotics-ai-libraries/flann) | Library | [Link](libraries/robotics-ai-libraries/flann/README.md) | [API Reference](https://www.cs.ubc.ca/research/flann/uploads/FLANN/flann_manual-1.8.4.pdf) |
| [Intel&reg; Geti&trade; SDK](https://github.com/open-edge-platform/geti-sdk) | Library | [Link](https://github.com/open-edge-platform/geti-sdk?tab=readme-ov-file#getting-started) | [API Reference](https://github.com/open-edge-platform/geti-sdk?tab=readme-ov-file#high-level-api-reference) |
| [OpenVINO&trade; toolkit](https://github.com/openvinotoolkit/openvino) | Library | [Link](https://docs.openvino.ai/2025/index.html) | [API Reference](https://docs.openvino.ai/2025/api/api_reference.html) |
| [OpenVINO&trade; Training Extensions](https://github.com/open-edge-platform/training_extensions) | Library | [Link](https://github.com/open-edge-platform/training_extensions?tab=readme-ov-file#introduction) | [API Reference](https://github.com/open-edge-platform/training_extensions?tab=readme-ov-file#quick-start) |
| [OpenVINO&trade; Model API](https://github.com/open-edge-platform/model_api) | Library | [Link](https://github.com/open-edge-platform/model_api?tab=readme-ov-file#installation) | [API Reference](https://github.com/open-edge-platform/model_api?tab=readme-ov-file#usage) |
| [Audio Analyzer](microservices/audio-analyzer) | Microservice | [Link](microservices/audio-analyzer/docs/user-guide/get-started.md) | [API Reference](microservices/audio-analyzer/docs/user-guide/api-reference.md) |
| [ORB Extractor](libraries/robotics-ai-libraries/orb-extractor) | Library | [Link](libraries/robotics-ai-libraries/orb-extractor/README.md) | [API Reference](libraries/robotics-ai-libraries/orb-extractor/include/orb_extractor.h)
| [PCL optimized with oneAPI DPC++](libraries/robotics-ai-libraries/pcl) | Library | [Link](libraries/robotics-ai-libraries/pcl) | [API Reference](https://pointclouds.org/documentation/annotated.html)
| [PLCopen Servo](plcopen-servo) | Library | [Link](libraries/edge-control-libraries/plcopen-motion-control/plcopen-servo) | [API Reference](https://docs.openedgeplatform.intel.com/edge-ai-libraries/plcopen-motion-control/main/rt-motion/rt-motion.html#run-rtmotion-with-ethercat-servo) |
| [Real-time Data Agent](libraries/edge-control-libraries/rt-data-agent) | Library | [Link](libraries/edge-control-libraries/rt-data-agent/README.md) | [API Reference](libraries/edge-control-libraries/rt-data-agent/README.md) |
| [RTmotion](libraries/edge-control-libraries/plcopen-motion-control/plcopen-motion) | Library | [Link](https://docs.openedgeplatform.intel.com/edge-ai-libraries/plcopen-motion-control/main/rt-motion/rt-motion.html) | [API Reference](https://docs.openedgeplatform.intel.com/edge-ai-libraries/plcopen-motion-control/main/rt-motion/rt-motion.html#rtmotion-function-blocks) |
| [Audio Intelligence](microservices/audio-intelligence) | Microservice | [Link](microservices/audio-intelligence/docs/user-guide/get-started.md) | [API Reference](microservices/audio-intelligence/docs/user-guide/api-reference.md) |
| [Deep Learning Streamer Pipeline Server](microservices/dlstreamer-pipeline-server) | Microservice | [Link](microservices/dlstreamer-pipeline-server#quick-try-out) | [API Reference](microservices/dlstreamer-pipeline-server/docs/user-guide/api-docs/pipeline-server.yaml) |
| [Document Ingestion](microservices/document-ingestion) | Microservice | [Link](microservices/document-ingestion/pgvector/docs/get-started.md) | [API Reference](microservices/document-ingestion/pgvector/docs/dataprep-api.yml) |
| [Model Registry](microservices/model-registry) | Microservice | [Link](microservices/model-registry/docs/user-guide/get-started.md) | [API Reference](microservices/model-registry/docs/user-guide/api-docs/openapi.yaml) |
| [Multimodal Embedding Serving](microservices/multimodal-embedding-serving) | Microservice | [Link](microservices/multimodal-embedding-serving/docs/user-guide/get-started.md) | [API Reference](microservices/multimodal-embedding-serving/docs/user-guide/api-docs/openapi.yaml) |
| [Time Series Analytics Microservice](microservices/time-series-analytics) | Microservice |  [Link](microservices/time-series-analytics/docs/user-guide/Overview.md) | [API Reference](microservices/time-series-analytics/docs/user-guide/api-reference.md), [Usage](microservices/time-series-analytics/docs/user-guide/get-started.md) |
| [Vector Retriever (with Milvus)](microservices/vector-retriever/milvus/) | Microservice | [Link](microservices/vector-retriever/milvus/docs/user-guide/get-started.md) | [API Reference](microservices/vector-retriever/milvus/docs/user-guide/api-reference.md) |
| [Visual-Data Preparation for Retrieval (with Milvus)](microservices/visual-data-preparation-for-retrieval/milvus/) | Microservice | [Link](microservices/visual-data-preparation-for-retrieval/milvus/docs/user-guide/get-started.md) | [API Reference](microservices/visual-data-preparation-for-retrieval/milvus/docs/user-guide/api-reference.md) |
| [Visual-Data Preparation for Retrieval (with VDMS)](microservices/visual-data-preparation-for-retrieval/vdms/) | Microservice | [Link](microservices/visual-data-preparation-for-retrieval/vdms/docs/user-guide/get-started.md) | [API Reference](microservices/visual-data-preparation-for-retrieval/vdms/docs/user-guide/api-reference.md) |
| [VLM Inference Serving](microservices/vlm-openvino-serving) | Microservice |  [Link](microservices/vlm-openvino-serving/README.md) | [Usage](microservices/vlm-openvino-serving/README.md) |
| [Intel® Geti™](https://github.com/open-edge-platform/geti)[`*`](#license) | Tool | [Link](https://geti.intel.com/) | [Docs](https://docs.geti.intel.com) |
| [Intel® SceneScape](https://github.com/open-edge-platform/scenescape)[`*`](#license) | Tool | [Link](https://docs.openedgeplatform.intel.com/scenescape/main/user-guide/Getting-Started-Guide.html) | [Docs](https://docs.openedgeplatform.intel.com/scenescape/main/toc.html) |
| [Visual Pipeline and Platform Evaluation Tool](tools/visual-pipeline-and-platform-evaluation-tool) | Tool | [Link](tools/visual-pipeline-and-platform-evaluation-tool/docs/user-guide/get-started.md) | [Build](tools/visual-pipeline-and-platform-evaluation-tool/docs/user-guide/how-to-build-source.md) instructions |
| [Chat Question and Answer](sample-applications/chat-question-and-answer) | Sample Application |  [Link](sample-applications/chat-question-and-answer/docs/user-guide/get-started.md) | [Build](sample-applications/chat-question-and-answer/docs/user-guide/build-from-source.md) instructions |
| [Chat Question and Answer Core](sample-applications/chat-question-and-answer-core) | Sample Application | [Link](sample-applications/chat-question-and-answer-core/docs/user-guide/get-started.md) | [Build](sample-applications/chat-question-and-answer-core/docs/user-guide/build-from-source.md) instructions |
| [Document Summarization](sample-applications/document-summarization) | Sample Application | [Link](sample-applications/document-summarization/docs/user-guide/get-started.md) | [Build](sample-applications/document-summarization/docs/user-guide/build-from-source.md) instructions |
| [PLCopen Benchmark](plcopen-benchmark) | Sample Application | [Link](sample-applications/plcopen-benchmark) | [Build](sample-applications/plcopen-benchmark/README.md) |
| [PLCopen Databus](plcopen-databus) | Sample Application | [Link](sample-applications/plcopen-databus) | [Build](sample-applications/plcopen-databus/README.md) |
| [Video Search and Summarization](sample-applications/video-search-and-summarization) | Sample Application | [Link](sample-applications/video-search-and-summarization/docs/user-guide/get-started.md) | [Build](sample-applications/video-search-and-summarization/docs/user-guide/build-from-source.md) instructions |
| [Optimized Isolation Forest Classifier Training and Inference Microservice](https://github.com/intel/isolation-forest-microservice) | Microservice| [Link](https://github.com/intel/isolation-forest-microservice/blob/main/README.md)| [Build](https://github.com/intel/isolation-forest-microservice/blob/main/README.md) |
| [Optimizied Random Forest Training and Inference Microservice](https://github.com/intel/random-forest-microservice) | Microservice | [Link](https://github.com/intel/random-forest-microservice/blob/main/README.md) | [Build](https://github.com/intel/random-forest-microservice/blob/main/README.md) |

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
| Intel® SceneScape | [Limited Edge Software Distribution License](https://github.com/open-edge-platform/scenescape/blob/main/LICENSE) |

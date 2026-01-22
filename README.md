[![License](https://img.shields.io/badge/License-Apache%202.0-blue)]()
[![#Libraries](https://img.shields.io/badge/%23Libraries-6-green)]()
[![#Microservices](https://img.shields.io/badge/%23Microservices-4-green)]()
[![#Tools](https://img.shields.io/badge/%23Tools-1-green)]()
[![#Samples](https://img.shields.io/badge/%23Samples-2-green)]()

# Edge-AI-Libraries

Welcome to **Edge AI Libraries** - highly optimized libraries, microservices,
and tools designed for building and deploying real-time AI solutions
on edge devices.

If you are an AI developer, data scientist, or system integrator, these assets
help you organize data, train models, run efficient inference, and deliver
robust, industry-grade automation systems for computer vision, multimedia,
and industrial use cases.

## Spotlight - Key Components

These flagship components represent the most advanced, widely adopted, and
impactful tools in the repository:

- [Deep Learning Streamer](https://github.com/open-edge-platform/dlstreamer/blob/main/README.md)

  Build efficient media analytics pipelines using streaming AI pipelines for
  audio/video media analytics using GStreamer for optimized media operations
  and OpenVINO for optimized inferencing

- [Intel® SceneScape](https://github.com/open-edge-platform/scenescape)

  Create 3D/4D dynamic digital twins from multimodal sensor data for advanced
  spatial analytics.

- [Geti™](https://github.com/open-edge-platform/geti)

  Build computer vision AI models enabling rapid dataset management, model
  training, and deployment to the edge.

- [Anomalib](https://github.com/open-edge-platform/anomalib)

  Deploy visual anomaly detection with this state-of-the-art library, offering
  algorithms for segmentation, classification, and reconstruction, plus features
  like experiment management and hyperparameter optimization.

- [OpenVINO Toolkit](https://github.com/openvinotoolkit/openvino)

  Optimize, run, and deploy AI models with this industry-standard toolkit,
  accelerating inference on Intel CPUs, GPUs, and NPUs. Supports a broad range
  of AI solutions including vision-based applications, generative AI,
  and vision-language models.

## Component Categories

### Model Training and Optimization

This group provides core AI libraries and tools focused on computer vision
model building, training, optimization, and deployment for Intel hardware.
They address challenges such as dataset curation, model lifecycle management,
and high-performance inference on edge devices.

- [Geti™](https://github.com/open-edge-platform/geti)

  Build computer vision AI models enabling rapid dataset management, model
  training, and deployment to the edge.

- [Anomalib](https://github.com/open-edge-platform/anomalib)

  Deploy visual anomaly detection with this state-of-the-art library, offering
  algorithms for segmentation, classification, and reconstruction, plus features
  like experiment management and hyperparameter optimization.

- [Geti™ SDK](https://github.com/open-edge-platform/geti-sdk)

  Software for efficient model training and deployment.

- [OpenVINO Toolkit](https://github.com/openvinotoolkit/openvino)

  Toolkit for optimizing and deploying AI inference, offering performance boost
  on Intel CPU, GPU, and NPU devices.

- [OpenVINO Training Extensions](https://github.com/open-edge-platform/training_extensions) 
  & [Model API](https://github.com/open-edge-platform/model_api)

  A set of advanced algorithms for model training and conversion.

- [Datumaro](https://github.com/open-edge-platform/datumaro)

  Dataset management framework to curate and convert vision datasets.

- [Edge AI Tuning Kit](https://github.com/open-edge-platform/edge-ai-tuning-kit)

  Create, tailor, and implement custom AI models directly on edge platforms.

### Streaming and Multimedia AI

Handling large-scale media analytics workloads, these components support
real-time audio and video AI pipeline processing, transcription, and multimodal
embedding generation, addressing common use cases like surveillance, content
indexing, and audio analysis.

- [Deep Learning Streamer](https://github.com/open-edge-platform/dlstreamer)
  & [Deep Learning Streamer Pipeline Server](./microservices/dlstreamer-pipeline-server)

  Streaming AI pipeline builder with scalable server for media
  inferencing. 

- [Audio Analyzer](./microservices/audio-analyzer)

  Microservices providing real-time audio transcription and
  intelligence extraction. 

- [VLM Inference Serving](./microservices/vlm-openvino-serving)
  & [Multimodal Embedding](./microservices/multimodal-embedding-serving)

  Services handling vision-language models and embedding generation
  for multimodal search.

- [Intel® SceneScape](https://github.com/open-edge-platform/scenescape)

  Software for creating dynamic 3D/4D digital twins for spatial
  analytics.

- [Time Series Analytics Microservice](./microservices/time-series-analytics)

  Real-time analytics microservice designed for anomaly detection
  and forecasting on sensor time-series data.

- [Multi-level Video Understanding Microservice](./microservices/multilevel-video-understanding/)
  
  Microservices providing a multi-level, temporal-enhanced approach to generate high quality summaries for video files, especially for long videos.

### Data Preparation and Retrieval 

Efficient data management and retrieval are crucial for AI performance
and scalability. This group offers components for dataset curation,
vector search, and document ingestion across multimodal data. 

- [Vector Retriever (Milvus)](./microservices/visual-data-preparation-for-retrieval/milvus)
  & [Visual Data Preparation (Milvus and VDMS)](./microservices/visual-data-preparation-for-retrieval/vdms)

  High-performance vector similarity search and visual data indexing. 

- [Model Registry](./microservices/model-registry)
  & [Document Ingestion](./microservices/document-ingestion/pgvector)

  Tools for managing AI model versions and preparing documents for AI
  workflows. 

- [Video Chunking Utils](./libraries/video-chunking-utils)

  Splits/segments video streams into chunks, supporting batch and
  pipeline-based analytics.

### Benchmarking Tools 

These support tools provide visual pipeline evaluation and performance
benchmarking to help analyze AI workloads and industrial
environments effectively.

- [Visual Pipeline and Platform Evaluation Tool](./tools/visual-pipeline-and-platform-evaluation-tool)

  Benchmark and analyze AI pipeline performance on various edge platforms. 

- [PLCopen Benchmark](./sample-applications/plcopen-benchmark)

  Compliance and performance testing toolkit for motion control. 

- [Edge AI Sizing Tool](https://github.com/open-edge-platform/edge-ai-sizing-tool)

  Showcase, monitor, and optimize the scalability and performance of
  AI workloads on Intel edge hardware. Configure models, choose
  performance modes, and visualize resource metrics in real time.

- [Edge System Qualification](https://github.com/open-edge-platform/edge-system-qualification)

  Command Line Interface (CLI) tool that provides a collection of test suites to
  qualify Edge AI system. It enables users to perform targeted tests, supporting
  a wide range of use cases from system evaluation to data
  extraction and reporting.

### Edge Control Libraries  

Focused on real-time industrial automation, motion control, and fieldbus
communication, these components provide reliable, standards-compliant
building blocks for manufacturing and factory automation applications. 

- [ECAT EnableKit](./libraries/edge-control-libraries/fieldbus/ecat-enablekit)
  & [EtherCAT Masterstack](./libraries/edge-control-libraries/fieldbus/ethercat-masterstack)

  EtherCAT communication protocol stack and development tools. 

- [PLCopen Servo](./libraries/edge-control-libraries/plcopen-motion-control/plcopen-servo)
  and
  [RTmotion](./libraries/edge-control-libraries/plcopen-motion-control/plcopen-motion)

  Libraries implementing motion control standards for servo drives
  and real-time trajectory management. 

- [PLCopen Databus](./sample-applications/plcopen-databus)

  Tools for data communication in automation networks. 

- [Real-time Data Agent](./libraries/edge-control-libraries/rt-data-agent)

  Microservice for collecting, processing, and distributing
  real-time sensor and industrial device data; supports both edge
  analytics and integration with operational systems.
     
### Robotics Libraries

Optimized libraries for robotic perception, localization, mapping,
and 3D point cloud analytics. These tools are designed to maximize
performance on heterogeneous Intel hardware using oneAPI DPC++, enabling
advanced robotic workloads at the edge.

- [FLANN optimized with oneAPI DPC++](./libraries/robotics-ai-libraries/flann)

  High-speed nearest neighbor library, optimized for Intel
  architectures; supports scalable feature matching, search, and
  clustering in robotic vision and SLAM.

- [ORB Extractor](./libraries/robotics-ai-libraries/orb-extractor)

  Efficient ORB feature and descriptor extraction for visual
  SLAM, mapping, and tracking; designed for multicamera and GPU
  acceleration scenarios.

- [Point Cloud Library Optimized with Intel oneAPI DPC++](./libraries/robotics-ai-libraries/pcl)

  Accelerated modules from PCL for real-time 2D/3D point cloud
  processing—supports object detection, mapping, segmentation, and
  scene understanding in automation and robotics.

- [Motion Control Gateway](./libraries/robotics-ai-libraries/motion-control-gateway)

  Unified interface library bridging motion control commands
  between AI modules and industrial/robotic devices; simplifies
  real-time control integration and system interoperability in mixed
  hardware environments.

### Sample Applications and Reference Implementations

Ready-to-use example applications demonstrating real-world AI use cases
to help users get started quickly and understand integration patterns: 

- [Chat Question and Answer](./sample-applications/chat-question-and-answer) 

  Conversational AI application integrating retrieval-augmented generation for
  question answering. 

- [Chat Question and Answer Core](./sample-applications/chat-question-and-answer-core) 

  Conversational AI application integrating retrieval-augmented
  generation for question answering.Optimized for Intel(R) Core.

- [Document Summarization](./sample-applications/document-summarization) 

  AI pipeline for automated summarization of textual documents. 

- [Video Search and Summarization](./sample-applications/video-search-and-summarization) 

  Application combining video content analysis with search and
  summarization capabilities. 

- [Edge Developer Kit Reference Scripts](https://github.com/open-edge-platform/edge-developer-kit-reference-scripts) 

  Automate the setup of edge AI development environments using these
  proven reference scripts. Quickly install required drivers,
  configure hardware, and validate platform readiness for Intel-based
  edge devices.

> Visit the [Edge AI Suites](https://github.com/open-edge-platform/edge-ai-suites)
> repository for a broader set of sample applications targeted at
> specific industry segments. 
     
### Edge Analytics Microservices

Specialized microservices delivering machine learning-powered
analytics optimized for edge deployment. These microservices support
scalable anomaly detection, classification, and predictive analytics on
structured and time-series data.

- [isolation-forest-microservice](https://github.com/intel/isolation-forest-microservice)

  An efficient Isolation Forest microservice for unsupervised
  anomaly detection supporting high-performance training and inference
  on tabular and streaming data.

- [random-forest-microservice](https://github.com/intel/random-forest-microservice)

  High-speed Random Forest microservice for supervised
  classification tasks, optimized for edge and industrial use cases
  with rapid training and low-latency inference.

### Edge-device Enablement Framework (EEF)
A comprehensive framework providing hardware abstraction, device management, 
and deployment tools for edge AI applications. Simplifies cross-platform 
development and enables consistent deployment across diverse edge hardware 
architectures.

- [Edge-device Enablement Framework](./frameworks/edgedevice-enablement-framework)

  Framework for Intel® platform enablement and streamlining 
  edge AI application deployment across heterogeneous device platforms.

  
## Contribute

To learn how to contribute to the project, see
[CONTRIBUTING.md](./CONTRIBUTING.md).

## Community and Support

If you need help, want to suggest a new feature, or report a bug, please use
the following channels:

- **Questions & Discussions:** Join the conversation in
  [GitHub Discussions](https://github.com/open-edge-platform/edge-ai-libraries/discussions)
  to ask questions, share ideas, or get help from the community.
- **Bug Reports & Feature Requests:** Submit issues via
  [Github Issues](https://github.com/open-edge-platform/edge-ai-libraries/issues)
  for bugs or feature requests.

## License

The **Edge AI Libraries** project is licensed under the [APACHE 2.0](./LICENSE) license, except for the following components:

| Component | License |
|:----------|:--------|
| Dataset Management Framework (Datumaro) | [MIT License](https://github.com/open-edge-platform/datumaro/blob/develop/LICENSE) |
| Intel® Geti™ | [Limited Edge Software Distribution License](https://github.com/open-edge-platform/geti/blob/main/LICENSE) |
| Deep Learning Streamer | [MIT License](https://github.com/open-edge-platform/edge-ai-libraries/blob/main/libraries/dl-streamer/LICENSE) |

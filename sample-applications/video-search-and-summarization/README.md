# Video Search and Summarization (VSS) Sample Application

Video search and summarization is a foundational sample application that provides the following set of video analytics capabilities:

- Video Search: This functionality enables efficient and intelligent search over video content directly at the edge. It leverages LangChain, multimodal embedding models, and agentic reasoning to extract and index visual, audio, and textual features from video frames using advanced embedding models. You can also perform natural language or multi-modal queries. Agentic reasoning allows the system to break down complex user queries, orchestrate multi-step retrievals, and combine insights from multiple video segments for more comprehensive and context-aware answers. LangChain orchestrates the retrieval and ranking process, ensuring relevant video segments are quickly identified and returned, all while minimizing latency and preserving data privacy by processing content locally on edge devices.
- Video Summarization: Creates concise and informative summaries of long videos. It identifies and extracts the most relevant segments, enabling efficient content review, improved searchability, and quick understanding of lengthy video material. It combines insights from different data types by combining Generative AI Vision Language Models (VLMs), Computer Vision, and Audio analysis. All processing can be performed at the edge, ensuring low latency and data privacy.
- Combined Search and Summarization capability: This feature integrates video search and summarization, allowing you to search directly over the generated video summaries. By leveraging the summary as a knowledge base, the system enhances the relevance and accuracy of search results, reducing the risk of hallucinations and irrelevant matches. This approach enables efficient retrieval of key information from long-form videos, ensuring that search queries are answered with contextually grounded and concise content.

The detailed documentation to help you get started, configure, and deploy the sample application along with the required microservices are as follows.

## Documentation

- **Overview**
  - [Overview | Architecture](./docs/user-guide/index.md): A high-level sample application introduction including Architecture details.
  
- **Getting Started**
  - [Get Started](./docs/user-guide/get-started.md): Step-by-step guide to get started with the sample application.
  - [System Requirements](./docs/user-guide/system-requirements.md): Hardware and software requirements for running the sample application.

- **Deployment**
  - [How to Build from Source](./docs/user-guide/build-from-source.md): Instructions for building from source code.
  - [How to Deploy with Helm](./docs/user-guide/deploy-with-helm.md): Guide for deploying using Helm\* chart.

- **API Reference**
  - [API Reference](./docs/user-guide/api-reference.md): Comprehensive reference for the available REST API endpoints.

- **Release Notes**
  - [Release Notes](./docs/user-guide/release-notes.md): Information on the latest updates, improvements, and bug fixes.
